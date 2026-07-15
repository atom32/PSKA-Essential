from __future__ import annotations

import unittest
from unittest.mock import patch

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.graphiti import GraphitiMemoryAdapter
from pska_essential.contracts import MemoryUpdate, Proposal, SourceRef
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workspace_status import build_workspace_status
from pska_essential.workflow import WorkflowService, build_fake_service


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


class _UploadedGateway:
    backend_name = "test"

    def list_datasets(self, *, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": "uploaded",
                "name": "Uploaded",
                "document_count": 1,
                "chunk_count": 0,
            }
        ][:page_size]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": dataset_id,
                "document_id": "doc-uploaded",
                "name": "uploaded.txt",
                "chunk_count": 0,
                "progress": 0.0,
                "progress_msg": "uploaded",
                "run": "UNSTART",
                "status": "uploaded",
            }
        ]


class _MixedUploadedGateway:
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
                "dataset_id": "uploaded",
                "name": "Uploaded",
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
                "progress": 1.0 if dataset_id == "ready" else 0.0,
                "progress_msg": "ready" if dataset_id == "ready" else "uploaded",
                "run": "DONE" if dataset_id == "ready" else "UNSTART",
                "status": "ready" if dataset_id == "ready" else "uploaded",
            }
        ]


class WorkspaceStatusTests(unittest.TestCase):
    def test_ready_workspace_suggests_agentic_question(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway())

        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["capabilities"]["memory"]["operations"]["update"]["supported"])
        self.assertEqual(status["kb"]["dataset_count"], 1)
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertEqual(status["next_actions"][0]["api"], "POST /api/ask")
        self.assertEqual(status["next_actions"][0]["view"], "ask")
        self.assertEqual(status["next_actions"][0]["params"]["dataset_ids"], ["demo"])
        self.assertEqual(status["next_actions"][0]["requires_input"], ["question"])

    def test_workspace_status_exposes_runtime_memory_namespace(self):
        with patch.dict(
            "os.environ",
            {"PSKA_WORKSPACE_ID": "workspace-a", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            status = build_workspace_status(service=build_fake_service(), gateway=_Gateway())

        self.assertEqual(status["workspace"]["workspace_id"], "workspace-a")
        self.assertEqual(status["workspace"]["tenant_id"], "tenant-a")
        self.assertEqual(status["workspace"]["memory_namespace"], "workspace:workspace-a:tenant:tenant-a")

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

    def test_uploaded_workspace_normalizes_parse_next_action(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_UploadedGateway())

        self.assertEqual(status["status"], "action_required")
        self.assertEqual(status["kb"]["readiness"]["ingestion_status"]["next_actions"], ["start_parse"])
        self.assertEqual(status["next_actions"][0]["action"], "parse_documents")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_kb_parse_documents")
        self.assertEqual(status["next_actions"][0]["api"], "POST /api/kb/datasets/{dataset_id}/parse")
        self.assertEqual(status["next_actions"][0]["params"]["dataset_ids"], ["uploaded"])

    def test_mixed_uploaded_workspace_keeps_ready_scope_action_visible(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_MixedUploadedGateway())
        actions = {item["action"]: item for item in status["next_actions"]}

        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["readiness"]["status"], "processing")
        self.assertEqual(actions["run_agentic_question"]["params"]["dataset_ids"], ["ready"])
        self.assertEqual(actions["parse_documents"]["params"]["dataset_ids"], ["uploaded"])

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

    def test_workspace_status_reports_graphiti_memory_capabilities(self):
        service = WorkflowService(
            retrieval=FakeRetrievalAdapter(),
            memory=GraphitiMemoryAdapter(base_url="http://graphiti.local"),
            store=SQLiteReviewStore(":memory:"),
        )

        status = build_workspace_status(service=service, gateway=_Gateway())
        operations = status["capabilities"]["memory"]["operations"]

        self.assertEqual(status["capabilities"]["memory"]["backend"], "graphiti")
        self.assertTrue(operations["apply"]["supported"])
        self.assertFalse(operations["update"]["supported"])
        self.assertIn("transactional fact update", operations["update"]["reason"])
        self.assertTrue(operations["delete"]["supported"])

    def test_workspace_status_does_not_apply_unsupported_accepted_memory_review(self):
        service = WorkflowService(
            retrieval=FakeRetrievalAdapter(),
            memory=GraphitiMemoryAdapter(base_url="http://graphiti.local"),
            store=SQLiteReviewStore(":memory:"),
        )
        run = service.start("historical unsupported update", {"dataset_ids": ["demo"]})
        source_ref = SourceRef(adapter="fake", dataset_id="demo", document_id="doc-1")
        proposal = Proposal(
            proposal_id="prop_unsupported_update",
            run_id=run.run_id,
            kind="memory_update",
            intent="update old memory",
            title="Memory Update",
            body="Historical accepted update",
            source_refs=[source_ref],
            memory_update=MemoryUpdate(
                target_id="edge-1",
                text="updated",
                source_refs=[source_ref],
                previous_text="old",
                reason="historical",
            ),
        )
        service.store.save_proposal(proposal)
        review = service.store.create_review(proposal.proposal_id)
        service.store.decide_review(review.review_id, "accept", "accepted before capability gate")

        status = build_workspace_status(service=service, gateway=_Gateway())
        actions = {item["action"]: item for item in status["next_actions"]}

        self.assertEqual(status["status"], "action_required")
        self.assertEqual(status["reviews"]["accepted_unapplied_count"], 1)
        self.assertNotIn("apply_accepted_memory", actions)
        self.assertEqual(actions["inspect_unsupported_memory_operation"]["params"]["review_id"], review.review_id)
        self.assertEqual(actions["inspect_unsupported_memory_operation"]["params"]["operation"], "update")
        self.assertIn("unsupported", actions["inspect_unsupported_memory_operation"]["reason"])

    def test_kb_error_is_explicit_next_action(self):
        status = build_workspace_status(service=build_fake_service(), gateway=_Gateway(fail=True))

        self.assertEqual(status["status"], "error")
        self.assertEqual(status["kb"]["status"], "error")
        self.assertEqual(status["kb"]["error"]["message"], "kb unavailable")
        self.assertEqual(status["next_actions"][0]["action"], "fix_kb_gateway")
        self.assertEqual(status["next_actions"][0]["view"], "settings")


if __name__ == "__main__":
    unittest.main()
