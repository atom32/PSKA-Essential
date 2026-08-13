from __future__ import annotations

import unittest

from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.memory_timeline import build_memory_timeline
from pska_essential.workflow import build_fake_service


class MemoryTimelineTests(unittest.TestCase):
    def test_timeline_combines_card_lifecycle_usage_and_sources(self):
        service = build_fake_service()
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-route",
                text="Use the PSKA architecture note before broad source search.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route PSKA questions to the architecture note first.",
                    "display_text": "PSKA questions should start from the architecture note.",
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
        )
        service.memory_search(
            "PSKA architecture",
            {},
            5,
            trace_context={"caller": "unit-test", "run_id": "run-timeline", "purpose": "answer_context"},
        )

        result = build_memory_timeline(service, "mem-route", audit=False)
        entry_types = [entry["type"] for entry in result["entries"]]

        self.assertEqual(result["schema"], "pska.memory_timeline.v1")
        self.assertEqual(result["memory_id"], "mem-route")
        self.assertIn("card_snapshot", entry_types)
        self.assertIn("usage_trace", entry_types)
        self.assertIn("source_anchor", entry_types)
        self.assertEqual(result["summary"]["usage_trace_count"], 1)
        self.assertEqual(result["summary"]["source_anchor_count"], 1)
        self.assertEqual(result["entries"][-1]["type"], "usage_trace")
        self.assertEqual(result["entries"][-1]["evidence"]["caller"], "unit-test")

    def test_timeline_records_audit_event(self):
        service = build_fake_service()
        service.memory.facts.append(MemoryFact(fact_id="mem-audit", text="Timeline audit memory."))

        result = build_memory_timeline(service, "mem-audit")

        audit = service.store.list_audit_events(action="memory.timeline")[0]
        self.assertEqual(audit.target_id, "mem-audit")
        self.assertEqual(audit.metadata["entry_count"], result["entry_count"])


if __name__ == "__main__":
    unittest.main()
