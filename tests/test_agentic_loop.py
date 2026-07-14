from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeMemoryAdapter
from pska_essential.agentic_loop import run_agentic_question
from pska_essential.contracts import SourceContext
from pska_essential.governance import AUTO_ACCEPT, AUTO_APPLY, WorkspaceGovernancePolicy
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService, build_fake_service


class _NoContextRetrieval:
    backend_name = "none"

    def retrieve(self, query, scope, limit, options=None):
        return []

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="", metadata={"missing": True})


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
        self.assertEqual(service.store.list_reviews(), [])

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
        self.assertEqual(len(service.store.list_reviews(status="pending")), 1)

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


if __name__ == "__main__":
    unittest.main()
