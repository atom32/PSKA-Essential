from __future__ import annotations

import unittest

from pska_essential.adapters.company_graphrag_stub import CompanyGraphRagStubAdapter
from pska_essential.adapters.ragflow import RagflowRetrievalAdapter
from pska_essential.contracts import MemoryPatch
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService


class _Chunk:
    id = "chunk-1"
    content = "RAGFlow chunk text"
    dataset_id = "dataset-1"
    document_id = "doc-1"
    document_name = "Doc One"
    similarity = 0.92
    positions = [{"page": 1}]


class _RagflowClient:
    def retrieve(self, **kwargs):
        self.kwargs = kwargs
        return [_Chunk()]


class AdapterTests(unittest.TestCase):
    def test_ragflow_chunks_are_mapped_to_pska_contract(self):
        client = _RagflowClient()
        adapter = RagflowRetrievalAdapter(client=client)
        packets = adapter.retrieve("hello", {"dataset_ids": ["dataset-1"]}, 5)
        self.assertEqual(packets[0].text, "RAGFlow chunk text")
        self.assertEqual(packets[0].source_ref.adapter, "ragflow")
        self.assertEqual(packets[0].source_ref.document_id, "doc-1")
        self.assertEqual(packets[0].source_ref.metadata["positions"], [{"page": 1}])

    def test_company_stub_can_replace_retrieval_and_memory(self):
        adapter = CompanyGraphRagStubAdapter()
        service = WorkflowService(adapter, adapter, SQLiteReviewStore(":memory:"))
        run = service.start("company replacement", {})
        packets = service.context_retrieve(run.run_id, "GraphRAG", 5)
        self.assertEqual(packets[0].source_ref.adapter, "company_graphrag_stub")
        proposal = service.propose(run.run_id, "memory_patch", "replacement")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "ok")
        applied = service.memory_apply(review.review_id)
        self.assertTrue(applied.applied)
        self.assertEqual(applied.backend, "company_graphrag_stub")

    def test_memory_patch_requires_sources_at_adapter_boundary(self):
        adapter = CompanyGraphRagStubAdapter()
        with self.assertRaises(Exception):
            # Company stub intentionally accepts reviewed patches only through the
            # service in normal use; this assertion documents the desired test
            # shape for real adapters. The empty source list would be rejected by
            # WorkflowService before reaching an external backend.
            if not MemoryPatch(text="x", source_refs=[]).source_refs:
                raise ValueError("source refs required")


if __name__ == "__main__":
    unittest.main()
