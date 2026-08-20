from __future__ import annotations

import unittest

from pska_essential.audit import audit_event
from pska_essential.observability_metrics import build_observability_metrics
from pska_essential.workflow import build_fake_service


class ObservabilityMetricsTests(unittest.TestCase):
    def test_metrics_flags_failures_zero_recall_and_duplicate_review_without_writes(self):
        service = build_fake_service()
        service.store.add_audit_event(
            audit_event(
                "source.extraction_job.run",
                "source_extraction_job",
                "job_failed",
                status="failed",
                error_type="ParseError",
                error_message="could not parse demo.pdf",
            )
        )
        service.store.add_audit_event(
            audit_event(
                "source.search",
                "source",
                "personal_source",
                query="missing source recall",
                count=0,
                embedding_required=False,
            )
        )
        service.store.add_audit_event(
            audit_event(
                "source.duplicate_report",
                "source",
                "duplicate_report",
                group_count=2,
                duplicate_file_count=3,
                writes_source_files=False,
                delete_move_merge_supported=False,
            )
        )
        service.store.add_audit_event(
            audit_event(
                "source.duplicate_group.mark",
                "source",
                "dup_group_1",
                status="reviewed",
                writes_source_files=False,
                writes_source_registry=True,
            )
        )
        service.store.add_audit_event(
            audit_event(
                "eval.run",
                "eval",
                "governed_context",
                suite="governed_context",
                status="error",
                ok=False,
                failed_steps=["source_recall"],
            )
        )
        service.store.add_audit_event(
            audit_event(
                "hermes.answer_proof",
                "hermes_turn",
                "proof_1",
                failed_check_count=1,
                passed_check_count=2,
                write_like_tool_count=0,
            )
        )
        service.store.add_audit_event(
            audit_event(
                "chatgpt.memory_summary.import",
                "memory",
                "cgmem_demo",
                status="created",
                created_count=3,
                skipped_private_count=1,
                writes_memory_directly=False,
            )
        )
        service.store.add_audit_event(
            audit_event(
                "chatgpt.conversations.import",
                "source_import",
                "cgconv_demo",
                status="imported",
                imported_conversation_count=2,
                writes_memory_directly=False,
            )
        )

        report = build_observability_metrics(service, limit=100)

        self.assertEqual(report["schema"], "pska.observability_metrics.v1")
        self.assertEqual(report["status"], "needs_attention")
        self.assertTrue(report["data_flow"]["read_only"])
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["writes_source_registry"])
        self.assertFalse(report["data_flow"]["writes_memory_directly"])
        self.assertFalse(report["data_flow"]["runs_jobs"])
        self.assertFalse(report["data_flow"]["activates_due_jobs"])
        self.assertFalse(report["data_flow"]["exports_external_trace"])
        groups = {group["id"]: group for group in report["groups"]}
        self.assertEqual(groups["source_extraction"]["metrics"]["failed_count"], 1)
        self.assertEqual(groups["source_extraction"]["metrics"]["chatgpt_conversation_import_count"], 1)
        self.assertEqual(groups["source_recall"]["metrics"]["zero_result_event_count"], 1)
        self.assertEqual(groups["duplicate_review"]["metrics"]["reported_group_count"], 2)
        self.assertEqual(groups["duplicate_review"]["metrics"]["review_status_counts"]["reviewed"], 1)
        self.assertEqual(groups["eval"]["metrics"]["failed_count"], 1)
        self.assertEqual(groups["answer_proof"]["metrics"]["failed_check_count"], 1)
        self.assertEqual(groups["memory_governance"]["metrics"]["chatgpt_memory_import_count"], 1)
        self.assertTrue(groups["source_extraction"]["failure_samples"])
        self.assertEqual(groups["source_recall"]["zero_result_samples"][0]["count"], 0)
        self.assertEqual(report["adapter_slots"]["current_provider"], "sqlite_audit")

    def test_metrics_report_no_recent_signal_for_empty_audit_window(self):
        service = build_fake_service()

        report = build_observability_metrics(service, limit=20)

        self.assertEqual(report["status"], "no_recent_signal")
        self.assertEqual(report["summary"]["event_count"], 0)
        self.assertEqual(report["summary"]["observed_group_count"], 0)
        self.assertTrue(all(group["status"] == "no_recent_signal" for group in report["groups"]))


if __name__ == "__main__":
    unittest.main()
