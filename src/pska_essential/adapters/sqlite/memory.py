from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from pska_essential.contracts import (
    MemoryApplyResult,
    MemoryDelete,
    MemoryFact,
    MemoryPatch,
    MemoryUpdate,
    SourceRef,
    to_jsonable,
    utc_now_iso,
)
from pska_essential.runtime_context import build_runtime_memory_scope


class SQLiteMemoryAdapter:
    """Small durable memory provider for local PSKA runtime.

    The adapter stores reviewed PSKA memory facts only. It is not a document
    store, vector index, graph backend, or review UI.
    """

    backend_name = "sqlite"
    memory_capabilities = {
        "search": True,
        "list": True,
        "get": True,
        "apply": True,
        "update": True,
        "delete": True,
    }

    def __init__(self, path: str | Path = ".pska-essential/memory.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        requested_limit = max(0, int(limit))
        if requested_limit <= 0:
            return []
        search_scope = _runtime_scope(scope)
        terms = _query_terms(query)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT fact_id, text, source_refs_json, valid_at, invalid_at, metadata_json
                FROM memory_facts
                WHERE workspace_id = ? AND tenant_id = ?
                  AND memory_namespace = ?
                  AND (invalid_at IS NULL OR invalid_at = '')
                ORDER BY updated_at DESC, fact_id DESC
                """,
                (
                    search_scope["workspace_id"],
                    search_scope["tenant_id"],
                    search_scope["memory_namespace"],
                ),
            ).fetchall()

        facts = [_fact_from_row(row) for row in rows]
        matches = [_ranked_fact(fact, terms, query) for fact in facts]
        ranked = [item for item in matches if item[0] > 0 or not terms]
        ranked.sort(key=lambda item: (item[0], _fact_recency(item[1]), item[1].fact_id), reverse=True)
        return [fact for _, fact in ranked[:requested_limit]]

    def list_facts(self, scope: dict[str, Any], limit: int, *, include_inactive: bool = False) -> list[MemoryFact]:
        requested_limit = max(0, int(limit))
        if requested_limit <= 0:
            return []
        search_scope = _runtime_scope(scope)
        invalid_filter = "" if include_inactive else "AND (invalid_at IS NULL OR invalid_at = '')"
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT fact_id, text, source_refs_json, valid_at, invalid_at, metadata_json
                FROM memory_facts
                WHERE workspace_id = ? AND tenant_id = ?
                  AND memory_namespace = ?
                  {invalid_filter}
                ORDER BY updated_at DESC, fact_id DESC
                LIMIT ?
                """,
                (
                    search_scope["workspace_id"],
                    search_scope["tenant_id"],
                    search_scope["memory_namespace"],
                    requested_limit,
                ),
            ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def get_fact(self, fact_id: str, scope: dict[str, Any]) -> MemoryFact | None:
        selected = str(fact_id or "").strip()
        if not selected:
            return None
        search_scope = _runtime_scope(scope)
        with self._lock:
            row = self._conn.execute(
                """
                SELECT fact_id, text, source_refs_json, valid_at, invalid_at, metadata_json
                FROM memory_facts
                WHERE fact_id = ?
                  AND workspace_id = ?
                  AND tenant_id = ?
                  AND memory_namespace = ?
                """,
                (
                    selected,
                    search_scope["workspace_id"],
                    search_scope["tenant_id"],
                    search_scope["memory_namespace"],
                ),
            ).fetchone()
        return _fact_from_row(row) if row is not None else None

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        if not reviewed_patch.text.strip():
            raise ValueError("reviewed memory patch requires text")
        if not reviewed_patch.source_refs:
            raise ValueError("reviewed memory patch requires source refs")
        metadata = _memory_metadata(reviewed_patch.metadata)
        metadata.setdefault("layer", reviewed_patch.layer)
        metadata.setdefault("confidence", reviewed_patch.confidence)
        metadata.setdefault("valid_at", metadata.get("applied_at") or utc_now_iso())
        fact_id = f"mem_{uuid4().hex}"
        valid_at = str(metadata.get("valid_at") or utc_now_iso())
        now = utc_now_iso()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memory_facts(
                    fact_id, text, source_refs_json, valid_at, invalid_at, metadata_json,
                    workspace_id, tenant_id, memory_namespace, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    reviewed_patch.text,
                    _json(reviewed_patch.source_refs),
                    valid_at,
                    "",
                    _json(metadata),
                    metadata["workspace_id"],
                    metadata["tenant_id"],
                    metadata["memory_namespace"],
                    str(metadata.get("created_at") or now),
                    now,
                ),
            )
            self._conn.commit()

        return MemoryApplyResult(
            applied=True,
            target_id=fact_id,
            backend=self.backend_name,
            message="SQLite memory fact applied",
            metadata={"operation": "apply"},
        )

    def update(self, reviewed_update: MemoryUpdate) -> MemoryApplyResult:
        if not reviewed_update.target_id:
            raise ValueError("reviewed memory update requires target_id")
        if not reviewed_update.text.strip():
            raise ValueError("reviewed memory update requires text")
        if not reviewed_update.source_refs:
            raise ValueError("reviewed memory update requires source refs")
        metadata = _memory_metadata(reviewed_update.metadata)
        with self._lock:
            row = self._fact_row_for_update(reviewed_update.target_id, metadata)
            previous = _fact_from_row(row)
            previous_metadata = dict(previous.metadata)
            version = int(previous_metadata.get("version") or 1) + 1
            versions = list(previous_metadata.get("versions") or [])
            versions.append(
                {
                    "version": version - 1,
                    "text": previous.text,
                    "updated_at": utc_now_iso(),
                    "reason": reviewed_update.reason,
                }
            )
            updated_metadata = {
                **previous_metadata,
                **metadata,
                "update_reason": reviewed_update.reason,
                "version": version,
                "versions": versions,
                "previous_text": reviewed_update.previous_text or previous.text,
                "display_text": reviewed_update.text,
                "current_text": reviewed_update.text,
                "canonical_text": reviewed_update.text,
            }
            now = utc_now_iso()
            self._conn.execute(
                """
                INSERT INTO memory_versions(
                    fact_id, version, text, source_refs_json, metadata_json, reason,
                    created_at, workspace_id, tenant_id, memory_namespace
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reviewed_update.target_id,
                    version - 1,
                    previous.text,
                    _json(previous.source_refs),
                    _json(previous_metadata),
                    reviewed_update.reason,
                    now,
                    metadata["workspace_id"],
                    metadata["tenant_id"],
                    metadata["memory_namespace"],
                ),
            )
            self._conn.execute(
                """
                UPDATE memory_facts
                SET text = ?,
                    source_refs_json = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE fact_id = ?
                  AND workspace_id = ?
                  AND tenant_id = ?
                  AND memory_namespace = ?
                """,
                (
                    reviewed_update.text,
                    _json(reviewed_update.source_refs),
                    _json(updated_metadata),
                    now,
                    reviewed_update.target_id,
                    metadata["workspace_id"],
                    metadata["tenant_id"],
                    metadata["memory_namespace"],
                ),
            )
            self._conn.commit()

        return MemoryApplyResult(
            applied=True,
            target_id=reviewed_update.target_id,
            backend=self.backend_name,
            message="SQLite memory fact updated",
            metadata={"operation": "update", "version": version, "previous_text": previous.text},
        )

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        if not reviewed_delete.target_id:
            raise ValueError("reviewed memory delete requires target_id")
        if not reviewed_delete.source_refs:
            raise ValueError("reviewed memory delete requires source refs")
        metadata = _memory_metadata(reviewed_delete.metadata)
        with self._lock:
            row = self._fact_row_for_update(reviewed_delete.target_id, metadata)
            previous = _fact_from_row(row)
            updated_metadata = {
                **previous.metadata,
                **metadata,
                "delete_reason": reviewed_delete.reason,
            }
            invalid_at = utc_now_iso()
            self._conn.execute(
                """
                UPDATE memory_facts
                SET invalid_at = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE fact_id = ?
                  AND workspace_id = ?
                  AND tenant_id = ?
                  AND memory_namespace = ?
                """,
                (
                    invalid_at,
                    _json(updated_metadata),
                    invalid_at,
                    reviewed_delete.target_id,
                    metadata["workspace_id"],
                    metadata["tenant_id"],
                    metadata["memory_namespace"],
                ),
            )
            self._conn.commit()

        return MemoryApplyResult(
            applied=True,
            target_id=reviewed_delete.target_id,
            backend=self.backend_name,
            message="SQLite memory fact deactivated",
            metadata={"operation": "delete"},
        )

    def _fact_row_for_update(self, fact_id: str, metadata: dict[str, Any]) -> sqlite3.Row:
        row = self._conn.execute(
            """
            SELECT fact_id, text, source_refs_json, valid_at, invalid_at, metadata_json
            FROM memory_facts
            WHERE fact_id = ?
              AND workspace_id = ?
              AND tenant_id = ?
              AND memory_namespace = ?
              AND (invalid_at IS NULL OR invalid_at = '')
            """,
            (
                fact_id,
                metadata["workspace_id"],
                metadata["tenant_id"],
                metadata["memory_namespace"],
            ),
        ).fetchone()
        if row is None:
            raise ValueError(f"memory fact not found: {fact_id}")
        return row

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    fact_id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    valid_at TEXT,
                    invalid_at TEXT,
                    metadata_json TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT '',
                    memory_namespace TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT '',
                    memory_namespace TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_memory_facts_scope
                    ON memory_facts(workspace_id, tenant_id, memory_namespace, invalid_at);
                CREATE INDEX IF NOT EXISTS idx_memory_versions_fact_scope
                    ON memory_versions(fact_id, workspace_id, tenant_id, memory_namespace);
                """
            )
            self._conn.commit()


