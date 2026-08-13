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

    def test_queue_surfaces_conversation_memory_candidates(self):
        service = build_fake_service()
        created = service.conversation_memory_candidates_create(
            session_id="sess-review-queue",
            messages=[
                {
                    "message_id": "msg-review-queue",
                    "role": "user",
                    "text": "For PSKA memory, conversation candidates need behavior deltas and evidence.",
                }
            ],
            candidates=[
                {
                    "text": "PSKA conversation memory candidates need behavior deltas and evidence.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When creating conversation memory candidates, include behavior deltas and evidence.",
                    "message_ids": ["msg-review-queue"],
                }
            ],
        )

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["status"], "action_required")
        self.assertEqual(queue["summary"]["conversation_candidate_count"], 1)
        self.assertIn("conversation_candidates", groups)
        item = groups["conversation_candidates"]["items"][0]
        self.assertEqual(item["item_type"], "conversation_memory_candidate")
        self.assertEqual(item["review_id"], created["created"][0]["review_id"])
        self.assertEqual(item["memory_type"], "working_habit")
        self.assertEqual(item["memory_scope"], "project")
        self.assertEqual(item["message_ids"], ["msg-review-queue"])
        self.assertEqual(item["next_actions"][0]["action"], "review_conversation_memory_candidate")
        self.assertEqual(groups["conversation_candidates"]["review_ids"], [created["created"][0]["review_id"]])
        self.assertEqual(groups["conversation_candidates"]["batch_actions"][0]["tool"], "pska_review_decide_batch")
        self.assertEqual(groups["conversation_candidates"]["batch_actions"][0]["params"]["decision"], "accept")
        self.assertEqual(groups["conversation_candidates"]["batch_actions"][1]["params"]["decision"], "reject")
        self.assertEqual(queue["next_actions"][0]["action"], "review_conversation_memory_candidate")
        self.assertEqual(queue["next_actions"][0]["tool"], "pska_review_get")

    def test_queue_surfaces_related_scope_candidate_groups(self):
        service = build_fake_service()
        service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-global", title="Conversation")],
            text="The user prefers concise memory review summaries.",
            memory_type="preference",
            behavior_delta="Keep memory review summaries concise.",
            memory_scope="global",
            reason="global preference candidate",
        )
        service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-project", title="Conversation")],
            text="For PSKA, the user prefers concise memory review summaries.",
            memory_type="preference",
            behavior_delta="Keep PSKA memory review summaries concise.",
            memory_scope="project",
            reason="project preference candidate",
        )

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["summary"]["related_candidate_group_count"], 1)
        self.assertIn("related_candidates", groups)
        item = groups["related_candidates"]["items"][0]
        self.assertEqual(item["item_type"], "memory_candidate_related_group")
        self.assertEqual(item["memory_type"], "preference")
        self.assertEqual(item["memory_scopes"], ["global", "project"])
        self.assertEqual(item["next_actions"][0]["action"], "inspect_related_memory_candidates")

    def test_queue_writes_audit(self):
        service = build_fake_service()

        build_memory_review_queue(service)

        event = service.store.list_audit_events(action="memory.review_queue")[0]
        self.assertEqual(event.metadata["status"], "ready")
        self.assertFalse(event.metadata["writes_memory_directly"])


if __name__ == "__main__":
    unittest.main()
