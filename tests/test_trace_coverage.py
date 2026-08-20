from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.audit import audit_event
from pska_essential.eval import run_eval
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.trace_coverage import build_trace_coverage
from pska_essential.workflow import build_fake_service


class TraceCoverageTests(unittest.TestCase):
    def test_trace_coverage_reports_recent_audit_categories_without_writes(self):
        service = build_fake_service()

        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            (root_path / "trace.md").write_text(
                "PSKA trace coverage should recover source and memory operations.",
                encoding="utf-8",
            )
            root = service.source_root_register(str(root_path), permission_mode="read_only")
            service.source_scan(root["root_id"], max_files=10)
            packets = service.source_search("trace coverage memory", {"root_ids": [root["root_id"]]}, limit=1)
            service.source_read(packets[0].source_ref)
            service.memory_search("trace coverage", {}, 3)
            service.source_tag_propose(
                packets[0].source_ref,
                "trace/coverage",
                reason="trace coverage test",
            )

        run_eval("smoke", service, gateway_factory=build_kb_gateway_from_env)
        report = build_trace_coverage(service)

        self.assertEqual(report["schema"], "pska.trace_coverage.v1")
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["data_flow"]["read_only"])
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["writes_source_registry"])
        self.assertFalse(report["data_flow"]["writes_memory_directly"])
        self.assertFalse(report["data_flow"]["exports_external_trace"])
        categories = {category["id"]: category for category in report["categories"]}
        self.assertEqual(categories["source"]["status"], "covered")
        self.assertIn("source.search", categories["source"]["observed_actions"])
        self.assertIn("source.read", categories["source"]["observed_actions"])
        self.assertEqual(categories["memory"]["status"], "covered")
        self.assertIn("memory.search", categories["memory"]["observed_actions"])
        self.assertEqual(categories["writeback"]["status"], "covered")
        self.assertIn("source.tag.propose", categories["writeback"]["observed_actions"])
        self.assertEqual(categories["eval"]["status"], "covered")
        self.assertIn("eval.run", categories["eval"]["observed_actions"])
        self.assertTrue(categories["source"]["sample_trace_ids"])
        sqlite = next(
            provider
            for provider in report["adapter_slots"]["providers"]
            if provider["name"] == "sqlite_audit"
        )
        self.assertEqual(sqlite["runtime"]["status"], "available")

    def test_trace_coverage_marks_partial_ask_trace_as_attention_needed(self):
        service = build_fake_service()
        run = service.start("partial ask trace", {"dataset_ids": ["demo"]})
        service.store.add_audit_event(
            audit_event(
                "agentic_loop.start",
                "workflow",
                run.run_id,
                question="partial ask trace",
            )
        )

        report = build_trace_coverage(service)

        ask = next(category for category in report["categories"] if category["id"] == "ask")
        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(ask["status"], "needs_attention")
        self.assertIn("agentic_loop.complete", ask["missing_required_actions"])
