from __future__ import annotations

import unittest

from pska_essential.adapters.company_graphrag_stub import CompanyGraphRagStubAdapter
from pska_essential.component_check import run_component_check
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService


class _ReadyGateway:
    backend_name = "test-kb"

    def list_datasets(self, *, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": "ready",
                "name": "Ready KB",
                "document_count": 1,
                "chunk_count": 1,
            }
        ]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-ready",
                "name": name or "ready.txt",
                "chunk_count": 1,
                "progress": 1.0,
                "run": "DONE",
                "status": "ready",
            }
        ]


class ComponentCheckTests(unittest.TestCase):
    def test_component_check_runs_requested_probes_and_audits(self):
        adapter = CompanyGraphRagStubAdapter()
        service = WorkflowService(adapter, adapter, SQLiteReviewStore(":memory:"))

        result = run_component_check(
            service,
            _ReadyGateway(),
            dataset_ids=["ready"],
            question="Can the configured components complete the loop?",
            require_memory=True,
            run_closed_loop=True,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["diagnostics"]["status"], "ok")
        self.assertEqual(result["memory_probe"]["status"], "ok")
        self.assertEqual(result["retrieval_probe"]["status"], "ok")
        self.assertEqual(result["closed_loop_probe"]["status"], "ok")
        self.assertEqual(
            [step["name"] for step in result["steps"]],
            ["runtime.diagnostics", "memory.probe", "retrieval.probe", "closed_loop.probe"],
        )
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("memory.probe", actions)
        self.assertIn("retrieval.probe", actions)
        self.assertIn("closed_loop.probe", actions)

    def test_component_check_requires_dataset_scope_for_loop_proof(self):
        adapter = CompanyGraphRagStubAdapter()
        service = WorkflowService(adapter, adapter, SQLiteReviewStore(":memory:"))

        result = run_component_check(
            service,
            _ReadyGateway(),
            dataset_ids=[],
            require_memory=False,
            run_closed_loop=True,
        )

        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["retrieval_probe"])
        self.assertIsNone(result["closed_loop_probe"])
        self.assertEqual(result["steps"][-1]["name"], "scope.check")
        self.assertEqual(result["steps"][-1]["status"], "incomplete")
        self.assertEqual(service.store.list_audit_events(), [])


if __name__ == "__main__":
    unittest.main()
