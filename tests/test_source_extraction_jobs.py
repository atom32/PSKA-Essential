from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.mcp_server import tool_registry
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.source_extraction_jobs import (
    enqueue_source_extraction_job,
    list_source_extraction_jobs,
    run_source_extraction_job,
)
from pska_essential.workflow import build_fake_service
from pska_essential.workspace_status import build_workspace_status


class _EmptyGateway:
    def list_datasets(self, *, page_size=200, name=None):
        return []


class SourceExtractionJobTests(unittest.TestCase):
    def test_enqueue_lists_and_runs_source_extraction_job(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "Plan.md").write_text(
                "# Plan\n\nHermes should extract source files through queued jobs.\n",
                encoding="utf-8",
            )
            root = service.source_root_register(root_path)

            queued = enqueue_source_extraction_job(
                service,
                root_id=root["root_id"],
                label="Extract project source",
                priority=7,
                max_files=10,
                extractor="auto",
            )
            listed = list_source_extraction_jobs(service, status="queued")
            result = run_source_extraction_job(service)

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["source_extraction_job"]["request"]["extractor"], "auto")
        self.assertEqual(listed[0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scan"]["counts"]["indexed"], 1)
        self.assertEqual(result["source_extraction_job"]["summary"]["indexed"], 1)
        self.assertEqual(result["source_extraction_job"]["attempt_count"], 1)
        self.assertFalse(result["scan"]["data_flow"]["writes_source_files"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("source.extraction_job.enqueue", actions)
        self.assertIn("source.extraction_job.run", actions)
        self.assertIn("source.scan", actions)

    def test_provider_jobs_and_workspace_status_expose_pending_extraction_job(self):
        service = build_fake_service()
        queued = enqueue_source_extraction_job(service, root_id="root-a", extractor="markitdown", priority=4)

        provider_jobs = build_provider_job_status(service, _EmptyGateway(), include_ready=False)
        extraction_job = next(job for job in provider_jobs["jobs"] if job["kind"] == "pska_source_extraction_job")
        status = build_workspace_status(service=service, gateway=_EmptyGateway())
        action = next(item for item in status["next_actions"] if item["action"] == "run_source_extraction_job")

        self.assertEqual(extraction_job["job_id"], queued["job"]["run_id"])
        self.assertEqual(extraction_job["root_id"], "root-a")
        self.assertEqual(extraction_job["extractor"], "markitdown")
        self.assertEqual(extraction_job["next_actions"], ["run_source_extraction_job"])
        self.assertFalse(extraction_job["data_flow"]["writes_source_files"])
        self.assertTrue(extraction_job["data_flow"]["writes_index"])
        self.assertEqual(action["tool"], "pska_source_extract_job_run")
        self.assertEqual(action["api"], f"POST /api/sources/extraction-jobs/{queued['job']['run_id']}/run")
        self.assertEqual(action["view"], "sources")
        self.assertIn("index metadata", action["reason"])

    def test_run_source_extraction_job_reports_empty_queue(self):
        result = run_source_extraction_job(build_fake_service())

        self.assertEqual(result["status"], "empty")
        self.assertIsNone(result["job"])

    def test_mcp_source_extract_job_tools_queue_list_and_run_selected_root(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "Plan.md").write_text(
                "# Plan\n\nMCP can run source extraction jobs without embeddings.\n",
                encoding="utf-8",
            )
            root = tools["pska_source_root_register"](str(root_path))

            queued = tools["pska_source_extract_job_enqueue"](
                root["root_id"],
                label="MCP extraction",
                priority=3,
                max_files=10,
                extractor="auto",
            )
            listed = tools["pska_source_extract_job_list"]("queued", limit=5)
            result = tools["pska_source_extract_job_run"](queued["job"]["run_id"])

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(listed[0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scan"]["counts"]["indexed"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=40)}
        self.assertIn("source.extraction_job.enqueue", actions)
        self.assertIn("source.extraction_job.run", actions)


if __name__ == "__main__":
    unittest.main()
