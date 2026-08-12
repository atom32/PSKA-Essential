from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.mcp_server import tool_registry
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.source_audit_jobs import (
    activate_due_source_audit_jobs,
    enqueue_source_audit_job,
    list_source_audit_jobs,
    run_source_audit_job,
    schedule_source_audit_job,
)
from pska_essential.workflow import build_fake_service
from pska_essential.workspace_status import build_workspace_status


class _EmptyGateway:
    def list_datasets(self, *, page_size=200, name=None):
        return []


class SourceAuditJobTests(unittest.TestCase):
    def test_enqueue_lists_and_runs_read_only_source_audit_job(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            (root_path / ".obsidian").mkdir()
            (root_path / "Architecture.md").write_text(
                "# Architecture\n\nHermes should inspect source evidence. [[Missing Note]]\n",
                encoding="utf-8",
            )
            root = service.source_root_register(root_path, kind="auto")
            service.source_scan(root["root_id"], max_files=10)

            queued = enqueue_source_audit_job(
                service,
                scope={"root_ids": [root["root_id"]]},
                label="Daily vault audit",
                priority=8,
                limit=10,
                cadence="daily",
            )
            listed = list_source_audit_jobs(service, status="queued")
            result = run_source_audit_job(service)

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["source_audit_job"]["request"]["cadence"], "daily")
        self.assertEqual(listed[0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["source_audit"]["schema"], "pska.source_audit.v1")
        self.assertEqual(result["source_audit"]["root_count"], 1)
        self.assertEqual(result["source_audit_job"]["status"], "completed")
        self.assertEqual(result["source_audit_job"]["attempt_count"], 1)
        self.assertFalse(result["source_audit"]["data_flow"]["writes_source_files"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("source.audit_job.enqueue", actions)
        self.assertIn("source.audit_job.run", actions)
        self.assertIn("source.audit.run", actions)

    def test_provider_jobs_and_workspace_status_expose_pending_source_audit_job(self):
        service = build_fake_service()
        queued = enqueue_source_audit_job(service, scope={"root_ids": ["root-a"]}, priority=4)

        provider_jobs = build_provider_job_status(service, _EmptyGateway(), include_ready=False)
        source_job = next(job for job in provider_jobs["jobs"] if job["kind"] == "pska_source_audit_job")
        status = build_workspace_status(service=service, gateway=_EmptyGateway())
        action = next(item for item in status["next_actions"] if item["action"] == "run_source_audit_job")

        self.assertEqual(source_job["job_id"], queued["job"]["run_id"])
        self.assertEqual(source_job["root_ids"], ["root-a"])
        self.assertEqual(source_job["next_actions"], ["run_source_audit_job"])
        self.assertFalse(source_job["data_flow"]["writes_source_files"])
        self.assertEqual(action["tool"], "pska_source_audit_job_run")
        self.assertEqual(action["api"], f"POST /api/sources/audit-jobs/{queued['job']['run_id']}/run")
        self.assertEqual(action["view"], "sources")
        self.assertIn("read-only", action["reason"])

    def test_due_schedule_ticks_to_queued_and_recurs_after_run(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            (root_path / "Daily.md").write_text("# Daily\n\nAudit this folder on a cadence.\n", encoding="utf-8")
            root = service.source_root_register(root_path, kind="auto")
            service.source_scan(root["root_id"], max_files=10)

            scheduled = schedule_source_audit_job(
                service,
                scope={"root_ids": [root["root_id"]]},
                label="Scheduled vault audit",
                cadence="daily",
                due_at="2000-01-01T00:00:00+00:00",
                priority=6,
            )
            provider_jobs = build_provider_job_status(service, _EmptyGateway(), include_ready=False)
            due_job = next(job for job in provider_jobs["jobs"] if job["kind"] == "pska_source_audit_job")
            status = build_workspace_status(service=service, gateway=_EmptyGateway())
            action = next(item for item in status["next_actions"] if item["action"] == "activate_due_source_audit_jobs")
            tick = activate_due_source_audit_jobs(
                service,
                now="2000-01-01T00:00:01+00:00",
            )
            result = run_source_audit_job(service)

        self.assertEqual(scheduled["status"], "waiting")
        self.assertEqual(scheduled["source_audit_job"]["schedule_mode"], "scheduled")
        self.assertEqual(due_job["status"], "waiting")
        self.assertTrue(due_job["due"])
        self.assertEqual(due_job["next_actions"], ["activate_due_source_audit_job"])
        self.assertEqual(action["tool"], "pska_source_audit_job_tick")
        self.assertEqual(action["api"], "POST /api/sources/audit-jobs/tick")
        self.assertEqual(tick["status"], "activated")
        self.assertEqual(tick["activated_count"], 1)
        self.assertEqual(result["status"], "completed")
        self.assertIsNotNone(result["next_job"])
        self.assertEqual(result["next_job"]["status"], "waiting")
        self.assertEqual(result["next_job"]["source_audit_job"]["previous_run_id"], result["job"]["run_id"])
        self.assertEqual(result["source_audit_job"]["next_run_id"], result["next_job"]["job"]["run_id"])
        actions = [event.action for event in service.store.list_audit_events(limit=50)]
        self.assertIn("source.audit_job.due", actions)

    def test_future_schedule_waits_until_due(self):
        service = build_fake_service()
        scheduled = schedule_source_audit_job(
            service,
            label="Future audit",
            cadence="once",
            due_at="2099-01-01T00:00:00+00:00",
        )
        tick = activate_due_source_audit_jobs(service, now="2026-01-01T00:00:00+00:00")

        self.assertEqual(scheduled["status"], "waiting")
        self.assertEqual(scheduled["next_actions"][0]["action"], "wait_until_due")
        self.assertEqual(tick["status"], "idle")
        self.assertEqual(tick["activated_count"], 0)

    def test_run_source_audit_job_reports_empty_queue(self):
        result = run_source_audit_job(build_fake_service())

        self.assertEqual(result["status"], "empty")
        self.assertIsNone(result["job"])

    def test_mcp_source_audit_job_tools_queue_list_and_run_selected_scope(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "Plan.md").write_text(
                "# Plan\n\nHermes should audit local source folders without embeddings.\n",
                encoding="utf-8",
            )
            root = tools["pska_source_root_register"](str(root_path))
            tools["pska_source_scan"](root["root_id"], max_files=10)

            queued = tools["pska_source_audit_job_enqueue"](
                {"root_ids": [root["root_id"]]},
                label="MCP source audit",
                priority=3,
                limit=10,
                cadence="manual",
            )
            listed = tools["pska_source_audit_job_list"]("queued", limit=5)
            result = tools["pska_source_audit_job_run"](queued["job"]["run_id"])
            scheduled = tools["pska_source_audit_schedule_create"](
                {"root_ids": [root["root_id"]]},
                label="MCP scheduled audit",
                cadence="once",
                due_at="2000-01-01T00:00:00+00:00",
            )
            tick = tools["pska_source_audit_job_tick"]("2000-01-01T00:00:01+00:00", limit=5)

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(listed[0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["source_audit"]["root_count"], 1)
        self.assertFalse(result["source_audit"]["data_flow"]["writes_source_files"])
        self.assertEqual(scheduled["status"], "waiting")
        self.assertEqual(tick["activated_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=40)}
        self.assertIn("source.audit_job.enqueue", actions)
        self.assertIn("source.audit_job.due", actions)
        self.assertIn("source.audit_job.run", actions)


if __name__ == "__main__":
    unittest.main()
