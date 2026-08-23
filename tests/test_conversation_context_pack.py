from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.conversation_context_pack import assemble_conversation_context_pack
from pska_essential.workflow import build_fake_service


class ConversationContextPackTests(unittest.TestCase):
    def test_context_pack_collects_sources_in_parallel_with_stable_output_order(self):
        service = build_fake_service()
        starts: dict[str, float] = {}

        def collector(block_type: str):
            def _collect(*args):
                warnings = args[-1]
                starts[block_type] = time.perf_counter()
                time.sleep(0.2)
                warnings.append({"code": f"{block_type}_test_warning", "message": block_type})
                block = {
                    "type": block_type,
                    "index": 1,
                    "title": f"{block_type} block",
                    "text": f"{block_type} context",
                    "score": 0.8,
                    "source_ref": {"adapter": block_type, "source_id": f"{block_type}-1"},
                    "metadata": {},
                }
                if block_type == "memory":
                    block["fact_id"] = "mem-parallel"
                    block["source_refs"] = [{"adapter": "memory", "source_id": "mem-source"}]
                return [block]

            return _collect

        with (
            patch("pska_essential.conversation_context_pack._memory_blocks", collector("memory")),
            patch("pska_essential.conversation_context_pack._conversation_blocks", collector("conversation")),
            patch("pska_essential.conversation_context_pack._evidence_blocks", collector("evidence")),
            patch("pska_essential.conversation_context_pack._source_blocks", collector("source")),
        ):
            started = time.perf_counter()
            response = assemble_conversation_context_pack(
                service,
                {
                    "caller": "hermes-webui-extension",
                    "user_message": "parallel PSKA context pack",
                    "mode": "project",
                    "scope": {"dataset_ids": ["demo"], "source_root_ids": ["root-demo"]},
                    "budget": {
                        "max_memory_notes": 2,
                        "max_conversation_blocks": 2,
                        "max_evidence_blocks": 2,
                        "max_source_blocks": 2,
                        "max_tokens": 3000,
                    },
                },
            )
            elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.65)
        self.assertEqual(set(starts), {"memory", "conversation", "evidence", "source"})
        self.assertLess(max(starts.values()) - min(starts.values()), 0.12)
        context_pack = response["context_pack"]
        self.assertEqual(
            [block["type"] for block in context_pack["blocks"]],
            ["memory", "conversation", "evidence", "source"],
        )
        self.assertEqual(context_pack["data_flow"]["control_plane"], "hermes_webui_extension")
        self.assertEqual(context_pack["data_flow"]["data_plane"], "pska")
        self.assertEqual(context_pack["data_flow"]["aggregation"], "parallel")
        self.assertEqual(context_pack["data_flow"]["prompt_context_rendered_by"], "pska")
        self.assertEqual(
            context_pack["data_flow"]["attempted_sources"],
            ["memory", "conversation", "evidence", "source"],
        )
        self.assertFalse(context_pack["data_flow"]["whole_recent_history_injected"])
        self.assertFalse(context_pack["data_flow"]["extension_reads_hermes_database"])
        self.assertEqual(context_pack["prompt_context_metadata"]["rendered_by"], "pska")
        self.assertIn("## PSKA Context Pack", context_pack["prompt_context_block"])
        self.assertIn("Flow: data-plane=pska", context_pack["prompt_context_block"])
        self.assertIn("History boundary: query recall=yes", context_pack["prompt_context_block"])
        self.assertIn("[memory recalled content]", context_pack["prompt_context_block"])
        self.assertIn("[conversation recalled content]", context_pack["prompt_context_block"])
        self.assertEqual(
            [warning["code"] for warning in context_pack["warnings"]],
            [
                "memory_test_warning",
                "conversation_test_warning",
                "evidence_test_warning",
                "source_test_warning",
            ],
        )

    def test_context_pack_filters_low_relevance_memory_from_answer_context(self):
        service = build_fake_service()
        service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-broad-pska",
                    text="用户长期维护 PSKA、Hermes Agent 和 Eidolia，并关注知识图谱和 RAG。",
                    source_refs=[SourceRef(adapter="test", source_id="broad")],
                    valid_at="2026-08-20T00:00:00+00:00",
                ),
                MemoryFact(
                    fact_id="mem-specific-review",
                    text="PSKA dogfooding 的 WebUI Review Detail 验证显示该候选仍为 pending，memory_apply=false。",
                    source_refs=[SourceRef(adapter="test", source_id="specific")],
                    valid_at="2026-08-19T00:00:00+00:00",
                ),
            ]
        )

        response = assemble_conversation_context_pack(
            service,
            {
                "caller": "hermes-webui-extension",
                "user_message": "PSKA dogfooding WebUI Review Detail pending memory_apply=false 说明了什么？",
                "mode": "memory-only",
                "conversation_recall": {"items": []},
                "budget": {
                    "max_memory_notes": 2,
                    "max_conversation_blocks": 0,
                    "max_evidence_blocks": 0,
                    "max_source_blocks": 0,
                    "max_tokens": 2000,
                },
            },
        )

        context_pack = response["context_pack"]
        self.assertEqual(context_pack["source_counts"]["memory"], 1)
        memory = context_pack["memory_notes"][0]
        self.assertEqual(memory["fact_id"], "mem-specific-review")
        self.assertIn("memory_apply=false", memory["text"])
        self.assertGreaterEqual(memory["metadata"]["context_relevance"]["score"], 1.8)
        self.assertIn("memory_context_relevance_filtered", [warning["code"] for warning in context_pack["warnings"]])

    def test_context_pack_keeps_memory_when_user_asks_about_memory(self):
        service = build_fake_service()
        service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-profile",
                    text="用户是徐大为，长期关注 PSKA、个人记忆和外部认知系统。",
                    source_refs=[SourceRef(adapter="test", source_id="profile")],
                    valid_at="2026-08-20T00:00:00+00:00",
                )
            ]
        )

        response = assemble_conversation_context_pack(
            service,
            {
                "caller": "hermes-webui-extension",
                "user_message": "你记得我什么？",
                "mode": "memory-only",
                "conversation_recall": {"items": []},
                "budget": {
                    "max_memory_notes": 1,
                    "max_conversation_blocks": 0,
                    "max_evidence_blocks": 0,
                    "max_source_blocks": 0,
                    "max_tokens": 1200,
                },
            },
        )

        context_pack = response["context_pack"]
        self.assertEqual(context_pack["source_counts"]["memory"], 1)
        memory = context_pack["memory_notes"][0]
        self.assertEqual(memory["fact_id"], "mem-profile")
        self.assertTrue(memory["metadata"]["context_relevance"]["bypassed"])
        self.assertNotIn("memory_context_relevance_filtered", [warning["code"] for warning in context_pack["warnings"]])

    def test_context_pack_filters_low_relevance_conversation_recall(self):
        service = build_fake_service()

        response = assemble_conversation_context_pack(
            service,
            {
                "caller": "hermes-webui-extension",
                "user_message": "PSKA dogfooding WebUI Review Detail pending memory_apply=false 说明了什么？",
                "mode": "memory-only",
                "conversation_recall": {
                    "items": [
                        {
                            "session_id": "sess-smoke",
                            "message_id": "msg-smoke",
                            "title": "PSKA smoke history import",
                            "role": "user",
                            "snippet": "请记住这个烟测标记，它应该作为普通 Hermes 对话历史被查询回来。",
                        },
                        {
                            "session_id": "sess-review",
                            "message_id": "msg-review",
                            "title": "PSKA dogfooding Review check",
                            "role": "assistant",
                            "snippet": "WebUI Review Detail 显示候选仍为 pending，memory_apply=false。",
                        },
                    ],
                },
                "budget": {
                    "max_memory_notes": 0,
                    "max_conversation_blocks": 2,
                    "max_evidence_blocks": 0,
                    "max_source_blocks": 0,
                    "max_tokens": 1200,
                },
            },
        )

        context_pack = response["context_pack"]
        self.assertEqual(context_pack["source_counts"]["conversation"], 1)
        conversation = context_pack["conversation_blocks"][0]
        self.assertEqual(conversation["source_ref"]["source_id"], "msg-review")
        self.assertIn("memory_apply=false", conversation["text"])
        self.assertIn(
            "conversation_context_relevance_filtered",
            [warning["code"] for warning in context_pack["warnings"]],
        )

    def test_project_context_pack_does_not_request_rag_evidence_without_kb_scope(self):
        service = build_fake_service()

        def fail_context_retrieve(*_args, **_kwargs):
            raise AssertionError("source-root-only context pack must not call RAG evidence retrieval")

        service.context_retrieve = fail_context_retrieve  # type: ignore[method-assign]

        response = assemble_conversation_context_pack(
            service,
            {
                "caller": "hermes-webui-extension",
                "user_message": "Use source roots only.",
                "mode": "project",
                "scope": {"source_root_ids": ["root-demo"]},
                "conversation_recall": {"items": []},
                "budget": {
                    "max_memory_notes": 0,
                    "max_conversation_blocks": 0,
                    "max_evidence_blocks": 3,
                    "max_source_blocks": 0,
                    "max_tokens": 1200,
                },
            },
        )

        context_pack = response["context_pack"]
        self.assertEqual(context_pack["source_counts"]["evidence"], 0)
        self.assertNotIn("evidence_retrieve_failed", [warning["code"] for warning in context_pack["warnings"]])


if __name__ == "__main__":
    unittest.main()
