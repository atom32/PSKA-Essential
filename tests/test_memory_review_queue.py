from __future__ import annotations

import unittest

from pska_essential.contracts import MemoryFact, MemoryPatch, Proposal, SourceRef
from pska_essential.memory_review_queue import build_memory_review_queue
from pska_essential.workflow import build_fake_service


class MemoryReviewQueueTests(unittest.TestCase):
    def test_queue_groups_reviews_health_and_focus_items(self):
        service = build_fake_service()
        review = service.source_memory_review_create(
            [SourceRef(adapter="fake", source_id="review-queue-memory")],
            text="PSKA review queue memory should be applied only after Memory Card quality is explicit.",
            memory_type="working_habit",
            behavior_delta="When applying review queue memory, require explicit Memory Card fields first.",
            memory_scope="project",
            reason="qualified candidate",
        )["review"]
        service.review_decide(review["review_id"], "accept", "ready")
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
        self.assertEqual(groups["accepted_unapplied"]["items"][0]["review_id"], review["review_id"])
        self.assertIn("duplicate_candidates", groups)
        self.assertIn(first_duplicate["review"]["review_id"], groups["duplicate_candidates"]["items"][0]["review_ids"])
        duplicate_item = groups["duplicate_candidates"]["items"][0]
        self.assertEqual(len(duplicate_item["candidate_items"]), 2)
        self.assertIn("PSKA architecture", duplicate_item["candidate_items"][0]["title"])
        self.assertIn("Route", duplicate_item["candidate_items"][0]["reason"])
        self.assertIn("memory_health", groups)
        self.assertIn("memory_focus", groups)
        self.assertFalse(queue["data_flow"]["writes_memory_directly"])
        self.assertEqual(queue["next_actions"][0]["tool"], "pska_memory_apply")

    def test_queue_surfaces_memory_candidate_quality_issues_before_apply(self):
        service = build_fake_service()
        run = service.start("Remember vague memory", {"dataset_ids": ["demo"]})
        source_ref = SourceRef(adapter="fake", source_id="quality-source")
        proposal = Proposal(
            proposal_id="prop_queue_low_quality_memory",
            run_id=run.run_id,
            kind="memory_patch",
            intent="unsafe memory",
            title="Memory Patch: unsafe memory",
            body="remember this",
            source_refs=[source_ref],
            memory_patch=MemoryPatch(text="remember this", source_refs=[source_ref]),
        )
        service.store.save_proposal(proposal)
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "ready")

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["status"], "action_required")
        self.assertEqual(queue["summary"]["accepted_unapplied_count"], 0)
        self.assertEqual(queue["summary"]["candidate_quality_issue_count"], 1)
        self.assertEqual(
            queue["summary"]["candidate_quality_breakdown"]["issue_types"],
            {"missing_memory_card_fields": 1, "vague_candidate_text": 1},
        )
        self.assertEqual(
            queue["summary"]["candidate_quality_breakdown"]["missing_fields"],
            {"behavior_delta": 1, "memory_scope": 1, "memory_type": 1},
        )
        self.assertEqual(queue["summary"]["candidate_quality_breakdown"]["top_issue_type"], "missing_memory_card_fields")
        self.assertEqual(queue["summary"]["candidate_quality_breakdown"]["top_missing_field"], "behavior_delta")
        self.assertIn("candidate_quality", groups)
        item = groups["candidate_quality"]["items"][0]
        self.assertEqual(item["review_id"], review.review_id)
        self.assertEqual(item["status"], "accepted")
        self.assertEqual(item["text"], "remember this")
        self.assertEqual(item["missing_fields"], ["memory_type", "memory_scope", "behavior_delta"])
        self.assertIn("missing_memory_card_fields", item["issue_types"])
        self.assertIn("vague_candidate_text", item["issue_types"])
        self.assertEqual(item["next_actions"][0]["action"], "review_memory_candidate_quality")
        self.assertEqual(queue["next_actions"][0]["action"], "review_memory_candidate_quality")

    def test_queue_quality_issue_can_mark_pending_candidate_needs_edit(self):
        service = build_fake_service()
        run = service.start("Remember vague pending memory", {"dataset_ids": ["demo"]})
        source_ref = SourceRef(adapter="fake", source_id="quality-source")
        proposal = Proposal(
            proposal_id="prop_queue_pending_low_quality_memory",
            run_id=run.run_id,
            kind="memory_patch",
            intent="unsafe memory",
            title="Memory Patch: unsafe memory",
            body="remember this",
            source_refs=[source_ref],
            memory_patch=MemoryPatch(text="remember this", source_refs=[source_ref]),
        )
        service.store.save_proposal(proposal)
        review = service.review_create(proposal.proposal_id)

        queue = build_memory_review_queue(service, audit=False)

        self.assertEqual(queue["summary"]["candidate_quality_issue_count"], 1)
        self.assertEqual(queue["next_actions"][0]["action"], "review_memory_candidate_quality")
        self.assertEqual(queue["next_actions"][1]["action"], "mark_memory_candidate_needs_edit")
        self.assertEqual(queue["next_actions"][1]["params"]["review_id"], review.review_id)

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
        self.assertEqual(len(item["candidate_items"]), 2)
        self.assertEqual(item["next_actions"][0]["action"], "inspect_related_memory_candidates")

    def test_queue_tracks_merged_replacements_without_needs_edit_work(self):
        service = build_fake_service()
        first = service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md first.",
            memory_scope="project",
            reason="route one",
        )
        second = service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture-v2", path="Architecture.md")],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md first.",
            memory_scope="project",
            reason="route two",
        )
        review_ids = [first["review"]["review_id"], second["review"]["review_id"]]

        merged = service.review_merge_candidates(
            review_ids,
            memory_candidate={
                "text": "When this workspace asks about PSKA architecture, inspect Architecture.md first.",
                "memory_type": "source_route",
                "memory_scope": "project",
                "behavior_delta": "Route future PSKA architecture questions to Architecture.md first.",
            },
            reason="merge duplicate route candidates",
        )

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["summary"]["needs_edit_count"], 0)
        self.assertEqual(queue["summary"]["merged_replacement_count"], 2)
        self.assertEqual(queue["summary"]["actionable_item_count"], 1)
        self.assertNotIn("needs_edit", groups)
        self.assertIn("merged_replacements", groups)
        replacement = groups["merged_replacements"]["items"][0]
        self.assertEqual(replacement["item_type"], "merged_candidate_replacement")
        self.assertIn(replacement["review_id"], review_ids)
        self.assertEqual(replacement["merged_into_review_id"], merged["review"]["review_id"])
        self.assertEqual(replacement["next_actions"][0]["action"], "open_merged_review")
        self.assertEqual(replacement["next_actions"][0]["params"]["review_id"], merged["review"]["review_id"])
        self.assertEqual(groups["pending_reviews"]["review_ids"], [merged["review"]["review_id"]])

    def test_queue_tracks_revised_replacements_without_needs_edit_work(self):
        service = build_fake_service()
        result = service.conversation_memory_candidates_create(
            session_id="sess-revised-replacement",
            messages=[
                {
                    "message_id": "msg-revised-replacement",
                    "role": "user",
                    "text": "For PSKA memory, revised candidates should not leave stale needs_edit queue work.",
                }
            ],
            candidates=[
                {
                    "text": "PSKA revised candidates should be traceable without stale queue work.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When revising PSKA memory candidates, keep old reviews traceable but out of active needs_edit.",
                    "message_ids": ["msg-revised-replacement"],
                }
            ],
        )
        review_id = result["created"][0]["review_id"]
        service.review_decide(review_id, "edit", "make it more direct")
        revised = service.review_revise(
            review_id,
            "rewrite candidate",
            memory_candidate={
                "text": "For PSKA memory, keep revised old reviews out of active needs_edit queues.",
                "memory_type": "working_habit",
                "memory_scope": "project",
                "behavior_delta": "When a PSKA memory candidate is revised, route reviewers to the successor review instead of the old needs_edit item.",
            },
        )

        queue = build_memory_review_queue(service, audit=False)
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(queue["summary"]["needs_edit_count"], 0)
        self.assertEqual(queue["summary"]["revised_replacement_count"], 1)
        self.assertNotIn("needs_edit", groups)
        self.assertIn("revised_replacements", groups)
        replacement = groups["revised_replacements"]["items"][0]
        self.assertEqual(replacement["item_type"], "revised_candidate_replacement")
        self.assertEqual(replacement["review_id"], review_id)
        self.assertEqual(replacement["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(replacement["next_actions"][0]["action"], "open_revised_review")
        self.assertEqual(replacement["next_actions"][0]["params"]["review_id"], revised["review"]["review_id"])

    def test_queue_writes_audit(self):
        service = build_fake_service()

        build_memory_review_queue(service)

        event = service.store.list_audit_events(action="memory.review_queue")[0]
        self.assertEqual(event.metadata["status"], "ready")
        self.assertFalse(event.metadata["writes_memory_directly"])


if __name__ == "__main__":
    unittest.main()
