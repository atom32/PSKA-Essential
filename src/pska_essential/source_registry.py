from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from pska_essential.contracts import ContextPacket, SourceContext, SourceRef, to_jsonable, utc_now_iso
from pska_essential.dedup import DedupError, czkawka_duplicate_report, fclones_duplicate_report
from pska_essential.extraction import (
    TEXT_EXTENSIONS,
    ExtractionError,
    ExtractionResult,
    ExtractionWarning,
    extract_source_file,
)


PERSONAL_SOURCE_ADAPTERS = {"local_folder", "obsidian_vault"}
PERMISSION_MODES = {"read_only", "sidecar_write", "native_write", "managed"}
NEIGHBOR_STRATEGIES = {"auto", "links", "backlinks", "folder"}
OBSIDIAN_MOC_WRITE_TARGET = "obsidian_moc"
PSKA_MOC_BEGIN = "<!-- PSKA:MOC:BEGIN -->"
PSKA_MOC_END = "<!-- PSKA:MOC:END -->"
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".obsidian",
    ".pska",
    ".venv",
    "__pycache__",
    "node_modules",
}

class SourceRegistryError(ValueError):
    """Raised when the personal source registry refuses an unsafe operation."""


def is_personal_source_ref(source_ref: SourceRef) -> bool:
    return source_ref.adapter in PERSONAL_SOURCE_ADAPTERS or str(
        source_ref.metadata.get("source_layer") or ""
    ) == "personal"


