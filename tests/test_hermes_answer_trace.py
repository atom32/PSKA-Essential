from __future__ import annotations

import hashlib
import unittest

from pska_essential.hermes_answer_trace import list_hermes_answer_proofs, record_hermes_answer_proof
from pska_essential.trace_query import build_trace_query
from pska_essential.workflow import build_fake_service


class HermesAnswerTraceTests(unittest.TestCase):
    def test_records_answer_side_tool_proof_as_audit_metadata(self):
        service = build_fake_service()

        result = record_hermes_answer_proof(
            service,
            session_id="sess-1",
            response_id="resp-1",
            caller="webui-extension-llm-proof",
            question="请基于 Northstar Robotics Q2 资料说明风险。",
            answer_preview="收入增长很好，但现金流、库存和未交付订单显示了履约与资金压力。",
            answer_length=36,
            dataset_ids=["ds-q2"],
            source_root_ids=["root-northstar"],
            source_refs=[
                {
                    "adapter": "ragflow",
                    "dataset_id": "ds-q2",
                    "document_id": "doc-q2",
                    "chunk_id": "chunk-7",
                }
            ],
            proof_summary={
                "tool_names": [
                    "mcp__pska_essential__pska_source_search",
                    "mcp__pska_essential__pska_memory_search",
                ],
                "completed_pska_tools": [
                    "mcp__pska_essential__pska_source_search",
                    "mcp__pska_essential__pska_memory_search",
                ],
                "tool_events": [
                    {
                        "type": "tool",
                        "name": "mcp__pska_essential__pska_source_search",
                        "args_preview": '{"query":"Northstar Q2"}',
                    },
                    {
                        "type": "tool_complete",
                        "name": "mcp__pska_essential__pska_source_search",
                        "is_error": False,
                    },
                ],
            },
            checks=[{"name": "Answer-side turn stayed read-only", "ok": True}],
            metadata={"used_memory_ids": ["mem-risk-model"]},
        )

        self.assertEqual(result["schema"], "pska.hermes_answer_proof.v1")
        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["proof"]["read_only"])
        self.assertFalse(result["proof"]["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["proof"]["data_flow"]["writes_source_files"])
        self.assertEqual(result["proof"]["answer"]["length"], 36)
        self.assertFalse(result["proof"]["answer"]["stored_full_text"])

        events = service.store.list_audit_events(action="hermes.answer_proof")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.target_type, "hermes_turn")
        self.assertEqual(event.metadata["session_id"], "sess-1")
        self.assertEqual(event.metadata["dataset_ids"], ["ds-q2"])
        self.assertEqual(event.metadata["metadata"]["used_memory_ids"], ["mem-risk-model"])
        self.assertFalse(event.metadata["stores_full_answer"])

    def test_lists_and_trace_queries_answer_proofs(self):
        service = build_fake_service()
        question = "这一轮回答用了哪些 PSKA 工具？"
        recorded = record_hermes_answer_proof(
            service,
            session_id="sess-2",
            question=question,
            answer_preview="它使用了来源检索和记忆检索。",
            dataset_ids=["ds-trace"],
            source_root_ids=["root-trace"],
            proof_summary={
                "tool_names": ["pska_source_search"],
                "completed_pska_tools": ["pska_source_search"],
                "write_like_tools": [],
            },
            metadata={"used_memory_ids": ["mem-trace"]},
        )

        listed = list_hermes_answer_proofs(service, session_id="sess-2", audit=False)
        self.assertEqual(listed["status"], "found")
        self.assertEqual(listed["proof_count"], 1)
        self.assertEqual(
            listed["proofs"][0]["question"]["sha256"],
            hashlib.sha256(question.encode("utf-8")).hexdigest(),
        )

        action_trace = build_trace_query(service, action="hermes.answer_proof", audit=False)
        self.assertEqual(action_trace["status"], "found")
        self.assertEqual(action_trace["entries"][0]["evidence"]["action"], "hermes.answer_proof")

        source_trace = build_trace_query(
            service,
            source_ref={"adapter": "ragflow", "dataset_id": "ds-trace"},
            audit=False,
        )
        self.assertEqual(source_trace["status"], "found")
        self.assertEqual(source_trace["entries"][0]["evidence"]["action"], "hermes.answer_proof")

        memory_trace = build_trace_query(service, memory_id="mem-trace", audit=False)
        self.assertEqual(memory_trace["status"], "found")
        self.assertEqual(memory_trace["entries"][0]["evidence"]["action"], "hermes.answer_proof")

        proof = recorded["proof"]
        self.assertEqual(proof["tool_summary"]["completed_pska_tools"], ["pska_source_search"])
        self.assertFalse(proof["data_flow"]["stores_full_question"])


if __name__ == "__main__":
    unittest.main()
