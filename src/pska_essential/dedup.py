from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
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


def fclones_command_path() -> str | None:
    override = os.getenv("PSKA_FCLONES_BIN", "").strip()
    if override:
        path = Path(override).expanduser()
        return str(path) if path.is_file() else None
    return shutil.which("fclones")


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


def _find_group_candidates(data: Any) -> list[Any]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, (dict, list))]
    if not isinstance(data, dict):
        return []
    for key in ("groups", "duplicates"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if any(isinstance(data.get(key), list) for key in ("files", "paths", "members", "items")):
        return [data]
    return [data]


def _group_members(group: dict[str, Any]) -> list[Any]:
    for key in ("files", "paths", "members", "items"):
        value = group.get(key)
        if isinstance(value, list):
            return value
    return []


def _member_from_candidate(candidate: Any) -> DedupMember:
    if isinstance(candidate, str):
        return DedupMember(path=candidate, absolute_path=candidate)
    if not isinstance(candidate, dict):
        return DedupMember(path="")
    raw_path = candidate.get("path") or candidate.get("name") or candidate.get("file") or candidate.get("filename") or ""
    path = str(raw_path)
    return DedupMember(
        path=path,
        absolute_path=path if Path(path).is_absolute() else "",
        size=_int_value(candidate.get("size") or candidate.get("len")),
        content_hash=str(candidate.get("hash") or candidate.get("content_hash") or ""),
        metadata={key: value for key, value in candidate.items() if key not in {"path", "name", "file", "filename"}},
    )


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
