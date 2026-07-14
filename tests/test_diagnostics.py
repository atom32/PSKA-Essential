from __future__ import annotations

import unittest
from types import SimpleNamespace

from pska_essential.diagnostics import add_retrieval_probe_audit, run_retrieval_probe
from pska_essential.review_store import SQLiteReviewStore


class _ReadyGateway:
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


class DiagnosticsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
