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

    def test_export_brief_uses_workflow_context(self):
        service = build_fake_service()
        run = service.start("brief workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        brief = service.export_brief(run.run_id, "markdown")
        self.assertIn("PSKA-Essential Brief", brief)
        self.assertIn("Source:", brief)

    def test_smoke_eval(self):
        service = build_fake_service()
        result = service.eval_run("smoke")
        self.assertTrue(result["ok"])
        self.assertTrue(result["blocked_before_review"])


if __name__ == "__main__":
    unittest.main()
