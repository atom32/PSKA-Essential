from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.agentic_loop import list_resumable_agentic_questions
from pska_essential.config import build_service_from_env
from pska_essential.ingest_loop import resume_ingest_loop, run_ingest_loop
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
        self.assertEqual(result["run"]["run_id"], result["run_id"])
        self.assertEqual(result["proposal"]["kind"], "writing_brief")
        self.assertIsNone(result["review"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(result["loop"]["status"], "ready")
        self.assertEqual(len(result["context_packets"]), 1)
        self.assertEqual(result["export"]["traceability"]["source_count"], 1)
        self.assertEqual(result["export"]["traceability"]["proposal_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertIn("workflow.export", actions)
        self.assertIn("agentic_loop.complete", actions)

    def test_ingest_loop_exposes_review_payload_without_applying_memory(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "memory.txt"
            path.write_text(
                "Durable PSKA knowledge must pass through review before memory is written.",
                encoding="utf-8",
            )
            service = build_service_from_env()
            gateway = build_kb_gateway_from_env()

            result = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(path)],
                dataset_name="loop-review-test",
                question="What governs durable PSKA knowledge?",
                proposal_kind="memory_patch",
                create_review=True,
                export_format="json",
                poll_interval_seconds=0.05,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertEqual(result["review"]["proposal_id"], result["proposal"]["proposal_id"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertTrue(result["loop"]["review_required"])
        self.assertEqual(result["loop"]["governance"]["action"], "manual_review")
        self.assertEqual(result["export"]["latest_proposal"]["kind"], "memory_patch")
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("review.create", actions)
        self.assertNotIn("memory.apply", actions)

    def test_ingest_loop_records_resumable_ask_when_uploaded_scope_is_processing(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "slow.txt"
            path.write_text(
                "This uploaded source will become queryable only after parsing completes.",
                encoding="utf-8",
            )
            service = build_service_from_env()
            gateway = build_kb_gateway_from_env()

            result = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(path)],
                dataset_name="loop-processing-test",
                question="What should happen after parsing completes?",
                parse=False,
                wait_ready=False,
                poll_interval_seconds=0.05,
            )

            resumable = list_resumable_agentic_questions(service, gateway, limit=5)

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["ask_status"], "not_ready")
        self.assertIsNotNone(result["run"])
        self.assertEqual(result["run"]["status"], "blocked")
        self.assertEqual(result["run"]["metadata"]["blocked_reason"], "kb_not_ready")
        self.assertEqual(result["run"]["metadata"]["ask_request"]["question"], "What should happen after parsing completes?")
        self.assertEqual(result["loop"]["status"], "not_ready")
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIsNone(result["export"])
        self.assertEqual(resumable[0]["run"]["run_id"], result["run_id"])
        self.assertFalse(resumable[0]["can_resume"])
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertIn("agentic_loop.not_ready", actions)
        self.assertIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)
        self.assertNotIn("agentic_loop.complete", actions)

    def test_ingest_loop_resume_preserves_export_intent_after_processing(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "slow-export.txt"
            path.write_text(
                "A resumable upload loop should finish as a sourced work product after parsing completes.",
                encoding="utf-8",
            )
            service = build_service_from_env()
            gateway = build_kb_gateway_from_env()

            blocked = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(path)],
                dataset_name="loop-resume-test",
                question="What should the resumable upload loop produce?",
                parse=False,
                wait_ready=False,
                export_format="json",
                poll_interval_seconds=0.05,
            )
            document_ids = [document["document_id"] for document in blocked["documents"]]
            gateway.parse_documents(dataset_id=blocked["dataset"]["dataset_id"], document_ids=document_ids, wait=True)

            resumed = resume_ingest_loop(service, gateway, run_id=blocked["run_id"])

        self.assertEqual(blocked["status"], "not_ready")
        self.assertEqual(blocked["run"]["metadata"]["ingest_loop"]["export_format"], "json")
        self.assertEqual(resumed["kind"], "ingest_loop_resume")
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["ask_status"], "ready")
        self.assertEqual(resumed["export_format"], "json")
        self.assertEqual(resumed["ingest"]["resumed_from_run_id"], blocked["run_id"])
        self.assertEqual(resumed["loop"]["resumed_from_run_id"], blocked["run_id"])
        self.assertEqual(resumed["export"]["traceability"]["source_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=80)}
        self.assertIn("agentic_loop.resume", actions)
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
        self.assertIsNone(result["run"])
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIsNone(result["export"])
        self.assertEqual(result["readiness"]["status"], "failed")
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertNotIn("agentic_loop.not_ready", actions)
        self.assertNotIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)
        self.assertNotIn("agentic_loop.complete", actions)


if __name__ == "__main__":
    unittest.main()
