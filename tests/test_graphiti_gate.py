from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.graphiti import GraphitiMemoryAdapter
from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService


class _GraphitiClient:
    def __init__(self):
        self.episodes = []
        self.deleted_edges = []

    def add_episode(self, **kwargs):
        self.episodes.append(kwargs)

    def search(self, **kwargs):
        return []

    def delete_entity_edge(self, uuid):
        self.deleted_edges.append(uuid)


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

    def test_graphiti_delete_entity_edge_is_only_called_after_review_acceptance(self):
        graphiti = _GraphitiClient()
        service = WorkflowService(
            retrieval=FakeRetrievalAdapter(),
            memory=GraphitiMemoryAdapter(client=graphiti, group_id="test-group"),
            store=SQLiteReviewStore(":memory:"),
        )
        fact = MemoryFact(
            fact_id="edge-1",
            text="outdated reviewed fact",
            source_refs=[SourceRef(adapter="fake", dataset_id="demo", document_id="doc-1")],
        )
        result = service.memory_delete_review(fact, "reviewed delete")
        review_id = result["review"]["review_id"]

        with self.assertRaises(WorkflowError):
            service.memory_apply(review_id)
        self.assertEqual(graphiti.deleted_edges, [])

        service.review_decide(review_id, "accept", "approved")
        deleted = service.memory_apply(review_id)
        self.assertTrue(deleted.applied)
        self.assertEqual(deleted.backend, "graphiti")
        self.assertEqual(deleted.target_id, "edge-1")
        self.assertEqual(deleted.metadata["operation"], "delete")
        self.assertEqual(graphiti.deleted_edges, ["edge-1"])

    def test_graphiti_update_review_fails_before_creating_dead_review(self):
        graphiti = _GraphitiClient()
        service = WorkflowService(
            retrieval=FakeRetrievalAdapter(),
            memory=GraphitiMemoryAdapter(client=graphiti, group_id="test-group"),
            store=SQLiteReviewStore(":memory:"),
        )
        fact = MemoryFact(
            fact_id="edge-1",
            text="reviewed fact",
            source_refs=[SourceRef(adapter="fake", dataset_id="demo", document_id="doc-1")],
        )

        with self.assertRaisesRegex(WorkflowError, "memory update is not supported by graphiti"):
            service.memory_update_review(fact, "updated fact", "reviewed update")

        self.assertEqual(service.store.list_reviews(), [])


if __name__ == "__main__":
    unittest.main()
