from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.source_audit_jobs import schedule_source_audit_job
from pska_essential.wakeup import build_wakeup_plan, install_launchd_agent
from pska_essential.workflow import build_fake_service


class WakeupPlanTests(unittest.TestCase):
    def test_wakeup_plan_generates_launchd_materials_without_installing(self):
        service = build_fake_service()
        schedule_source_audit_job(
            service,
            scope={"root_ids": ["root-a"]},
            label="Daily source audit",
            cadence="daily",
            due_at="2026-01-01T00:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pska_essential.wakeup.platform.system",
            return_value="Darwin",
        ):
            plan = build_wakeup_plan(
                service,
                api_base_url="http://127.0.0.1:8765",
                interval_minutes=15,
                limit=20,
                label="com.pska.test.source-audit-tick",
                launch_agents_dir=temp_dir,
                now="2026-01-01T00:00:01+00:00",
            )

            self.assertEqual(plan["schema"], "pska.wakeup_plan.v1")
            self.assertEqual(plan["status"], "install_required")
            self.assertEqual(plan["source_audit"]["scheduled_count"], 1)
            self.assertEqual(plan["source_audit"]["due_count"], 1)
            self.assertIn("/api/sources/audit-jobs/tick", plan["target"]["url"])
            self.assertFalse(Path(plan["launchd"]["plist_path"]).exists())
            self.assertEqual(plan["launchd"]["program_arguments"][0], "/usr/bin/curl")
            self.assertTrue(plan["data_flow"]["read_only"])
            self.assertFalse(plan["data_flow"]["calls_tick_endpoint"])
            self.assertFalse(plan["data_flow"]["activates_due_jobs"])
            self.assertFalse(plan["data_flow"]["runs_jobs"])
            self.assertTrue(plan["scheduled_trigger_data_flow"]["activates_due_jobs"])
            self.assertFalse(plan["scheduled_trigger_data_flow"]["runs_jobs"])

    def test_explicit_install_writes_matching_plist_without_loading_or_ticking(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pska_essential.wakeup.platform.system",
            return_value="Darwin",
        ):
            installed = install_launchd_agent(
                api_base_url="http://127.0.0.1:9876",
                interval_minutes=10,
                limit=7,
                label="com.pska.test.source-audit-tick",
                launch_agents_dir=temp_dir,
                load=False,
            )
            plist_path = Path(installed["launchd"]["plist_path"])
            self.assertTrue(plist_path.exists())
            self.assertFalse(installed["data_flow"]["calls_tick_endpoint"])
            self.assertFalse(installed["data_flow"]["activates_due_jobs"])

            plist = plistlib.loads(plist_path.read_bytes())
            self.assertEqual(plist["Label"], "com.pska.test.source-audit-tick")
            self.assertEqual(plist["StartInterval"], 600)
            self.assertIn("http://127.0.0.1:9876/api/sources/audit-jobs/tick", plist["ProgramArguments"])
            self.assertIn('{"limit":7}', plist["ProgramArguments"])

            plan = build_wakeup_plan(
                service,
                api_base_url="http://127.0.0.1:9876",
                interval_minutes=10,
                limit=7,
                label="com.pska.test.source-audit-tick",
                launch_agents_dir=temp_dir,
            )
            self.assertEqual(plan["status"], "configured")
            self.assertTrue(plan["launchd"]["plist_matches_expected"])
            self.assertFalse(plan["data_flow"]["writes_launch_agent"])


if __name__ == "__main__":
    unittest.main()
