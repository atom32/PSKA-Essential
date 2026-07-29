from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.sqlite import SQLiteMemoryAdapter
from pska_essential.contracts import to_jsonable
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService


def main() -> int:
    try:
        result = run_smoke()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pska-review-memory-") as temp_dir, _patched_env(
        {
            "PSKA_WORKSPACE_ID": "",
            "PSKA_TENANT_ID": "",
            "PSKA_GOVERNANCE_DURABLE_MEMORY": "manual_review",
            "PSKA_GOVERNANCE_CONVERSATION_MEMORY": "manual_review",
        }
    ):
        temp_path = Path(temp_dir)
        memory_db = temp_path / "memory.sqlite3"
        review_db = temp_path / "review.sqlite3"
        service = WorkflowService(
            FakeRetrievalAdapter(),
            SQLiteMemoryAdapter(memory_db),
            SQLiteReviewStore(review_db),
        )
        scope = {"dataset_ids": ["demo"], "memory_namespace": "smoke:review-memory"}

        run = service.start("review memory smoke", scope)
        packets = service.context_retrieve(run.run_id, "PSKA-Essential adapter memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember PSKA review memory smoke")
        review = service.review_create(proposal.proposal_id)
        create_blocked = _apply_is_blocked(service, review.review_id)
        service.review_decide(review.review_id, "accept", "smoke accepted create")
        applied = service.memory_apply(review.review_id)

        _require(not service.memory_search("PSKA-Essential", {}, 10), "scoped memory leaked into default scope")
        facts = service.memory_search("PSKA-Essential", scope, 10)
        _require(len(facts) == 1, "scoped memory was not searchable after accepted create")
        fact = facts[0]

        update_result = service.memory_update_review(
            fact,
            "Current smoke review memory fact.",
            "smoke accepted update",
        )
        update_review_id = str(update_result["review"]["review_id"])
        update_blocked = _apply_is_blocked(service, update_review_id)
        service.review_decide(update_review_id, "accept", "smoke accepted update")
        updated = service.memory_apply(update_review_id)

        _require(not service.memory_search("PSKA-Essential", scope, 10), "old scoped memory text still matched")
        updated_facts = service.memory_search("Current smoke", scope, 10)
        _require(len(updated_facts) == 1, "scoped memory was not searchable after accepted update")

        delete_result = service.memory_delete_review(updated_facts[0], "smoke accepted delete")
        delete_review_id = str(delete_result["review"]["review_id"])
        delete_blocked = _apply_is_blocked(service, delete_review_id)
        service.review_decide(delete_review_id, "accept", "smoke accepted delete")
        deleted = service.memory_apply(delete_review_id)
        _require(not service.memory_search("Current smoke", scope, 10), "scoped memory was not removed after delete")

        _require(create_blocked and update_blocked and delete_blocked, "memory apply was not blocked before review")
        return {
            "ok": True,
            "backend": "sqlite",
            "scope": scope,
            "temp_dir": temp_dir,
            "review_db": str(review_db),
            "memory_db": str(memory_db),
            "context_packets": len(packets),
            "reviews": {
                "create": review.review_id,
                "update": update_review_id,
                "delete": delete_review_id,
            },
            "memory_apply": {
                "create": to_jsonable(applied),
                "update": to_jsonable(updated),
                "delete": to_jsonable(deleted),
            },
            "blocked_before_review": {
                "create": create_blocked,
                "update": update_blocked,
                "delete": delete_blocked,
            },
        }


def _apply_is_blocked(service: WorkflowService, review_id: str) -> bool:
    try:
        service.memory_apply(review_id)
    except WorkflowError as exc:
        return "accepted review" in str(exc)
    return False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@contextmanager
def _patched_env(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
