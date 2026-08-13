from __future__ import annotations

import unittest

from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.memory_cards import get_memory_card, list_memory_cards
from pska_essential.memory_use_trace import explain_memory_why_used, list_memory_use_traces
from pska_essential.workflow import build_fake_service


class MemoryUseTraceTests(unittest.TestCase):
    def test_memory_search_audit_records_returned_fact_ids_for_trace(self):
        service = build_fake_service()
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-editor",
                text="The user's editor is VS Code.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "preference",
                    "memory_scope": "global",
                    "behavior_delta": "Prefer VS Code when discussing editor workflows.",
                    "display_text": "The user's editor is VS Code.",
                },
            )
        )

        service.memory_search(
            "editor",
            {},
            5,
            trace_context={
                "caller": "unit-test",
                "run_id": "run-trace",
                "purpose": "answer_context",
            },
        )
        trace = list_memory_use_traces(service, memory_id="mem-editor", audit=False)

        self.assertEqual(trace["schema"], "pska.memory_use_trace.v1")
        self.assertEqual(trace["count"], 1)
        self.assertEqual(trace["traces"][0]["action"], "memory.search")
        self.assertEqual(trace["traces"][0]["returned_fact_ids"], ["mem-editor"])
        self.assertEqual(trace["traces"][0]["memory_ids"], ["mem-editor"])
        self.assertEqual(trace["traces"][0]["caller"], "unit-test")
        self.assertEqual(trace["traces"][0]["run_id"], "run-trace")
        self.assertEqual(trace["traces"][0]["purpose"], "answer_context")

    def test_why_used_combines_card_metadata_with_recent_trace(self):
        service = build_fake_service()
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-source-route",
                text="Use PSKA architecture notes before broad search.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route PSKA architecture questions to the architecture notes first.",
                    "display_text": "PSKA architecture questions should start from the architecture notes.",
                },
            )
        )

        service.memory_search("PSKA architecture", {}, 5)
        result = explain_memory_why_used(service, "mem-source-route", audit=False)

        self.assertEqual(result["schema"], "pska.memory_why_used.v1")
        self.assertEqual(result["confidence"], "candidate_retrieval")
        self.assertEqual(result["trace_count"], 1)
        self.assertIn("PSKA architecture", result["explanation"])
        self.assertEqual(result["card"]["memory_type"], "source_route")

    def test_card_list_and_get_events_are_traceable(self):
        service = build_fake_service()
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-card",
                text="Card trace test memory.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={"memory_type": "project_state", "memory_scope": "workspace"},
            )
        )

        list_memory_cards(service, limit=10)
        get_memory_card(service, "mem-card")
        trace = list_memory_use_traces(service, memory_id="mem-card", audit=False)

        self.assertEqual([item["action"] for item in trace["traces"]], ["memory.card.get", "memory.card.list"])
        self.assertEqual(trace["traces"][0]["memory_ids"], ["mem-card"])
        self.assertEqual(trace["traces"][1]["memory_ids"], ["mem-card"])


if __name__ == "__main__":
    unittest.main()
