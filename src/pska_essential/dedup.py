from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


class DedupError(RuntimeError):
    """Raised when a duplicate detection provider cannot produce a report."""


@dataclass(frozen=True)
class DedupMember:
    path: str
    absolute_path: str = ""
    size: int = 0
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "absolute_path": self.absolute_path,
            "size": self.size,
            "content_hash": self.content_hash,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class DedupGroup:
    method: str
    members: list[DedupMember]
    confidence: float = 1.0
    content_hash: str = ""
    size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "method": self.method,
            "confidence": self.confidence,
            "content_hash": self.content_hash,
            "size": self.size,
            "member_count": len(self.members),
            "members": [member.to_dict() for member in self.members],
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class DedupReport:
    mode: str
    groups: list[DedupGroup]
    provider: str
    status: str = "ok"
    message: str = ""
    command: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider": self.provider,
            "status": self.status,
            "message": self.message,
            "command": list(self.command),
            "group_count": len(self.groups),
            "duplicate_file_count": sum(max(len(group.members) - 1, 0) for group in self.groups),
            "groups": [group.to_dict() for group in self.groups],
            "metadata": dict(self.metadata),
        }


def fclones_available() -> bool:
    return fclones_command_path() is not None


def czkawka_available() -> bool:
    return czkawka_command_path() is not None


