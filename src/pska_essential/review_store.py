from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pska_essential.contracts import (
    AuditEvent,
    Proposal,
    ReviewBatch,
    ReviewDecision,
    WorkflowRun,
    to_jsonable,
    utc_now_iso,
)
from pska_essential.runtime_context import build_runtime_workspace_context


_SCOPED_TABLES = ("workflows", "proposals", "reviews", "memory_applies", "audit_events")


class SQLiteReviewStore:
    """Minimal local state for workflow, review, and audit.

    This store deliberately does not persist raw documents or build a knowledge
    index. External KB/GraphRAG systems remain the source of knowledge.
    """

    def __init__(self, path: str | Path = ".pska-essential/review.sqlite3") -> None:
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

    def save_workflow(self, workflow: WorkflowRun) -> WorkflowRun:
        scope = _ensure_metadata_scope(workflow.metadata)
        payload = to_jsonable(workflow)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workflows(run_id, payload_json, updated_at, workspace_id, tenant_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET payload_json = excluded.payload_json,
                                                    updated_at = excluded.updated_at,
                                                    workspace_id = excluded.workspace_id,
                                                    tenant_id = excluded.tenant_id
                """,
                (
                    workflow.run_id,
                    json.dumps(payload, ensure_ascii=False),
                    workflow.updated_at,
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()
        return workflow

    def get_workflow(self, run_id: str) -> WorkflowRun:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json
                FROM workflows
                WHERE run_id = ? AND workspace_id = ? AND tenant_id = ?
                """,
                (run_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        if row is None:
            raise KeyError(f"workflow not found: {run_id}")
        return WorkflowRun.from_dict(json.loads(row["payload_json"]))

    def list_workflows(self, *, limit: int = 50) -> list[WorkflowRun]:
        scope = _current_scope_filter()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json
                FROM workflows
                WHERE workspace_id = ? AND tenant_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (scope["workspace_id"], scope["tenant_id"], limit),
            ).fetchall()
        return [WorkflowRun.from_dict(json.loads(row["payload_json"])) for row in rows]

    def save_proposal(self, proposal: Proposal) -> Proposal:
        scope = _ensure_metadata_scope(proposal.metadata, fallback=self._workflow_scope(proposal.run_id))
        payload = to_jsonable(proposal)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO proposals(proposal_id, run_id, kind, payload_json, created_at, workspace_id, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET payload_json = excluded.payload_json,
                                                       workspace_id = excluded.workspace_id,
                                                       tenant_id = excluded.tenant_id
                """,
                (
                    proposal.proposal_id,
                    proposal.run_id,
                    proposal.kind,
                    json.dumps(payload, ensure_ascii=False),
                    proposal.created_at,
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json
                FROM proposals
                WHERE proposal_id = ? AND workspace_id = ? AND tenant_id = ?
                """,
                (proposal_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        if row is None:
            raise KeyError(f"proposal not found: {proposal_id}")
        return Proposal.from_dict(json.loads(row["payload_json"]))

    def create_review(self, proposal_id: str) -> ReviewBatch:
        proposal = self.get_proposal(proposal_id)
        metadata: dict[str, Any] = {}
        scope = _ensure_metadata_scope(metadata, fallback=_scope_from_metadata(proposal.metadata))
        review = ReviewBatch(review_id=f"rev_{proposal_id}", proposal_id=proposal_id, metadata=metadata)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO reviews(review_id, proposal_id, status, decision, reason, payload_json, updated_at, workspace_id, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET status = excluded.status,
                                                    payload_json = excluded.payload_json,
                                                    updated_at = excluded.updated_at,
                                                    workspace_id = excluded.workspace_id,
                                                    tenant_id = excluded.tenant_id
                """,
                (
                    review.review_id,
                    proposal.proposal_id,
                    review.status,
                    "",
                    "",
                    json.dumps(to_jsonable(review), ensure_ascii=False),
                    review.created_at,
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()
        return review

    def get_review(self, review_id: str) -> dict[str, Any]:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT *
                FROM reviews
                WHERE review_id = ? AND workspace_id = ? AND tenant_id = ?
                """,
                (review_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        if row is None:
            raise KeyError(f"review not found: {review_id}")
        return dict(row)

    def list_reviews(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        scope = _current_scope_filter()
        params: list[Any] = [scope["workspace_id"], scope["tenant_id"]]
        where = "WHERE reviews.workspace_id = ? AND reviews.tenant_id = ?"
        if status:
            where += " AND reviews.status = ?"
            params.append(status)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT reviews.review_id,
                       reviews.proposal_id,
                       reviews.status,
                       reviews.decision,
                       reviews.reason,
                       reviews.updated_at,
                       proposals.payload_json AS proposal_json,
                       memory_applies.payload_json AS memory_apply_json
                FROM reviews
                JOIN proposals ON proposals.proposal_id = reviews.proposal_id
                LEFT JOIN memory_applies ON memory_applies.id = (
                    SELECT id
                    FROM memory_applies
                    WHERE memory_applies.review_id = reviews.review_id
                      AND memory_applies.workspace_id = reviews.workspace_id
                      AND memory_applies.tenant_id = reviews.tenant_id
                    ORDER BY id DESC
                    LIMIT 1
                )
                {where}
                ORDER BY reviews.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return self._attach_review_revision_lineage([_review_record_from_row(row) for row in rows])

    def get_review_record(self, review_id: str) -> dict[str, Any]:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT reviews.review_id,
                       reviews.proposal_id,
                       reviews.status,
                       reviews.decision,
                       reviews.reason,
                       reviews.updated_at,
                       proposals.payload_json AS proposal_json,
                       memory_applies.payload_json AS memory_apply_json
                FROM reviews
                JOIN proposals ON proposals.proposal_id = reviews.proposal_id
                LEFT JOIN memory_applies ON memory_applies.id = (
                    SELECT id
                    FROM memory_applies
                    WHERE memory_applies.review_id = reviews.review_id
                      AND memory_applies.workspace_id = reviews.workspace_id
                      AND memory_applies.tenant_id = reviews.tenant_id
                    ORDER BY id DESC
                    LIMIT 1
                )
                WHERE reviews.review_id = ? AND reviews.workspace_id = ? AND reviews.tenant_id = ?
                """,
                (review_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        if row is None:
            raise KeyError(f"review not found: {review_id}")
        return self._attach_review_revision_lineage([_review_record_from_row(row)])[0]

    def decide_review(self, review_id: str, decision: str, reason: str) -> ReviewDecision:
        row = self.get_review(review_id)
        scope = _current_scope_filter()
        normalized = _normalize_decision(decision)
        status = {"accept": "accepted", "reject": "rejected", "edit": "needs_edit"}[normalized]
        decided = ReviewDecision(
            review_id=review_id,
            proposal_id=str(row["proposal_id"]),
            decision=normalized,
            reason=reason,
            status=status,
        )
        with self._lock:
            self._conn.execute(
                """
                UPDATE reviews
                SET status = ?, decision = ?, reason = ?, payload_json = ?, updated_at = ?
                WHERE review_id = ? AND workspace_id = ? AND tenant_id = ?
                """,
                (
                    status,
                    normalized,
                    reason,
                    json.dumps(to_jsonable(decided), ensure_ascii=False),
                    decided.decided_at,
                    review_id,
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()
        return decided

    def save_memory_apply(self, review_id: str, payload: dict[str, Any]) -> None:
        scope = self._review_scope(review_id)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memory_applies(review_id, payload_json, created_at, workspace_id, tenant_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    json.dumps(payload, ensure_ascii=False),
                    utc_now_iso(),
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()

    def get_memory_apply(self, review_id: str) -> dict[str, Any] | None:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json
                FROM memory_applies
                WHERE review_id = ? AND workspace_id = ? AND tenant_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (review_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        scope = _scope_from_metadata(event.metadata)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_events(audit_event_id, action, target_type, target_id, payload_json, created_at, workspace_id, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.audit_event_id,
                    event.action,
                    event.target_type,
                    event.target_id,
                    json.dumps(to_jsonable(event), ensure_ascii=False),
                    event.created_at,
                    scope["workspace_id"],
                    scope["tenant_id"],
                ),
            )
            self._conn.commit()
        return event

    def list_audit_events(
        self,
        *,
        action: str | None = None,
        limit: int | None = None,
        descending: bool = False,
    ) -> list[AuditEvent]:
        scope = _current_scope_filter()
        order = "DESC" if descending else "ASC"
        query = "SELECT payload_json FROM audit_events WHERE workspace_id = ? AND tenant_id = ?"
        params: list[Any] = [scope["workspace_id"], scope["tenant_id"]]
        if action:
            query += " AND action = ?"
            params.append(action)
        query += f" ORDER BY created_at {order}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [AuditEvent(**json.loads(row["payload_json"])) for row in rows]

    def _attach_review_revision_lineage(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not records:
            return records

        by_review_id = {str(record["review_id"]): record for record in records}
        scope = _current_scope_filter()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT target_id, payload_json
                FROM audit_events
                WHERE action = ? AND workspace_id = ? AND tenant_id = ?
                ORDER BY created_at ASC
                """,
                ("review.revise", scope["workspace_id"], scope["tenant_id"]),
            ).fetchall()

        for row in rows:
            event = json.loads(row["payload_json"])
            metadata = event.get("metadata") or {}
            previous_review_id = _nonempty_str(metadata.get("previous_review_id"))
            previous_proposal_id = _nonempty_str(metadata.get("previous_proposal_id"))
            next_review_id = _nonempty_str(event.get("target_id")) or _nonempty_str(row["target_id"])
            next_proposal_id = _nonempty_str(metadata.get("proposal_id"))

            if previous_review_id in by_review_id:
                _merge_revision(
                    by_review_id[previous_review_id],
                    next_review_id=next_review_id,
                    next_proposal_id=next_proposal_id,
                )
            if next_review_id in by_review_id:
                _merge_revision(
                    by_review_id[next_review_id],
                    previous_review_id=previous_review_id,
                    previous_proposal_id=previous_proposal_id,
                )

        return records

    def _workflow_scope(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT workspace_id, tenant_id FROM workflows WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return _scope_from_row(row) if row else None

    def _review_scope(self, review_id: str) -> dict[str, Any]:
        scope = _current_scope_filter()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT workspace_id, tenant_id
                FROM reviews
                WHERE review_id = ? AND workspace_id = ? AND tenant_id = ?
                """,
                (review_id, scope["workspace_id"], scope["tenant_id"]),
            ).fetchone()
        if row is None:
            raise KeyError(f"review not found: {review_id}")
        return _scope_from_row(row)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS memory_applies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    tenant_id TEXT NOT NULL DEFAULT ''
                );
                """
            )
            self._migrate_workspace_columns()
            self._conn.commit()

    def _migrate_workspace_columns(self) -> None:
        for table in _SCOPED_TABLES:
            columns = {
                str(row["name"])
                for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "workspace_id" not in columns:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN workspace_id TEXT")
            if "tenant_id" not in columns:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT")
            self._conn.execute(
                f"UPDATE {table} SET workspace_id = 'default' WHERE workspace_id IS NULL OR workspace_id = ''"
            )
            self._conn.execute(f"UPDATE {table} SET tenant_id = '' WHERE tenant_id IS NULL")
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_workspace_tenant ON {table}(workspace_id, tenant_id)"
            )


def _normalize_decision(decision: str) -> str:
    normalized = decision.strip().lower()
    aliases = {"approved": "accept", "approve": "accept", "accepted": "accept", "yes": "accept"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"accept", "reject", "edit"}:
        raise ValueError("decision must be one of: accept, reject, edit")
    return normalized


def _current_scope_filter() -> dict[str, str]:
    context = build_runtime_workspace_context()
    return {
        "workspace_id": context.workspace_id,
        "tenant_id": context.tenant_id,
    }


def _ensure_metadata_scope(
    metadata: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
) -> dict[str, str]:
    fallback_scope = fallback or _current_scope_filter()
    metadata.setdefault("workspace_id", fallback_scope["workspace_id"])
    metadata.setdefault("tenant_id", fallback_scope["tenant_id"])
    context = build_runtime_workspace_context().to_dict()
    metadata.setdefault("workspace_configured", context["workspace_configured"])
    metadata.setdefault("tenant_configured", context["tenant_configured"])
    return _scope_from_metadata(metadata)


def _scope_from_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    current = _current_scope_filter()
    workspace_id = str(metadata.get("workspace_id") or current["workspace_id"])
    tenant_id = str(metadata.get("tenant_id") if metadata.get("tenant_id") is not None else current["tenant_id"])
    return {
        "workspace_id": workspace_id or "default",
        "tenant_id": tenant_id,
    }


def _scope_from_row(row: sqlite3.Row) -> dict[str, str]:
    return {
        "workspace_id": str(row["workspace_id"] or "default"),
        "tenant_id": str(row["tenant_id"] or ""),
    }


def _nonempty_str(value: Any) -> str:
    return str(value) if value else ""


def _merge_revision(record: dict[str, Any], **fields: str) -> None:
    revision = record.setdefault("revision", {})
    revision.update({key: value for key, value in fields.items() if value})


def _review_record_from_row(row: sqlite3.Row) -> dict[str, Any]:
    proposal = json.loads(row["proposal_json"])
    source_refs = proposal.get("source_refs") or []
    return {
        "review_id": str(row["review_id"]),
        "proposal_id": str(row["proposal_id"]),
        "status": str(row["status"]),
        "decision": str(row["decision"]),
        "reason": str(row["reason"]),
        "updated_at": str(row["updated_at"]),
        "proposal": proposal,
        "source_refs": source_refs,
        "source_count": len(source_refs),
        "memory_apply": json.loads(row["memory_apply_json"]) if row["memory_apply_json"] else None,
    }
