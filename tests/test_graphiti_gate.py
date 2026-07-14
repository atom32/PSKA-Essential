from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.graphiti import GraphitiMemoryAdapter
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService


class _GraphitiClient:
    def __init__(self):
        self.episodes = []

    def add_episode(self, **kwargs):
        self.episodes.append(kwargs)

    def search(self, **kwargs):
        return []


class GraphitiGateTests(unittest.TestCase):
    def test_graphiti_add_episode_is_only_called_after_review_acceptance(self):
        graphiti = _GraphitiClient()
        service = WorkflowService(
            retrieval=FakeRetrievalAdapter(),
            memory=GraphitiMemoryAdapter(client=graphiti, group_id="test-group"),
            store=SQLiteReviewStore(":memory:"),
        )
        run = service.start("graphiti gate", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "graphiti patch")
        review = service.review_create(proposal.proposal_id)

        with self.assertRaises(WorkflowError):
            service.memory_apply(review.review_id)
        self.assertEqual(graphiti.episodes, [])

        service.review_decide(review.review_id, "accept", "approved")
        result = service.memory_apply(review.review_id)
        self.assertTrue(result.applied)
        self.assertEqual(len(graphiti.episodes), 1)
        self.assertEqual(graphiti.episodes[0]["group_id"], "test-group")


if __name__ == "__main__":
    unittest.main()
