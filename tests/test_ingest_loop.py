from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.config import build_service_from_env
from pska_essential.ingest_loop import run_ingest_loop
from pska_essential.kb_gateway import build_kb_gateway_from_env, reset_fake_kb_gateway


class IngestLoopTests(unittest.TestCase):
    def test_ingest_loop_uploads_waits_asks_and_exports(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "workspace.txt"
            path.write_text(
                "PSKA turns uploaded materials into sourced work products through a governed workflow.",
                encoding="utf-8",
            )
            service = build_service_from_env()
            gateway = build_kb_gateway_from_env()

            result = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(path)],
                dataset_name="loop-test",
                question="What does PSKA produce from uploaded materials?",
                export_format="json",
                poll_interval_seconds=0.05,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["kind"], "ingest_loop")
        self.assertTrue(result["readiness"]["ready"])
        self.assertEqual(result["ask_status"], "ready")
        self.assertTrue(result["run_id"].startswith("run_"))
        self.assertEqual(result["export"]["traceability"]["source_count"], 1)
        self.assertEqual(result["export"]["traceability"]["proposal_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertIn("workflow.export", actions)
        self.assertIn("agentic_loop.complete", actions)

    def test_ingest_loop_stops_when_ingested_scope_is_not_ready(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "bad.pdf"
            path.write_bytes(b"%PDF-1.5\nbinary")
            service = build_service_from_env()
            gateway = build_kb_gateway_from_env()

            result = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(path)],
                dataset_name="loop-test-bad",
                question="Should not run",
                poll_interval_seconds=0.05,
            )

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["ask_status"], None)
        self.assertIsNone(result["export"])
        self.assertEqual(result["readiness"]["status"], "failed")
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertNotIn("workflow.export", actions)
        self.assertNotIn("agentic_loop.complete", actions)


if __name__ == "__main__":
    unittest.main()