class SQLiteSourceRegistry:
    """Source-safe personal registry for local folders and Obsidian vaults.

    The registry stores rebuildable metadata, FTS text, and source coordinates.
    User files remain the canonical source and are not modified by M1/M2/M3/M4 tools.
    """

    backend_name = "sqlite_source_registry"

    def __init__(self, path: str | Path = ".pska-essential/sources.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def list_roots(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT r.*,
                       SUM(CASE WHEN o.status = 'active' THEN 1 ELSE 0 END) AS active_object_count
                FROM source_roots r
                LEFT JOIN source_objects o ON o.root_id = r.root_id
                GROUP BY r.root_id
                ORDER BY r.label COLLATE NOCASE, r.absolute_path COLLATE NOCASE
                """
            ).fetchall()
        return [_root_payload(row) for row in rows]

    def register_root(
        self,
        path: str | Path,
        *,
        kind: str = "local_folder",
        permission_mode: str = "read_only",
        label: str | None = None,
    ) -> dict[str, Any]:
        absolute = _safe_absolute_path(path)
        if not absolute.exists():
            raise SourceRegistryError(f"source root does not exist: {absolute}")
        if not absolute.is_dir():
            raise SourceRegistryError(f"source root must be a directory: {absolute}")
        normalized_kind = _normalize_kind(kind, absolute)
        normalized_permission = _normalize_permission(permission_mode)
        root_id = _stable_id("root", str(absolute))
        now = utc_now_iso()
        display_label = label.strip() if label else absolute.name
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO source_roots(
                    root_id, label, kind, absolute_path, permission_mode, created_at, last_scan_at
                )
                VALUES (?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(absolute_path) DO UPDATE SET
                    label = excluded.label,
                    kind = excluded.kind,
                    permission_mode = excluded.permission_mode
                """,
                (root_id, display_label, normalized_kind, str(absolute), normalized_permission, now),
            )
            self.conn.commit()
        return self.get_root(root_id)

    def get_root(self, root_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.conn.execute("SELECT * FROM source_roots WHERE root_id = ?", (root_id,)).fetchone()
            if row is None:
                raise SourceRegistryError(f"source root not found: {root_id}")
            payload = _root_payload(row)
            count = self.conn.execute(
                "SELECT COUNT(*) AS count FROM source_objects WHERE root_id = ? AND status = 'active'",
                (root_id,),
            ).fetchone()["count"]
        payload["active_object_count"] = int(count or 0)
        return payload

    def scan(
        self,
        root_id: str,
        *,
        max_files: int = 1000,
        max_bytes: int = 1_000_000,
        extractor: str = "auto",
    ) -> dict[str, Any]:
        root = self.get_root(root_id)
        root_path = Path(root["absolute_path"])
        if not root_path.exists() or not root_path.is_dir():
            raise SourceRegistryError(f"source root is no longer readable: {root_path}")
        if max_files <= 0:
            raise SourceRegistryError("max_files must be positive")
        if max_bytes <= 0:
            raise SourceRegistryError("max_bytes must be positive")

        now = utc_now_iso()
        scanned_paths: list[str] = []
        counts = {
            "scanned": 0,
            "indexed": 0,
            "metadata_only": 0,
            "too_large": 0,
            "unsupported": 0,
            "errors": 0,
            "skipped_after_limit": 0,
        }
        with self.lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE source_objects SET status = 'missing', deleted_at = ? WHERE root_id = ?",
                    (now, root_id),
                )
                for file_path in _walk_source_files(root_path):
                    if counts["scanned"] >= max_files:
                        counts["skipped_after_limit"] += 1
                        continue
                    counts["scanned"] += 1
                    rel_path = file_path.relative_to(root_path).as_posix()
                    scanned_paths.append(rel_path)
                    try:
                        result = self._index_file(root, file_path, rel_path, max_bytes=max_bytes, extractor=extractor)
                    except OSError as exc:
                        counts["errors"] += 1
                        self._upsert_error_object(root, file_path, rel_path, str(exc))
                        continue
                    counts[result] = counts.get(result, 0) + 1
                self.conn.execute(
                    "UPDATE source_roots SET last_scan_at = ? WHERE root_id = ?",
                    (now, root_id),
                )

            active_count = self.conn.execute(
                "SELECT COUNT(*) AS count FROM source_objects WHERE root_id = ? AND status = 'active'",
                (root_id,),
            ).fetchone()["count"]
        return {
            "root": self.get_root(root_id),
            "counts": counts,
            "active_object_count": int(active_count or 0),
            "permission_mode": root["permission_mode"],
            "data_flow": {
                "writes_source_files": False,
                "writes_index": True,
                "embedding_required": False,
            },
            "extraction": {
                "extractor": extractor or "auto",
                "optional_adapters_allowed": (extractor or "auto") in {"auto", "markitdown"},
            },
        }

    def search(
        self,
        query: str,
        scope: dict[str, Any] | None = None,
        *,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[ContextPacket]:
        if limit <= 0:
            return []
        fts_query = _fts_query(query)
        if not fts_query:
            return []
        scope = dict(scope or {})
        filters = dict(filters or {})
        root_ids = _scope_strings(scope, "root_ids", "root_id")
        kinds = _scope_strings(scope, "source_kinds", "source_kind")
        path_prefixes = _scope_strings(filters, "path_prefixes", "path_prefix")

        where = ["source_fts MATCH ?", "o.status = 'active'"]
        params: list[Any] = [fts_query]
        if root_ids:
            where.append(f"f.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        for prefix in path_prefixes:
            where.append("o.path LIKE ?")
            params.append(f"{prefix.rstrip('/')}%")
        params.append(limit)
        with self.lock:
            try:
                rows = self.conn.execute(
                    f"""
                    SELECT f.section_id, f.object_id, f.root_id, f.title AS fts_title,
                           snippet(source_fts, 4, '', '', '...', 18) AS snippet,
                           bm25(source_fts) AS rank,
                           o.path, o.kind AS object_kind, o.content_hash, o.extraction_status,
                           s.section_type, s.heading_path, s.line_start, s.line_end,
                           s.title AS section_title,
                           r.kind AS root_kind, r.permission_mode, r.label AS root_label
                    FROM source_fts f
                    JOIN source_objects o ON o.object_id = f.object_id
                    JOIN source_sections s ON s.section_id = f.section_id
                    JOIN source_roots r ON r.root_id = f.root_id
                    WHERE {' AND '.join(where)}
                    ORDER BY rank
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            except sqlite3.OperationalError:
                return self._like_search(query, root_ids=root_ids, kinds=kinds, limit=limit)
        return [_packet_from_search_row(row, index) for index, row in enumerate(rows, start=1)]

    def read_source(self, source_ref: SourceRef) -> SourceContext:
        section_id = (
            str(source_ref.metadata.get("section_id") or "")
            or source_ref.chunk_id
            or source_ref.source_id
        )
        if not section_id:
            raise SourceRegistryError("personal source read requires section_id or chunk_id")
        with self.lock:
            row = self.conn.execute(
                """
                SELECT s.*, s.title AS section_title,
                       o.path, o.content_hash, o.extraction_status,
                       f.body AS indexed_body,
                       r.root_id, r.kind AS root_kind, r.absolute_path, r.permission_mode, r.label AS root_label
                FROM source_sections s
                JOIN source_objects o ON o.object_id = s.object_id
                JOIN source_roots r ON r.root_id = o.root_id
                LEFT JOIN source_fts f ON f.section_id = s.section_id
                WHERE s.section_id = ?
                """,
                (section_id,),
            ).fetchone()
        if row is None:
            return SourceContext(source_ref=source_ref, text="", metadata={"missing": True})
        root_path = Path(row["absolute_path"])
        file_path = _path_inside_root(root_path, row["path"])
        if not file_path.exists():
            return SourceContext(
                source_ref=source_ref,
                text="",
                metadata=_source_metadata(row) | {"missing": True},
            )
        indexed_body = str(row["indexed_body"] or "")
        suffix = Path(str(row["path"])).suffix.lower()
        if indexed_body and suffix not in TEXT_EXTENSIONS and str(row["section_type"] or "") != "file_metadata":
            return SourceContext(
                source_ref=_source_ref_from_row(row),
                text=indexed_body,
                metadata=_source_metadata(row) | {"line_count": max(len(indexed_body.splitlines()), 1)},
            )
        text = _read_text_file(file_path, max_bytes=5_000_000)
        if text is None:
            return SourceContext(
                source_ref=source_ref,
                text="",
                metadata=_source_metadata(row) | {"missing": True, "reason": "source is not text-readable"},
            )
        lines = text.splitlines()
        start = max(int(row["line_start"] or 1), 1)
        end = int(row["line_end"] or len(lines)) or len(lines)
        selected = "\n".join(lines[start - 1 : end])
        return SourceContext(
            source_ref=_source_ref_from_row(row),
            text=selected,
            metadata=_source_metadata(row) | {"line_count": max(end - start + 1, 0)},
        )

    def duplicate_report(
        self,
        scope: dict[str, Any] | None = None,
        *,
        mode: str = "exact_hash",
        limit: int = 50,
    ) -> dict[str, Any]:
        if limit <= 0:
            return _empty_duplicate_report(mode)
        scope = dict(scope or {})
        root_ids = _scope_strings(scope, "root_ids", "root_id")
        kinds = _scope_strings(scope, "source_kinds", "source_kind")
        if mode == "fclones_hash":
            return self._fclones_duplicate_report(scope, root_ids=root_ids, kinds=kinds, limit=limit)
        if mode == "czkawka_hash":
            return self._czkawka_duplicate_report(scope, root_ids=root_ids, kinds=kinds, limit=limit)
        if mode != "exact_hash":
            raise SourceRegistryError("duplicate report mode must be exact_hash, fclones_hash, or czkawka_hash")
        where = ["o.status = 'active'", "o.content_hash != ''"]
        params: list[Any] = []
        if root_ids:
            where.append(f"o.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        params.append(limit)
        with self.lock:
            groups = self.conn.execute(
                f"""
                SELECT o.content_hash, o.size, COUNT(*) AS member_count
                FROM source_objects o
                JOIN source_roots r ON r.root_id = o.root_id
                WHERE {' AND '.join(where)}
                GROUP BY o.content_hash, o.size
                HAVING COUNT(*) > 1
                ORDER BY member_count DESC, o.size DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            report_id = _stable_id("dup_report", f"{utc_now_iso()}:{mode}:{json.dumps(scope, sort_keys=True)}")
            now = utc_now_iso()
            self.conn.execute(
                """
                INSERT INTO duplicate_reports(report_id, mode, scope_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (report_id, mode, json.dumps(scope, sort_keys=True), now),
            )
            payload_groups = []
            for index, group in enumerate(groups, start=1):
                group_id = _stable_id(
                    "dup",
                    f"{report_id}:{group['content_hash']}:{group['size']}",
                )
                members = self._duplicate_members(
                    content_hash=str(group["content_hash"]),
                    size=int(group["size"]),
                    root_ids=root_ids,
                    kinds=kinds,
                )
                self.conn.execute(
                    """
                    INSERT INTO duplicate_groups(
                        group_id, report_id, method, confidence, content_hash, size,
                        member_count, action_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'reported')
                    """,
                    (
                        group_id,
                        report_id,
                        mode,
                        1.0,
                        group["content_hash"],
                        int(group["size"]),
                        len(members),
                    ),
                )
                for member in members:
                    self.conn.execute(
                        """
                        INSERT INTO duplicate_members(
                            group_id, object_id, root_id, path, reason, content_hash, size
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            group_id,
                            member["object_id"],
                            member["root_id"],
                            member["path"],
                            "same_content_hash_and_size",
                            member["content_hash"],
                            member["size"],
                        ),
                    )
                payload_groups.append(
                    {
                        "group_id": group_id,
                        "index": index,
                        "method": mode,
                        "confidence": 1.0,
                        "content_hash": group["content_hash"],
                        "size": int(group["size"]),
                        "member_count": len(members),
                        "members": members,
                    }
                )
            self.conn.commit()
        duplicate_file_count = sum(max(group["member_count"] - 1, 0) for group in payload_groups)
        return {
            "report_id": report_id,
            "mode": mode,
            "scope": scope,
            "group_count": len(payload_groups),
            "duplicate_file_count": duplicate_file_count,
            "groups": payload_groups,
            "data_flow": {
                "writes_source_files": False,
                "writes_index": True,
                "delete_move_merge_supported": False,
            },
        }

    def saved_search_create(
        self,
        label: str,
        query: str,
        scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        *,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        normalized_label = label.strip()
        normalized_query = query.strip()
        if not normalized_label:
            raise SourceRegistryError("saved search label is required")
        if not normalized_query:
            raise SourceRegistryError("saved search query is required")
        scope_payload = dict(scope or {})
        filters_payload = dict(filters or {})
        search_id = _stable_id(
            "search",
            f"{normalized_label}:{normalized_query}:{json.dumps(scope_payload, sort_keys=True)}",
        )
        now = utc_now_iso()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO saved_searches(
                    search_id, label, query, filters_json, scope_json, sort, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET
                    label = excluded.label,
                    query = excluded.query,
                    filters_json = excluded.filters_json,
                    scope_json = excluded.scope_json,
                    sort = excluded.sort
                """,
                (
                    search_id,
                    normalized_label,
                    normalized_query,
                    json.dumps(filters_payload, sort_keys=True),
                    json.dumps(scope_payload, sort_keys=True),
                    sort,
                    now,
                ),
            )
            self.conn.commit()
        return {
            "search_id": search_id,
            "label": normalized_label,
            "query": normalized_query,
            "filters": filters_payload,
            "scope": scope_payload,
            "sort": sort,
            "created_at": now,
            "data_flow": {
                "writes_source_files": False,
                "writes_index": True,
            },
        }

    def propose_tag(
        self,
        target_ref: SourceRef,
        tag: str,
        *,
        reason: str = "",
        write_target: str = "sidecar",
    ) -> dict[str, Any]:
        normalized_tag = tag.strip()
        if not normalized_tag:
            raise SourceRegistryError("tag is required")
        if write_target != "sidecar":
            raise SourceRegistryError("tag write_target must be sidecar in M3")
        target = self._target_for_ref(target_ref)
        proposal_id = _stable_id(
            "src_prop",
            f"tag:{target['root_id']}:{target['object_id']}:{target['section_id']}:{normalized_tag}:{utc_now_iso()}",
        )
        payload = {"tag": normalized_tag}
        proposal = self._create_action_proposal(
            proposal_id=proposal_id,
            action="tag",
            target=target,
            target_ref=target_ref,
            payload=payload,
            reason=reason,
            write_target=write_target,
        )
        return proposal

    def apply_tag(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._get_action_proposal(proposal_id)
        if proposal["action"] != "tag":
            raise SourceRegistryError(f"source action proposal is not a tag proposal: {proposal_id}")
        payload = dict(proposal["payload"])
        tag = str(payload.get("tag") or "").strip()
        if not tag:
            raise SourceRegistryError("tag proposal payload is missing tag")
        existing = self._existing_tag_for_proposal(proposal_id)
        if existing:
            return _applied_action_result(proposal, existing, already_applied=True)
        self._ensure_sidecar_write_allowed(proposal)
        now = utc_now_iso()
        tag_id = _stable_id("tag", f"{proposal_id}:{tag}")
        record = {
            "tag_id": tag_id,
            "root_id": proposal["root_id"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "name": tag,
            "origin": "pska",
            "status": "active",
            "proposal_id": proposal_id,
            "created_at": now,
        }
        sidecar = self._append_sidecar_annotation(
            proposal,
            {"tag": tag, "tag_id": tag_id},
            applied_at=now,
        )
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO source_tags(
                        tag_id, root_id, object_id, section_id, name, origin,
                        status, proposal_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag_id) DO NOTHING
                    """,
                    (
                        tag_id,
                        proposal["root_id"],
                        proposal["object_id"],
                        proposal["section_id"],
                        tag,
                        "pska",
                        "active",
                        proposal_id,
                        now,
                    ),
                )
                self._mark_action_proposal_applied(proposal_id, now)
        proposal["status"] = "applied"
        proposal["applied_at"] = now
        record["sidecar"] = sidecar
        return _applied_action_result(proposal, record, already_applied=False)

    def propose_comment(
        self,
        target_ref: SourceRef,
        body: str,
        *,
        reason: str = "",
        write_target: str = "sidecar",
    ) -> dict[str, Any]:
        normalized_body = body.strip()
        if not normalized_body:
            raise SourceRegistryError("comment body is required")
        if write_target != "sidecar":
            raise SourceRegistryError("comment write_target must be sidecar in M3")
        target = self._target_for_ref(target_ref)
        proposal_id = _stable_id(
            "src_prop",
            f"comment:{target['root_id']}:{target['object_id']}:{target['section_id']}:{normalized_body}:{utc_now_iso()}",
        )
        proposal = self._create_action_proposal(
            proposal_id=proposal_id,
            action="comment",
            target=target,
            target_ref=target_ref,
            payload={"body": normalized_body},
            reason=reason,
            write_target=write_target,
        )
        return proposal

    def apply_comment(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._get_action_proposal(proposal_id)
        if proposal["action"] != "comment":
            raise SourceRegistryError(f"source action proposal is not a comment proposal: {proposal_id}")
        payload = dict(proposal["payload"])
        body = str(payload.get("body") or "").strip()
        if not body:
            raise SourceRegistryError("comment proposal payload is missing body")
        existing = self._existing_comment_for_proposal(proposal_id)
        if existing:
            return _applied_action_result(proposal, existing, already_applied=True)
        self._ensure_sidecar_write_allowed(proposal)
        now = utc_now_iso()
        comment_id = _stable_id("comment", f"{proposal_id}:{body}")
        record = {
            "comment_id": comment_id,
            "root_id": proposal["root_id"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "body": body,
            "origin": "pska",
            "write_target": "sidecar",
            "status": "active",
            "proposal_id": proposal_id,
            "created_at": now,
        }
        sidecar = self._append_sidecar_annotation(
            proposal,
            {"body": body, "comment_id": comment_id},
            applied_at=now,
        )
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO source_comments(
                        comment_id, root_id, object_id, section_id, body, origin,
                        write_target, status, proposal_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(comment_id) DO NOTHING
                    """,
                    (
                        comment_id,
                        proposal["root_id"],
                        proposal["object_id"],
                        proposal["section_id"],
                        body,
                        "pska",
                        "sidecar",
                        "active",
                        proposal_id,
                        now,
                    ),
                )
                self._mark_action_proposal_applied(proposal_id, now)
        proposal["status"] = "applied"
        proposal["applied_at"] = now
        record["sidecar"] = sidecar
        return _applied_action_result(proposal, record, already_applied=False)

    def propose_obsidian_moc(
        self,
        root_id: str,
        source_refs: list[SourceRef],
        *,
        moc_path: str = "PSKA MOC.md",
        title: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        root = self.get_root(root_id)
        if root["kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian MOC proposals require an obsidian_vault source root")
        normalized_path = _normalize_moc_path(moc_path)
        normalized_title = title.strip() or Path(normalized_path).stem
        selected_targets = self._moc_targets(root, source_refs)
        if not selected_targets:
            raise SourceRegistryError("Obsidian MOC proposal requires at least one source ref from the selected vault")
        proposal_id = _stable_id(
            "src_prop",
            f"obsidian_moc:{root_id}:{normalized_path}:{utc_now_iso()}",
        )
        rendered_block = _render_moc_block(normalized_title, selected_targets)
        object_id = _stable_id("obj", f"{root_id}:{normalized_path}")
        target_ref = SourceRef(
            adapter=root["kind"],
            document_id=object_id,
            source_id=object_id,
            title=normalized_title,
            path=normalized_path,
            metadata={
                "source_layer": "personal",
                "root_id": root["root_id"],
                "root_kind": root["kind"],
                "root_label": root["label"],
                "permission_mode": root["permission_mode"],
                "path": normalized_path,
                "source_action": "obsidian_moc",
            },
        )
        target = {
            "root_id": root["root_id"],
            "root_kind": root["kind"],
            "root_label": root["label"],
            "absolute_path": root["absolute_path"],
            "permission_mode": root["permission_mode"],
            "object_id": object_id,
            "section_id": "",
            "path": normalized_path,
            "title": normalized_title,
            "section_type": "file",
            "heading_path": "",
            "line_start": 1,
            "line_end": 1,
        }
        payload = {
            "schema": "pska.obsidian_moc_proposal.v1",
            "moc_path": normalized_path,
            "title": normalized_title,
            "source_refs": [to_jsonable(item["source_ref"]) for item in selected_targets],
            "links": [
                {
                    "path": item["path"],
                    "title": item["title"],
                    "link": item["link"],
                }
                for item in selected_targets
            ],
            "rendered_block": rendered_block,
            "link_count": len(selected_targets),
            "mode": "replace_pska_block_or_append",
        }
        return self._create_action_proposal(
            proposal_id=proposal_id,
            action="obsidian_moc",
            target=target,
            target_ref=target_ref,
            payload=payload,
            reason=reason,
            write_target=OBSIDIAN_MOC_WRITE_TARGET,
        )

    def apply_obsidian_moc(self, proposal_id: str) -> dict[str, Any]:
        proposal = self._get_action_proposal(proposal_id)
        if proposal["action"] != "obsidian_moc":
            raise SourceRegistryError(f"source action proposal is not an Obsidian MOC proposal: {proposal_id}")
        if proposal["status"] == "applied":
            return _applied_moc_result(proposal, already_applied=True, changed=False)
        self._ensure_obsidian_moc_write_allowed(proposal)
        payload = dict(proposal["payload"])
        moc_path = _normalize_moc_path(str(payload.get("moc_path") or proposal["path"] or "PSKA MOC.md"))
        rendered_block = str(payload.get("rendered_block") or "").strip()
        if not rendered_block:
            raise SourceRegistryError("Obsidian MOC proposal payload is missing rendered_block")
        root_path = Path(proposal["absolute_path"])
        target_path = _path_inside_root(root_path, moc_path)
        before = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        title = str(payload.get("title") or Path(moc_path).stem)
        after = _upsert_moc_block(before, title=title, rendered_block=rendered_block)
        changed = before != after
        now = utc_now_iso()
        if changed:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(after, encoding="utf-8")
        with self.lock:
            with self.conn:
                self._mark_action_proposal_applied(proposal_id, now)
        proposal["status"] = "applied"
        proposal["applied_at"] = now
        record = {
            "path": moc_path,
            "absolute_path": str(target_path),
            "link_count": int(payload.get("link_count") or 0),
            "changed": changed,
            "created_file": changed and not bool(before),
            "write_target": OBSIDIAN_MOC_WRITE_TARGET,
            "next_actions": [
                {
                    "action": "scan_source_root",
                    "tool": "pska_source_scan",
                    "params": {"root_id": proposal["root_id"]},
                    "reason": "MOC note was written; rescan the vault to refresh links and FTS.",
                }
            ],
        }
        return _applied_moc_result(proposal, record=record, already_applied=False, changed=changed)

    def neighbors(
        self,
        source_ref: SourceRef,
        *,
        strategy: str = "auto",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        normalized_strategy = (strategy or "auto").strip().lower()
        if normalized_strategy not in NEIGHBOR_STRATEGIES:
            raise SourceRegistryError("source neighbor strategy must be auto, links, backlinks, or folder")
        target = self._target_for_ref(source_ref)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(candidate: dict[str, Any]) -> None:
            object_id = str(candidate.get("object_id") or "")
            if not object_id or object_id == target["object_id"] or object_id in seen:
                return
            seen.add(object_id)
            results.append(candidate)

        with self.lock:
            if normalized_strategy in {"auto", "links"}:
                for candidate in self._outgoing_link_neighbors(target, limit=limit):
                    add(candidate)
            if normalized_strategy in {"auto", "backlinks"}:
                for candidate in self._backlink_neighbors(target, limit=limit):
                    add(candidate)
            if normalized_strategy in {"auto", "folder"}:
                for candidate in self._folder_neighbors(target, limit=limit):
                    add(candidate)
        return results[:limit]

    def audit(self, scope: dict[str, Any] | None = None, *, limit: int = 20) -> dict[str, Any]:
        if limit <= 0:
            limit = 20
        scope = dict(scope or {})
        root_ids = _scope_strings(scope, "root_ids", "root_id")
        kinds = _scope_strings(scope, "source_kinds", "source_kind")
        with self.lock:
            roots = self._audit_roots(root_ids=root_ids, kinds=kinds)
            root_summaries = [self._audit_root_summary(root) for root in roots]
            duplicate_preview = self._audit_duplicate_preview(root_ids=root_ids, kinds=kinds, limit=limit)
            unresolved_links = self._audit_unresolved_links(root_ids=root_ids, kinds=kinds, limit=limit)
            unlinked_markdown = self._audit_unlinked_markdown(root_ids=root_ids, kinds=kinds, limit=limit)
            route_candidates = self._audit_route_candidates(root_ids=root_ids, kinds=kinds, limit=limit)
        next_actions = _source_audit_next_actions(
            roots=root_summaries,
            duplicate_preview=duplicate_preview,
            unresolved_links=unresolved_links,
            unlinked_markdown=unlinked_markdown,
            route_candidates=route_candidates,
            scope=scope,
        )
        return {
            "schema": "pska.source_audit.v1",
            "audit_id": _stable_id("source_audit", f"{utc_now_iso()}:{json.dumps(scope, sort_keys=True)}"),
            "created_at": utc_now_iso(),
            "scope": scope,
            "root_count": len(root_summaries),
            "roots": root_summaries,
            "duplicate_preview": duplicate_preview,
            "unresolved_links": unresolved_links,
            "unlinked_markdown": unlinked_markdown,
            "route_candidates": route_candidates,
            "next_actions": next_actions,
            "data_flow": {
                "writes_source_files": False,
                "writes_source_registry": False,
                "writes_memory_directly": False,
                "embedding_required": False,
            },
        }

    def _audit_roots(self, *, root_ids: list[str], kinds: list[str]) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if root_ids:
            where.append(f"r.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = self.conn.execute(
            f"""
            SELECT r.*,
                   SUM(CASE WHEN o.status = 'active' THEN 1 ELSE 0 END) AS active_object_count
            FROM source_roots r
            LEFT JOIN source_objects o ON o.root_id = r.root_id
            {where_sql}
            GROUP BY r.root_id
            ORDER BY r.label COLLATE NOCASE, r.absolute_path COLLATE NOCASE
            """,
            params,
        ).fetchall()
        return [_root_payload(row) for row in rows]

    def _audit_root_summary(self, root: dict[str, Any]) -> dict[str, Any]:
        root_id = root["root_id"]
        object_counts = {
            row["kind"]: int(row["count"] or 0)
            for row in self.conn.execute(
                """
                SELECT kind, COUNT(*) AS count
                FROM source_objects
                WHERE root_id = ? AND status = 'active'
                GROUP BY kind
                ORDER BY kind COLLATE NOCASE
                """,
                (root_id,),
            ).fetchall()
        }
        extraction_counts = {
            row["extraction_status"]: int(row["count"] or 0)
            for row in self.conn.execute(
                """
                SELECT extraction_status, COUNT(*) AS count
                FROM source_objects
                WHERE root_id = ? AND status = 'active'
                GROUP BY extraction_status
                ORDER BY extraction_status COLLATE NOCASE
                """,
                (root_id,),
            ).fetchall()
        }
        size_row = self.conn.execute(
            """
            SELECT COUNT(*) AS active_count, COALESCE(SUM(size), 0) AS total_size
            FROM source_objects
            WHERE root_id = ? AND status = 'active'
            """,
            (root_id,),
        ).fetchone()
        link_row = self.conn.execute(
            """
            SELECT COUNT(*) AS link_count,
                   SUM(CASE WHEN target_path = '' THEN 1 ELSE 0 END) AS unresolved_link_count
            FROM source_links
            WHERE root_id = ?
            """,
            (root_id,),
        ).fetchone()
        return {
            **root,
            "active_object_count": int(size_row["active_count"] or 0),
            "total_size": int(size_row["total_size"] or 0),
            "object_counts": object_counts,
            "extraction_counts": extraction_counts,
            "link_count": int(link_row["link_count"] or 0),
            "unresolved_link_count": int(link_row["unresolved_link_count"] or 0),
            "needs_scan": not bool(root.get("last_scan_at")),
        }

    def _audit_duplicate_preview(
        self,
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> dict[str, Any]:
        where = ["o.status = 'active'", "o.content_hash != ''"]
        params: list[Any] = []
        if root_ids:
            where.append(f"o.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        params.append(limit)
        groups = self.conn.execute(
            f"""
            SELECT o.content_hash, o.size, COUNT(*) AS member_count
            FROM source_objects o
            JOIN source_roots r ON r.root_id = o.root_id
            WHERE {' AND '.join(where)}
            GROUP BY o.content_hash, o.size
            HAVING COUNT(*) > 1
            ORDER BY member_count DESC, o.size DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        payload_groups = []
        for group in groups:
            members = self._duplicate_members(
                content_hash=str(group["content_hash"]),
                size=int(group["size"]),
                root_ids=root_ids,
                kinds=kinds,
            )
            payload_groups.append(
                {
                    "method": "exact_hash",
                    "confidence": 1.0,
                    "content_hash": group["content_hash"],
                    "size": int(group["size"]),
                    "member_count": len(members),
                    "members": members,
                }
            )
        duplicate_file_count = sum(max(group["member_count"] - 1, 0) for group in payload_groups)
        return {
            "group_count": len(payload_groups),
            "duplicate_file_count": duplicate_file_count,
            "groups": payload_groups,
            "data_flow": {
                "writes_source_files": False,
                "writes_source_registry": False,
                "delete_move_merge_supported": False,
            },
        }

    def _audit_unresolved_links(
        self,
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> dict[str, Any]:
        where = ["l.target_path = ''", "o.status = 'active'"]
        params: list[Any] = []
        if root_ids:
            where.append(f"l.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT l.root_id, r.kind AS root_kind, r.label AS root_label,
                   l.source_path, l.target_text, l.link_kind, l.link_text
            FROM source_links l
            JOIN source_objects o ON o.object_id = l.object_id AND o.root_id = l.root_id
            JOIN source_roots r ON r.root_id = l.root_id
            WHERE {' AND '.join(where)}
            ORDER BY r.label COLLATE NOCASE, l.source_path COLLATE NOCASE, l.target_text COLLATE NOCASE
            LIMIT ?
            """,
            params,
        ).fetchall()
        items = [
            {
                "root_id": row["root_id"],
                "root_kind": row["root_kind"],
                "root_label": row["root_label"],
                "source_path": row["source_path"],
                "target_text": row["target_text"],
                "link_kind": row["link_kind"],
                "link_text": row["link_text"],
            }
            for row in rows
        ]
        return {"count": len(items), "items": items}

    def _audit_unlinked_markdown(
        self,
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> dict[str, Any]:
        where = ["o.status = 'active'", "o.kind = 'markdown'"]
        params: list[Any] = []
        if root_ids:
            where.append(f"o.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end
            FROM source_objects o
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE {' AND '.join(where)}
              AND NOT EXISTS (
                  SELECT 1 FROM source_links outgoing
                  WHERE outgoing.object_id = o.object_id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM source_links incoming
                  WHERE incoming.root_id = o.root_id AND incoming.target_path = o.path
              )
            ORDER BY r.label COLLATE NOCASE, o.path COLLATE NOCASE
            LIMIT ?
            """,
            params,
        ).fetchall()
        items = [
            _neighbor_payload(
                row,
                relation="unlinked_markdown",
                score=0.5,
                reason="markdown note has no indexed outgoing links or backlinks",
            )
            for row in rows
        ]
        return {"count": len(items), "items": items}

    def _audit_route_candidates(
        self,
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        where = ["o.status = 'active'"]
        params: list[Any] = []
        if root_ids:
            where.append(f"o.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        route_terms = ["readme", "index", "moc", "handoff", "architecture", "overview", "map"]
        term_clauses = []
        for term in route_terms:
            term_clauses.append("(LOWER(o.path) LIKE ? OR LOWER(o.title) LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
        where.append("(" + " OR ".join(term_clauses) + ")")
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end
            FROM source_objects o
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE {' AND '.join(where)}
            ORDER BY r.label COLLATE NOCASE, o.path COLLATE NOCASE
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            _neighbor_payload(
                row,
                relation="route_candidate",
                score=0.8,
                reason="filename or title looks like a source-route entry point",
            )
            for row in rows
        ]

    def _target_for_ref(self, target_ref: SourceRef) -> dict[str, Any]:
        section_id = (
            str(target_ref.metadata.get("section_id") or "")
            or target_ref.chunk_id
            or target_ref.source_id
        )
        object_id = str(target_ref.metadata.get("object_id") or "") or target_ref.document_id or ""
        with self.lock:
            if section_id:
                row = self.conn.execute(
                    """
                    SELECT o.object_id, o.root_id, o.path, o.title,
                           r.kind AS root_kind, r.label AS root_label,
                           r.absolute_path, r.permission_mode,
                           s.section_id, s.title AS section_title, s.section_type,
                           s.heading_path, s.line_start, s.line_end
                    FROM source_sections s
                    JOIN source_objects o ON o.object_id = s.object_id
                    JOIN source_roots r ON r.root_id = o.root_id
                    WHERE s.section_id = ? AND o.status = 'active'
                    """,
                    (section_id,),
                ).fetchone()
            elif object_id:
                row = self.conn.execute(
                    """
                    SELECT o.object_id, o.root_id, o.path, o.title,
                           r.kind AS root_kind, r.label AS root_label,
                           r.absolute_path, r.permission_mode,
                           s.section_id, s.title AS section_title, s.section_type,
                           s.heading_path, s.line_start, s.line_end
                    FROM source_objects o
                    JOIN source_roots r ON r.root_id = o.root_id
                    LEFT JOIN source_sections s ON s.section_id = (
                        SELECT section_id FROM source_sections
                        WHERE object_id = o.object_id
                        ORDER BY line_start ASC, section_id ASC
                        LIMIT 1
                    )
                    WHERE o.object_id = ? AND o.status = 'active'
                    """,
                    (object_id,),
                ).fetchone()
            else:
                row = None
        if row is None:
            raise SourceRegistryError("source action target could not be resolved from SourceRef")
        return _target_payload(row)

    def _outgoing_link_neighbors(self, target: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end,
                   l.link_kind, l.link_text, l.target_text
            FROM source_links l
            JOIN source_objects o
              ON o.root_id = l.root_id
             AND o.path = l.target_path
             AND o.status = 'active'
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE l.object_id = ?
              AND l.target_path != ''
              AND o.object_id != ?
            ORDER BY l.ordinal ASC, o.path COLLATE NOCASE
            LIMIT ?
            """,
            (target["object_id"], target["object_id"], limit),
        ).fetchall()
        return [
            _neighbor_payload(
                row,
                relation="outgoing_link",
                score=1.0,
                reason=f"linked from {target['path']} via {row['link_text']}",
            )
            for row in rows
        ]

    def _backlink_neighbors(self, target: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end,
                   l.link_kind, l.link_text, l.target_text
            FROM source_links l
            JOIN source_objects o
              ON o.object_id = l.object_id
             AND o.root_id = l.root_id
             AND o.status = 'active'
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE l.root_id = ?
              AND l.target_path = ?
              AND o.object_id != ?
            ORDER BY o.path COLLATE NOCASE
            LIMIT ?
            """,
            (target["root_id"], target["path"], target["object_id"], limit),
        ).fetchall()
        return [
            _neighbor_payload(
                row,
                relation="backlink",
                score=0.92,
                reason=f"links to {target['path']} via {row['link_text']}",
            )
            for row in rows
        ]

    def _folder_neighbors(self, target: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        target_parent = _parent_path(target["path"])
        rows = self.conn.execute(
            """
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end
            FROM source_objects o
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE o.root_id = ?
              AND o.status = 'active'
              AND o.object_id != ?
            ORDER BY o.path COLLATE NOCASE
            LIMIT ?
            """,
            (target["root_id"], target["object_id"], max(limit * 8, 50)),
        ).fetchall()
        results = []
        for row in rows:
            if _parent_path(row["path"]) != target_parent:
                continue
            results.append(
                _neighbor_payload(
                    row,
                    relation="same_folder",
                    score=0.55,
                    reason=f"same folder as {target['path']}",
                )
            )
            if len(results) >= limit:
                break
        return results

    def _create_action_proposal(
        self,
        *,
        proposal_id: str,
        action: str,
        target: dict[str, Any],
        target_ref: SourceRef,
        payload: dict[str, Any],
        reason: str,
        write_target: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO source_action_proposals(
                    proposal_id, action, target_ref_json, root_id, object_id,
                    section_id, path, payload_json, reason, write_target,
                    status, created_at, applied_at, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, '', '')
                """,
                (
                    proposal_id,
                    action,
                    json.dumps(to_jsonable(target_ref), sort_keys=True, ensure_ascii=False),
                    target["root_id"],
                    target["object_id"],
                    target["section_id"],
                    target["path"],
                    json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    reason,
                    write_target,
                    now,
                ),
            )
            self.conn.commit()
        return _action_proposal_payload(
            {
                "proposal_id": proposal_id,
                "action": action,
                "target_ref": to_jsonable(target_ref),
                "root_id": target["root_id"],
                "root_kind": target["root_kind"],
                "root_label": target["root_label"],
                "permission_mode": target["permission_mode"],
                "object_id": target["object_id"],
                "section_id": target["section_id"],
                "path": target["path"],
                "payload": payload,
                "reason": reason,
                "write_target": write_target,
                "status": "pending",
                "created_at": now,
                "applied_at": "",
                "error": "",
            }
        )

    def _get_action_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT p.*, r.kind AS root_kind, r.label AS root_label,
                       r.permission_mode, r.absolute_path
                FROM source_action_proposals p
                JOIN source_roots r ON r.root_id = p.root_id
                WHERE p.proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise SourceRegistryError(f"source action proposal not found: {proposal_id}")
        return _action_proposal_from_row(row)

    def _ensure_sidecar_write_allowed(self, proposal: dict[str, Any]) -> None:
        if proposal["write_target"] != "sidecar":
            raise SourceRegistryError("only sidecar apply is supported in M3")
        if proposal["permission_mode"] not in {"sidecar_write", "native_write", "managed"}:
            raise SourceRegistryError(
                "source action apply requires permission_mode sidecar_write, native_write, or managed"
            )

    def _ensure_obsidian_moc_write_allowed(self, proposal: dict[str, Any]) -> None:
        if proposal["write_target"] != OBSIDIAN_MOC_WRITE_TARGET:
            raise SourceRegistryError("Obsidian MOC apply requires obsidian_moc write_target")
        if proposal["root_kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian MOC apply requires an obsidian_vault source root")
        if proposal["permission_mode"] not in {"native_write", "managed"}:
            raise SourceRegistryError("Obsidian MOC apply requires permission_mode native_write or managed")

    def _moc_targets(self, root: dict[str, Any], source_refs: list[SourceRef]) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source_ref in source_refs:
            target = self._target_for_ref(source_ref)
            if target["root_id"] != root["root_id"]:
                raise SourceRegistryError("Obsidian MOC source refs must all belong to the selected source root")
            if target["root_kind"] != "obsidian_vault":
                raise SourceRegistryError("Obsidian MOC source refs must belong to an Obsidian vault")
            path = str(target["path"] or "")
            if not path or path in seen:
                continue
            seen.add(path)
            title = str(target.get("title") or Path(path).stem)
            targets.append(
                {
                    "path": path,
                    "title": title,
                    "link": _obsidian_wikilink(path, title),
                    "source_ref": SourceRef(
                        adapter=target["root_kind"],
                        document_id=target["object_id"],
                        chunk_id=target["section_id"],
                        source_id=target["section_id"] or target["object_id"],
                        title=title,
                        path=path,
                        metadata={
                            "source_layer": "personal",
                            "root_id": target["root_id"],
                            "root_kind": target["root_kind"],
                            "root_label": target["root_label"],
                            "permission_mode": target["permission_mode"],
                            "object_id": target["object_id"],
                            "section_id": target["section_id"],
                            "path": path,
                        },
                    ),
                }
            )
        return targets

    def _append_sidecar_annotation(
        self,
        proposal: dict[str, Any],
        payload: dict[str, Any],
        *,
        applied_at: str,
    ) -> dict[str, Any]:
        root_path = Path(proposal["absolute_path"])
        sidecar_dir = root_path / ".pska"
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = sidecar_dir / "annotations.jsonl"
        entry = {
            "schema": "pska.source_annotation.v1",
            "proposal_id": proposal["proposal_id"],
            "action": proposal["action"],
            "root_id": proposal["root_id"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "path": proposal["path"],
            "reason": proposal["reason"],
            "write_target": "sidecar",
            "payload": payload,
            "created_at": proposal["created_at"],
            "applied_at": applied_at,
        }
        with sidecar_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return {
            "path": ".pska/annotations.jsonl",
            "absolute_path": str(sidecar_path),
            "writes_original_source_files": False,
        }

    def _mark_action_proposal_applied(self, proposal_id: str, applied_at: str) -> None:
        self.conn.execute(
            """
            UPDATE source_action_proposals
            SET status = 'applied', applied_at = ?, error = ''
            WHERE proposal_id = ?
            """,
            (applied_at, proposal_id),
        )

    def _existing_tag_for_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM source_tags WHERE proposal_id = ? ORDER BY created_at DESC LIMIT 1",
                (proposal_id,),
            ).fetchone()
        return dict(row) if row else None

    def _existing_comment_for_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM source_comments WHERE proposal_id = ? ORDER BY created_at DESC LIMIT 1",
                (proposal_id,),
            ).fetchone()
        return dict(row) if row else None

    def _index_file(
        self,
        root: dict[str, Any],
        file_path: Path,
        rel_path: str,
        *,
        max_bytes: int,
        extractor: str,
    ) -> str:
        stat = file_path.stat()
        object_id = _stable_id("obj", f"{root['root_id']}:{rel_path}")
        content_hash = _file_hash(file_path)
        mime = mimetypes.guess_type(file_path.name)[0] or ""
        extraction = _extract_file(file_path, max_bytes=max_bytes, extractor=extractor)
        text = extraction.text if extraction and extraction.status == "indexed" else None
        extraction_status = "unsupported"
        error = ""
        if extraction is not None:
            extraction_status = extraction.status
            error = _extraction_warning_summary(extraction)
        elif file_path.suffix.lower() in TEXT_EXTENSIONS and stat.st_size > max_bytes:
            extraction_status = "too_large"
        title = _title_for_file(file_path, text)
        self._upsert_object(
            root,
            object_id=object_id,
            rel_path=rel_path,
            kind=_object_kind(file_path),
            mime=mime,
            size=stat.st_size,
            mtime=stat.st_mtime,
            ctime=stat.st_ctime,
            content_hash=content_hash,
            title=title,
            extraction_status=extraction_status,
            error=error,
        )
        self.conn.execute("DELETE FROM source_sections WHERE object_id = ?", (object_id,))
        self.conn.execute("DELETE FROM source_fts WHERE object_id = ?", (object_id,))
        self.conn.execute("DELETE FROM source_links WHERE object_id = ?", (object_id,))
        sections = _sections_for_extraction(object_id, file_path, extraction, text)
        for section in sections:
            self.conn.execute(
                """
                INSERT INTO source_sections(
                    section_id, object_id, section_type, heading_path, line_start, line_end,
                    excerpt_hash, title
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section["section_id"],
                    object_id,
                    section["section_type"],
                    section["heading_path"],
                    section["line_start"],
                    section["line_end"],
                    section["excerpt_hash"],
                    section["title"],
                ),
            )
            self.conn.execute(
                """
                INSERT INTO source_fts(section_id, object_id, root_id, title, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    section["section_id"],
                    object_id,
                    root["root_id"],
                    section["title"],
                    section["body"],
                ),
            )
        if text is not None:
            for link in _links_for_file(root, file_path, rel_path, text):
                self.conn.execute(
                    """
                    INSERT INTO source_links(
                        link_id, root_id, object_id, source_path, target_text,
                        target_path, link_kind, link_text, ordinal, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(link_id) DO UPDATE SET
                        target_path = excluded.target_path,
                        link_text = excluded.link_text,
                        ordinal = excluded.ordinal,
                        created_at = excluded.created_at
                    """,
                    (
                        link["link_id"],
                        root["root_id"],
                        object_id,
                        rel_path,
                        link["target_text"],
                        link["target_path"],
                        link["link_kind"],
                        link["link_text"],
                        link["ordinal"],
                        link["created_at"],
                    ),
                )
        if extraction_status == "indexed":
            return "indexed"
        if extraction_status == "too_large":
            return "too_large"
        if extraction_status == "unsupported":
            return "unsupported"
        return "metadata_only"

    def _fclones_duplicate_report(
        self,
        scope: dict[str, Any],
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> dict[str, Any]:
        return self._external_duplicate_report(
            scope,
            root_ids=root_ids,
            kinds=kinds,
            limit=limit,
            mode="fclones_hash",
            provider="fclones",
            adapter=fclones_duplicate_report,
        )

    def _czkawka_duplicate_report(
        self,
        scope: dict[str, Any],
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> dict[str, Any]:
        return self._external_duplicate_report(
            scope,
            root_ids=root_ids,
            kinds=kinds,
            limit=limit,
            mode="czkawka_hash",
            provider="czkawka",
            adapter=czkawka_duplicate_report,
        )

    def _external_duplicate_report(
        self,
        scope: dict[str, Any],
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
        mode: str,
        provider: str,
        adapter: Any,
    ) -> dict[str, Any]:
        roots = self._duplicate_report_roots(root_ids=root_ids, kinds=kinds)
        report_id = _stable_id("dup_report", f"{utc_now_iso()}:{mode}:{json.dumps(scope, sort_keys=True)}")
        now = utc_now_iso()
        try:
            adapter_report = adapter(
                [Path(root["absolute_path"]) for root in roots],
                limit=limit,
            )
        except DedupError as exc:
            status = "error"
            message = str(exc)
            groups = []
            command: list[str] = []
            metadata: dict[str, Any] = {"error_type": exc.__class__.__name__}
        else:
            payload = adapter_report.to_dict()
            status = str(payload.get("status") or "ok")
            message = str(payload.get("message") or "")
            command = [str(item) for item in payload.get("command") or []]
            metadata = dict(payload.get("metadata") or {})
            groups = payload.get("groups") or []
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO duplicate_reports(report_id, mode, scope_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (report_id, mode, json.dumps(scope, sort_keys=True), now),
            )
            payload_groups = []
            for index, group in enumerate(groups, start=1):
                members = self._external_members_from_group(group, reason=f"{mode}_group")
                if len(members) < 2:
                    continue
                group_id = _stable_id("dup", f"{report_id}:{index}:{json.dumps(group, sort_keys=True)}")
                content_hash = str(group.get("content_hash") or "")
                size = int(group.get("size") or max((int(member.get("size") or 0) for member in members), default=0))
                self.conn.execute(
                    """
                    INSERT INTO duplicate_groups(
                        group_id, report_id, method, confidence, content_hash, size,
                        member_count, action_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'reported')
                    """,
                    (
                        group_id,
                        report_id,
                        mode,
                        float(group.get("confidence") or 1.0),
                        content_hash,
                        size,
                        len(members),
                    ),
                )
                for member in members:
                    self.conn.execute(
                        """
                        INSERT INTO duplicate_members(
                            group_id, object_id, root_id, path, reason, content_hash, size
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            group_id,
                            member["object_id"],
                            member["root_id"],
                            member["path"],
                            f"{mode}_group",
                            member.get("content_hash") or content_hash,
                            int(member.get("size") or size),
                        ),
                    )
                payload_groups.append(
                    {
                        "group_id": group_id,
                        "index": index,
                        "method": mode,
                        "confidence": float(group.get("confidence") or 1.0),
                        "content_hash": content_hash,
                        "size": size,
                        "member_count": len(members),
                        "members": members,
                    }
                )
            self.conn.commit()
        return {
            "report_id": report_id,
            "mode": mode,
            "provider": provider,
            "status": status,
            "message": message,
            "scope": scope,
            "group_count": len(payload_groups),
            "duplicate_file_count": sum(max(group["member_count"] - 1, 0) for group in payload_groups),
            "groups": payload_groups,
            "command": command,
            "metadata": metadata,
            "data_flow": {
                "writes_source_files": False,
                "writes_index": True,
                "delete_move_merge_supported": False,
            },
        }

    def _duplicate_report_roots(self, *, root_ids: list[str], kinds: list[str]) -> list[dict[str, Any]]:
        where = ["1 = 1"]
        params: list[Any] = []
        if root_ids:
            where.append(f"root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        with self.lock:
            rows = self.conn.execute(
                f"""
                SELECT * FROM source_roots
                WHERE {' AND '.join(where)}
                ORDER BY label COLLATE NOCASE, absolute_path COLLATE NOCASE
                """,
                params,
            ).fetchall()
        return [_root_payload(row) for row in rows]

    def _external_members_from_group(self, group: dict[str, Any], *, reason: str) -> list[dict[str, Any]]:
        members = []
        for member in group.get("members") or []:
            rel = self._resolve_external_duplicate_member(member, reason=reason)
            if rel is not None:
                members.append(rel)
        return members

    def _resolve_external_duplicate_member(self, member: dict[str, Any], *, reason: str) -> dict[str, Any] | None:
        absolute = str(member.get("absolute_path") or member.get("path") or "")
        if not absolute:
            return None
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                       o.content_hash, o.size, o.extraction_status,
                       r.kind AS root_kind, r.label AS root_label, r.permission_mode, r.absolute_path,
                       s.section_id, s.title AS section_title, s.section_type,
                       s.heading_path, s.line_start, s.line_end
                FROM source_objects o
                JOIN source_roots r ON r.root_id = o.root_id
                LEFT JOIN source_sections s ON s.section_id = (
                    SELECT section_id FROM source_sections
                    WHERE object_id = o.object_id
                    ORDER BY line_start ASC, section_id ASC
                    LIMIT 1
                )
                WHERE o.status = 'active'
                """
            ).fetchall()
        resolved_path = Path(absolute).expanduser().resolve()
        for row in rows:
            root_path = Path(row["absolute_path"]).resolve()
            candidate = (root_path / str(row["path"])).resolve()
            if candidate == resolved_path:
                return _duplicate_member_payload(row) | {"reason": reason}
        return None

    def _upsert_object(
        self,
        root: dict[str, Any],
        *,
        object_id: str,
        rel_path: str,
        kind: str,
        mime: str,
        size: int,
        mtime: float,
        ctime: float,
        content_hash: str,
        title: str,
        extraction_status: str,
        error: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO source_objects(
                object_id, root_id, path, kind, mime, size, mtime, ctime, content_hash,
                title, status, extraction_status, error, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, '')
            ON CONFLICT(root_id, path) DO UPDATE SET
                kind = excluded.kind,
                mime = excluded.mime,
                size = excluded.size,
                mtime = excluded.mtime,
                ctime = excluded.ctime,
                content_hash = excluded.content_hash,
                title = excluded.title,
                status = 'active',
                extraction_status = excluded.extraction_status,
                error = excluded.error,
                deleted_at = ''
            """,
            (
                object_id,
                root["root_id"],
                rel_path,
                kind,
                mime,
                size,
                mtime,
                ctime,
                content_hash,
                title,
                extraction_status,
                error,
            ),
        )

    def _upsert_error_object(self, root: dict[str, Any], file_path: Path, rel_path: str, error: str) -> None:
        stat = file_path.stat()
        self._upsert_object(
            root,
            object_id=_stable_id("obj", f"{root['root_id']}:{rel_path}"),
            rel_path=rel_path,
            kind=_object_kind(file_path),
            mime=mimetypes.guess_type(file_path.name)[0] or "",
            size=stat.st_size,
            mtime=stat.st_mtime,
            ctime=stat.st_ctime,
            content_hash="",
            title=file_path.stem or file_path.name,
            extraction_status="error",
            error=error,
        )

    def _like_search(
        self,
        query: str,
        *,
        root_ids: list[str],
        kinds: list[str],
        limit: int,
    ) -> list[ContextPacket]:
        terms = _query_terms(query)
        if not terms:
            return []
        where = ["o.status = 'active'"]
        params: list[Any] = []
        if root_ids:
            where.append(f"f.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        like_clauses = []
        for term in terms:
            like_clauses.append("(f.title LIKE ? OR f.body LIKE ? OR o.path LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
        where.append("(" + " OR ".join(like_clauses) + ")")
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT f.section_id, f.object_id, f.root_id, f.title AS fts_title,
                   substr(f.body, 1, 220) AS snippet, 0.0 AS rank,
                   o.path, o.kind AS object_kind, o.content_hash, o.extraction_status,
                   s.section_type, s.heading_path, s.line_start, s.line_end,
                   s.title AS section_title,
                   r.kind AS root_kind, r.permission_mode, r.label AS root_label
            FROM source_fts f
            JOIN source_objects o ON o.object_id = f.object_id
            JOIN source_sections s ON s.section_id = f.section_id
            JOIN source_roots r ON r.root_id = f.root_id
            WHERE {' AND '.join(where)}
            ORDER BY o.mtime DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [_packet_from_search_row(row, index) for index, row in enumerate(rows, start=1)]

    def _duplicate_members(
        self,
        *,
        content_hash: str,
        size: int,
        root_ids: list[str],
        kinds: list[str],
    ) -> list[dict[str, Any]]:
        where = ["o.status = 'active'", "o.content_hash = ?", "o.size = ?"]
        params: list[Any] = [content_hash, size]
        if root_ids:
            where.append(f"o.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        rows = self.conn.execute(
            f"""
            SELECT o.object_id, o.root_id, o.path, o.title, o.kind AS object_kind,
                   o.content_hash, o.size, o.extraction_status,
                   r.kind AS root_kind, r.label AS root_label, r.permission_mode,
                   s.section_id, s.title AS section_title, s.section_type,
                   s.heading_path, s.line_start, s.line_end
            FROM source_objects o
            JOIN source_roots r ON r.root_id = o.root_id
            LEFT JOIN source_sections s ON s.section_id = (
                SELECT section_id FROM source_sections
                WHERE object_id = o.object_id
                ORDER BY line_start ASC, section_id ASC
                LIMIT 1
            )
            WHERE {' AND '.join(where)}
            ORDER BY r.label COLLATE NOCASE, o.path COLLATE NOCASE
            """,
            params,
        ).fetchall()
        return [_duplicate_member_payload(row) for row in rows]

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_roots (
                root_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                kind TEXT NOT NULL,
                absolute_path TEXT NOT NULL UNIQUE,
                permission_mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_scan_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS source_objects (
                object_id TEXT PRIMARY KEY,
                root_id TEXT NOT NULL,
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                ctime REAL NOT NULL,
                content_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                extraction_status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                deleted_at TEXT NOT NULL DEFAULT '',
                UNIQUE(root_id, path)
            );

            CREATE TABLE IF NOT EXISTS source_sections (
                section_id TEXT PRIMARY KEY,
                object_id TEXT NOT NULL,
                section_type TEXT NOT NULL,
                heading_path TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                excerpt_hash TEXT NOT NULL,
                title TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(
                section_id UNINDEXED,
                object_id UNINDEXED,
                root_id UNINDEXED,
                title,
                body,
                tokenize='unicode61'
            );

            CREATE INDEX IF NOT EXISTS idx_source_objects_root
                ON source_objects(root_id, status, path);
            CREATE INDEX IF NOT EXISTS idx_source_sections_object
                ON source_sections(object_id);

            CREATE TABLE IF NOT EXISTS source_links (
                link_id TEXT PRIMARY KEY,
                root_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                target_text TEXT NOT NULL,
                target_path TEXT NOT NULL,
                link_kind TEXT NOT NULL,
                link_text TEXT NOT NULL,
                ordinal INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_source_links_source
                ON source_links(object_id);
            CREATE INDEX IF NOT EXISTS idx_source_links_target
                ON source_links(root_id, target_path);

            CREATE TABLE IF NOT EXISTS duplicate_reports (
                report_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS duplicate_groups (
                group_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                method TEXT NOT NULL,
                confidence REAL NOT NULL,
                content_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                member_count INTEGER NOT NULL,
                action_status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS duplicate_members (
                group_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                root_id TEXT NOT NULL,
                path TEXT NOT NULL,
                reason TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                PRIMARY KEY(group_id, object_id)
            );

            CREATE TABLE IF NOT EXISTS saved_searches (
                search_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                query TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                sort TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_action_proposals (
                proposal_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                target_ref_json TEXT NOT NULL,
                root_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                section_id TEXT NOT NULL,
                path TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                write_target TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                error TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_tags (
                tag_id TEXT PRIMARY KEY,
                root_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                section_id TEXT NOT NULL,
                name TEXT NOT NULL,
                origin TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_comments (
                comment_id TEXT PRIMARY KEY,
                root_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                section_id TEXT NOT NULL,
                body TEXT NOT NULL,
                origin TEXT NOT NULL,
                write_target TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._ensure_column("source_links", "ordinal", "INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _root_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = {
        "root_id": row["root_id"],
        "label": row["label"],
        "kind": row["kind"],
        "absolute_path": row["absolute_path"],
        "permission_mode": row["permission_mode"],
        "created_at": row["created_at"],
        "last_scan_at": row["last_scan_at"],
    }
    if "active_object_count" in row.keys():
        payload["active_object_count"] = int(row["active_object_count"] or 0)
    return payload


def _packet_from_search_row(row: sqlite3.Row, index: int) -> ContextPacket:
    ref = _source_ref_from_row(row)
    text = str(row["snippet"] or "")
    title = str(row["section_title"] or row["fts_title"] or row["path"])
    rank = float(row["rank"] or 0.0)
    return ContextPacket(
        context_id=f"ctx_source_{index}_{row['section_id']}",
        text=text,
        source_ref=ref,
        score=1.0 / (1.0 + abs(rank)),
        title=title,
        metadata={
            "source_layer": "personal",
            "rank": rank,
            "root_id": row["root_id"],
            "root_kind": row["root_kind"],
            "path": row["path"],
            "section_id": row["section_id"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "extraction_status": row["extraction_status"],
        },
    )


def _source_ref_from_row(row: sqlite3.Row) -> SourceRef:
    title = str(row["section_title"] or row["path"])
    return SourceRef(
        adapter=str(row["root_kind"]),
        document_id=str(row["object_id"]),
        chunk_id=str(row["section_id"]),
        source_id=str(row["section_id"]),
        title=title,
        path=str(row["path"]),
        metadata=_source_metadata(row),
    )


def _duplicate_member_payload(row: sqlite3.Row) -> dict[str, Any]:
    metadata = {
        "source_layer": "personal",
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "permission_mode": row["permission_mode"],
        "object_id": row["object_id"],
        "section_id": row["section_id"] or "",
        "path": row["path"],
        "content_hash": row["content_hash"],
        "section_type": row["section_type"] or "file",
        "heading_path": row["heading_path"] or "",
        "line_start": row["line_start"] or 1,
        "line_end": row["line_end"] or 1,
        "extraction_status": row["extraction_status"],
        "writes_source_files": False,
    }
    source_ref = SourceRef(
        adapter=str(row["root_kind"]),
        document_id=str(row["object_id"]),
        chunk_id=str(row["section_id"] or ""),
        source_id=str(row["section_id"] or row["object_id"]),
        title=str(row["section_title"] or row["title"] or row["path"]),
        path=str(row["path"]),
        metadata=metadata,
    )
    return {
        "object_id": row["object_id"],
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "path": row["path"],
        "title": row["title"],
        "content_hash": row["content_hash"],
        "size": int(row["size"]),
        "reason": "same_content_hash_and_size",
        "source_ref": source_ref,
    }


def _neighbor_payload(row: sqlite3.Row, *, relation: str, score: float, reason: str) -> dict[str, Any]:
    metadata = {
        "source_layer": "personal",
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "permission_mode": row["permission_mode"],
        "object_id": row["object_id"],
        "section_id": row["section_id"] or "",
        "path": row["path"],
        "content_hash": row["content_hash"],
        "section_type": row["section_type"] or "file",
        "heading_path": row["heading_path"] or "",
        "line_start": row["line_start"] or 1,
        "line_end": row["line_end"] or 1,
        "extraction_status": row["extraction_status"],
        "writes_source_files": False,
        "neighbor_relation": relation,
        "neighbor_reason": reason,
    }
    source_ref = SourceRef(
        adapter=str(row["root_kind"]),
        document_id=str(row["object_id"]),
        chunk_id=str(row["section_id"] or ""),
        source_id=str(row["section_id"] or row["object_id"]),
        title=str(row["section_title"] or row["title"] or row["path"]),
        path=str(row["path"]),
        metadata=metadata,
    )
    return {
        "relation": relation,
        "score": score,
        "reason": reason,
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "path": row["path"],
        "title": row["title"],
        "object_id": row["object_id"],
        "source_ref": source_ref,
        "data_flow": {
            "writes_source_files": False,
            "embedding_required": False,
        },
    }


def _target_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "absolute_path": row["absolute_path"],
        "permission_mode": row["permission_mode"],
        "object_id": row["object_id"],
        "section_id": row["section_id"] or "",
        "path": row["path"],
        "title": row["section_title"] or row["title"] or row["path"],
        "section_type": row["section_type"] or "file",
        "heading_path": row["heading_path"] or "",
        "line_start": row["line_start"] or 1,
        "line_end": row["line_end"] or 1,
    }


def _action_proposal_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "proposal_id": row["proposal_id"],
        "action": row["action"],
        "target_ref": json.loads(row["target_ref_json"]),
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "absolute_path": row["absolute_path"],
        "permission_mode": row["permission_mode"],
        "object_id": row["object_id"],
        "section_id": row["section_id"],
        "path": row["path"],
        "payload": json.loads(row["payload_json"]),
        "reason": row["reason"],
        "write_target": row["write_target"],
        "status": row["status"],
        "created_at": row["created_at"],
        "applied_at": row["applied_at"],
        "error": row["error"],
    }


def _action_proposal_payload(proposal: dict[str, Any], *, include_absolute_path: bool = False) -> dict[str, Any]:
    result = {
        "proposal_id": proposal["proposal_id"],
        "action": proposal["action"],
        "status": proposal["status"],
        "target_ref": proposal["target_ref"],
        "target": {
            "root_id": proposal["root_id"],
            "root_kind": proposal["root_kind"],
            "root_label": proposal["root_label"],
            "permission_mode": proposal["permission_mode"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "path": proposal["path"],
        },
        "payload": proposal["payload"],
        "reason": proposal["reason"],
        "write_target": proposal["write_target"],
        "created_at": proposal["created_at"],
        "applied_at": proposal["applied_at"],
        "error": proposal["error"],
        "data_flow": {
            "writes_source_files": False,
            "writes_original_source_files": False,
            "writes_sidecar": proposal["write_target"] == "sidecar",
            "requires_apply": proposal["status"] == "pending",
        },
    }
    if include_absolute_path:
        result["absolute_path"] = proposal.get("absolute_path", "")
    return result


def _applied_action_result(
    proposal: dict[str, Any],
    record: dict[str, Any],
    *,
    already_applied: bool,
) -> dict[str, Any]:
    return {
        "proposal": _action_proposal_payload(proposal),
        "record": to_jsonable(record),
        "applied": True,
        "already_applied": already_applied,
        "data_flow": {
            "writes_source_files": False,
            "writes_original_source_files": False,
            "writes_sidecar": not already_applied,
            "write_target": "sidecar",
        },
    }


def _applied_moc_result(
    proposal: dict[str, Any],
    record: dict[str, Any] | None = None,
    *,
    already_applied: bool,
    changed: bool,
) -> dict[str, Any]:
    payload = dict(proposal.get("payload") or {})
    moc_path = str(payload.get("moc_path") or proposal.get("path") or "")
    record_payload = record or {
        "path": moc_path,
        "absolute_path": str(Path(str(proposal.get("absolute_path") or "")) / moc_path) if moc_path else "",
        "link_count": int(payload.get("link_count") or 0),
        "changed": changed,
        "write_target": OBSIDIAN_MOC_WRITE_TARGET,
        "next_actions": [],
    }
    return {
        "proposal": _action_proposal_payload(proposal),
        "record": to_jsonable(record_payload),
        "applied": True,
        "already_applied": already_applied,
        "data_flow": {
            "writes_source_files": bool(changed),
            "writes_original_source_files": bool(changed),
            "writes_sidecar": False,
            "write_target": OBSIDIAN_MOC_WRITE_TARGET,
            "requires_native_permission": True,
        },
    }


def _empty_duplicate_report(mode: str) -> dict[str, Any]:
    return {
        "report_id": "",
        "mode": mode,
        "status": "empty",
        "scope": {},
        "group_count": 0,
        "duplicate_file_count": 0,
        "groups": [],
        "data_flow": {
            "writes_source_files": False,
            "writes_index": False,
            "delete_move_merge_supported": False,
        },
    }


def _source_audit_next_actions(
    *,
    roots: list[dict[str, Any]],
    duplicate_preview: dict[str, Any],
    unresolved_links: dict[str, Any],
    unlinked_markdown: dict[str, Any],
    route_candidates: list[dict[str, Any]],
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for root in roots:
        if root.get("needs_scan"):
            actions.append(
                {
                    "action": "scan_source_root",
                    "tool": "pska_source_scan",
                    "params": {"root_id": root["root_id"]},
                    "reason": "source root has not been scanned yet",
                }
            )
    if duplicate_preview.get("group_count"):
        actions.append(
            {
                "action": "review_duplicates",
                "tool": "pska_duplicate_report",
                "params": {"scope": scope, "mode": "exact_hash"},
                "reason": f"{duplicate_preview['group_count']} exact duplicate group(s) found",
            }
        )
    if unresolved_links.get("count"):
        actions.append(
            {
                "action": "inspect_unresolved_links",
                "tool": "pska_source_audit_run",
                "params": {"scope": scope},
                "reason": f"{unresolved_links['count']} unresolved Markdown/Obsidian link(s) found",
            }
        )
    if unlinked_markdown.get("count"):
        first = unlinked_markdown["items"][0]
        actions.append(
            {
                "action": "inspect_unlinked_notes",
                "tool": "pska_source_read",
                "params": {"source_ref": to_jsonable(first["source_ref"])},
                "reason": f"{unlinked_markdown['count']} Markdown note(s) have no indexed links or backlinks",
            }
        )
        moc_root = _first_native_obsidian_root(roots)
        if moc_root:
            moc_refs = [
                to_jsonable(item["source_ref"])
                for item in unlinked_markdown.get("items", [])
                if item.get("root_id") == moc_root["root_id"]
            ][:10]
            if moc_refs:
                actions.append(
                    {
                        "action": "propose_obsidian_moc",
                        "tool": "pska_obsidian_moc_propose",
                        "params": {
                            "root_id": moc_root["root_id"],
                            "source_refs": moc_refs,
                            "moc_path": "PSKA MOC.md",
                            "title": f"{moc_root['label']} MOC",
                        },
                        "reason": (
                            f"{len(moc_refs)} unlinked Obsidian note(s) can be collected into a governed MOC proposal"
                        ),
                    }
                )
    if route_candidates:
        actions.append(
            {
                "action": "create_source_memory_candidates_from_audit",
                "tool": "pska_source_memory_candidates_from_audit",
                "params": {
                    "scope": scope,
                    "candidate_limit": min(len(route_candidates), 5),
                    "memory_scope": "project",
                },
                "reason": f"{len(route_candidates)} route-like source entry point(s) can become governed Memory Card candidates",
            }
        )
    return actions


def _first_native_obsidian_root(roots: list[dict[str, Any]]) -> dict[str, Any] | None:
    for root in roots:
        if root.get("kind") == "obsidian_vault" and root.get("permission_mode") in {"native_write", "managed"}:
            return root
    return None


def _normalize_moc_path(path: str) -> str:
    value = str(path or "PSKA MOC.md").strip().replace("\\", "/")
    if not value:
        value = "PSKA MOC.md"
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise SourceRegistryError("Obsidian MOC path must be a relative markdown path inside the vault")
    if any(part.startswith(".") for part in candidate.parts):
        raise SourceRegistryError("Obsidian MOC path must not target hidden vault folders")
    if candidate.suffix.lower() not in {"", ".md", ".markdown", ".mdown"}:
        raise SourceRegistryError("Obsidian MOC path must be a Markdown file")
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")
    return candidate.as_posix()


def _render_moc_block(title: str, targets: list[dict[str, Any]]) -> str:
    lines = [
        PSKA_MOC_BEGIN,
        "## PSKA Source Index",
        "",
        f"Updated: {utc_now_iso()}",
        "",
    ]
    for target in targets:
        lines.append(f"- {target['link']}")
    lines.extend(["", PSKA_MOC_END])
    return "\n".join(lines)


def _upsert_moc_block(text: str, *, title: str, rendered_block: str) -> str:
    existing = text.rstrip()
    if not existing:
        return f"# {title.strip() or 'PSKA MOC'}\n\n{rendered_block.strip()}\n"
    begin = existing.find(PSKA_MOC_BEGIN)
    end = existing.find(PSKA_MOC_END)
    if begin >= 0 and end >= begin:
        end += len(PSKA_MOC_END)
        return f"{existing[:begin].rstrip()}\n\n{rendered_block.strip()}\n\n{existing[end:].lstrip()}".rstrip() + "\n"
    return f"{existing}\n\n{rendered_block.strip()}\n"


def _obsidian_wikilink(path: str, title: str) -> str:
    target = path.rsplit(".", 1)[0] if path.lower().endswith((".md", ".markdown", ".mdown")) else path
    safe_target = target.replace("|", " ").strip()
    safe_title = (title or Path(path).stem).replace("|", " ").strip()
    if safe_title and safe_title != Path(safe_target).name:
        return f"[[{safe_target}|{safe_title}]]"
    return f"[[{safe_target}]]"


def _source_metadata(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_layer": "personal",
        "root_id": row["root_id"],
        "root_kind": row["root_kind"],
        "root_label": row["root_label"],
        "permission_mode": row["permission_mode"],
        "object_id": row["object_id"],
        "section_id": row["section_id"],
        "path": row["path"],
        "content_hash": row["content_hash"],
        "section_type": row["section_type"],
        "heading_path": row["heading_path"],
        "line_start": row["line_start"],
        "line_end": row["line_end"],
        "extraction_status": row["extraction_status"],
        "writes_source_files": False,
    }


def _walk_source_files(root_path: Path):
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if name not in SKIP_DIRS and not name.startswith(".Trash")
        ]
        for filename in sorted(filenames):
            if filename.startswith(".DS_Store"):
                continue
            yield Path(dirpath) / filename


def _sections_for_file(object_id: str, file_path: Path, text: str | None) -> list[dict[str, Any]]:
    if text is None:
        title = file_path.stem or file_path.name
        return [
            _section(
                object_id,
                key="metadata",
                section_type="file_metadata",
                heading_path="",
                line_start=1,
                line_end=1,
                title=title,
                body=f"{title}\n{file_path.name}",
            )
        ]
    if file_path.suffix.lower() in {".md", ".markdown", ".mdown"}:
        sections = _markdown_sections(object_id, text)
        if sections:
            return sections
    lines = text.splitlines()
    return [
        _section(
            object_id,
            key="file",
            section_type="file",
            heading_path="",
            line_start=1,
            line_end=max(len(lines), 1),
            title=file_path.stem or file_path.name,
            body=text,
        )
    ]


def _sections_for_extraction(
    object_id: str,
    file_path: Path,
    extraction: ExtractionResult | None,
    text: str | None,
) -> list[dict[str, Any]]:
    if extraction is None or not extraction.sections:
        return _sections_for_file(object_id, file_path, text)
    if file_path.suffix.lower() in {".md", ".markdown", ".mdown"}:
        sections = _markdown_sections(object_id, extraction.text)
        if sections:
            return sections
    sections = []
    for index, extracted in enumerate(extraction.sections, start=1):
        body = extracted.text
        sections.append(
            _section(
                object_id,
                key=f"{extraction.extractor}:{index}:{extracted.title}",
                section_type=extracted.section_type,
                heading_path=extracted.heading_path,
                line_start=max(int(extracted.line_start or 1), 1),
                line_end=max(int(extracted.line_end or extracted.line_start or 1), 1),
                title=extracted.title or file_path.stem or file_path.name,
                body=body,
            )
        )
    return sections


def _extract_file(file_path: Path, *, max_bytes: int, extractor: str) -> ExtractionResult | None:
    try:
        return extract_source_file(file_path, max_bytes=max_bytes, extractor=extractor)
    except ExtractionError as exc:
        return ExtractionResult(
            text="",
            sections=[],
            extractor=extractor or "auto",
            status="error",
            warnings=[
                ExtractionWarning(code="extractor_error", message=str(exc))
            ],
        )


def _extraction_warning_summary(extraction: ExtractionResult) -> str:
    warnings = []
    for warning in extraction.warnings:
        if isinstance(warning, dict):
            message = str(warning.get("message") or warning.get("code") or "")
        else:
            message = warning.message
        if message:
            warnings.append(message)
    return "; ".join(warnings[:3])


def _markdown_sections(object_id: str, text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return []
    sections = []
    stack: list[tuple[int, str]] = []
    for idx, (line_no, level, title) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = headings[idx + 1][0] - 1 if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_no - 1 : end])
        heading_path = " / ".join(item[1] for item in stack)
        sections.append(
            _section(
                object_id,
                key=f"md:{line_no}:{title}",
                section_type="markdown_heading",
                heading_path=heading_path,
                line_start=line_no,
                line_end=max(end, line_no),
                title=title,
                body=body,
            )
        )
    return sections


def _links_for_file(root: dict[str, Any], file_path: Path, rel_path: str, text: str) -> list[dict[str, Any]]:
    if file_path.suffix.lower() not in {".md", ".markdown", ".mdown"}:
        return []
    root_path = Path(root["absolute_path"])
    source_parent = Path(rel_path).parent
    if source_parent.as_posix() == ".":
        source_parent = Path("")
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for match in re.finditer(r"!?\[\[([^\]#\|]+)(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]", text):
        target_text = match.group(1).strip()
        target_path = _resolve_obsidian_link(root_path, target_text)
        key = ("obsidian_wikilink", target_text, target_path)
        if target_text and key not in seen:
            seen.add(key)
            links.append(
                _link_payload(
                    root["root_id"],
                    rel_path,
                    target_text,
                    target_path,
                    "obsidian_wikilink",
                    match.group(0),
                    len(links) + 1,
                )
            )

    for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target_text = _clean_markdown_link_target(match.group(1))
        if not target_text:
            continue
        target_path = _resolve_markdown_link(root_path, source_parent, target_text)
        key = ("markdown_link", target_text, target_path)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            _link_payload(
                root["root_id"],
                rel_path,
                target_text,
                target_path,
                "markdown_link",
                match.group(0),
                len(links) + 1,
            )
        )
    return links


def _link_payload(
    root_id: str,
    source_path: str,
    target_text: str,
    target_path: str,
    link_kind: str,
    link_text: str,
    ordinal: int,
) -> dict[str, Any]:
    return {
        "link_id": _stable_id("link", f"{root_id}:{source_path}:{link_kind}:{target_text}:{target_path}"),
        "target_text": target_text,
        "target_path": target_path,
        "link_kind": link_kind,
        "link_text": link_text,
        "ordinal": ordinal,
        "created_at": utc_now_iso(),
    }


def _resolve_obsidian_link(root_path: Path, target_text: str) -> str:
    target = target_text.strip().replace("\\", "/")
    if not target or _is_external_link(target):
        return ""
    target = target.split("#", 1)[0].strip()
    if not target:
        return ""
    candidates = []
    if "/" in target:
        candidates.append(target)
        if not Path(target).suffix:
            candidates.append(f"{target}.md")
    else:
        wanted_names = {target, f"{target}.md"}
        wanted_stem = Path(target).stem
        for path in _walk_source_files(root_path):
            if path.suffix.lower() not in {".md", ".markdown", ".mdown"}:
                continue
            if path.name in wanted_names or path.stem == wanted_stem:
                candidates.append(path.relative_to(root_path).as_posix())
    return _first_existing_relpath(root_path, candidates)


def _resolve_markdown_link(root_path: Path, source_parent: Path, target_text: str) -> str:
    target = target_text.strip().replace("\\", "/")
    if not target or _is_external_link(target) or target.startswith("#"):
        return ""
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return ""
    if target.startswith("/"):
        candidates = [target.lstrip("/")]
    else:
        candidates = [((source_parent / target).as_posix()).lstrip("./")]
    if not Path(target).suffix:
        candidates.extend(f"{candidate}.md" for candidate in list(candidates))
    return _first_existing_relpath(root_path, candidates)


def _clean_markdown_link_target(target: str) -> str:
    cleaned = target.strip()
    if cleaned.startswith("<") and ">" in cleaned:
        cleaned = cleaned[1 : cleaned.index(">")]
    elif " " in cleaned:
        cleaned = cleaned.split(" ", 1)[0]
    return unquote(cleaned.strip())


def _first_existing_relpath(root_path: Path, candidates: list[str]) -> str:
    for candidate in candidates:
        rel_path = candidate.strip().lstrip("./")
        if not rel_path:
            continue
        try:
            path = _path_inside_root(root_path, rel_path)
        except SourceRegistryError:
            continue
        if path.exists() and path.is_file():
            return path.relative_to(root_path).as_posix()
    return ""


def _is_external_link(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target))


def _parent_path(rel_path: str) -> str:
    parent = Path(rel_path).parent.as_posix()
    return "" if parent == "." else parent


def _section(
    object_id: str,
    *,
    key: str,
    section_type: str,
    heading_path: str,
    line_start: int,
    line_end: int,
    title: str,
    body: str,
) -> dict[str, Any]:
    return {
        "section_id": _stable_id("sec", f"{object_id}:{key}"),
        "section_type": section_type,
        "heading_path": heading_path,
        "line_start": line_start,
        "line_end": line_end,
        "excerpt_hash": _text_hash(body[:2000]),
        "title": title,
        "body": body,
    }


def _safe_absolute_path(path: str | Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    return raw.resolve()


def _path_inside_root(root_path: Path, rel_path: str) -> Path:
    candidate = (root_path / rel_path).resolve()
    try:
        candidate.relative_to(root_path.resolve())
    except ValueError as exc:
        raise SourceRegistryError("source path escapes registered root") from exc
    return candidate


def _normalize_kind(kind: str, path: Path) -> str:
    value = (kind or "").strip().lower()
    if value in {"auto", ""}:
        value = "obsidian_vault" if (path / ".obsidian").is_dir() else "local_folder"
    if value not in PERSONAL_SOURCE_ADAPTERS:
        raise SourceRegistryError("source root kind must be local_folder or obsidian_vault")
    return value


def _normalize_permission(permission_mode: str) -> str:
    value = (permission_mode or "read_only").strip().lower()
    if value not in PERMISSION_MODES:
        raise SourceRegistryError(
            "permission_mode must be read_only, sidecar_write, native_write, or managed"
        )
    return value


def _object_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".mdown"}:
        return "markdown"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "file"


def _read_text_file(path: Path, *, max_bytes: int) -> str | None:
    data = path.read_bytes()
    if len(data) > max_bytes:
        return None
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _title_for_file(path: Path, text: str | None) -> str:
    if text:
        for line in text.splitlines()[:80]:
            match = re.match(r"^#\s+(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
    return path.stem or path.name


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _text_hash(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _query_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[\w\u4e00-\u9fff]+", query, flags=re.UNICODE) if term.strip()]


def _fts_query(query: str) -> str:
    terms = _query_terms(query)
    if not terms:
        return ""
    return " OR ".join(f'"{term.replace("\"", "\"\"")}"' for term in terms[:12])


def _scope_strings(data: dict[str, Any], plural_key: str, singular_key: str) -> list[str]:
    values = data.get(plural_key)
    if values is None:
        values = data.get(singular_key)
    if values is None:
        return []
    if isinstance(values, str):
        return [values] if values else []
    if isinstance(values, list):
        return [str(value) for value in values if str(value)]
    return []
