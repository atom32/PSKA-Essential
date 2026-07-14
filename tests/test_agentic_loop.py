from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeMemoryAdapter
from pska_essential.agentic_loop import run_agentic_question
from pska_essential.contracts import ContextPacket, SourceContext, SourceRef
from pska_essential.governance import AUTO_ACCEPT, AUTO_APPLY, WorkspaceGovernancePolicy
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService, build_fake_service


class _NoContextRetrieval:
    backend_name = "none"

    def retrieve(self, query, scope, limit, options=None):
        return []

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="", metadata={"missing": True})


class _QueryRecordingRetrieval:
    backend_name = "query_recording"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve(self, query, scope, limit, options=None):
        self.queries.append(query)
        index = len(self.queries)
        return [
            ContextPacket(
                context_id=f"ctx-query-{index}",
                text=f"Context returned for {query}",
                source_ref=SourceRef(adapter=self.backend_name, dataset_id="demo", document_id=f"doc-{index}"),
                title=query,
            )
        ]

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="Recorded query source")


class AgenticLoopTests(unittest.TestCase):
    def test_transient_writing_brief_does_not_create_review_by_default(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Explain the PSKA boundary",
            dataset_ids=["demo"],
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertIsNone(result["review"])
        self.assertFalse(result["loop"]["review_required"])
        self.assertEqual(result["artifact"]["latest_proposal"]["kind"], "writing_brief")
        self.assertIn("brief.prepare", [step["name"] for step in result["loop"]["steps"]])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        artifact_loop = result["artifact"]["run"]["metadata"]["agentic_loop"]
        self.assertEqual(persisted_loop["status"], "ready")
        self.assertEqual(persisted_loop["governance"]["action"], "skip")
        self.assertFalse(persisted_loop["review_required"])
        self.assertFalse(persisted_loop["durable_proposal"])
        self.assertEqual(persisted_loop["proposal_id"], result["proposal"]["proposal_id"])
        self.assertEqual(artifact_loop["proposal_id"], result["proposal"]["proposal_id"])
        self.assertEqual(service.store.list_reviews(), [])
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_agentic_loop_uses_explicit_retrieval_query_plan(self):
        retrieval = _QueryRecordingRetrieval()
        service = WorkflowService(
            retrieval=retrieval,
            memory=FakeMemoryAdapter(),
            store=SQLiteReviewStore(":memory:"),
        )

        result = run_agentic_question(
            service,
            question="Primary question",
            dataset_ids=["demo"],
            retrieval_queries=["Secondary angle", "primary question", "Tertiary angle"],
            limit=1,
            max_iterations=3,
            min_context_packets=3,
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(retrieval.queries, ["Primary question", "Secondary angle", "Tertiary angle"])
        self.assertEqual(result["loop"]["retrieval_query_plan"], retrieval.queries)
        retrieve_steps = [step for step in result["loop"]["steps"] if step["name"] == "context.retrieve"]
        self.assertEqual([step["metadata"]["query"] for step in retrieve_steps], retrieval.queries)
        ask_request = service.state(result["run"]["run_id"]).metadata["ask_request"]
        self.assertEqual(ask_request["retrieval_queries"], ["Secondary angle", "Tertiary angle"])
        context_events = service.store.list_audit_events(action="context.retrieve")
        self.assertEqual([event.metadata["query"] for event in context_events], retrieval.queries)

    def test_durable_memory_patch_creates_review_even_when_caller_does_not_force_it(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember the review gate",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            create_review=False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertIsNotNone(result["review"])
        self.assertTrue(result["loop"]["review_required"])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        self.assertEqual(persisted_loop["governance"]["action"], "manual_review")
        self.assertTrue(persisted_loop["durable_proposal"])
        self.assertTrue(persisted_loop["review_required"])
        self.assertEqual(persisted_loop["review_id"], result["review"]["review_id"])
        self.assertEqual(len(service.store.list_reviews(status="pending")), 1)
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_memory_lifecycle_changes_are_not_agentic_question_proposal_kinds(self):
        service = build_fake_service()

        for proposal_kind in ["memory_delete", "memory_update"]:
            with self.subTest(proposal_kind=proposal_kind):
                with self.assertRaisesRegex(ValueError, "explicit memory fact"):
                    run_agentic_question(
                        service,
                        question="Change a memory somehow",
                        dataset_ids=["demo"],
                        proposal_kind=proposal_kind,
                    )

    def test_no_context_returns_insufficient_context_without_proposal(self):
        service = WorkflowService(
            retrieval=_NoContextRetrieval(),
            memory=FakeMemoryAdapter(),
            store=SQLiteReviewStore(":memory:"),
        )
        result = run_agentic_question(
            service,
            question="What is unsupported?",
            dataset_ids=["empty"],
            proposal_kind="memory_patch",
        )

        self.assertEqual(result["status"], "insufficient_context")
        self.assertEqual(result["context_packets"], [])
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIn("No context", result["message"])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        self.assertEqual(persisted_loop["status"], "insufficient_context")
        self.assertEqual(persisted_loop["governance"]["action"], "skip")
        self.assertEqual(persisted_loop["requested_governance_action"], "manual_review")
        self.assertEqual(persisted_loop["required_context_count"], 1)

    def test_partial_context_below_minimum_does_not_create_proposal(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Explain adapter boundaries",
            dataset_ids=["demo"],
            limit=1,
            max_iterations=1,
            min_context_packets=2,
            proposal_kind="memory_patch",
        )

        self.assertEqual(result["status"], "insufficient_context")
        self.assertEqual(len(result["context_packets"]), 1)
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertEqual(service.store.list_reviews(), [])
        self.assertIn("2 required", result["message"])

    def test_auto_accept_policy_accepts_review_without_applying_memory(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember the policy boundary",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_ACCEPT),
        )

        self.assertEqual(result["loop"]["governance"]["action"], AUTO_ACCEPT)
        self.assertEqual(result["review"]["status"], "accepted")
        self.assertEqual(result["review_decision"]["status"], "accepted")
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(service.memory_search("policy boundary"), [])

    def test_auto_apply_policy_applies_memory_after_accepted_review(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember automatic governed memory",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_APPLY),
        )

        self.assertEqual(result["loop"]["governance"]["action"], AUTO_APPLY)
        self.assertEqual(result["review"]["status"], "accepted")
        self.assertEqual(result["review_decision"]["status"], "accepted")
        self.assertTrue(result["memory_apply"]["applied"])
        self.assertEqual(len(service.memory_search("automatic governed memory")), 1)

    def test_reviewed_memory_influences_later_agentic_questions(self):
        service = build_fake_service()
        run_agentic_question(
            service,
            question="Remember reusable durable policy context",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_APPLY),
        )

        result = run_agentic_question(
            service,
            question="Use reusable durable policy context",
            dataset_ids=["demo"],
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["memory_facts"]), 1)
        expected_memory_source_count = len(result["memory_facts"][0]["source_refs"])
        self.assertEqual(result["artifact"]["traceability"]["memory_count"], 1)
        self.assertEqual(result["artifact"]["traceability"]["memory_source_count"], expected_memory_source_count)
        self.assertEqual(len(result["artifact"]["memory_source_manifest"]), expected_memory_source_count)
        self.assertEqual(result["artifact"]["memory_source_manifest"][0]["adapter"], "fake")
        self.assertEqual(result["artifact"]["memory_facts"][0]["fact_id"], result["memory_facts"][0]["fact_id"])
        self.assertIn("Durable workspace memory", result["proposal"]["body"])
        exported = service.export_brief(result["run"]["run_id"], "markdown")
        self.assertIn("## Durable Workspace Memory", exported)
        self.assertIn("| Source | Adapter | Dataset | Document | Chunk/Source |", exported)
        self.assertIn("| 1 | fake |", exported)
        exported_json = service.export_brief(result["run"]["run_id"], "json")
        self.assertEqual(exported_json["traceability"]["memory_source_count"], expected_memory_source_count)
        export_events = [
            event for event in service.store.list_audit_events() if event.action == "workflow.export"
        ]
        self.assertEqual(export_events[-1].metadata["memory_count"], 1)
        self.assertEqual(export_events[-1].metadata["memory_source_count"], expected_memory_source_count)
        memory_step = next(step for step in result["loop"]["steps"] if step["name"] == "memory.search")
        self.assertEqual(memory_step["metadata"]["returned_count"], 1)
        memory_search_events = [
            event for event in service.store.list_audit_events() if event.action == "memory.search"
        ]
        self.assertGreaterEqual(len(memory_search_events), 2)
        self.assertEqual(memory_search_events[-1].metadata["count"], 1)


if __name__ == "__main__":
    unittest.main()
