from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.graphiti import GraphitiMemoryAdapter
from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService


class _GraphitiClient:
    def __init__(self):
        self.episodes = []
        self.deleted_edges = []
        self.searches = []

    def add_episode(self, **kwargs):
        self.episodes.append(kwargs)

    def search(self, **kwargs):
        self.searches.append(kwargs)
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

    def test_graphiti_group_id_uses_runtime_memory_namespace_when_configured(self):
        graphiti = _GraphitiClient()
        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-a", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            service = WorkflowService(
                retrieval=FakeRetrievalAdapter(),
                memory=GraphitiMemoryAdapter(client=graphiti, group_id="test-group"),
                store=SQLiteReviewStore(":memory:"),
            )
            run = service.start("graphiti scoped gate", {"dataset_ids": ["demo"]})
            service.context_retrieve(run.run_id, "memory review", 1)
            proposal = service.propose(run.run_id, "memory_patch", "graphiti scoped patch")
            review = service.review_create(proposal.proposal_id)
            service.review_decide(review.review_id, "accept", "approved")

            result = service.memory_apply(review.review_id)
            service.memory_search("graphiti scoped patch", {}, 10)

        expected_group_id = "test-group:workspace:workspace-a:tenant:tenant-a"
        self.assertTrue(result.applied)
        self.assertEqual(graphiti.episodes[0]["group_id"], expected_group_id)
        self.assertEqual(result.metadata["group_id"], expected_group_id)
        self.assertEqual(graphiti.searches[0]["group_ids"], [expected_group_id])

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
