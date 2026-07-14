from __future__ import annotations

import unittest

from pska_essential.workspace_status import build_workspace_status
from pska_essential.workflow import build_fake_service


class _Gateway:
    backend_name = "test"

    def __init__(self, *, ready: bool = True, fail: bool = False) -> None:
        self.ready = ready
        self.fail = fail

    def list_datasets(self, *, name=None, page_size=30):
        if self.fail:
            raise RuntimeError("kb unavailable")
        return [
            {
                "backend": "test",
                "dataset_id": "demo",
                "name": "Demo",
                "document_count": 1,
                "chunk_count": 1 if self.ready else 0,
            }
        ]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": dataset_id,
                "document_id": "doc-1",
                "name": "demo.txt",
                "chunk_count": 1 if self.ready else 0,
                "progress": 1.0 if self.ready else 0.2,
                "progress_msg": "ready" if self.ready else "embedding",
                "run": "DONE" if self.ready else "RUNNING",
                "status": "ready" if self.ready else "processing",
            }
        ]


class WorkspaceStatusTests(unittest.TestCase):
    def test_ready_workspace_suggests_agentic_question(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway())

        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["dataset_count"], 1)
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")

    def test_processing_workspace_suggests_waiting_for_ingestion(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway(ready=False))

        self.assertEqual(status["status"], "processing")
        self.assertEqual(status["kb"]["readiness"]["status"], "processing")
        self.assertEqual(status["next_actions"][0]["action"], "wait_for_ingestion")

    def test_review_and_apply_states_are_next_actions(self):
        service = build_fake_service()
        run = service.start("workspace status review", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember status")
        review = service.review_create(proposal.proposal_id)

        pending = build_workspace_status(service=service, gateway=_Gateway())
        self.assertEqual(pending["status"], "action_required")
        self.assertIn("review_pending_durable_knowledge", [item["action"] for item in pending["next_actions"]])

        service.review_decide(review.review_id, "accept", "approved")
        accepted = build_workspace_status(service=service, gateway=_Gateway())
        actions = [item["action"] for item in accepted["next_actions"]]
        self.assertIn("apply_accepted_memory", actions)
        self.assertEqual(accepted["reviews"]["accepted_unapplied_count"], 1)

    def test_kb_error_is_explicit_next_action(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway(fail=True))

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["kb"]["status"], "error")
        self.assertEqual(status["kb"]["error"]["message"], "kb unavailable")
        self.assertEqual(status["next_actions"][0]["action"], "fix_kb_gateway")


if __name__ == "__main__":
    unittest.main()
