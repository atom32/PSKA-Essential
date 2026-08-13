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
SIDECAR_WRITE_TARGET = "sidecar"
OBSIDIAN_FRONTMATTER_WRITE_TARGET = "obsidian_frontmatter"
OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET = "obsidian_markdown_comment"
OBSIDIAN_MOC_WRITE_TARGET = "obsidian_moc"
MOC_GROUP_BY_MODES = {"none", "folder", "tag", "topic", "project"}
PSKA_COMMENT_END = "<!-- PSKA:COMMENT:END -->"
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
        object_kinds = _scope_strings(filters, "object_kinds", "object_kind")
        extraction_statuses = _scope_strings(filters, "extraction_statuses", "extraction_status")
        terms = _query_terms(query)
        boost_sql, boost_params = _search_boost_sql(terms)

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
        if object_kinds:
            where.append(f"o.kind IN ({','.join('?' for _ in object_kinds)})")
            params.extend(object_kinds)
        if extraction_statuses:
            where.append(f"o.extraction_status IN ({','.join('?' for _ in extraction_statuses)})")
            params.extend(extraction_statuses)
        query_limit = max(limit * 3, limit)
        query_params = boost_params + params + [query_limit]
        with self.lock:
            try:
                rows = self.conn.execute(
                    f"""
                    SELECT *,
                           lexical_rank - rank_boost AS final_rank
                    FROM (
                        SELECT f.section_id, f.object_id, f.root_id, f.title AS fts_title,
                               snippet(source_fts, 4, '', '', '...', 30) AS snippet_plain,
                               snippet(source_fts, 4, '[', ']', '...', 30) AS snippet_highlighted,
                               bm25(source_fts, 0.0, 0.0, 0.0, 4.0, 1.0) AS lexical_rank,
                               {boost_sql} AS rank_boost,
                               o.path, o.title AS object_title, o.kind AS object_kind,
                               o.content_hash, o.extraction_status,
                               s.section_type, s.heading_path, s.line_start, s.line_end,
                               s.title AS section_title,
                               r.kind AS root_kind, r.permission_mode, r.label AS root_label,
                               o.mtime AS object_mtime
                        FROM source_fts f
                        JOIN source_objects o ON o.object_id = f.object_id
                        JOIN source_sections s ON s.section_id = f.section_id
                        JOIN source_roots r ON r.root_id = f.root_id
                        WHERE {' AND '.join(where)}
                    )
                    ORDER BY final_rank ASC, lexical_rank ASC, rank_boost DESC, path COLLATE NOCASE
                    LIMIT ?
                    """,
                    query_params,
                ).fetchall()
            except sqlite3.OperationalError:
                return self._like_search(
                    query,
                    root_ids=root_ids,
                    kinds=kinds,
                    path_prefixes=path_prefixes,
                    object_kinds=object_kinds,
                    extraction_statuses=extraction_statuses,
                    limit=limit,
                )
            rows = list(rows)
            rows.extend(
                self._like_search_rows(
                    query,
                    root_ids=root_ids,
                    kinds=kinds,
                    path_prefixes=path_prefixes,
                    object_kinds=object_kinds,
                    extraction_statuses=extraction_statuses,
                    exclude_section_ids=[str(row["section_id"]) for row in rows],
                    limit=limit,
                )
            )
            rows = sorted(rows, key=_search_row_sort_key)[:limit]
        return [_packet_from_search_row(row, index, query_terms=terms) for index, row in enumerate(rows, start=1)]

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

    def source_collection_create(
        self,
        label: str,
        *,
        description: str = "",
        selector: dict[str, Any] | None = None,
        source_refs: list[SourceRef | dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_label = label.strip()
        if not normalized_label:
            raise SourceRegistryError("source collection label is required")
        selector_payload = _normalize_collection_selector(selector or {})
        refs = [ref if isinstance(ref, SourceRef) else SourceRef.from_dict(ref) for ref in (source_refs or [])]
        ref_payloads = [to_jsonable(_source_ref_from_target(self._target_for_ref(ref))) for ref in refs]
        if selector_payload["kind"] == "manual" and not ref_payloads:
            raise SourceRegistryError("manual source collection requires source_refs")
        collection_id = _stable_id(
            "collection",
            f"{normalized_label}:{json.dumps(selector_payload, sort_keys=True)}:{json.dumps(ref_payloads, sort_keys=True)}",
        )
        now = utc_now_iso()
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO source_collections(
                    collection_id, label, description, selector_json, source_refs_json,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(collection_id) DO UPDATE SET
                    label = excluded.label,
                    description = excluded.description,
                    selector_json = excluded.selector_json,
                    source_refs_json = excluded.source_refs_json,
                    status = 'active',
                    updated_at = excluded.updated_at
                """,
                (
                    collection_id,
                    normalized_label,
                    description.strip(),
                    json.dumps(selector_payload, sort_keys=True),
                    json.dumps(ref_payloads, sort_keys=True),
                    now,
                    now,
                ),
            )
            self.conn.commit()
        return {
            "collection_id": collection_id,
            "label": normalized_label,
            "description": description.strip(),
            "selector": selector_payload,
            "source_refs": ref_payloads,
            "source_ref_count": len(ref_payloads),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "data_flow": {
                "writes_source_files": False,
                "writes_index": True,
                "embedding_required": False,
            },
        }

    def source_collection_list(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT * FROM source_collections
                WHERE status = 'active'
                ORDER BY updated_at DESC, label COLLATE NOCASE
                """
            ).fetchall()
        return [_source_collection_payload(row) for row in rows]

    def source_collection_get(self, collection_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM source_collections WHERE collection_id = ? AND status = 'active'",
                (collection_id,),
            ).fetchone()
        if row is None:
            raise SourceRegistryError(f"source collection not found: {collection_id}")
        return _source_collection_payload(row)

    def source_collection_resolve(self, collection_id: str, *, limit: int = 10) -> dict[str, Any]:
        collection = self.source_collection_get(collection_id)
        selector = dict(collection.get("selector") or {})
        kind = selector.get("kind") or "manual"
        if kind == "search":
            query = str(selector.get("query") or "").strip()
            packets = self.search(
                query,
                selector.get("scope") or {},
                limit=limit or int(selector.get("limit") or 10),
                filters=selector.get("filters") or {},
            )
            materialized_from = "search_selector"
        elif kind == "manual":
            refs = [SourceRef.from_dict(item) for item in collection.get("source_refs") or []]
            packets = self._packets_from_refs(refs, limit=limit)
            materialized_from = "manual_refs"
        else:
            raise SourceRegistryError("source collection selector kind must be manual or search")
        return {
            "collection": collection,
            "context_packets": packets,
            "count": len(packets),
            "materialized_from": materialized_from,
            "data_flow": {
                "writes_source_files": False,
                "writes_index": False,
                "embedding_required": False,
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
        normalized_write_target = _normalize_tag_write_target(write_target)
        target = self._target_for_ref(target_ref)
        if normalized_write_target == OBSIDIAN_FRONTMATTER_WRITE_TARGET:
            self._ensure_obsidian_frontmatter_tag_target(target)
        proposal_id = _stable_id(
            "src_prop",
            f"tag:{target['root_id']}:{target['object_id']}:{target['section_id']}:{normalized_tag}:{normalized_write_target}:{utc_now_iso()}",
        )
        payload = {"tag": normalized_tag}
        if normalized_write_target == OBSIDIAN_FRONTMATTER_WRITE_TARGET:
            payload.update(
                {
                    "schema": "pska.obsidian_frontmatter_tag_proposal.v1",
                    "frontmatter_field": "tags",
                    "mode": "append_unique_tag",
                }
            )
        proposal = self._create_action_proposal(
            proposal_id=proposal_id,
            action="tag",
            target=target,
            target_ref=target_ref,
            payload=payload,
            reason=reason,
            write_target=normalized_write_target,
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
            return _applied_tag_result(proposal, existing, already_applied=True, changed=False)
        now = utc_now_iso()
        tag_id = _stable_id("tag", f"{proposal_id}:{tag}")
        record = {
            "tag_id": tag_id,
            "root_id": proposal["root_id"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "name": tag,
            "origin": "pska",
            "write_target": proposal["write_target"],
            "status": "active",
            "proposal_id": proposal_id,
            "created_at": now,
        }
        changed = False
        if proposal["write_target"] == SIDECAR_WRITE_TARGET:
            self._ensure_sidecar_write_allowed(proposal)
            sidecar = self._append_sidecar_annotation(
                proposal,
                {"tag": tag, "tag_id": tag_id},
                applied_at=now,
            )
            record["sidecar"] = sidecar
            changed = True
        elif proposal["write_target"] == OBSIDIAN_FRONTMATTER_WRITE_TARGET:
            self._ensure_obsidian_frontmatter_tag_write_allowed(proposal)
            frontmatter = self._apply_obsidian_frontmatter_tag(proposal, tag)
            record["write_target"] = OBSIDIAN_FRONTMATTER_WRITE_TARGET
            record["frontmatter"] = frontmatter
            changed = bool(frontmatter.get("changed"))
        else:
            raise SourceRegistryError("tag apply supports sidecar or obsidian_frontmatter write_target")
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO source_tags(
                        tag_id, root_id, object_id, section_id, name, origin,
                        write_target, status, proposal_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag_id) DO NOTHING
                    """,
                    (
                        tag_id,
                        proposal["root_id"],
                        proposal["object_id"],
                        proposal["section_id"],
                        tag,
                        "pska",
                        proposal["write_target"],
                        "active",
                        proposal_id,
                        now,
                    ),
                )
                self._mark_action_proposal_applied(proposal_id, now)
        proposal["status"] = "applied"
        proposal["applied_at"] = now
        return _applied_tag_result(proposal, record, already_applied=False, changed=changed)

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
        normalized_write_target = _normalize_comment_write_target(write_target)
        target = self._target_for_ref(target_ref)
        if normalized_write_target == OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET:
            self._ensure_obsidian_markdown_comment_target(target)
        proposal_id = _stable_id(
            "src_prop",
            f"comment:{target['root_id']}:{target['object_id']}:{target['section_id']}:{normalized_body}:{normalized_write_target}:{utc_now_iso()}",
        )
        payload = {"body": normalized_body}
        if normalized_write_target == OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET:
            payload.update(
                {
                    "schema": "pska.obsidian_markdown_comment_proposal.v1",
                    "mode": "append_unique_pska_comment_block",
                    "heading_path": target.get("heading_path", ""),
                    "line_start": target.get("line_start", 1),
                    "line_end": target.get("line_end", 1),
                }
            )
        proposal = self._create_action_proposal(
            proposal_id=proposal_id,
            action="comment",
            target=target,
            target_ref=target_ref,
            payload=payload,
            reason=reason,
            write_target=normalized_write_target,
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
            return _applied_comment_result(proposal, existing, already_applied=True, changed=False)
        now = utc_now_iso()
        comment_id = _stable_id("comment", f"{proposal_id}:{body}")
        record = {
            "comment_id": comment_id,
            "root_id": proposal["root_id"],
            "object_id": proposal["object_id"],
            "section_id": proposal["section_id"],
            "body": body,
            "origin": "pska",
            "write_target": proposal["write_target"],
            "status": "active",
            "proposal_id": proposal_id,
            "created_at": now,
        }
        changed = False
        if proposal["write_target"] == SIDECAR_WRITE_TARGET:
            self._ensure_sidecar_write_allowed(proposal)
            sidecar = self._append_sidecar_annotation(
                proposal,
                {"body": body, "comment_id": comment_id},
                applied_at=now,
            )
            record["sidecar"] = sidecar
            changed = True
        elif proposal["write_target"] == OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET:
            self._ensure_obsidian_markdown_comment_write_allowed(proposal)
            markdown_comment = self._apply_obsidian_markdown_comment(
                proposal,
                body,
                comment_id=comment_id,
                applied_at=now,
            )
            record["markdown_comment"] = markdown_comment
            changed = bool(markdown_comment.get("changed"))
        else:
            raise SourceRegistryError("comment apply supports sidecar or obsidian_markdown_comment write_target")
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
                        proposal["write_target"],
                        "active",
                        proposal_id,
                        now,
                    ),
                )
                self._mark_action_proposal_applied(proposal_id, now)
        proposal["status"] = "applied"
        proposal["applied_at"] = now
        return _applied_comment_result(proposal, record, already_applied=False, changed=changed)

    def propose_obsidian_moc(
        self,
        root_id: str,
        source_refs: list[SourceRef],
        *,
        moc_path: str = "PSKA MOC.md",
        title: str = "",
        reason: str = "",
        group_by: str = "none",
    ) -> dict[str, Any]:
        root = self.get_root(root_id)
        if root["kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian MOC proposals require an obsidian_vault source root")
        normalized_path = _normalize_moc_path(moc_path)
        normalized_title = title.strip() or Path(normalized_path).stem
        normalized_group_by = _normalize_moc_group_by(group_by)
        selected_targets = self._moc_targets(root, source_refs)
        if not selected_targets:
            raise SourceRegistryError("Obsidian MOC proposal requires at least one source ref from the selected vault")
        proposal_id = _stable_id(
            "src_prop",
            f"obsidian_moc:{root_id}:{normalized_path}:{normalized_group_by}:{utc_now_iso()}",
        )
        groups = _moc_groups(selected_targets, normalized_group_by)
        rendered_block = _render_moc_block(normalized_title, selected_targets, group_by=normalized_group_by, groups=groups)
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
            "group_by": normalized_group_by,
            "source_refs": [to_jsonable(item["source_ref"]) for item in selected_targets],
            "links": [
                {
                    "path": item["path"],
                    "title": item["title"],
                    "link": item["link"],
                }
                for item in selected_targets
            ],
            "groups": groups,
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

    def _apply_obsidian_frontmatter_tag(self, proposal: dict[str, Any], tag: str) -> dict[str, Any]:
        root_path = Path(proposal["absolute_path"])
        target_path = _path_inside_root(root_path, proposal["path"])
        if not target_path.exists() or not target_path.is_file():
            raise SourceRegistryError("Obsidian frontmatter tag apply requires an existing Markdown note")
        before = target_path.read_text(encoding="utf-8")
        after, frontmatter = _upsert_obsidian_frontmatter_tag(before, tag)
        changed = before != after
        if changed:
            target_path.write_text(after, encoding="utf-8")
        return {
            "path": proposal["path"],
            "absolute_path": str(target_path),
            "field": "tags",
            "tag": tag,
            "changed": changed,
            "tags": frontmatter["tags"],
            "created_frontmatter": frontmatter["created_frontmatter"],
            "write_target": OBSIDIAN_FRONTMATTER_WRITE_TARGET,
            "next_actions": [
                {
                    "action": "scan_source_root",
                    "tool": "pska_source_scan",
                    "params": {"root_id": proposal["root_id"]},
                    "reason": "frontmatter tag was written; rescan the vault to refresh indexed metadata.",
                }
            ],
        }

    def _apply_obsidian_markdown_comment(
        self,
        proposal: dict[str, Any],
        body: str,
        *,
        comment_id: str,
        applied_at: str,
    ) -> dict[str, Any]:
        root_path = Path(proposal["absolute_path"])
        target_path = _path_inside_root(root_path, proposal["path"])
        if not target_path.exists() or not target_path.is_file():
            raise SourceRegistryError("Obsidian markdown comment apply requires an existing Markdown note")
        before = target_path.read_text(encoding="utf-8")
        after, markdown_comment = _upsert_obsidian_markdown_comment_block(
            before,
            body=body,
            comment_id=comment_id,
            path=str(proposal.get("path") or ""),
            heading_path=str(proposal.get("payload", {}).get("heading_path") or proposal.get("heading_path") or ""),
            line_start=int(proposal.get("line_start") or 1),
            line_end=int(proposal.get("line_end") or 1),
            reason=str(proposal.get("reason") or ""),
            applied_at=applied_at,
        )
        changed = before != after
        if changed:
            target_path.write_text(after, encoding="utf-8")
        return {
            "path": proposal["path"],
            "absolute_path": str(target_path),
            "comment_id": comment_id,
            "changed": changed,
            "block_marker": markdown_comment["block_marker"],
            "target": markdown_comment["target"],
            "write_target": OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET,
            "next_actions": [
                {
                    "action": "scan_source_root",
                    "tool": "pska_source_scan",
                    "params": {"root_id": proposal["root_id"]},
                    "reason": "Markdown comment block was written; rescan the vault to refresh indexed text.",
                }
            ],
        }

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
                           o.content_hash, o.extraction_status,
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
                           o.content_hash, o.extraction_status,
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
        if proposal["write_target"] != SIDECAR_WRITE_TARGET:
            raise SourceRegistryError("source action apply requires sidecar write_target")
        if proposal["permission_mode"] not in {"sidecar_write", "native_write", "managed"}:
            raise SourceRegistryError(
                "source action apply requires permission_mode sidecar_write, native_write, or managed"
            )

    def _ensure_obsidian_frontmatter_tag_target(self, target: dict[str, Any]) -> None:
        if target["root_kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian frontmatter tag proposals require an obsidian_vault source root")
        if Path(str(target["path"] or "")).suffix.lower() not in {".md", ".markdown", ".mdown"}:
            raise SourceRegistryError("Obsidian frontmatter tag proposals require a Markdown note")

    def _ensure_obsidian_frontmatter_tag_write_allowed(self, proposal: dict[str, Any]) -> None:
        if proposal["write_target"] != OBSIDIAN_FRONTMATTER_WRITE_TARGET:
            raise SourceRegistryError("Obsidian frontmatter tag apply requires obsidian_frontmatter write_target")
        if proposal["root_kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian frontmatter tag apply requires an obsidian_vault source root")
        if proposal["permission_mode"] not in {"native_write", "managed"}:
            raise SourceRegistryError("Obsidian frontmatter tag apply requires permission_mode native_write or managed")
        if Path(str(proposal["path"] or "")).suffix.lower() not in {".md", ".markdown", ".mdown"}:
            raise SourceRegistryError("Obsidian frontmatter tag apply requires a Markdown note")

    def _ensure_obsidian_markdown_comment_target(self, target: dict[str, Any]) -> None:
        if target["root_kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian markdown comment proposals require an obsidian_vault source root")
        if Path(str(target["path"] or "")).suffix.lower() not in {".md", ".markdown", ".mdown"}:
            raise SourceRegistryError("Obsidian markdown comment proposals require a Markdown note")

    def _ensure_obsidian_markdown_comment_write_allowed(self, proposal: dict[str, Any]) -> None:
        if proposal["write_target"] != OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET:
            raise SourceRegistryError("Obsidian markdown comment apply requires obsidian_markdown_comment write_target")
        if proposal["root_kind"] != "obsidian_vault":
            raise SourceRegistryError("Obsidian markdown comment apply requires an obsidian_vault source root")
        if proposal["permission_mode"] not in {"native_write", "managed"}:
            raise SourceRegistryError("Obsidian markdown comment apply requires permission_mode native_write or managed")
        if Path(str(proposal["path"] or "")).suffix.lower() not in {".md", ".markdown", ".mdown"}:
            raise SourceRegistryError("Obsidian markdown comment apply requires a Markdown note")

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
            tags = _unique_sorted(_moc_tags_from_metadata(source_ref.metadata) + self._moc_tags_for_target(target))
            projects = _unique_sorted(_moc_projects_from_metadata(source_ref.metadata, path=path, tags=tags))
            targets.append(
                {
                    "path": path,
                    "title": title,
                    "link": _obsidian_wikilink(path, title),
                    "tags": tags,
                    "projects": projects,
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
                            "tags": tags,
                            "projects": projects,
                        },
                    ),
                }
            )
        return targets

    def _moc_tags_for_target(self, target: dict[str, Any]) -> list[str]:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT DISTINCT name
                FROM source_tags
                WHERE root_id = ?
                  AND object_id = ?
                  AND status = 'active'
                ORDER BY name COLLATE NOCASE
                """,
                (target["root_id"], target["object_id"]),
            ).fetchall()
        return [str(row["name"]).strip() for row in rows if str(row["name"] or "").strip()]

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

    def _packets_from_refs(self, refs: list[SourceRef], *, limit: int = 10) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        if limit <= 0:
            return packets
        for ref in refs:
            try:
                target = self._target_for_ref(ref)
                source = self.read_source(_source_ref_from_target(target))
            except SourceRegistryError:
                continue
            packets.append(
                ContextPacket(
                    context_id=f"ctx_collection_{len(packets) + 1}_{target['section_id'] or target['object_id']}",
                    text=source.text[:500],
                    source_ref=source.source_ref,
                    score=1.0,
                    title=target["title"],
                    metadata=dict(source.metadata or {}) | {"collection_materialized_from": "manual_refs"},
                )
            )
            if len(packets) >= limit:
                break
        return packets

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
        path_prefixes: list[str] | None = None,
        object_kinds: list[str] | None = None,
        extraction_statuses: list[str] | None = None,
        limit: int,
    ) -> list[ContextPacket]:
        terms = _query_terms(query)
        rows = self._like_search_rows(
            query,
            root_ids=root_ids,
            kinds=kinds,
            path_prefixes=path_prefixes or [],
            object_kinds=object_kinds or [],
            extraction_statuses=extraction_statuses or [],
            limit=limit,
        )
        return [
            _packet_from_search_row(row, index, query_terms=terms)
            for index, row in enumerate(rows, start=1)
        ]

    def _like_search_rows(
        self,
        query: str,
        *,
        root_ids: list[str],
        kinds: list[str],
        path_prefixes: list[str],
        object_kinds: list[str],
        extraction_statuses: list[str],
        limit: int,
        exclude_section_ids: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        terms = _query_terms(query)
        if not terms or limit <= 0:
            return []
        boost_sql, boost_params = _search_boost_sql(terms)
        where = ["o.status = 'active'"]
        params: list[Any] = boost_params
        if root_ids:
            where.append(f"f.root_id IN ({','.join('?' for _ in root_ids)})")
            params.extend(root_ids)
        if kinds:
            where.append(f"r.kind IN ({','.join('?' for _ in kinds)})")
            params.extend(kinds)
        for prefix in path_prefixes:
            where.append("o.path LIKE ?")
            params.append(f"{prefix.rstrip('/')}%")
        if object_kinds:
            where.append(f"o.kind IN ({','.join('?' for _ in object_kinds)})")
            params.extend(object_kinds)
        if extraction_statuses:
            where.append(f"o.extraction_status IN ({','.join('?' for _ in extraction_statuses)})")
            params.extend(extraction_statuses)
        if exclude_section_ids:
            where.append(f"f.section_id NOT IN ({','.join('?' for _ in exclude_section_ids)})")
            params.extend(exclude_section_ids)
        like_clauses = []
        for term in terms:
            like_clauses.append("(f.title LIKE ? OR f.body LIKE ? OR o.path LIKE ? OR s.heading_path LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%", f"%{term}%", f"%{term}%"])
        where.append("(" + " OR ".join(like_clauses) + ")")
        params.append(limit)
        return self.conn.execute(
            f"""
            SELECT *,
                   lexical_rank - rank_boost AS final_rank
            FROM (
                SELECT f.section_id, f.object_id, f.root_id, f.title AS fts_title,
                       substr(f.body, 1, 260) AS snippet_plain,
                       substr(f.body, 1, 260) AS snippet_highlighted,
                       0.0 AS lexical_rank,
                       {boost_sql} AS rank_boost,
                       o.path, o.title AS object_title, o.kind AS object_kind,
                       o.content_hash, o.extraction_status,
                       s.section_type, s.heading_path, s.line_start, s.line_end,
                       s.title AS section_title,
                       r.kind AS root_kind, r.permission_mode, r.label AS root_label,
                       o.mtime AS object_mtime
                FROM source_fts f
                JOIN source_objects o ON o.object_id = f.object_id
                JOIN source_sections s ON s.section_id = f.section_id
                JOIN source_roots r ON r.root_id = f.root_id
                WHERE {' AND '.join(where)}
            )
            ORDER BY final_rank ASC, rank_boost DESC, object_mtime DESC, path COLLATE NOCASE
            LIMIT ?
            """,
            params,
        ).fetchall()

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

            CREATE TABLE IF NOT EXISTS source_collections (
                collection_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT NOT NULL,
                selector_json TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
                write_target TEXT NOT NULL DEFAULT 'sidecar',
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
        self._ensure_column("source_tags", "write_target", "TEXT NOT NULL DEFAULT 'sidecar'")
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


def _source_collection_payload(row: sqlite3.Row) -> dict[str, Any]:
    source_refs = _json_list(row["source_refs_json"])
    return {
        "collection_id": row["collection_id"],
        "label": row["label"],
        "description": row["description"],
        "selector": _json_dict(row["selector_json"]),
        "source_refs": source_refs,
        "source_ref_count": len(source_refs),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "data_flow": {
            "writes_source_files": False,
            "writes_index": False,
            "embedding_required": False,
        },
    }


def _packet_from_search_row(row: sqlite3.Row, index: int, *, query_terms: list[str] | None = None) -> ContextPacket:
    ref = _source_ref_from_row(row)
    text = str(_row_value(row, "snippet_plain") or _row_value(row, "snippet") or "")
    title = str(row["section_title"] or row["fts_title"] or row["path"])
    lexical_rank = float(_row_value(row, "lexical_rank") or _row_value(row, "rank") or 0.0)
    rank_boost = float(_row_value(row, "rank_boost") or 0.0)
    final_rank = float(_row_value(row, "final_rank") or (lexical_rank - rank_boost))
    match_reason = _search_match_reason(row, query_terms or [])
    return ContextPacket(
        context_id=f"ctx_source_{index}_{row['section_id']}",
        text=text,
        source_ref=ref,
        score=1.0 / (1.0 + abs(final_rank)),
        title=title,
        metadata={
            "source_layer": "personal",
            "rank": final_rank,
            "lexical_rank": lexical_rank,
            "rank_boost": rank_boost,
            "match_reason": match_reason,
            "snippet_plain": text,
            "snippet_highlighted": str(_row_value(row, "snippet_highlighted") or text),
            "root_id": row["root_id"],
            "root_kind": row["root_kind"],
            "path": row["path"],
            "object_title": _row_value(row, "object_title") or "",
            "section_id": row["section_id"],
            "section_title": row["section_title"] or "",
            "heading_path": row["heading_path"] or "",
            "section_type": row["section_type"] or "",
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "extraction_status": row["extraction_status"],
            "embedding_required": False,
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


def _source_ref_from_target(target: dict[str, Any]) -> SourceRef:
    metadata = {
        "source_layer": "personal",
        "root_id": target["root_id"],
        "root_kind": target["root_kind"],
        "root_label": target["root_label"],
        "permission_mode": target["permission_mode"],
        "object_id": target["object_id"],
        "section_id": target["section_id"],
        "path": target["path"],
        "content_hash": target.get("content_hash", ""),
        "section_type": target["section_type"],
        "heading_path": target["heading_path"],
        "line_start": target["line_start"],
        "line_end": target["line_end"],
        "extraction_status": target.get("extraction_status", ""),
        "writes_source_files": False,
    }
    return SourceRef(
        adapter=str(target["root_kind"]),
        document_id=str(target["object_id"]),
        chunk_id=str(target["section_id"] or ""),
        source_id=str(target["section_id"] or target["object_id"]),
        title=str(target["title"] or target["path"]),
        path=str(target["path"]),
        metadata=metadata,
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
        "content_hash": row["content_hash"],
        "extraction_status": row["extraction_status"],
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
            "writes_sidecar": False,
            "write_target": proposal["write_target"],
            "may_write_source_files_on_apply": proposal["write_target"]
            in {
                OBSIDIAN_FRONTMATTER_WRITE_TARGET,
                OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET,
                OBSIDIAN_MOC_WRITE_TARGET,
            },
            "may_write_sidecar_on_apply": proposal["write_target"] == SIDECAR_WRITE_TARGET,
            "requires_native_permission": proposal["write_target"]
            in {
                OBSIDIAN_FRONTMATTER_WRITE_TARGET,
                OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET,
                OBSIDIAN_MOC_WRITE_TARGET,
            },
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
            "write_target": SIDECAR_WRITE_TARGET,
        },
    }


def _applied_tag_result(
    proposal: dict[str, Any],
    record: dict[str, Any],
    *,
    already_applied: bool,
    changed: bool,
) -> dict[str, Any]:
    write_target = str(proposal.get("write_target") or SIDECAR_WRITE_TARGET)
    writes_native = write_target == OBSIDIAN_FRONTMATTER_WRITE_TARGET and bool(changed)
    return {
        "proposal": _action_proposal_payload(proposal),
        "record": to_jsonable(record),
        "applied": True,
        "already_applied": already_applied,
        "data_flow": {
            "writes_source_files": writes_native,
            "writes_original_source_files": writes_native,
            "writes_sidecar": write_target == SIDECAR_WRITE_TARGET and not already_applied,
            "write_target": write_target,
            "requires_native_permission": write_target == OBSIDIAN_FRONTMATTER_WRITE_TARGET,
        },
    }


def _applied_comment_result(
    proposal: dict[str, Any],
    record: dict[str, Any],
    *,
    already_applied: bool,
    changed: bool,
) -> dict[str, Any]:
    write_target = str(proposal.get("write_target") or SIDECAR_WRITE_TARGET)
    writes_native = write_target == OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET and bool(changed)
    return {
        "proposal": _action_proposal_payload(proposal),
        "record": to_jsonable(record),
        "applied": True,
        "already_applied": already_applied,
        "data_flow": {
            "writes_source_files": writes_native,
            "writes_original_source_files": writes_native,
            "writes_sidecar": write_target == SIDECAR_WRITE_TARGET and not already_applied,
            "write_target": write_target,
            "requires_native_permission": write_target == OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET,
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


def _normalize_moc_group_by(group_by: str) -> str:
    value = str(group_by or "none").strip().lower()
    if value in {"", "flat", "link", "links"}:
        return "none"
    if value in MOC_GROUP_BY_MODES:
        return value
    raise SourceRegistryError("Obsidian MOC group_by must be one of none, folder, tag, topic, or project")


def _normalize_tag_write_target(write_target: str) -> str:
    value = str(write_target or SIDECAR_WRITE_TARGET).strip().lower()
    if value in {"", SIDECAR_WRITE_TARGET}:
        return SIDECAR_WRITE_TARGET
    if value in {OBSIDIAN_FRONTMATTER_WRITE_TARGET, "frontmatter", "obsidian_tags"}:
        return OBSIDIAN_FRONTMATTER_WRITE_TARGET
    raise SourceRegistryError("tag write_target must be sidecar or obsidian_frontmatter")


def _normalize_comment_write_target(write_target: str) -> str:
    value = str(write_target or SIDECAR_WRITE_TARGET).strip().lower()
    if value in {"", SIDECAR_WRITE_TARGET}:
        return SIDECAR_WRITE_TARGET
    if value in {OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET, "markdown_comment", "obsidian_comment"}:
        return OBSIDIAN_MARKDOWN_COMMENT_WRITE_TARGET
    raise SourceRegistryError("comment write_target must be sidecar or obsidian_markdown_comment")


def _normalize_collection_selector(selector: dict[str, Any]) -> dict[str, Any]:
    payload = dict(selector or {})
    kind = str(payload.get("kind") or "manual").strip().lower()
    if kind in {"", "refs", "source_refs"}:
        kind = "manual"
    if kind == "saved_search":
        kind = "search"
    if kind not in {"manual", "search"}:
        raise SourceRegistryError("source collection selector kind must be manual or search")
    if kind == "manual":
        return {"kind": "manual"}
    query = str(payload.get("query") or "").strip()
    if not query:
        raise SourceRegistryError("search source collection requires selector.query")
    limit = max(int(payload.get("limit") or 10), 1)
    return {
        "kind": "search",
        "query": query,
        "scope": _normalize_mapping(payload.get("scope")),
        "filters": _normalize_mapping(payload.get("filters")),
        "limit": min(limit, 100),
        "sort": str(payload.get("sort") or "relevance"),
    }


def _search_boost_sql(terms: list[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for term in terms[:8]:
        pattern = f"%{term}%"
        clauses.append("CASE WHEN lower(f.title) LIKE lower(?) THEN 0.70 ELSE 0 END")
        params.append(pattern)
        clauses.append("CASE WHEN lower(o.title) LIKE lower(?) THEN 0.55 ELSE 0 END")
        params.append(pattern)
        clauses.append("CASE WHEN lower(o.path) LIKE lower(?) THEN 0.45 ELSE 0 END")
        params.append(pattern)
        clauses.append("CASE WHEN lower(s.heading_path) LIKE lower(?) THEN 0.35 ELSE 0 END")
        params.append(pattern)
    if not clauses:
        return "0.0", []
    return "(" + " + ".join(clauses) + ")", params


def _search_match_reason(row: sqlite3.Row, terms: list[str]) -> str:
    title = str(_row_value(row, "section_title") or _row_value(row, "fts_title") or "")
    object_title = str(_row_value(row, "object_title") or "")
    path = str(_row_value(row, "path") or "")
    heading = str(_row_value(row, "heading_path") or "")
    haystacks = [
        ("section_title", title),
        ("object_title", object_title),
        ("path", path),
        ("heading_path", heading),
    ]
    for label, value in haystacks:
        if any(term.lower() in value.lower() for term in terms if term):
            return label
    return "body"


def _search_row_sort_key(row: sqlite3.Row) -> tuple[float, float, float, float, str]:
    lexical_rank = float(_row_value(row, "lexical_rank") or _row_value(row, "rank") or 0.0)
    rank_boost = float(_row_value(row, "rank_boost") or 0.0)
    final_rank = float(_row_value(row, "final_rank") or (lexical_rank - rank_boost))
    object_mtime = float(_row_value(row, "object_mtime") or 0.0)
    path = str(_row_value(row, "path") or "")
    return (final_rank, lexical_rank, -rank_boost, -object_mtime, path.lower())


def _row_value(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def _moc_groups(targets: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    normalized = _normalize_moc_group_by(group_by)
    if normalized == "none":
        return [
            {
                "label": "All Sources",
                "key": "all_sources",
                "link_count": len(targets),
                "links": [
                    {"path": target["path"], "title": target["title"], "link": target["link"]}
                    for target in targets
                ],
            }
        ]
    grouped: dict[str, dict[str, Any]] = {}
    for target in targets:
        for label in _moc_group_labels(target, normalized):
            key = _moc_group_key(label)
            group = grouped.setdefault(key, {"label": label, "key": key, "links": []})
            if not any(item["path"] == target["path"] for item in group["links"]):
                group["links"].append({"path": target["path"], "title": target["title"], "link": target["link"]})
    groups = sorted(grouped.values(), key=lambda item: str(item["label"]).lower())
    for group in groups:
        group["links"].sort(key=lambda item: (str(item["path"]).lower(), str(item["title"]).lower()))
        group["link_count"] = len(group["links"])
    return groups


def _moc_group_labels(target: dict[str, Any], group_by: str) -> list[str]:
    path = str(target.get("path") or "")
    if group_by == "folder":
        parent = Path(path).parent.as_posix()
        return [parent if parent not in {"", "."} else "Root"]
    if group_by == "tag":
        tags = [str(item).strip() for item in target.get("tags") or [] if str(item).strip()]
        return tags or ["Untagged"]
    if group_by == "project":
        projects = [str(item).strip() for item in target.get("projects") or [] if str(item).strip()]
        if projects:
            return projects
        parts = [part for part in Path(path).parts if part and part != "."]
        return [parts[0]] if len(parts) > 1 else ["General"]
    if group_by == "topic":
        return [_moc_topic_label(target)]
    return ["All Sources"]


def _moc_group_key(label: str) -> str:
    key = re.sub(r"[^a-z0-9/_-]+", "-", label.strip().lower()).strip("-")
    return key or "untitled"


def _moc_topic_label(target: dict[str, Any]) -> str:
    tags = [str(item).strip() for item in target.get("tags") or [] if str(item).strip()]
    for tag in tags:
        if tag.lower().startswith("topic/"):
            value = tag.split("/", 1)[1].strip()
            if value:
                return value
    title = str(target.get("title") or Path(str(target.get("path") or "")).stem)
    cleaned = re.sub(r"[_-]+", " ", title).strip()
    for separator in (":", "-", "|", " - "):
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
            break
    return cleaned or "General"


def _moc_tags_from_metadata(metadata: dict[str, Any] | None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    values: list[str] = []
    for key in ("tags", "tag", "source_tags", "frontmatter_tags"):
        value = metadata.get(key)
        if isinstance(value, list | tuple | set):
            values.extend(str(item).strip().lstrip("#") for item in value if str(item).strip())
        elif isinstance(value, str):
            text = value.strip()
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1]
            values.extend(item.strip().strip("\"'").lstrip("#") for item in re.split(r"[,\s]+", text) if item.strip())
    return _unique_sorted(values)


def _moc_projects_from_metadata(metadata: dict[str, Any] | None, *, path: str, tags: list[str]) -> list[str]:
    values: list[str] = []
    if isinstance(metadata, dict):
        for key in ("project", "project_id", "projects"):
            value = metadata.get(key)
            if isinstance(value, list | tuple | set):
                values.extend(str(item).strip() for item in value if str(item).strip())
            elif isinstance(value, str) and value.strip():
                values.append(value.strip())
    for tag in tags:
        lowered = tag.lower()
        if lowered.startswith("project/") or lowered.startswith("projects/"):
            value = tag.split("/", 1)[1].strip()
            if value:
                values.append(value)
    if values:
        return _unique_sorted(values)
    parts = [part for part in Path(path).parts if part and part != "."]
    return [parts[0]] if len(parts) > 1 else []


def _unique_sorted(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    output.sort(key=str.lower)
    return output


def _render_moc_block(
    title: str,
    targets: list[dict[str, Any]],
    *,
    group_by: str = "none",
    groups: list[dict[str, Any]] | None = None,
) -> str:
    normalized_group_by = _normalize_moc_group_by(group_by)
    moc_groups = groups if groups is not None else _moc_groups(targets, normalized_group_by)
    lines = [
        PSKA_MOC_BEGIN,
        "## PSKA Source Index",
        "",
        f"Updated: {utc_now_iso()}",
        "",
    ]
    if normalized_group_by == "none":
        for target in targets:
            lines.append(f"- {target['link']}")
    else:
        lines.extend([f"Grouping: {normalized_group_by}", ""])
        for group in moc_groups:
            lines.append(f"### {group['label']}")
            for link in group.get("links") or []:
                lines.append(f"- {link['link']}")
            lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
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


def _upsert_obsidian_markdown_comment_block(
    text: str,
    *,
    body: str,
    comment_id: str,
    path: str,
    heading_path: str,
    line_start: int,
    line_end: int,
    reason: str,
    applied_at: str,
) -> tuple[str, dict[str, Any]]:
    normalized_body = body.strip()
    if not normalized_body:
        raise SourceRegistryError("markdown comment body is required")
    block_marker = f"<!-- PSKA:COMMENT:{comment_id} -->"
    if block_marker in text:
        return text, {
            "block_marker": block_marker,
            "target": _comment_target_payload(path, heading_path, line_start, line_end),
        }
    rendered_block = _render_obsidian_markdown_comment_block(
        body=normalized_body,
        comment_id=comment_id,
        path=path,
        heading_path=heading_path,
        line_start=line_start,
        line_end=line_end,
        reason=reason,
        applied_at=applied_at,
    )
    existing = text.rstrip()
    if not existing:
        updated = f"{rendered_block}\n"
    else:
        updated = f"{existing}\n\n{rendered_block}\n"
    return updated, {
        "block_marker": block_marker,
        "target": _comment_target_payload(path, heading_path, line_start, line_end),
    }


def _render_obsidian_markdown_comment_block(
    *,
    body: str,
    comment_id: str,
    path: str,
    heading_path: str,
    line_start: int,
    line_end: int,
    reason: str,
    applied_at: str,
) -> str:
    block_marker = f"<!-- PSKA:COMMENT:{comment_id} -->"
    target = _comment_target_payload(path, heading_path, line_start, line_end)
    lines = [
        block_marker,
        "> [!note] PSKA Comment",
        f"> Applied: {applied_at}",
        f"> Target: {target['path']}:{target['line_start']}-{target['line_end']}",
    ]
    if target["heading_path"]:
        lines.append(f"> Heading: {target['heading_path']}")
    if reason.strip():
        lines.append(f"> Reason: {reason.strip()}")
    lines.append(">")
    for line in body.splitlines() or [body]:
        lines.append(f"> {line}")
    lines.append(PSKA_COMMENT_END)
    return "\n".join(lines)


def _comment_target_payload(path: str, heading_path: str, line_start: int, line_end: int) -> dict[str, Any]:
    normalized_start = max(int(line_start or 1), 1)
    normalized_end = max(int(line_end or normalized_start), normalized_start)
    return {
        "path": path,
        "heading_path": heading_path,
        "line_start": normalized_start,
        "line_end": normalized_end,
    }


def _upsert_obsidian_frontmatter_tag(text: str, tag: str) -> tuple[str, dict[str, Any]]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        raise SourceRegistryError("frontmatter tag is required")
    frontmatter, body, has_frontmatter = _split_yaml_frontmatter(text)
    lines = frontmatter.splitlines()
    tags, tag_start, tag_end = _frontmatter_tags(lines)
    if tag_start is not None and normalized_tag in tags:
        return text, {
            "tags": tags,
            "created_frontmatter": False,
        }
    if normalized_tag not in tags:
        tags.append(normalized_tag)
    rendered_tags = ["tags:", *[f"  - {item}" for item in tags]]
    if tag_start is None:
        insert_at = _frontmatter_insert_index(lines)
        updated_lines = lines[:insert_at] + rendered_tags + lines[insert_at:]
    else:
        updated_lines = lines[:tag_start] + rendered_tags + lines[tag_end:]
    updated_frontmatter = "\n".join(updated_lines).strip()
    if has_frontmatter:
        updated = f"---\n{updated_frontmatter}\n---\n{body}"
    else:
        updated = f"---\n{updated_frontmatter}\n---\n{text}"
    if text.endswith("\n") and not updated.endswith("\n"):
        updated += "\n"
    return updated, {
        "tags": tags,
        "created_frontmatter": not has_frontmatter,
    }


def _split_yaml_frontmatter(text: str) -> tuple[str, str, bool]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text, False
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "".join(lines[1:index]).rstrip("\r\n")
            body = "".join(lines[index + 1 :])
            return frontmatter, body, True
    return "", text, False


def _frontmatter_tags(lines: list[str]) -> tuple[list[str], int | None, int]:
    for index, line in enumerate(lines):
        match = re.match(r"^tags\s*:\s*(.*)$", line)
        if not match:
            continue
        raw = match.group(1).strip()
        if raw.startswith("[") and raw.endswith("]"):
            tags = [item.strip().strip("\"'") for item in raw[1:-1].split(",") if item.strip()]
            return tags, index, index + 1
        if raw:
            return [item for item in raw.split() if item], index, index + 1
        tags = []
        end = index + 1
        while end < len(lines):
            item = re.match(r"^\s*-\s+(.+?)\s*$", lines[end])
            if not item:
                break
            tags.append(item.group(1).strip().strip("\"'"))
            end += 1
        return [item for item in tags if item], index, end
    return [], None, len(lines)


def _frontmatter_insert_index(lines: list[str]) -> int:
    index = len(lines)
    while index > 0 and not lines[index - 1].strip():
        index -= 1
    return index


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


def _normalize_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_dict(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        decoded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []
