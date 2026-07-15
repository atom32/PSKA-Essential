from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pska_essential.component_check import main as component_check_main
from pska_essential.env_file import load_env_file, preload_env_file
from pska_essential.kb_gateway import reset_fake_kb_gateway
from pska_essential.mcp_server import main as mcp_main


class EnvFileTests(unittest.TestCase):
    def test_load_env_file_sets_values_without_overriding_existing_exports(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PSKA_RETRIEVAL_PROVIDER": "ragflow"}, clear=True):
            path = Path(tmp) / ".env.pska"
            path.write_text(
                "\n".join(
                    [
                        "# Explicit PSKA config",
                        "PSKA_DEV_FAKE=1",
                        "export PSKA_RETRIEVAL_PROVIDER=fake",
                        "PSKA_MEMORY_PROVIDER='fake'",
                        'PSKA_WORKSPACE_ID="workspace one"',
                        "RAGFLOW_API_KEY=abc#kept",
                        "GRAPHITI_BASE_URL=http://127.0.0.1:8000 # local graphiti",
                    ]
                ),
                encoding="utf-8",
            )

            loaded = load_env_file(path)

            self.assertEqual(loaded["PSKA_RETRIEVAL_PROVIDER"], "fake")
            self.assertEqual(os.environ["PSKA_RETRIEVAL_PROVIDER"], "ragflow")
            self.assertEqual(os.environ["PSKA_DEV_FAKE"], "1")
            self.assertEqual(os.environ["PSKA_MEMORY_PROVIDER"], "fake")
            self.assertEqual(os.environ["PSKA_WORKSPACE_ID"], "workspace one")
            self.assertEqual(os.environ["RAGFLOW_API_KEY"], "abc#kept")
            self.assertEqual(os.environ["GRAPHITI_BASE_URL"], "http://127.0.0.1:8000")

    def test_load_env_file_fails_for_missing_file(self):
        with self.assertRaisesRegex(FileNotFoundError, "env file not found"):
            load_env_file("/tmp/pska-missing-env-file")

    def test_load_env_file_rejects_invalid_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.pska"
            path.write_text("not a valid env line", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected KEY=VALUE"):
                load_env_file(path)

    def test_preload_env_file_skips_help_requests(self):
        with patch.dict(os.environ, {"PSKA_ENV_FILE": "/tmp/pska-missing-env-file"}, clear=True):
            parser = preload_env_file(["--help"])

        self.assertIsNotNone(parser)

    def test_mcp_list_tools_loads_explicit_env_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            reset_fake_kb_gateway()
            env_file = _write_fake_env(Path(tmp) / ".env.pska")
            output = io.StringIO()

            with redirect_stdout(output):
                code = mcp_main(["--env-file", str(env_file), "--list-tools"])

        tools = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertIn("pska_ingest_loop", tools)
        self.assertIn("pska_workspace_status", tools)

    def test_mcp_help_does_not_require_env_file(self):
        with patch.dict(os.environ, {"PSKA_ENV_FILE": "/tmp/pska-missing-env-file"}, clear=True):
            output = io.StringIO()
            with redirect_stdout(output):
                code = mcp_main(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("--env-file", output.getvalue())

    def test_component_check_loads_explicit_env_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            reset_fake_kb_gateway()
            env_file = _write_fake_env(
                Path(tmp) / ".env.pska",
                extra=[
                    "PSKA_COMPONENT_DATASET_IDS=demo",
                    "PSKA_COMPONENT_SKIP_MEMORY=1",
                    "PSKA_COMPONENT_SKIP_CLOSED_LOOP=1",
                ],
            )
            output = io.StringIO()

            with redirect_stdout(output):
                code = component_check_main(["--env-file", str(env_file)])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["providers"]["retrieval"], "fake")
        self.assertEqual(result["providers"]["kb"], "fake")

    def test_component_check_reports_startup_config_error_as_json(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "ragflow",
            "PSKA_KB_PROVIDER": "ragflow",
            "PSKA_MEMORY_PROVIDER": "company_graphrag_stub",
            "PSKA_REVIEW_DB": ":memory:",
            "RAGFLOW_BASE_URL": "http://127.0.0.1:9380",
            "PSKA_COMPONENT_DATASET_IDS": "demo",
        }
        with patch.dict(os.environ, env, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = component_check_main([])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["steps"][0]["name"], "runtime.startup")
        self.assertEqual(result["steps"][0]["metadata"]["error_type"], "ValueError")
        self.assertIn("RAGFlow retrieval is missing required env: RAGFLOW_API_KEY", result["message"])


def _write_fake_env(path: Path, *, extra: list[str] | None = None) -> Path:
    lines = [
        "PSKA_DEV_FAKE=1",
        "PSKA_RETRIEVAL_PROVIDER=fake",
        "PSKA_KB_PROVIDER=fake",
        "PSKA_MEMORY_PROVIDER=fake",
        "PSKA_REVIEW_DB=:memory:",
    ]
    lines.extend(extra or [])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
