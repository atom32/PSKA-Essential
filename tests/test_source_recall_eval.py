from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.source_recall_eval import build_source_recall_eval
from pska_essential.workflow import build_fake_service


class SourceRecallEvalTests(unittest.TestCase):
    def test_fixture_eval_proves_no_embedding_source_recall_without_live_writes(self):
        service = build_fake_service()

        report = build_source_recall_eval(service, mode="fixture", limit=5)

        self.assertEqual(report["schema"], "pska.source_recall_eval.v1")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["summary"]["case_count"], 4)
        self.assertEqual(report["summary"]["failed_case_count"], 0)
        self.assertEqual(report["summary"]["expected_hit_count"], 3)
        self.assertTrue(report["data_flow"]["read_only"])
        self.assertTrue(report["data_flow"]["uses_isolated_fixture"])
        self.assertTrue(report["data_flow"]["writes_audit_events"])
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["writes_source_registry"])
        self.assertFalse(report["data_flow"]["writes_memory_directly"])
        self.assertFalse(report["data_flow"]["embedding_required"])
        self.assertTrue(all(not case["metrics"]["embedding_required"] for case in report["cases"]))
        audit = service.store.list_audit_events(action="source.recall_eval.run", limit=1)
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].metadata["status"], "ok")
        self.assertEqual(audit[0].metadata["case_count"], 4)

    def test_provided_cases_surface_missed_expected_sources(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as tmp:
            root_path = Path(tmp)
            (root_path / "alpha.md").write_text(
                "# Alpha\n\nThe alpha source explains PSKA recall evaluation and expected paths.",
                encoding="utf-8",
            )
            (root_path / "beta.md").write_text(
                "# Beta\n\nThe beta source is a harmless decoy about lunch.",
                encoding="utf-8",
            )
            root = service.source_root_register(str(root_path), permission_mode="read_only")
            service.source_scan(root["root_id"], max_files=10)
            report = build_source_recall_eval(
                service,
                mode="provided",
                scope={"root_ids": [root["root_id"]]},
                cases=[
                    {
                        "case_id": "provided.hit",
                        "query": "PSKA recall evaluation expected paths",
                        "expected_paths": ["alpha.md"],
                    },
                    {
                        "case_id": "provided.miss",
                        "query": "PSKA recall evaluation expected paths",
                        "expected_paths": ["missing.md"],
                    },
                ],
                limit=3,
            )

        self.assertEqual(report["status"], "needs_attention")
        self.assertEqual(report["summary"]["case_count"], 2)
        self.assertEqual(report["summary"]["passed_case_count"], 1)
        self.assertEqual(report["summary"]["failed_case_count"], 1)
        cases = {case["case_id"]: case for case in report["cases"]}
        self.assertEqual(cases["provided.hit"]["status"], "ok")
        self.assertEqual(cases["provided.hit"]["metrics"]["expected_rank"], 1)
        self.assertEqual(cases["provided.miss"]["status"], "error")
        self.assertTrue(report["next_actions"])
        audit = service.store.list_audit_events(action="source.recall_eval.run", limit=1)
        self.assertEqual(audit[0].metadata["status"], "needs_attention")
        self.assertEqual(audit[0].metadata["failed_case_count"], 1)


if __name__ == "__main__":
    unittest.main()
