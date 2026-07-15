from __future__ import annotations

import unittest
from types import SimpleNamespace

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.contracts import ContextPacket, SourceContext, SourceRef
from pska_essential.diagnostics import (
    add_live_closed_loop_probe_audit,
    add_memory_probe_audit,
    add_retrieval_probe_audit,
    build_runtime_diagnostics,
    run_live_closed_loop_probe,
    run_memory_probe,
    run_retrieval_probe,
)
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


class _BrokenRetrieval:
    backend_name = "ragflow"

    def retrieve(self, query, scope, limit, options=None):
        raise RuntimeError("LookupError('Provider xxxx not found for model bge-m3@xxxx.')")


class _BrokenReadinessGateway:
    backend_name = "test-kb"

    def list_datasets(self, *, name=None, page_size=30):
        raise RuntimeError("KB list failed")


class _BrokenMemory:
    backend_name = "graphiti"

    def search(self, query, scope, limit):
        raise RuntimeError("Graphiti HTTP POST /search failed: 500 Internal Server Error")


class _LiveRetrieval:
    backend_name = "live-test"

    def retrieve(self, query, scope, limit, options=None):
        source_ref = SourceRef(
            adapter=self.backend_name,
            dataset_id="ready",
            document_id="doc-ready",
            chunk_id="chunk-ready",
            title="Ready Source",
            metadata={"content_excerpt": "Ready live source says PSKA can produce a sourced work product."},
        )
        return [
            ContextPacket(
                context_id="ctx-live-ready",
                text="Ready live source says PSKA can produce a sourced work product.",
                source_ref=source_ref,
                score=0.91,
                title="Ready Source",
            )
        ][:limit]

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text=str(source_ref.metadata.get("content_excerpt") or ""))


