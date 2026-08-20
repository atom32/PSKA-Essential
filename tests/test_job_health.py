from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.digest_jobs import enqueue_digest_job
from pska_essential.job_health import build_job_health
from pska_essential.source_audit_jobs import schedule_source_audit_job
from pska_essential.source_extraction_jobs import enqueue_source_extraction_job
from pska_essential.workflow import build_fake_service
from tests.test_product_api import _FakeGateway


class JobHealthTests(unittest.TestCase):
    def test_job_health_groups_digest_source_audit_and_extraction_actions(self):
        service = build_fake_service()
        enqueue_digest_job(service, dataset_ids=["demo"], question="Digest job health", priority=3)
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            (root_path / "note.md").write_text("PSKA job health source note.", encoding="utf-8")
            root = service.source_root_register(str(root_path), permission_mode="read_only")
            enqueue_source_extraction_job(service, root_id=root["root_id"], label="Job health extraction")
            schedule_source_audit_job(
                service,
                scope={"root_ids": [root["root_id"]]},
                label="Job health audit",
                due_at="2000-01-01T00:00:00+00:00",
            )

        report = build_job_health(
            service,
            _FakeGateway(),
            now="2026-01-02T00:00:00+00:00",
            include_kb=False,
        )

        self.assertEqual(report["schema"], "pska.job_health.v1")
        self.assertEqual(report["status"], "action_required")
        self.assertTrue(report["data_flow"]["read_only"])
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["writes_memory_directly"])
        self.assertFalse(report["data_flow"]["runs_jobs"])
        self.assertFalse(report["data_flow"]["activates_due_jobs"])
        groups = {group["id"]: group for group in report["groups"]}
        self.assertEqual(groups["digest"]["status"], "action_required")
        self.assertEqual(groups["source_audit"]["counts"]["due"], 1)
        self.assertEqual(groups["source_extraction"]["status"], "action_required")
        self.assertNotIn("kb_ingestion", groups)
        actions = {action["action"] for action in report["next_actions"]}
        self.assertIn("run_digest_job", actions)
        self.assertIn("run_source_extraction_job", actions)
        self.assertIn("activate_due_source_audit_jobs", actions)
        self.assertEqual(report["scheduler"]["source_audit_tick"]["tool"], "pska_source_audit_job_tick")

    def test_job_health_flags_failed_jobs_without_running_them(self):
        service = build_fake_service()
        queued = enqueue_digest_job(service, dataset_ids=["demo"], question="Failed digest")
        run = service.state(queued["job"]["run_id"])
        run.status = "failed"
        run.metadata["digest_job"]["status"] = "failed"
        run.metadata["digest_job"]["last_status"] = "error"
        run.metadata["digest_job"]["last_message"] = "provider failed"
        service.store.save_workflow(run)

        report = build_job_health(service, _FakeGateway(), include_kb=False)

        self.assertEqual(report["status"], "needs_attention")
        digest = next(group for group in report["groups"] if group["id"] == "digest")
        self.assertEqual(digest["status"], "needs_attention")
        self.assertEqual(digest["counts"]["failed"], 1)
        self.assertEqual(digest["jobs"][0]["last_message"], "provider failed")
        self.assertIn("inspect_failure", {action["action"] for action in digest["next_actions"]})
