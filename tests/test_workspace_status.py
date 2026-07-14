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


class _MixedGateway:
    backend_name = "test"

    def list_datasets(self, *, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": "ready",
                "name": "Ready",
                "document_count": 1,
                "chunk_count": 1,
            },
            {
                "backend": "test",
                "dataset_id": "processing",
                "name": "Processing",
                "document_count": 1,
                "chunk_count": 0,
            },
        ][:page_size]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": dataset_id,
                "document_id": f"doc-{dataset_id}",
                "name": f"{dataset_id}.txt",
                "chunk_count": 1 if dataset_id == "ready" else 0,
                "progress": 1.0 if dataset_id == "ready" else 0.2,
                "progress_msg": "ready" if dataset_id == "ready" else "embedding",
                "run": "DONE" if dataset_id == "ready" else "RUNNING",
                "status": "ready" if dataset_id == "ready" else "processing",
            }
        ]


class WorkspaceStatusTests(unittest.TestCase):
    def test_ready_workspace_suggests_agentic_question(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway())

        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["dataset_count"], 1)
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertEqual(status["next_actions"][0]["api"], "POST /api/ask")
        self.assertEqual(status["next_actions"][0]["view"], "ask")
        self.assertEqual(status["next_actions"][0]["params"]["dataset_ids"], ["demo"])
        self.assertEqual(status["next_actions"][0]["requires_input"], ["question"])

    def test_mixed_workspace_keeps_ready_scope_action_visible(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_MixedGateway())
        actions = {item["action"]: item for item in status["next_actions"]}

        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["readiness"]["status"], "processing")
        self.assertEqual(len(status["kb"]["dataset_readiness"]), 2)
        self.assertEqual(actions["run_agentic_question"]["params"]["dataset_ids"], ["ready"])
        self.assertEqual(actions["wait_for_ingestion"]["params"]["dataset_ids"], ["processing"])

    def test_processing_workspace_suggests_waiting_for_ingestion(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway(ready=False))

        self.assertEqual(status["status"], "processing")
        self.assertEqual(status["kb"]["readiness"]["status"], "processing")
        self.assertEqual(status["next_actions"][0]["action"], "wait_for_ingestion")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_kb_ingestion_status")
        self.assertEqual(status["next_actions"][0]["view"], "kb")

    def test_review_and_apply_states_are_next_actions(self):
        service = build_fake_service()
        run = service.start("workspace status review", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember status")
        review = service.review_create(proposal.proposal_id)

        pending = build_workspace_status(service=service, gateway=_Gateway())
        self.assertEqual(pending["status"], "action_required")
        self.assertIn("review_pending_durable_knowledge", [item["action"] for item in pending["next_actions"]])
        review_action = next(item for item in pending["next_actions"] if item["action"] == "review_pending_durable_knowledge")
        self.assertEqual(review_action["tool"], "pska_review_get")
        self.assertEqual(review_action["params"]["review_id"], review.review_id)

        service.review_decide(review.review_id, "accept", "approved")
        accepted = build_workspace_status(service=service, gateway=_Gateway())
        actions = [item["action"] for item in accepted["next_actions"]]
        self.assertIn("apply_accepted_memory", actions)
        self.assertEqual(accepted["reviews"]["accepted_unapplied_count"], 1)
        apply_action = next(item for item in accepted["next_actions"] if item["action"] == "apply_accepted_memory")
        self.assertEqual(apply_action["tool"], "pska_memory_apply")
        self.assertEqual(apply_action["params"]["review_id"], review.review_id)

    def test_kb_error_is_explicit_next_action(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway(fail=True))

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["kb"]["status"], "error")
        self.assertEqual(status["kb"]["error"]["message"], "kb unavailable")
        self.assertEqual(status["next_actions"][0]["action"], "fix_kb_gateway")
        self.assertEqual(status["next_actions"][0]["view"], "settings")


if __name__ == "__main__":
    unittest.main()