def _runtime_scope(scope: dict[str, Any]) -> dict[str, str]:
    runtime_scope = build_runtime_memory_scope(scope)
    return {
        "workspace_id": str(runtime_scope.get("workspace_id") or "default"),
        "tenant_id": str(runtime_scope.get("tenant_id") or ""),
        "memory_namespace": str(runtime_scope.get("memory_namespace") or ""),
    }


def _memory_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    scoped = build_runtime_memory_scope(metadata)
    payload = dict(scoped)
    payload["workspace_id"] = str(payload.get("workspace_id") or "default")
    payload["tenant_id"] = str(payload.get("tenant_id") or "")
    payload["memory_namespace"] = str(payload.get("memory_namespace") or "")
    payload.setdefault("created_at", utc_now_iso())
    payload.setdefault("updated_at", utc_now_iso())
    return payload


def _fact_from_row(row: sqlite3.Row) -> MemoryFact:
    metadata = json.loads(row["metadata_json"])
    return MemoryFact(
        fact_id=str(row["fact_id"]),
        text=str(row["text"]),
        source_refs=[SourceRef.from_dict(item) for item in json.loads(row["source_refs_json"])],
        valid_at=str(row["valid_at"] or "") or None,
        invalid_at=str(row["invalid_at"] or "") or None,
        metadata=metadata,
    )


