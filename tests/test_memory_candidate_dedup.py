from __future__ import annotations

import unittest

from pska_essential.contracts import SourceRef
from pska_essential.memory_candidate_dedup import build_memory_candidate_dedup
from pska_essential.workflow import build_fake_service


class MemoryCandidateDedupTests(unittest.TestCase):
    def test_groups_near_duplicate_source_route_reviews_without_embeddings(self):
        service = build_fake_service()
        ref = SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")
        first = service.source_memory_review_create(
            [ref],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route one",
        )
        second = service.source_memory_review_create(
            [ref],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route two",
        )
        service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="identity", path="Identity.md")],
            text="The user prefers concise memory review summaries.",
            memory_type="preference",
            behavior_delta="Keep memory review summaries concise.",
            memory_scope="project",
            reason="different type",
        )

        result = build_memory_candidate_dedup(service, audit=False)

        self.assertEqual(result["schema"], "pska.memory_candidate_dedup.v1")
        self.assertEqual(result["status"], "review")
        self.assertEqual(result["summary"]["candidate_count"], 3)
        self.assertEqual(result["summary"]["group_count"], 1)
        group = result["groups"][0]
        self.assertEqual(group["schema"], "pska.memory_candidate_dedup_group.v1")
        self.assertEqual(group["memory_type"], "source_route")
        self.assertEqual(group["memory_scope"], "project")
        self.assertIn("near_text", group["match_types"])
        self.assertIn("architecture.md", group["shared_paths"])
        self.assertEqual(
            {item["review_id"] for item in group["items"]},
            {first["review"]["review_id"], second["review"]["review_id"]},
        )
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["embedding_required"])

    def test_writes_audit_without_memory_writes(self):
        service = build_fake_service()

        result = build_memory_candidate_dedup(service)

        self.assertEqual(result["status"], "ready")
        event = service.store.list_audit_events(action="memory.candidate_dedup")[0]
        self.assertEqual(event.metadata["group_count"], 0)
        self.assertFalse(event.metadata["writes_memory_directly"])
        self.assertFalse(event.metadata["embedding_required"])


if __name__ == "__main__":
    unittest.main()
