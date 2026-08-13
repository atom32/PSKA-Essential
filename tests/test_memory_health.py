from __future__ import annotations

import unittest

from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.memory_health import scan_memory_health
from pska_essential.workflow import build_fake_service


class MemoryHealthTests(unittest.TestCase):
    def test_memory_health_reports_quality_and_stale_issues(self):
        service = build_fake_service()
        service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-raw",
                    text="Raw memory missing envelope fields.",
                    source_refs=[],
                    metadata={"created_at": "2026-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="mem-stale",
                    text="The project is temporarily blocked on vendor review.",
                    source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                    metadata={
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "Check vendor review before planning release work.",
                        "refresh_rule": "review_after_date",
                        "review_after": "2000-01-01T00:00:00+00:00",
                    },
                ),
            ]
        )

        result = scan_memory_health(service, audit=False)
        issues = {issue["type"]: issue for issue in result["issues"]}

        self.assertEqual(result["schema"], "pska.memory_health.v1")
        self.assertEqual(result["summary"]["quality"], 1)
        self.assertEqual(result["summary"]["stale"], 1)
        self.assertEqual(issues["quality"]["memory_ids"], ["mem-raw"])
        self.assertEqual(issues["stale"]["memory_ids"], ["mem-stale"])
        self.assertEqual(result["next_actions"][0]["tool"], "pska_memory_health_scan")

    def test_memory_health_reports_conservative_pairwise_conflict(self):
        service = build_fake_service()
        service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-linux",
                    text="The project deployment target is Linux.",
                    source_refs=[SourceRef(adapter="fake", source_id="linux")],
                    metadata={
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "Assume Linux deployment target when planning infra.",
                        "display_text": "The project deployment target is Linux.",
                    },
                ),
                MemoryFact(
                    fact_id="mem-windows",
                    text="The project deployment target is Windows.",
                    source_refs=[SourceRef(adapter="fake", source_id="windows")],
                    metadata={
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "Assume Windows deployment target when planning infra.",
                        "display_text": "The project deployment target is Windows.",
                    },
                ),
            ]
        )

        result = scan_memory_health(service, issue_type="conflict", audit=False)

        self.assertEqual(result["issue_count"], 1)
        self.assertEqual(result["issues"][0]["type"], "conflict")
        self.assertEqual(set(result["issues"][0]["memory_ids"]), {"mem-linux", "mem-windows"})
        self.assertGreaterEqual(result["issues"][0]["evidence"]["relatedness"], 0.55)

    def test_memory_health_scan_writes_audit(self):
        service = build_fake_service()
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-raw",
                text="Raw memory missing envelope fields.",
                metadata={},
            )
        )

        scan_memory_health(service)

        event = service.store.list_audit_events(action="memory.health.scan")[0]
        self.assertEqual(event.metadata["quality_count"], 1)
        self.assertEqual(event.metadata["memory_ids"], ["mem-raw"])


if __name__ == "__main__":
    unittest.main()
