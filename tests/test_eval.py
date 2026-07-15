from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pska_essential.config import build_service_from_env
from pska_essential.eval import main as eval_main
from pska_essential.eval import run_eval
from pska_essential.kb_gateway import build_kb_gateway_from_env, reset_fake_kb_gateway
from pska_essential.mcp_server import tool_registry


class EvalTests(unittest.TestCase):
    def test_eval_dispatcher_wraps_smoke_eval(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, _fake_env(tmp), clear=True):
            service = build_service_from_env()

            result = run_eval("smoke", service, gateway_factory=build_kb_gateway_from_env)

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["suite"], "smoke")

    def test_product_acceptance_eval_runs_upload_resume_review_and_audit_loop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, _fake_env(tmp), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()

            result = run_eval("product_acceptance", service, gateway_factory=build_kb_gateway_from_env)

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["suite"], "product_acceptance")
        step_names = [step["name"] for step in result["steps"]]
        self.assertEqual(
            step_names,
            [
                "upload_loop.ready_export",
                "upload_loop.not_ready_contract",
                "upload_loop.resumable_index",
                "upload_loop.resume_export",
                "durable_knowledge.governed_transition",
                "audit.traceability",
            ],
        )
        self.assertEqual(result["providers"]["kb"], "fake")
        self.assertTrue(result["artifacts"]["ready_run_id"])
        self.assertTrue(result["artifacts"]["blocked_run_id"])
        self.assertTrue(result["artifacts"]["resumed_run_id"])

    def test_eval_cli_runs_product_acceptance_from_explicit_env(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            reset_fake_kb_gateway()
            env_file = Path(tmp) / ".env.pska"
            env_file.write_text(
                "\n".join(f"{key}={value}" for key, value in _fake_env(tmp).items()),
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                code = eval_main(["--env-file", str(env_file), "product_acceptance"])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["steps"][1]["name"], "upload_loop.not_ready_contract")

    def test_eval_cli_reports_startup_errors_as_json(self):
        with patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = eval_main(["product_acceptance"])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["steps"][0]["name"], "runtime.startup")
        self.assertIn("PSKA_RETRIEVAL_PROVIDER is required", result["message"])

    def test_mcp_eval_run_exposes_product_acceptance_suite(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, _fake_env(tmp), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())

            result = tools["pska_eval_run"]("product_acceptance")

        self.assertTrue(result["ok"])
        self.assertEqual(result["suite"], "product_acceptance")
        self.assertEqual(result["steps"][3]["name"], "upload_loop.resume_export")


def _fake_env(tmp: str) -> dict[str, str]:
    return {
        "PSKA_DEV_FAKE": "1",
        "PSKA_RETRIEVAL_PROVIDER": "fake",
        "PSKA_KB_PROVIDER": "fake",
        "PSKA_MEMORY_PROVIDER": "fake",
        "PSKA_REVIEW_DB": str(Path(tmp) / "review.sqlite3"),
    }


if __name__ == "__main__":
    unittest.main()
