from __future__ import annotations

import time
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
