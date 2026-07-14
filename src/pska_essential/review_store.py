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
        payload = to_jsonable(workflow)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO workflows(run_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET payload_json = excluded.payload_json,
                                                    updated_at = excluded.updated_at
                """,
                (workflow.run_id, json.dumps(payload, ensure_ascii=False), workflow.updated_at),
            )
            self._conn.commit()
        return workflow

    def get_workflow(self, run_id: str) -> WorkflowRun:
        with self._lock:
            row = self._conn.execute("SELECT payload_json FROM workflows WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"workflow not found: {run_id}")
        return WorkflowRun.from_dict(json.loads(row["payload_json"]))

    def list_workflows(self, *, limit: int = 50) -> list[WorkflowRun]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM workflows ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [WorkflowRun.from_dict(json.loads(row["payload_json"])) for row in rows]

    def save_proposal(self, proposal: Proposal) -> Proposal:
        payload = to_jsonable(proposal)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO proposals(proposal_id, run_id, kind, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (
                    proposal.proposal_id,
                    proposal.run_id,
                    proposal.kind,
                    json.dumps(payload, ensure_ascii=False),
                    proposal.created_at,
                ),
            )
            self._conn.commit()
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"proposal not found: {proposal_id}")
        return Proposal.from_dict(json.loads(row["payload_json"]))

    def create_review(self, proposal_id: str) -> ReviewBatch:
        proposal = self.get_proposal(proposal_id)
        review = ReviewBatch(review_id=f"rev_{proposal_id}", proposal_id=proposal_id)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO reviews(review_id, proposal_id, status, decision, reason, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET status = excluded.status,
                                                    payload_json = excluded.payload_json,
                                                    updated_at = excluded.updated_at
                """,
                (
                    review.review_id,
                    proposal.proposal_id,
                    review.status,
                    "",
                    "",
                    json.dumps(to_jsonable(review), ensure_ascii=False),
                    review.created_at,
                ),
            )
            self._conn.commit()
        return review

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM reviews WHERE review_id = ?", (review_id,)).fetchone()
        if row is None:
            raise KeyError(f"review not found: {review_id}")
        return dict(row)

    def list_reviews(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if status:
            where = "WHERE reviews.status = ?"
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
                    ORDER BY id DESC
                    LIMIT 1
                )
                {where}
                ORDER BY reviews.updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "review_id": str(row["review_id"]),
                "proposal_id": str(row["proposal_id"]),
                "status": str(row["status"]),
                "decision": str(row["decision"]),
                "reason": str(row["reason"]),
                "updated_at": str(row["updated_at"]),
                "proposal": json.loads(row["proposal_json"]),
                "memory_apply": json.loads(row["memory_apply_json"]) if row["memory_apply_json"] else None,
            }
            for row in rows
        ]

    def decide_review(self, review_id: str, decision: str, reason: str) -> ReviewDecision:
        row = self.get_review(review_id)
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
                WHERE review_id = ?
                """,
                (
                    status,
                    normalized,
                    reason,
                    json.dumps(to_jsonable(decided), ensure_ascii=False),
                    decided.decided_at,
                    review_id,
                ),
            )
            self._conn.commit()
        return decided

    def save_memory_apply(self, review_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory_applies(review_id, payload_json, created_at) VALUES (?, ?, ?)",
                (review_id, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
            )
            self._conn.commit()

    def get_memory_apply(self, review_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json
                FROM memory_applies
                WHERE review_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (review_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit_events(audit_event_id, action, target_type, target_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.audit_event_id,
                    event.action,
                    event.target_type,
                    event.target_id,
                    json.dumps(to_jsonable(event), ensure_ascii=False),
                    event.created_at,
                ),
            )
            self._conn.commit()
        return event

    def list_audit_events(self) -> list[AuditEvent]:
        with self._lock:
            rows = self._conn.execute("SELECT payload_json FROM audit_events ORDER BY created_at").fetchall()
        return [AuditEvent(**json.loads(row["payload_json"])) for row in rows]

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_applies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_event_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()


def _normalize_decision(decision: str) -> str:
    normalized = decision.strip().lower()
    aliases = {"approved": "accept", "approve": "accept", "accepted": "accept", "yes": "accept"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"accept", "reject", "edit"}:
        raise ValueError("decision must be one of: accept, reject, edit")
    return normalized
