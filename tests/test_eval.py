from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.config import build_service_from_env
from pska_essential.eval import main as eval_main
from pska_essential.eval import run_eval, run_governed_context_eval, run_product_acceptance_eval
from pska_essential.kb_gateway import build_kb_gateway_from_env, reset_fake_kb_gateway
from pska_essential.mcp_server import tool_registry
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService, build_fake_service


class EvalTests(unittest.TestCase):
    def test_eval_dispatcher_wraps_smoke_eval(self):
        service = build_fake_service()

        result = run_eval("smoke", service, gateway_factory=build_kb_gateway_from_env)

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["suite"], "smoke")

    def test_product_acceptance_eval_runs_upload_resume_review_and_audit_loop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, _fake_env(tmp), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()

            result = run_eval("product_acceptance", service, gateway_factory=build_kb_gateway_from_env)
            eval_audit = service.store.list_audit_events(action="eval.run", limit=1)

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
        self.assertEqual(eval_audit[0].metadata["suite"], "product_acceptance")
        self.assertEqual(eval_audit[0].metadata["status"], "ok")
        self.assertEqual(eval_audit[0].metadata["step_count"], 6)

    def test_product_acceptance_eval_leaves_manual_review_pending_outside_dev_fake(self):
        with patch.dict(os.environ, {}, clear=True):
            gateway = reset_fake_kb_gateway()
            service = WorkflowService(
                retrieval=FakeRetrievalAdapter(corpus_loader=gateway.retrieval_corpus),
                memory=FakeMemoryAdapter(),
                store=SQLiteReviewStore(":memory:"),
            )

            result = run_product_acceptance_eval(service, gateway)

        self.assertTrue(result["ok"])
        self.assertFalse(result["providers"]["dev_fake"])
        self.assertFalse(result["providers"]["auto_apply_allowed"])
        durable = next(step for step in result["steps"] if step["name"] == "durable_knowledge.governed_transition")
        self.assertTrue(durable["metadata"]["blocked_before_review"])
        self.assertFalse(durable["metadata"]["applied"])
        self.assertTrue(durable["metadata"]["review_left_pending"])
        audit = next(step for step in result["steps"] if step["name"] == "audit.traceability")
        self.assertNotIn("memory.apply", audit["metadata"]["required_actions"])
        self.assertNotIn("memory.apply", audit["metadata"]["observed_actions"])

    def test_governed_context_eval_covers_source_memory_trace_and_writeback_safety(self):
        result = run_governed_context_eval()

        self.assertTrue(result["ok"])
        self.assertEqual(result["suite"], "governed_context")
        self.assertFalse(result["data_flow"]["uses_live_kb"])
        self.assertFalse(result["data_flow"]["uses_live_memory_provider"])
        self.assertFalse(result["data_flow"]["writes_user_source_files"])
        self.assertFalse(result["data_flow"]["embedding_required"])
        steps = {step["name"]: step for step in result["steps"]}
        self.assertEqual(set(steps), {
            "source_recall.no_embedding_search",
            "memory_utility.search_returns_promoted_source_route",
            "memory_trace.why_used_is_audit_backed",
            "writeback_safety.read_only_root_blocks_apply",
        })
        self.assertFalse(steps["source_recall.no_embedding_search"]["metadata"]["embedding_required"])
        self.assertEqual(
            steps["source_recall.no_embedding_search"]["metadata"]["selected_path"],
            "routing.md",
        )
        self.assertGreaterEqual(
            steps["memory_trace.why_used_is_audit_backed"]["metadata"]["trace_count"],
            1,
        )
        self.assertEqual(
            steps["memory_trace.why_used_is_audit_backed"]["metadata"]["confidence"],
            "candidate_retrieval",
        )
        self.assertTrue(
            steps["writeback_safety.read_only_root_blocks_apply"]["metadata"]["source_file_unchanged"]
        )
        self.assertIn(
            "permission_mode",
            steps["writeback_safety.read_only_root_blocks_apply"]["metadata"]["blocked_message"],
        )
        self.assertNotIn(
            "source.tag.apply",
            steps["writeback_safety.read_only_root_blocks_apply"]["metadata"]["observed_actions"],
        )

    def test_eval_dispatcher_runs_governed_context_suite_and_audits_outer_service(self):
        service = build_fake_service()

        result = run_eval("governed_context", service, gateway_factory=build_kb_gateway_from_env)
        eval_audit = service.store.list_audit_events(action="eval.run", limit=1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["suite"], "governed_context")
        self.assertEqual(eval_audit[0].metadata["suite"], "governed_context")
        self.assertEqual(eval_audit[0].metadata["status"], "ok")
        self.assertEqual(eval_audit[0].metadata["step_count"], 4)

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

    def test_eval_cli_runs_governed_context_without_runtime_provider_env(self):
        with patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()

            with redirect_stdout(output):
                code = eval_main(["governed_context"])

        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["suite"], "governed_context")
        self.assertFalse(result["data_flow"]["uses_live_kb"])
        self.assertFalse(result["data_flow"]["writes_live_source_registry"])

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

    def test_mcp_eval_run_exposes_governed_context_suite(self):
        tools = tool_registry(build_fake_service())

        result = tools["pska_eval_run"]("governed_context")

        self.assertTrue(result["ok"])
        self.assertEqual(result["suite"], "governed_context")
        self.assertEqual(result["steps"][0]["name"], "source_recall.no_embedding_search")


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
