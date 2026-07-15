from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pska_essential.kb_gateway import reset_fake_kb_gateway
from pska_essential.workspace_status_cli import main as workspace_status_main


class WorkspaceStatusCliTests(unittest.TestCase):
    def test_workspace_status_cli_loads_env_file_and_prints_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            reset_fake_kb_gateway()
            env_file = _write_env(Path(tmp) / ".env.pska")
            output = io.StringIO()

            with redirect_stdout(output):
                code = workspace_status_main(["--env-file", str(env_file)])

        status = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["providers"]["kb"], "fake")
        self.assertEqual(status["status"], "empty")
        self.assertEqual(status["next_actions"][0]["action"], "run_file_to_work_product_loop")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_ingest_loop")

    def test_workspace_status_cli_returns_nonzero_for_explicit_status_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            env_file = _write_env(
                Path(tmp) / ".env.pska",
                lines=[
                    "PSKA_RETRIEVAL_PROVIDER=company_graphrag_stub",
                    "PSKA_MEMORY_PROVIDER=company_graphrag_stub",
                    "PSKA_KB_PROVIDER=ragflow",
                    "PSKA_REVIEW_DB=:memory:",
                    "RAGFLOW_BASE_URL=http://127.0.0.1:1",
                    "RAGFLOW_API_KEY=test-key",
                    "RAGFLOW_TIMEOUT=0.001",
                ],
            )
            output = io.StringIO()

            with redirect_stdout(output):
                code = workspace_status_main(["--env-file", str(env_file)])

        status = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["next_actions"][0]["action"], "fix_kb_gateway")
        self.assertTrue(status["kb"]["error"]["type"])
        self.assertTrue(status["kb"]["error"]["message"])

    def test_workspace_status_cli_reports_startup_config_error_as_json(self):
        with patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = workspace_status_main([])

        status = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["steps"][0]["name"], "runtime.startup")
        self.assertEqual(status["next_actions"][0]["action"], "fix_runtime_config")
        self.assertIn("PSKA_RETRIEVAL_PROVIDER is required", status["message"])


def _write_env(path: Path, *, lines: list[str] | None = None) -> Path:
    values = lines or [
        "PSKA_DEV_FAKE=1",
        "PSKA_RETRIEVAL_PROVIDER=fake",
        "PSKA_KB_PROVIDER=fake",
        "PSKA_MEMORY_PROVIDER=fake",
        "PSKA_REVIEW_DB=:memory:",
    ]
    path.write_text("\n".join(values), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
