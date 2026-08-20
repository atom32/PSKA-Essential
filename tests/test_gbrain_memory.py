from __future__ import annotations

import json
import unittest

from pska_essential.adapters.gbrain import GBrainAdapterError, GBrainHttpMemoryAdapter
from pska_essential.adapters.gbrain.memory import _parse_mcp_response
from pska_essential.contracts import MemoryDelete, MemoryPatch, SourceRef


class _FakeCaller:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GBrainMemoryAdapterTests(unittest.TestCase):
    def test_search_maps_recall_facts_and_results_to_memory_facts(self):
        caller = _FakeCaller(
            [
                {
                    "protocol_version": 1,
                    "facts": [
                        {
                            "fact_id": "42",
                            "fact": "User prefers review-gated PSKA memory.",
                            "kind": "preference",
                            "entity_slug": "people/user",
                            "provenance": "pska_review:review-1",
                            "valid_from": "2026-08-19T00:00:00Z",
                        }
                    ],
                    "results": [
                        {
                            "slug": "notes/pska",
                            "title": "PSKA notes",
                            "chunk": "PSKA keeps durable writes behind review.",
                            "evidence": "keyword_exact",
                            "create_safety": "exists",
                            "provenance": "notes/pska.md",
                        }
                    ],
                    "search_degraded": "keyword_only_no_embedding_provider",
                }
            ]
        )
        adapter = GBrainHttpMemoryAdapter(mcp_url="http://127.0.0.1:33333/mcp", token="t", caller=caller)

        facts = adapter.search("review gate", {"gbrain_entity": "people/user"}, 5)

        self.assertEqual(caller.calls[0][0], "recall")
        self.assertEqual(caller.calls[0][1]["query"], "review gate")
        self.assertEqual(caller.calls[0][1]["entity"], "people/user")
        self.assertEqual(facts[0].fact_id, "42")
        self.assertEqual(facts[0].text, "User prefers review-gated PSKA memory.")
        self.assertEqual(facts[0].source_refs[0].adapter, "gbrain")
        self.assertEqual(facts[0].metadata["search_degraded"], "keyword_only_no_embedding_provider")
        self.assertEqual(facts[1].fact_id, "gbrain_result:notes/pska")
        self.assertEqual(facts[1].source_refs[0].title, "PSKA notes")

    def test_apply_calls_remember_with_review_provenance(self):
        caller = _FakeCaller([{"id": "77", "status": "inserted", "status_text": "remembered"}])
        adapter = GBrainHttpMemoryAdapter(mcp_url="http://127.0.0.1:33333/mcp", token="t", caller=caller)
        patch = MemoryPatch(
            text="PSKA should keep GBrain behind governed adapters.",
            source_refs=[SourceRef(adapter="hermes", source_id="turn-1", title="Conversation turn")],
            metadata={
                "review_id": "review-1",
                "proposal_id": "proposal-1",
                "run_id": "run-1",
                "gbrain_entity": "projects/pska",
                "gbrain_kind": "belief",
                "gbrain_visibility": "private",
                "gbrain_ttl": "30d",
            },
        )

        result = adapter.apply(patch)

        tool_name, payload = caller.calls[0]
        self.assertEqual(tool_name, "remember")
        self.assertEqual(payload["fact"], patch.text)
        self.assertEqual(payload["entity"], "projects/pska")
        self.assertEqual(payload["kind"], "belief")
        self.assertEqual(payload["visibility"], "private")
        self.assertEqual(payload["ttl"], "30d")
        self.assertIn("pska_review:review-1", payload["provenance"])
        self.assertIn("proposal:proposal-1", payload["provenance"])
        self.assertTrue(result.applied)
        self.assertEqual(result.backend, "gbrain")
        self.assertEqual(result.target_id, "77")

    def test_delete_uses_protocol_forget_and_falls_back_to_legacy_forget_fact(self):
        caller = _FakeCaller(
            [
                GBrainAdapterError("GBrain MCP forget failed: unknown_tool"),
                {"id": "42", "expired": True, "reason": "cleanup"},
            ]
        )
        adapter = GBrainHttpMemoryAdapter(mcp_url="http://127.0.0.1:33333/mcp", token="t", caller=caller)
        delete = MemoryDelete(
            target_id="42",
            source_refs=[SourceRef(adapter="review", source_id="review-1", title="Accepted review")],
            reason="cleanup",
        )

        result = adapter.delete(delete)

        self.assertEqual([name for name, _args in caller.calls], ["forget", "forget_fact"])
        self.assertEqual(caller.calls[0][1]["id"], "42")
        self.assertEqual(caller.calls[1][1]["id"], 42)
        self.assertTrue(result.applied)
        self.assertTrue(result.metadata["used_forget_fact_fallback"])

    def test_mcp_tool_text_response_parser_returns_json_payload(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps({"id": "1", "status": "inserted"})}]},
            }
        )

        self.assertEqual(_parse_mcp_response(raw, "remember"), {"id": "1", "status": "inserted"})


if __name__ == "__main__":
    unittest.main()