class DiagnosticsTests(unittest.TestCase):
    def test_runtime_diagnostics_checks_memory_search_without_search_audit(self):
        service = WorkflowService(_LiveRetrieval(), _BrokenMemory(), SQLiteReviewStore(":memory:"))

        diagnostics = build_runtime_diagnostics(
            service=service,
            kb_gateway_factory=lambda: _ReadyGateway(),
        )

        checks = {item["name"]: item for item in diagnostics["checks"]}
        self.assertEqual(diagnostics["status"], "error")
        self.assertEqual(checks["memory_search_contract"]["status"], "error")
        self.assertTrue(checks["memory_search_contract"]["metadata"]["semantic_checked"])
        self.assertEqual(checks["memory_search_contract"]["metadata"]["provider"], "graphiti")
        self.assertIn("LLM or embedding provider", checks["memory_search_contract"]["message"])
        self.assertEqual(service.store.list_audit_events(action="memory.search"), [])

    def test_memory_probe_rejects_fake_as_live_proof(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_memory_probe(service, query="probe memory")

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertEqual(probe["provider"], "fake")
        self.assertEqual(probe["memory_count"], 0)

    def test_memory_probe_reports_provider_errors_and_audits(self):
        service = WorkflowService(_LiveRetrieval(), _BrokenMemory(), SQLiteReviewStore(":memory:"))

        probe = run_memory_probe(service, query="probe graphiti")
        add_memory_probe_audit(service.store, probe)

        self.assertEqual(probe["status"], "error")
        self.assertEqual(probe["provider"], "graphiti")
        self.assertIn("LLM or embedding provider", probe["message"])
        event = service.store.list_audit_events(action="memory.probe", limit=1)[0]
        self.assertEqual(event.metadata["status"], "error")
        self.assertEqual(event.metadata["error_type"], "RuntimeError")

    def test_retrieval_probe_surfaces_model_provider_errors_and_audits(self):
        service = SimpleNamespace(retrieval=_BrokenRetrieval())
        store = SQLiteReviewStore(":memory:")

        probe = run_retrieval_probe(
            service,
            _ReadyGateway(),
            question="probe",
            dataset_ids=["ready"],
            limit=1,
        )
        add_retrieval_probe_audit(store, probe)

        self.assertEqual(probe["status"], "error")
        self.assertEqual(probe["provider"], "ragflow")
        self.assertIn("model-provider configuration", probe["message"])
        event = store.list_audit_events(action="retrieval.probe", limit=1)[0]
        self.assertEqual(event.metadata["status"], "error")
        self.assertEqual(event.metadata["error_type"], "RuntimeError")
        self.assertIn("bge-m3", event.metadata["error_message"])

    def test_retrieval_probe_resolves_dataset_names(self):
        service = SimpleNamespace(retrieval=_LiveRetrieval())

        probe = run_retrieval_probe(
            service,
            _ReadyGateway(),
            question="probe by name",
            dataset_ids=[],
            dataset_names=["Ready KB"],
            limit=1,
        )

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["scope"]["dataset_ids"], ["ready"])
        self.assertEqual(probe["scope"]["resolved_dataset_names"], [{"name": "Ready KB", "dataset_id": "ready"}])

    def test_retrieval_probe_reports_readiness_errors_without_traceback(self):
        service = SimpleNamespace(retrieval=_LiveRetrieval())

        probe = run_retrieval_probe(
            service,
            _BrokenReadinessGateway(),
            question="probe readiness",
            dataset_ids=["ready"],
            limit=1,
        )

        self.assertEqual(probe["status"], "readiness_error")
        self.assertEqual(probe["context_count"], 0)
        self.assertEqual(probe["error"]["type"], "RuntimeError")
        self.assertIn("KB list failed", probe["message"])

    def test_live_closed_loop_probe_reports_readiness_errors_without_traceback(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_live_closed_loop_probe(
            service,
            _BrokenReadinessGateway(),
            question="probe live readiness",
            dataset_ids=["ready"],
        )

        self.assertEqual(probe["status"], "readiness_error")
        self.assertEqual(probe["context_count"], 0)
        self.assertEqual(probe["steps"][-1]["name"], "kb.readiness")
        self.assertIn("KB list failed", probe["message"])

    def test_live_closed_loop_probe_runs_ready_non_fake_workflow_and_audits(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_live_closed_loop_probe(
            service,
            _ReadyGateway(),
            question="Can PSKA produce a sourced work product?",
            dataset_ids=["ready"],
            limit=1,
        )
        add_live_closed_loop_probe_audit(service.store, probe)

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["providers"]["kb"], "test-kb")
        self.assertEqual(probe["providers"]["retrieval"], "live-test")
        self.assertEqual(probe["readiness"]["status"], "ready")
        self.assertEqual(probe["retrieval_probe"]["status"], "ok")
        self.assertEqual(probe["ask"]["status"], "ready")
        self.assertEqual(probe["context_count"], 1)
        self.assertEqual(probe["source_count"], 1)
        self.assertEqual(probe["source_inspection_count"], 1)
        self.assertTrue(probe["export"]["exported"])
        self.assertEqual(probe["export"]["source_count"], 1)
        event = service.store.list_audit_events(action="closed_loop.probe", limit=1)[0]
        self.assertEqual(event.metadata["status"], "ok")
        self.assertEqual(event.metadata["exported"], True)
        self.assertEqual(event.metadata["source_count"], 1)
        self.assertEqual(event.metadata["source_inspection_count"], 1)
        self.assertEqual(event.target_id, probe["run_id"])

    def test_live_closed_loop_probe_resolves_dataset_names(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_live_closed_loop_probe(
            service,
            _ReadyGateway(),
            question="Can PSKA run by KB name?",
            dataset_ids=[],
            dataset_names=["Ready KB"],
            limit=1,
        )

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["scope"]["dataset_ids"], ["ready"])
        self.assertEqual(probe["scope"]["resolved_dataset_names"], [{"name": "Ready KB", "dataset_id": "ready"}])

    def test_live_closed_loop_probe_reports_unresolved_dataset_names(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_live_closed_loop_probe(
            service,
            _ReadyGateway(),
            question="Missing scope",
            dataset_ids=[],
            dataset_names=["Missing KB"],
            limit=1,
        )

        self.assertEqual(probe["status"], "incomplete")
        self.assertEqual(probe["scope"]["unresolved_dataset_names"], ["Missing KB"])
        self.assertEqual(probe["steps"][0]["name"], "scope.check")
        self.assertEqual(probe["context_count"], 0)

    def test_live_closed_loop_probe_rejects_fake_kb_or_retrieval(self):
        service = WorkflowService(FakeRetrievalAdapter(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))
        gateway = SimpleNamespace(backend_name="fake")

        probe = run_live_closed_loop_probe(
            service,
            gateway,
            question="This should not count as live",
            dataset_ids=["demo"],
        )

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertIn("fake", probe["message"].lower())
        self.assertEqual(probe["context_count"], 0)
        self.assertEqual(probe["steps"][0]["name"], "provider.check")

    def test_live_closed_loop_probe_rejects_durable_proposal_kind(self):
        service = WorkflowService(_LiveRetrieval(), FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))

        probe = run_live_closed_loop_probe(
            service,
            _ReadyGateway(),
            question="Do not write memory from diagnostics",
            dataset_ids=["ready"],
            proposal_kind="memory_patch",
        )

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertIn("transient", probe["message"])
        self.assertEqual(probe["steps"][0]["name"], "governance.check")
        self.assertEqual(service.store.list_reviews(), [])


if __name__ == "__main__":
    unittest.main()
