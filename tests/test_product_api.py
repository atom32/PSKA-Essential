from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pska_essential.product_api import build_server
from pska_essential.workflow import build_fake_service


class _FakeGateway:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, str]] = []
        self.parse_calls: list[dict[str, object]] = []
        self.ready = True

    def list_datasets(self, *, name=None, page_size=30):
        datasets = [
            {
                "backend": "fake-kb",
                "dataset_id": "demo",
                "name": "Demo",
                "document_count": 1,
                "chunk_count": 2 if self.ready else 0,
            }
        ]
        if name:
            return [item for item in datasets if item["name"] == name]
        return datasets

    def create_dataset(self, *, name, description="", chunk_method="naive"):
        return {
            "backend": "fake-kb",
            "dataset_id": "created",
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
        }

    def ingest_files(
        self,
        *,
        file_paths,
        dataset_name=None,
        dataset_id=None,
        description="",
        chunk_method="naive",
        parse=True,
        wait=False,
        timeout_seconds=300.0,
    ):
        self.uploaded = [
            {"name": Path(path).name, "text": Path(path).read_text(encoding="utf-8")} for path in file_paths
        ]
        return {
            "backend": "fake-kb",
            "dataset_created": not bool(dataset_id),
            "dataset": {"dataset_id": dataset_id or "created", "name": dataset_name or "Existing"},
            "documents": [
                {
                    "dataset_id": dataset_id or "created",
                    "document_id": "doc-1",
                    "name": self.uploaded[0]["name"],
                    "progress": 0.0,
                    "run": "UNSTART",
                }
            ],
            "parse": {"parse_started": bool(parse)},
        }

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "fake-kb",
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "note.txt",
                "chunk_count": 1 if self.ready else 0,
                "progress": 1.0 if self.ready else 0.1,
                "run": "DONE" if self.ready else "RUNNING",
            }
        ]

    def parse_documents(self, *, dataset_id, document_ids, wait=False, timeout_seconds=300.0):
        self.parse_calls.append({"dataset_id": dataset_id, "document_ids": document_ids, "wait": wait})
        return {"backend": "fake-kb", "dataset_id": dataset_id, "document_ids": document_ids, "parse_started": True}

    def document_graph(self, *, dataset_id, document_id):
        return {
            "backend": "fake-kb",
            "dataset_id": dataset_id,
            "document_id": document_id,
            "templates": [{"name": "demo-structure", "nodes": [], "edges": []}],
            "note": "Fake graph for Product API tests.",
        }


class ProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"PSKA_WORKSPACE_ID": "", "PSKA_TENANT_ID": ""}, clear=False)
        self.env_patch.start()
        self.gateway = _FakeGateway()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=build_fake_service(),
            kb_gateway_factory=lambda: self.gateway,
            static_dir=self.static_dir.name,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.static_dir.cleanup()
        self.env_patch.stop()

    def test_static_health_ask_review_and_apply_loop(self):
        html = self._get_text("/")
        self.assertIn("PSKA", html)
        health = self._get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["governance"]["durable_memory"], "manual_review")
        self.assertEqual(health["workspace"]["workspace_id"], "default")
        self.assertFalse(health["workspace"]["workspace_configured"])

        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern memory?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertEqual(
            [step["name"] for step in asked["loop"]["steps"][:3]],
            ["scope.check", "governance.policy", "kb.readiness"],
        )
        review_id = asked["review"]["review_id"]
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(asked["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        source = self._post_json("/api/sources/read", {"source_ref": asked["context_packets"][0]["source_ref"]})
        self.assertIn("PSKA-Essential", source["source"]["text"])
        source_audit = self._get_json("/api/audit?limit=10&action=source.read")
        self.assertEqual(source_audit["events"][0]["action"], "source.read")
        self.assertEqual(source_audit["events"][0]["metadata"]["adapter"], "fake")
        self.assertEqual(
            source_audit["events"][0]["metadata"]["document_id"],
            asked["context_packets"][0]["source_ref"]["document_id"],
        )
        workflows = self._get_json("/api/workflows?limit=5")
        self.assertEqual(workflows["workflows"][0]["run_id"], asked["run"]["run_id"])
        self.assertEqual(workflows["workflows"][0]["metadata"]["agentic_loop"]["review_id"], review_id)
        opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        exported = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("## Source Manifest", exported["export"])
        exported_json = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=json")
        self.assertEqual(exported_json["export"]["traceability"]["context_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["source_count"], 1)
        self.assertEqual(exported_json["export"]["latest_proposal"]["kind"], "memory_patch")

        reviews = self._get_json("/api/reviews?status=pending")
        self.assertEqual(reviews["reviews"][0]["review_id"], review_id)
        review_record = self._get_json(f"/api/reviews/{review_id}")["review"]
        self.assertEqual(review_record["review_id"], review_id)
        self.assertEqual(review_record["proposal"]["kind"], "memory_patch")
        self.assertIsNone(review_record["memory_apply"])

        decision = self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "accept", "reason": "test"})
        self.assertEqual(decision["decision"]["status"], "accepted")

        applied = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertTrue(applied["applied"]["applied"])
        applied_again = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertEqual(applied_again["applied"]["target_id"], applied["applied"]["target_id"])
        late_decision = self._post_json_error(
            f"/api/reviews/{review_id}/decision",
            {"decision": "reject", "reason": "too late"},
        )
        self.assertEqual(late_decision["status"], 400)
        self.assertIn("after durable memory has been applied", late_decision["body"]["error"]["message"])

        accepted_reviews = self._get_json("/api/reviews?status=accepted")
        self.assertEqual(accepted_reviews["reviews"][0]["memory_apply"]["target_id"], applied["applied"]["target_id"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("workflow.export", actions)
        self.assertIn("memory.apply", actions)
        self.assertIn("source.read", actions)
        memory_event = next(event for event in audit["events"] if event["action"] == "memory.apply")
        self.assertEqual(memory_event["metadata"]["proposal_kind"], "memory_patch")
        self.assertEqual(memory_event["metadata"]["source_count"], 1)
        self.assertEqual(memory_event["metadata"]["source_refs"][0]["adapter"], "fake")
        self.assertEqual(audit["events"][0]["metadata"]["workspace_id"], "default")

    def test_workflow_open_does_not_export_until_explicit_export(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern exports?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        run_id = asked["run"]["run_id"]

        def workflow_export_count() -> int:
            audit = self._get_json("/api/audit?limit=50")
            return sum(1 for event in audit["events"] if event["action"] == "workflow.export")

        before_open = workflow_export_count()
        self.assertEqual(before_open, 0)
        opened = self._get_json(f"/api/workflows/{run_id}")
        self.assertEqual(opened["workflow"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["run"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["latest_proposal"]["kind"], "writing_brief")
        self.assertEqual(opened["artifact"]["traceability"]["context_count"], 1)
        self.assertEqual(opened["artifact"]["traceability"]["source_count"], 1)
        self.assertNotIn("export", opened["artifact"]["traceability"])
        self.assertEqual(workflow_export_count(), before_open)

        exported = self._get_json(f"/api/workflows/{run_id}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("Export audit event:", exported["export"])
        self.assertEqual(workflow_export_count(), before_open + 1)
        json_exported = self._get_json(f"/api/workflows/{run_id}/export?format=json")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["action"], "workflow.export")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["target_id"], run_id)
        self.assertEqual(json_exported["export"]["traceability"]["export"]["format"], "json")
        self.assertEqual(workflow_export_count(), before_open + 2)

    def test_transient_ask_does_not_create_review_by_default(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 2,
                "min_context_packets": 2,
                "proposal_kind": "writing_brief",
                "use_kg": True,
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertFalse(asked["loop"]["review_required"])
        self.assertTrue(asked["run"]["scope"]["use_kg"])
        self.assertEqual(len(asked["context_packets"]), 2)
        retrieve_steps = [step for step in asked["loop"]["steps"] if step["name"] == "context.retrieve"]
        self.assertEqual(len(retrieve_steps), 2)

    def test_ask_blocks_when_retrieved_context_is_below_minimum(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 1,
                "min_context_packets": 2,
                "proposal_kind": "memory_patch",
            },
        )

        self.assertEqual(asked["status"], "insufficient_context")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertIn("2 required", asked["message"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("agentic_loop.insufficient_context", actions)
        self.assertNotIn("workflow.export", actions)

    def test_readiness_route_reports_scope_status(self):
        readiness = self._post_json("/api/kb/readiness", {"dataset_ids": ["demo"]})["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["status"], "ready")

    def test_dataset_readiness_route_reports_scope_status(self):
        readiness = self._get_json("/api/kb/datasets/demo/readiness")["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["dataset_ids"], ["demo"])

    def test_parse_documents_route_uses_product_api_boundary(self):
        parsed = self._post_json(
            "/api/kb/datasets/demo/parse",
            {"document_ids": ["doc-1"], "wait": False},
        )

        self.assertTrue(parsed["parse"]["parse_started"])
        self.assertEqual(self.gateway.parse_calls, [{"dataset_id": "demo", "document_ids": ["doc-1"], "wait": False}])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.parse")
        self.assertEqual(audit["events"][0]["metadata"]["document_ids"], ["doc-1"])

    def test_document_graph_route_uses_product_api_boundary(self):
        graph = self._get_json("/api/kb/datasets/demo/documents/doc-1/graph")

        self.assertEqual(graph["graph"]["dataset_id"], "demo")
        self.assertEqual(graph["graph"]["document_id"], "doc-1")
        self.assertEqual(len(graph["graph"]["templates"]), 1)
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.graph.read")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_id"], "demo")
        self.assertEqual(audit["events"][0]["metadata"]["document_id"], "doc-1")

    def test_runtime_diagnostics_route_reports_product_checks(self):
        payload = self._get_json("/api/runtime/diagnostics")

        self.assertTrue(payload["ok"])
        diagnostics = payload["diagnostics"]
        self.assertEqual(diagnostics["status"], "warning")
        self.assertEqual(diagnostics["workspace"]["workspace_id"], "default")
        checks = {item["name"]: item for item in diagnostics["checks"]}
        self.assertEqual(checks["product_api"]["status"], "ok")
        self.assertEqual(checks["review_store"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["metadata"]["dataset_sample_count"], 1)
        self.assertEqual(checks["retrieval_provider"]["metadata"]["provider"], "fake")
        self.assertEqual(checks["memory_provider"]["metadata"]["provider"], "fake")

    def test_ask_blocks_dataset_that_is_not_ready(self):
        self.gateway.ready = False
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Can this be answered yet?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "not_ready")
        self.assertIsNone(asked["run"])
        self.assertEqual(asked["context_packets"], [])
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertEqual(asked["readiness"]["status"], "processing")
        self.assertEqual(asked["loop"]["steps"][-1]["name"], "kb.readiness")

    def test_multipart_ingest_uses_product_api_boundary(self):
        boundary = "pska-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dataset_name"\r\n\r\n'
            "Uploaded KB\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "trusted workspace notes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/kb/ingest",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(self.gateway.uploaded, [{"name": "note.txt", "text": "trusted workspace notes"}])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.ingest")
        self.assertEqual(audit["events"][0]["metadata"]["document_names"], ["note.txt"])
        self.assertTrue(audit["events"][0]["metadata"]["parse_started"])

    def test_dataset_create_writes_kb_audit_record(self):
        created = self._post_json(
            "/api/kb/datasets",
            {"name": "New Dataset", "description": "notes", "chunk_method": "naive"},
        )

        self.assertEqual(created["dataset"]["dataset_id"], "created")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.create")
        self.assertEqual(audit["events"][0]["target_id"], "created")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_name"], "New Dataset")

    def test_audit_route_filters_by_action(self):
        self._post_json(
            "/api/kb/datasets",
            {"name": "Filtered Dataset", "description": "", "chunk_method": "naive"},
        )
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")

        filtered = self._get_json("/api/audit?limit=20&action=workflow.export")

        self.assertTrue(filtered["events"])
        self.assertEqual({event["action"] for event in filtered["events"]}, {"workflow.export"})

    def test_bundled_frontend_contains_reader_view(self):
        html = Path("src/pska_essential/web/index.html").read_text(encoding="utf-8")
        script = Path("src/pska_essential/web/app.js").read_text(encoding="utf-8")
        self.assertIn("Source Reader", html)
        self.assertIn("ingestion-status", html)
        self.assertIn("parse-documents", html)
        self.assertIn("audit-action-filter", html)
        self.assertIn("source.read", html)
        self.assertIn("review-status-filter", html)
        self.assertIn("needs_edit", html)
        self.assertIn("ask-dataset-picker", html)
        self.assertIn("ask-document-picker", html)
        self.assertIn("ask-add-dataset", html)
        self.assertIn("ask-load-documents", html)
        self.assertIn("max_iterations", html)
        self.assertIn("min_context_packets", html)
        self.assertIn("use_kg", html)
        self.assertIn('data-view="reader"', html)
        self.assertIn('data-view="writing"', html)
        self.assertIn('data-view="activity"', html)
        self.assertIn("Brief Workspace", html)
        self.assertIn("runtime-diagnostics", html)
        self.assertIn("Workspace", script)
        self.assertIn("Tenant", script)
        self.assertIn("max_iterations", script)
        self.assertIn("min_context_packets", script)
        self.assertIn("use_kg", script)
        self.assertIn('/api/sources/read', script)
        self.assertIn('/api/audit?limit=50', script)
        self.assertIn('state.auditAction', script)
        self.assertIn('action=${encodeURIComponent(state.auditAction)}', script)
        self.assertIn('auditSummary', script)
        self.assertIn('setAuditActionFilter', script)
        self.assertIn('auditActionForAskResult', script)
        self.assertIn('result.status === "not_ready"', script)
        self.assertIn('return "agentic_loop.complete"', script)
        self.assertIn('event.action === "source.read"', script)
        self.assertIn("await loadAuditEvents(\"source.read\");\n  document.querySelector('.nav-item[data-view=\"reader\"]').click();", script)
        self.assertIn('await loadAuditEvents("kb.graph.read");', script)
        self.assertIn('await loadAuditEvents("workflow.export");', script)
        self.assertIn('await loadAuditEvents("review.decide");', script)
        self.assertIn('await loadAuditEvents("memory.apply");', script)
        self.assertIn('/api/reviews?limit=50', script)
        self.assertIn('/api/reviews?status=pending&limit=50', script)
        self.assertIn('state.reviewStatus', script)
        self.assertIn('state.reviewView', script)
        self.assertIn('pendingReviews', script)
        self.assertIn('status=${encodeURIComponent(state.reviewStatus)}', script)
        self.assertIn('setReviewStatusFilter', script)
        self.assertIn('loadPendingReviews', script)
        self.assertIn('showToast("Knowledge base created.");\n    await loadDatasets();\n    await loadAuditEvents("kb.dataset.create");', script)
        self.assertIn('renderIngestResult(result.ingest);\n    await loadDatasets();\n    await loadAuditEvents("kb.ingest");', script)
        self.assertIn('await loadDocuments(datasetId, { silent: true });\n  await loadAuditEvents("kb.parse");', script)
        self.assertIn('/api/runtime/diagnostics', script)
        self.assertIn('/api/workflows/${encodeURIComponent(runId)}', script)
        self.assertIn('/documents/${encodeURIComponent(documentId)}/graph', script)
        self.assertIn('/api/workflows?limit=20', script)
        self.assertIn('loop.review_required', script)
        self.assertIn('loop.durable_proposal', script)
        self.assertIn('container.append(loopPanel({ loop }));', script)
        self.assertIn('/parse', script)
        self.assertIn('/readiness', script)
        self.assertIn('diagnosticCard', script)
        self.assertIn('auditEventCard', script)
        self.assertIn('source_count', script)
        self.assertIn('memory_target_id', script)
        self.assertIn('readDocumentGraph', script)
        self.assertIn('Graph loaded', script)
        self.assertIn('addAskDataset', script)
        self.assertIn('loadAskDocuments', script)
        self.assertIn('askDocumentCard', script)
        self.assertIn('setAskDatasetIds', script)
        self.assertIn('askResultActions', script)
        self.assertIn('openWorkflowRun', script)
        self.assertIn('sourceManifestCard', script)
        self.assertIn('latest_proposal', script)
        self.assertIn('openWritingRun', script)
        self.assertNotIn('function loadBrief', script)
        self.assertIn('openReview', script)
        self.assertIn('/api/reviews/${encodeURIComponent(reviewId)}', script)
        self.assertIn('syncReviewRecord', script)
        self.assertIn('Apply Memory', script)
        self.assertIn('syncReviewDecision', script)
        self.assertIn('syncMemoryApply', script)
        self.assertIn('Memory applied', script)
        self.assertIn('Locked', script)
        self.assertIn('memory_apply', script)
        self.assertIn('Retrieved Context', script)
        self.assertIn('parseActiveDocuments', script)
        self.assertIn('startIngestionPolling', script)

    def _get_text(self, path: str) -> str:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.read().decode("utf-8")

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))

    def _post_json_error(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                self.fail(f"expected HTTP error, got {response.status}")
        except HTTPError as exc:
            return {
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }


if __name__ == "__main__":
    unittest.main()