def _ranked_fact(fact: MemoryFact, terms: list[str], raw_query: str) -> tuple[float, MemoryFact]:
    haystack = _search_text(fact)
    if not terms:
        return 1.0, fact
    score = sum(1.0 for term in terms if term in haystack)
    compact_query = raw_query.strip().casefold()
    if compact_query and compact_query in haystack:
        score += 2.0
    return score, fact


def _search_text(fact: MemoryFact) -> str:
    metadata = fact.metadata or {}
    parts = [
        fact.text,
        str(metadata.get("display_text") or ""),
        str(metadata.get("current_text") or ""),
        str(metadata.get("canonical_text") or ""),
    ]
    return "\n".join(parts).casefold()


def _fact_recency(fact: MemoryFact) -> str:
    metadata = fact.metadata or {}
    for key in ("updated_at", "applied_at", "created_at", "observed_at"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return fact.valid_at or ""


def _query_terms(query: str) -> list[str]:
    normalized = query.strip().casefold()
    if not normalized:
        return []
    words = re.findall(r"[0-9a-z_][0-9a-z_-]{1,}", normalized)
    cjk = re.findall(r"[\u3400-\u9fff]{2,}", normalized)
    terms = [*words, *cjk]
    if terms:
        return _unique_terms(terms)
    return [normalized]


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique


def _json(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)
