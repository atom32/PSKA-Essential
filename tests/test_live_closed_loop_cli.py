from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from pska_essential.live_closed_loop import main as live_closed_loop_main


class LiveClosedLoopCliTests(unittest.TestCase):
    def test_live_closed_loop_cli_reports_missing_scope_as_json(self):
        with patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = live_closed_loop_main([])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["kind"], "live_closed_loop_probe")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["steps"][0]["name"], "scope.check")
        self.assertEqual(result["next_actions"][0]["action"], "select_ready_dataset")
        self.assertIn("PSKA_LIVE_DATASET_IDS or PSKA_LIVE_DATASET_NAMES is required", result["message"])

    def test_live_closed_loop_cli_reports_startup_config_error_as_json(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "ragflow",
            "PSKA_KB_PROVIDER": "ragflow",
            "PSKA_MEMORY_PROVIDER": "company_graphrag_stub",
            "PSKA_REVIEW_DB": ":memory:",
            "RAGFLOW_BASE_URL": "http://127.0.0.1:9380",
            "PSKA_LIVE_DATASET_NAMES": "Demo KB",
        }
        with patch.dict(os.environ, env, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = live_closed_loop_main([])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["kind"], "live_closed_loop_probe")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["scope"]["dataset_names"], ["Demo KB"])
        self.assertEqual(result["steps"][0]["name"], "runtime.startup")
        self.assertEqual(result["next_actions"][0]["action"], "fix_runtime_config")
        self.assertIn("RAGFlow retrieval is missing required env: RAGFLOW_API_KEY", result["message"])


if __name__ == "__main__":
    unittest.main()
