from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeMemoryAdapter
from pska_essential.contracts import ContextPacket, SourceContext, SourceRef
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService, build_fake_service


class _RecordingRetrieval:
    backend_name = "recording"

    def __init__(self) -> None:
        self.options = None

    def retrieve(self, query, scope, limit, options=None):
        self.options = options
        return [
            ContextPacket(
                context_id="ctx-recording",
                text="Recorded retrieval",
                source_ref=SourceRef(adapter=self.backend_name, dataset_id="demo", document_id="doc-1"),
            )
        ]

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="Recorded retrieval")


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

    def test_memory_delete_requires_review_and_deactivates_fact(self):
        service = build_fake_service()
        run = service.start("delete workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember deletion target")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "approved")
        applied = service.memory_apply(review.review_id)
        facts = service.memory_search("deletion target", {}, 10)
        self.assertEqual(facts[0].fact_id, applied.target_id)

        delete_result = service.memory_delete_review(facts[0], "outdated")
        delete_review_id = delete_result["review"]["review_id"]
        self.assertEqual(delete_result["proposal"]["kind"], "memory_delete")
        self.assertEqual(delete_result["proposal"]["memory_delete"]["target_id"], applied.target_id)
        with self.assertRaises(WorkflowError):
            service.memory_apply(delete_review_id)

        service.review_decide(delete_review_id, "accept", "delete approved")
        deletion = service.memory_apply(delete_review_id)

        self.assertTrue(deletion.applied)
        self.assertEqual(deletion.target_id, applied.target_id)
        self.assertEqual(deletion.metadata["operation"], "delete")
        self.assertEqual(service.memory_search("deletion target", {}, 10), [])
        memory_delete = next(event for event in service.store.list_audit_events() if event.action == "memory.delete")
        self.assertEqual(memory_delete.metadata["proposal_kind"], "memory_delete")
        self.assertEqual(memory_delete.metadata["memory_target_id"], applied.target_id)
        self.assertEqual(memory_delete.metadata["source_count"], 1)

    def test_memory_update_requires_review_and_versions_fact(self):
        service = build_fake_service()
        run = service.start("update workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember obsoletephrase")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "approved")
        applied = service.memory_apply(review.review_id)
        facts = service.memory_search("obsoletephrase", {}, 10)
        self.assertEqual(facts[0].fact_id, applied.target_id)

        update_result = service.memory_update_review(facts[0], "Reviewed durable memory target", "better wording")
        update_review_id = update_result["review"]["review_id"]
        self.assertEqual(update_result["proposal"]["kind"], "memory_update")
        self.assertEqual(update_result["proposal"]["memory_update"]["target_id"], applied.target_id)
        with self.assertRaises(WorkflowError):
            service.memory_apply(update_review_id)

        service.review_decide(update_review_id, "accept", "update approved")
        updated = service.memory_apply(update_review_id)

        self.assertTrue(updated.applied)
        self.assertEqual(updated.target_id, applied.target_id)
        self.assertEqual(updated.metadata["operation"], "update")
        self.assertEqual(updated.metadata["version"], 2)
        self.assertEqual(service.memory_search("obsoletephrase", {}, 10), [])
        updated_facts = service.memory_search("durable memory target", {}, 10)
        self.assertEqual(updated_facts[0].text, "Reviewed durable memory target")
        self.assertEqual(updated_facts[0].metadata["version"], 2)
        self.assertEqual(updated_facts[0].metadata["versions"][0]["text"], proposal.memory_patch.text)
        memory_update = next(event for event in service.store.list_audit_events() if event.action == "memory.update")
        self.assertEqual(memory_update.metadata["proposal_kind"], "memory_update")
        self.assertEqual(memory_update.metadata["memory_target_id"], applied.target_id)
        self.assertEqual(memory_update.metadata["version"], 2)

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

    def test_context_retrieve_passes_use_kg_to_adapter_and_audit(self):
        retrieval = _RecordingRetrieval()
        service = WorkflowService(retrieval, FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))
        run = service.start("graph-aware workflow", {"dataset_ids": ["demo"], "use_kg": True})

        service.context_retrieve(run.run_id, "adapter", 1)

        self.assertTrue(retrieval.options["use_kg"])
        context_event = next(event for event in service.store.list_audit_events() if event.action == "context.retrieve")
        self.assertTrue(context_event.metadata["use_kg"])

    def test_smoke_eval(self):
        service = build_fake_service()
        result = service.eval_run("smoke")
        self.assertTrue(result["ok"])
        self.assertTrue(result["blocked_before_review"])


if __name__ == "__main__":
    unittest.main()
