from __future__ import annotations

import unittest

from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.memory_review_queue import build_memory_review_queue
from pska_essential.workflow import build_fake_service


class MemoryReviewQueueTests(unittest.TestCase):
    def test_queue_groups_reviews_health_and_focus_items(self):
        service = build_fake_service()
        run = service.start("Remember reviewed memory", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "review queue memory", 1)
        proposal = service.propose(run.run_id, "memory_patch", "review queue memory")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "ready")
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-raw",
                text="Raw memory missing envelope fields.",
                metadata={},
            )
        )
        service.memory.facts.append(
            MemoryFact(
                fact_id="mem-route",
                text="Use PSKA docs first.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route PSKA questions to docs first.",
                    "display_text": "Use PSKA docs first.",
                },
            )
        )
        service.memory_search("PSKA docs", {}, 10)
        ref = SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")
        first_duplicate = service.source_memory_review_create(
            [ref],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route one",
        )
        service.source_memory_review_create(
            [ref],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route two",
        )

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["schema"], "pska.memory_review_queue.v1")
        self.assertEqual(queue["status"], "apply_ready")
        self.assertEqual(groups["accepted_unapplied"]["items"][0]["review_id"], review.review_id)
        self.assertIn("duplicate_candidates", groups)
        self.assertIn(first_duplicate["review"]["review_id"], groups["duplicate_candidates"]["items"][0]["review_ids"])
        self.assertIn("memory_health", groups)
        self.assertIn("memory_focus", groups)
        self.assertFalse(queue["data_flow"]["writes_memory_directly"])
        self.assertEqual(queue["next_actions"][0]["tool"], "pska_memory_apply")

    def test_queue_writes_audit(self):
        service = build_fake_service()

        build_memory_review_queue(service)

        event = service.store.list_audit_events(action="memory.review_queue")[0]
        self.assertEqual(event.metadata["status"], "ready")
        self.assertFalse(event.metadata["writes_memory_directly"])


if __name__ == "__main__":
    unittest.main()