def fclones_command_path() -> str | None:
    override = os.getenv("PSKA_FCLONES_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which("fclones")


def czkawka_command_path() -> str | None:
    override = os.getenv("PSKA_CZKAWKA_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which("czkawka_cli") or shutil.which("czkawka")


def fclones_duplicate_report(
    roots: list[Path],
    *,
    limit: int = 50,
    timeout_seconds: int = 120,
) -> DedupReport:
    command_path = fclones_command_path()
    if not command_path:
        return DedupReport(
            mode="fclones_hash",
            provider="fclones",
            groups=[],
            status="unavailable",
            message="CLI command `fclones` was not found on PATH or PSKA_FCLONES_BIN.",
            metadata={"install_hint": "Install fclones and keep it on PATH, or set PSKA_FCLONES_BIN."},
        )
    selected_roots = [str(path) for path in roots if path.exists()]
    if not selected_roots:
        return DedupReport(
            mode="fclones_hash",
            provider="fclones",
            groups=[],
            status="empty_scope",
            message="No readable source roots were selected.",
        )
    command = [command_path, "group", "--format", "json", *selected_roots]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DedupError(f"fclones duplicate report timed out after {timeout_seconds}s") from exc
    if completed.returncode not in {0, 1}:
        raise DedupError((completed.stderr or completed.stdout or "fclones failed").strip())
    groups = parse_fclones_groups(completed.stdout)
    return DedupReport(
        mode="fclones_hash",
        provider="fclones",
        status="ok",
        message=f"fclones returned {len(groups[:limit])} duplicate group(s).",
        command=command,
        groups=groups[:limit],
        metadata={"stderr": completed.stderr.strip()} if completed.stderr.strip() else {},
    )


def czkawka_duplicate_report(
    roots: list[Path],
    *,
    limit: int = 50,
    timeout_seconds: int = 120,
) -> DedupReport:
    command_path = czkawka_command_path()
    if not command_path:
        return DedupReport(
            mode="czkawka_hash",
            provider="czkawka",
            groups=[],
            status="unavailable",
            message="CLI command `czkawka_cli` was not found on PATH or PSKA_CZKAWKA_BIN.",
            metadata={
                "install_hint": (
                    "Download the Czkawka CLI binary and set PSKA_CZKAWKA_BIN, or add czkawka_cli to PATH."
                )
            },
        )
    selected_roots = [str(path) for path in roots if path.exists()]
    if not selected_roots:
        return DedupReport(
            mode="czkawka_hash",
            provider="czkawka",
            groups=[],
            status="empty_scope",
            message="No readable source roots were selected.",
        )
    with TemporaryDirectory(prefix="pska-czkawka-report-") as temp_dir:
        output_path = Path(temp_dir) / "duplicates.json"
        command = [
            command_path,
            "dup",
            "-d",
            *selected_roots,
            "-m",
            "1",
            "-W",
            "-M",
            "-N",
            "-C",
            str(output_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            if completed.returncode not in {0, 11}:
                raise DedupError((completed.stderr or completed.stdout or "czkawka failed").strip())
            raw = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout
        except subprocess.TimeoutExpired as exc:
            raise DedupError(f"czkawka duplicate report timed out after {timeout_seconds}s") from exc
    groups = parse_czkawka_groups(raw)
    return DedupReport(
        mode="czkawka_hash",
        provider="czkawka",
        status="ok",
        message=f"Czkawka returned {len(groups[:limit])} duplicate group(s).",
        command=command,
        groups=groups[:limit],
        metadata={"stderr": completed.stderr.strip()} if completed.stderr.strip() else {},
    )


def parse_fclones_groups(raw: str) -> list[DedupGroup]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DedupError("fclones returned non-JSON output") from exc
    groups = _find_group_candidates(data)
    parsed: list[DedupGroup] = []
    for group in groups:
        if isinstance(group, list):
            members = [_member_from_candidate(item) for item in group]
            members = [member for member in members if member.path or member.absolute_path]
            if len(members) < 2:
                continue
            parsed.append(
                DedupGroup(
                    method="fclones_hash",
                    confidence=1.0,
                    size=max((member.size for member in members), default=0),
                    members=members,
                )
            )
            continue
        if not isinstance(group, dict):
            continue
        members = [_member_from_candidate(item) for item in _group_members(group)]
        members = [member for member in members if member.path or member.absolute_path]
        if len(members) < 2:
            continue
        size = _int_value(group.get("size") or group.get("file_size") or group.get("len"))
        content_hash = str(group.get("hash") or group.get("content_hash") or group.get("digest") or "")
        parsed.append(
            DedupGroup(
                method="fclones_hash",
                confidence=1.0,
                content_hash=content_hash,
                size=size or max((member.size for member in members), default=0),
                members=members,
                metadata={key: value for key, value in group.items() if key not in {"files", "paths", "members"}},
            )
        )
    return parsed


def parse_czkawka_groups(raw: str) -> list[DedupGroup]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DedupError("czkawka returned non-JSON output") from exc
    groups = _find_czkawka_group_candidates(data)
    parsed: list[DedupGroup] = []
    for group in groups:
        members = _members_from_group_candidate(group)
        if len(members) < 2:
            continue
        size = _group_size(group, members)
        content_hash = _group_hash(group)
        parsed.append(
            DedupGroup(
                method="czkawka_hash",
                confidence=1.0,
                content_hash=content_hash,
                size=size,
                members=members,
                metadata=_group_metadata(group),
            )
        )
    return parsed


def _find_czkawka_group_candidates(data: Any) -> list[Any]:
    if _looks_like_czkawka_size_map(data):
        groups: list[Any] = []
        for size, value in data.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, list):
                        groups.append({"size": size, "files": item})
                    elif isinstance(item, dict):
                        groups.append(item | {"size": item.get("size") or size})
            elif isinstance(value, dict):
                groups.append(value | {"size": value.get("size") or size})
        return groups
    if isinstance(data, dict):
        for key in (
            "files_with_identical_hashes",
            "files_with_identical_size",
            "files_with_identical_names",
            "files_with_identical_size_names",
        ):
            value = data.get(key)
            if _looks_like_czkawka_size_map(value):
                return _find_czkawka_group_candidates(value)
    return _find_group_candidates(data)


def _looks_like_czkawka_size_map(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return all(_is_int_like(key) for key in value)


def _find_group_candidates(data: Any) -> list[Any]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, (dict, list))]
    if not isinstance(data, dict):
        return []
    for key in ("groups", "duplicates", "duplicate_groups", "results", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, (dict, list))]
    if any(isinstance(data.get(key), list) for key in ("files", "paths", "members", "items")):
        return [data]
    return [data]


def _group_members(group: dict[str, Any]) -> list[Any]:
    for key in ("files", "paths", "members", "items", "entries"):
        value = group.get(key)
        if isinstance(value, list):
            return value
    return []


def _members_from_group_candidate(group: Any) -> list[DedupMember]:
    if isinstance(group, list):
        raw_members = group
    elif isinstance(group, dict):
        raw_members = _group_members(group)
    else:
        raw_members = []
    members = [_member_from_candidate(item) for item in raw_members]
    return [member for member in members if member.path or member.absolute_path]


def _member_from_candidate(candidate: Any) -> DedupMember:
    if isinstance(candidate, str):
        return DedupMember(path=candidate, absolute_path=candidate)
    if not isinstance(candidate, dict):
        return DedupMember(path="")
    raw_path = (
        candidate.get("path")
        or candidate.get("name")
        or candidate.get("file")
        or candidate.get("filename")
        or candidate.get("file_name")
        or ""
    )
    path = str(raw_path)
    content_hash = candidate.get("hash") or candidate.get("content_hash") or candidate.get("hash_string") or ""
    return DedupMember(
        path=path,
        absolute_path=path if Path(path).is_absolute() else "",
        size=_int_value(candidate.get("size") or candidate.get("len")),
        content_hash=str(content_hash),
        metadata={
            key: value
            for key, value in candidate.items()
            if key not in {"path", "name", "file", "filename", "file_name"}
        },
    )


def _group_size(group: Any, members: list[DedupMember]) -> int:
    if isinstance(group, dict):
        size = _int_value(group.get("size") or group.get("file_size") or group.get("len"))
        if size:
            return size
    return max((member.size for member in members), default=0)


def _group_hash(group: Any) -> str:
    if not isinstance(group, dict):
        return ""
    return str(group.get("hash") or group.get("content_hash") or group.get("digest") or group.get("hash_string") or "")


def _group_metadata(group: Any) -> dict[str, Any]:
    if not isinstance(group, dict):
        return {}
    return {
        key: value
        for key, value in group.items()
        if key not in {"files", "paths", "members", "items", "entries"}
    }


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_int_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True
