from __future__ import annotations

import unittest

from pska_essential.workflow import WorkflowError, build_fake_service


class WorkflowTests(unittest.TestCase):
    def test_fake_adapter_e2e_blocks_memory_until_review(self):
        service = build_fake_service()
        run = service.start("test workflow", {"dataset_ids": ["demo"]})
        packets = service.context_retrieve(run.run_id, "adapter memory review", 2)
        self.assertGreaterEqual(len(packets), 1)

        proposal = service.propose(run.run_id, "memory_patch", "remember reviewed workflow")
        review = service.review_create(proposal.proposal_id)

        with self.assertRaises(WorkflowError):
            service.memory_apply(review.review_id)

        decision = service.review_decide(review.review_id, "accept", "approved in test")
        self.assertEqual(decision.status, "accepted")
        result = service.memory_apply(review.review_id)
        self.assertTrue(result.applied)
        applied_again = service.memory_apply(review.review_id)
        self.assertEqual(applied_again.target_id, result.target_id)

        facts = service.memory_search("reviewed workflow", {}, 10)
        self.assertEqual(len(facts), 1)
        events = service.store.list_audit_events()
        review_create = next(event for event in events if event.action == "review.create")
        review_decide = next(event for event in events if event.action == "review.decide")
        memory_apply = next(event for event in events if event.action == "memory.apply")
        self.assertEqual(review_create.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(review_create.metadata["run_id"], run.run_id)
        self.assertEqual(review_create.metadata["source_count"], len(proposal.source_refs))
        self.assertEqual(review_decide.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(review_decide.metadata["proposal_kind"], "memory_patch")
        self.assertEqual(memory_apply.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(memory_apply.metadata["run_id"], run.run_id)
        self.assertEqual(memory_apply.metadata["proposal_kind"], "memory_patch")
        self.assertEqual(memory_apply.metadata["source_count"], len(proposal.source_refs))
        self.assertEqual(memory_apply.metadata["source_refs"][0]["adapter"], "fake")

        with self.assertRaisesRegex(WorkflowError, "after durable memory has been applied"):
            service.review_decide(review.review_id, "reject", "too late")
        self.assertEqual(service.store.get_review(review.review_id)["status"], "accepted")
        review_decide_events = [
            event for event in service.store.list_audit_events() if event.action == "review.decide"
        ]
        self.assertEqual(len(review_decide_events), 1)

    def test_export_brief_uses_workflow_context(self):
        service = build_fake_service()
        run = service.start("brief workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        proposal = service.propose(run.run_id, "writing_brief", "explain adapter boundaries")

        brief = service.export_brief(run.run_id, "markdown")
        self.assertIn("PSKA-Essential Brief", brief)
        self.assertIn("Export audit event:", brief)
        self.assertIn("Export format: `markdown`", brief)
        self.assertIn("## Work Product", brief)
        self.assertIn(proposal.body, brief)
        self.assertIn("## Source Manifest", brief)
        self.assertIn("| # | Title | Adapter | Dataset | Document | Chunk/Source | Score |", brief)
        self.assertIn("## Supporting Context", brief)
        self.assertIn("Source [1]:", brief)

        json_export = service.export_brief(run.run_id, "json")
        self.assertEqual(json_export["latest_proposal"]["proposal_id"], proposal.proposal_id)
        self.assertEqual(json_export["traceability"]["context_count"], 1)
        self.assertEqual(json_export["traceability"]["proposal_count"], 1)
        self.assertEqual(json_export["traceability"]["source_count"], 1)
        self.assertEqual(json_export["traceability"]["export"]["action"], "workflow.export")
        self.assertEqual(json_export["traceability"]["export"]["target_id"], run.run_id)
        self.assertEqual(json_export["traceability"]["export"]["format"], "json")
        self.assertEqual(json_export["source_manifest"][0]["source_ref"]["adapter"], "fake")

        export_events = [
            event for event in service.store.list_audit_events() if event.action == "workflow.export"
        ]
        self.assertEqual(len(export_events), 2)
        self.assertEqual(
            json_export["traceability"]["export"]["audit_event_id"],
            export_events[-1].audit_event_id,
        )

    def test_workflow_artifact_reads_work_product_without_export_audit(self):
        service = build_fake_service()
        run = service.start("artifact workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        proposal = service.propose(run.run_id, "writing_brief", "inspect without export")

        artifact = service.workflow_artifact(run.run_id)

        self.assertEqual(artifact["run"]["run_id"], run.run_id)
        self.assertEqual(artifact["latest_proposal"]["proposal_id"], proposal.proposal_id)
        self.assertEqual(artifact["traceability"]["context_count"], 1)
        self.assertEqual(artifact["traceability"]["proposal_count"], 1)
        self.assertEqual(artifact["traceability"]["source_count"], 1)
        self.assertNotIn("export", artifact["traceability"])
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_render_brief_does_not_create_export_audit(self):
        service = build_fake_service()
        run = service.start("render workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        service.propose(run.run_id, "writing_brief", "render without export")

        brief = service.render_brief(run.run_id, "markdown")

        self.assertIn("PSKA-Essential Brief", brief)
        self.assertIn("## Source Manifest", brief)
        self.assertNotIn("Export audit event:", brief)
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_source_read_writes_source_audit_record(self):
        service = build_fake_service()
        run = service.start("source workflow", {"dataset_ids": ["demo"]})
        packet = service.context_retrieve(run.run_id, "adapter", 1)[0]

        source = service.source_read(packet.source_ref)

        self.assertTrue(source.text)
        source_read = next(event for event in service.store.list_audit_events() if event.action == "source.read")
        self.assertEqual(source_read.target_type, "source")
        self.assertEqual(source_read.metadata["adapter"], "fake")
        self.assertEqual(source_read.metadata["document_id"], packet.source_ref.document_id)
        self.assertEqual(source_read.metadata["source_ref"]["adapter"], "fake")

    def test_smoke_eval(self):
        service = build_fake_service()
        result = service.eval_run("smoke")
        self.assertTrue(result["ok"])
        self.assertTrue(result["blocked_before_review"])


if __name__ == "__main__":
    unittest.main()
