from __future__ import annotations

import unittest
from unittest.mock import patch

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.contracts import ContextPacket, MemoryFact, MemoryPatch, Proposal, SourceContext, SourceRef
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService, build_fake_service


class _RecordingRetrieval:
    backend_name = "recording"

    def __init__(self) -> None:
        self.options = None

    def retrieve(self, query, scope, limit, options=None):
        self.options = options
        return [
            ContextPacket(
                context_id="ctx-recording",
                text="Recorded retrieval",
                source_ref=SourceRef(adapter=self.backend_name, dataset_id="demo", document_id="doc-1"),
            )
        ]

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="Recorded retrieval")


class WorkflowTests(unittest.TestCase):
    def test_fake_adapter_e2e_blocks_memory_until_review(self):
        service = build_fake_service()
        run = service.start("test workflow", {"dataset_ids": ["demo"]})
        packets = service.context_retrieve(run.run_id, "adapter memory review", 2)
        self.assertGreaterEqual(len(packets), 1)

        proposal = service.propose(run.run_id, "memory_patch", "remember reviewed workflow")
        review = service.review_create(proposal.proposal_id)

        with self.assertRaises(WorkflowError):
            service.memory_apply(review.review_id)

        decision = service.review_decide(review.review_id, "accept", "approved in test")
        self.assertEqual(decision.status, "accepted")
        result = service.memory_apply(review.review_id)
        self.assertTrue(result.applied)
        applied_again = service.memory_apply(review.review_id)
        self.assertEqual(applied_again.target_id, result.target_id)

        facts = service.memory_search("reviewed workflow", {}, 10)
        self.assertEqual(len(facts), 1)
        events = service.store.list_audit_events()
        review_create = next(event for event in events if event.action == "review.create")
        review_decide = next(event for event in events if event.action == "review.decide")
        memory_apply = next(event for event in events if event.action == "memory.apply")
        self.assertEqual(review_create.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(review_create.metadata["run_id"], run.run_id)
        self.assertEqual(review_create.metadata["source_count"], len(proposal.source_refs))
        self.assertEqual(review_decide.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(review_decide.metadata["proposal_kind"], "memory_patch")
        self.assertEqual(memory_apply.metadata["proposal_id"], proposal.proposal_id)
        self.assertEqual(memory_apply.metadata["run_id"], run.run_id)
        self.assertEqual(memory_apply.metadata["proposal_kind"], "memory_patch")
        self.assertEqual(memory_apply.metadata["source_count"], len(proposal.source_refs))
        self.assertEqual(memory_apply.metadata["source_refs"][0]["adapter"], "fake")

        with self.assertRaisesRegex(WorkflowError, "after durable memory has been applied"):
            service.review_decide(review.review_id, "reject", "too late")
        self.assertEqual(service.store.get_review(review.review_id)["status"], "accepted")
        review_decide_events = [
            event for event in service.store.list_audit_events() if event.action == "review.decide"
        ]
        self.assertEqual(len(review_decide_events), 1)

    def test_memory_patch_body_is_compact_even_with_large_context(self):
        corpus = [
            {
                "id": f"doc-{index}",
                "title": f"Large Source {index}",
                "text": f"Important source-backed point {index}. " + ("raw source dump " * 400),
            }
            for index in range(1, 6)
        ]
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            FakeMemoryAdapter(),
            SQLiteReviewStore(":memory:"),
        )
        run = service.start("large context memory", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "source-backed point", 5)

        proposal = service.propose(run.run_id, "memory_patch", "remember compact memory")

        self.assertEqual(proposal.body, proposal.memory_patch.text)
        self.assertLessEqual(len(proposal.memory_patch.text), 1600)
        self.assertIn("Reviewed memory candidate for: remember compact memory", proposal.memory_patch.text)
        self.assertIn("Evidence source count: 5", proposal.memory_patch.text)
        self.assertIn("Evidence summary:", proposal.memory_patch.text)
        self.assertEqual(len(proposal.memory_patch.source_refs), 5)
        self.assertNotIn("Large Source 4", proposal.memory_patch.text)

    def test_memory_delete_requires_review_and_deactivates_fact(self):
        service = build_fake_service()
        run = service.start("delete workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember deletion target")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "approved")
        applied = service.memory_apply(review.review_id)
        facts = service.memory_search("deletion target", {}, 10)
        self.assertEqual(facts[0].fact_id, applied.target_id)

        delete_result = service.memory_delete_review(facts[0], "outdated")
        delete_review_id = delete_result["review"]["review_id"]
        self.assertEqual(delete_result["proposal"]["kind"], "memory_delete")
        self.assertEqual(delete_result["proposal"]["memory_delete"]["target_id"], applied.target_id)
        with self.assertRaises(WorkflowError):
            service.memory_apply(delete_review_id)

        service.review_decide(delete_review_id, "accept", "delete approved")
        deletion = service.memory_apply(delete_review_id)

        self.assertTrue(deletion.applied)
        self.assertEqual(deletion.target_id, applied.target_id)
        self.assertEqual(deletion.metadata["operation"], "delete")
        self.assertEqual(service.memory_search("deletion target", {}, 10), [])
        memory_delete = next(event for event in service.store.list_audit_events() if event.action == "memory.delete")
        self.assertEqual(memory_delete.metadata["proposal_kind"], "memory_delete")
        self.assertEqual(memory_delete.metadata["memory_target_id"], applied.target_id)
        self.assertEqual(memory_delete.metadata["source_count"], 1)

    def test_memory_update_requires_review_and_versions_fact(self):
        service = build_fake_service()
        run = service.start("update workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter memory review", 1)
        proposal = service.propose(run.run_id, "memory_patch", "remember obsoletephrase")
        review = service.review_create(proposal.proposal_id)
        service.review_decide(review.review_id, "accept", "approved")
        applied = service.memory_apply(review.review_id)
        facts = service.memory_search("obsoletephrase", {}, 10)
        self.assertEqual(facts[0].fact_id, applied.target_id)

        update_result = service.memory_update_review(facts[0], "Reviewed durable memory target", "better wording")
        update_review_id = update_result["review"]["review_id"]
        self.assertEqual(update_result["proposal"]["kind"], "memory_update")
        self.assertEqual(update_result["proposal"]["memory_update"]["target_id"], applied.target_id)
        self.assertEqual(update_result["artifact"]["traceability"]["source_count"], 1)
        self.assertEqual(update_result["artifact"]["source_manifest"][0]["origin"], "proposal")
        self.assertEqual(update_result["artifact"]["source_manifest"][0]["source_ref"]["adapter"], "fake")
        with self.assertRaises(WorkflowError):
            service.memory_apply(update_review_id)

        service.review_decide(update_review_id, "accept", "update approved")
        updated = service.memory_apply(update_review_id)

        self.assertTrue(updated.applied)
        self.assertEqual(updated.target_id, applied.target_id)
        self.assertEqual(updated.metadata["operation"], "update")
        self.assertEqual(updated.metadata["version"], 2)
        self.assertEqual(service.memory_search("obsoletephrase", {}, 10), [])
        updated_facts = service.memory_search("durable memory target", {}, 10)
        self.assertEqual(updated_facts[0].text, "Reviewed durable memory target")
        self.assertEqual(updated_facts[0].metadata["version"], 2)
        self.assertEqual(updated_facts[0].metadata["versions"][0]["text"], proposal.memory_patch.text)
        memory_update = next(event for event in service.store.list_audit_events() if event.action == "memory.update")
        self.assertEqual(memory_update.metadata["proposal_kind"], "memory_update")
        self.assertEqual(memory_update.metadata["memory_target_id"], applied.target_id)
        self.assertEqual(memory_update.metadata["version"], 2)
        lifecycle = service.memory_lifecycle(applied.target_id)
        self.assertEqual(lifecycle["change_count"], 2)
        self.assertEqual([event["action"] for event in lifecycle["events"]], ["memory.apply", "memory.update"])
        self.assertEqual(lifecycle["latest_event"]["action"], "memory.update")

    def test_conversation_memory_change_auto_applies_remember_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            result = service.memory_change_from_conversation(
                user_message="Remember that I prefer AMD CPUs.",
                text="The user prefers AMD CPUs.",
                session_id="sess-1",
                message_id="msg-1",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["operation"], "memory_patch")
        self.assertEqual(result["governance"]["origin"], "conversation")
        self.assertEqual(result["governance"]["action"], "auto_apply")
        self.assertEqual(result["review"]["status"], "accepted")
        self.assertEqual(result["proposal"]["metadata"]["origin"], "conversation")
        self.assertEqual(result["proposal"]["source_refs"][0]["adapter"], "hermes")
        self.assertEqual(result["memory_apply"]["backend"], "fake")
        self.assertEqual(service.store.list_reviews(status="pending"), [])
        facts = service.memory_search("AMD CPUs", {}, 10)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].text, "The user prefers AMD CPUs.")
        self.assertEqual(facts[0].metadata["origin"], "conversation")
        self.assertIn("created_at", facts[0].metadata)
        self.assertIn("observed_at", facts[0].metadata)
        self.assertIn("applied_at", facts[0].metadata)
        self.assertEqual(facts[0].metadata["triage"]["route"], "conversation_policy")
        self.assertFalse(facts[0].metadata["triage"]["review_recommended"])
        event = next(event for event in service.store.list_audit_events() if event.action == "memory.conversation_change")
        self.assertEqual(event.metadata["operation"], "memory_patch")
        self.assertEqual(event.metadata["status"], "applied")

    def test_low_confidence_conversation_memory_stays_conversation_native(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            result = service.memory_change_from_conversation(
                user_message="Maybe remember that I may prefer Linux laptops.",
                text="The user may prefer Linux laptops.",
                confidence=0.5,
                session_id="sess-low-confidence",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["governance"]["action"], "auto_apply")
        triage = result["proposal"]["memory_patch"]["metadata"]["triage"]
        self.assertEqual(triage["route"], "conversation_policy")
        self.assertFalse(triage["review_recommended"])
        self.assertGreaterEqual(triage["uncertainty"], 0.5)
        facts = service.memory_search("Linux laptops", {}, 10)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].metadata["confidence"], 0.5)
        self.assertEqual(service.store.list_reviews(status="pending"), [])

    def test_conversation_memory_change_can_force_review(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            result = service.memory_change_from_conversation(
                user_message="Maybe remember this uncertain long-term preference.",
                text="The user may prefer uncertain long-term preference.",
                force_review=True,
            )

        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["governance"]["action"], "manual_review")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(len(service.store.list_reviews(status="pending")), 1)
        self.assertEqual(service.memory_search("uncertain", {}, 10), [])

    def test_conversation_memory_candidates_create_review_items_without_memory_writes(self):
        service = build_fake_service()
        result = service.conversation_memory_candidates_create(
            session_id="sess-candidates",
            messages=[
                {
                    "message_id": "msg-1",
                    "role": "user",
                    "text": "For PSKA memory design, keep behavior_delta explicit and avoid vague personality summaries.",
                }
            ],
            candidates=[
                {
                    "text": "For PSKA memory design, memory candidates should include explicit behavior_delta rather than vague personality summaries.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When proposing PSKA memory changes, include concrete behavior_delta and avoid vague personality summaries.",
                    "reason": "stable memory design preference",
                    "message_ids": ["msg-1"],
                }
            ],
        )

        self.assertEqual(result["schema"], "pska.conversation_memory_candidates.v1")
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["skipped_count"], 0)
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertTrue(result["data_flow"]["creates_review"])
        self.assertEqual(service.memory_search("behavior_delta", {}, 10), [])
        review = service.store.get_review_record(result["created"][0]["review_id"])
        self.assertEqual(review["status"], "pending")
        self.assertEqual(review["proposal"]["memory_patch"]["metadata"]["candidate_origin"], "conversation_candidate")
        self.assertEqual(review["proposal"]["memory_patch"]["metadata"]["memory_type"], "working_habit")
        self.assertEqual(review["proposal"]["source_refs"][0]["adapter"], "hermes")
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("memory.conversation_candidates.create", actions)

    def test_memory_candidate_revision_can_edit_candidate_fields(self):
        service = build_fake_service()
        result = service.conversation_memory_candidates_create(
            session_id="sess-candidates",
            messages=[
                {
                    "message_id": "msg-1",
                    "role": "user",
                    "text": "For PSKA memory design, prefer exact behavior deltas.",
                }
            ],
            candidates=[
                {
                    "text": "The user prefers exact behavior deltas for PSKA memory design.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When proposing PSKA memories, include exact behavior deltas.",
                    "message_ids": ["msg-1"],
                }
            ],
        )
        review_id = result["created"][0]["review_id"]
        service.review_decide(review_id, "edit", "make it less generic")

        revised = service.review_revise(
            review_id,
            "manual candidate rewrite",
            memory_candidate={
                "text": "For PSKA, remember only concrete memory rules that change future behavior.",
                "memory_type": "preference",
                "memory_scope": "workspace",
                "behavior_delta": "When reviewing PSKA memory candidates, reject vague summaries and keep concrete behavior rules.",
                "confidence": 0.91,
            },
        )

        proposal = Proposal.from_dict(revised["proposal"])
        self.assertEqual(revised["previous_review"]["status"], "needs_edit")
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertEqual(proposal.memory_patch.text, "For PSKA, remember only concrete memory rules that change future behavior.")
        self.assertEqual(proposal.memory_patch.confidence, 0.91)
        self.assertEqual(proposal.memory_patch.metadata["memory_type"], "preference")
        self.assertEqual(proposal.memory_patch.metadata["memory_scope"], "workspace")
        self.assertEqual(
            proposal.memory_patch.metadata["behavior_delta"],
            "When reviewing PSKA memory candidates, reject vague summaries and keep concrete behavior rules.",
        )
        self.assertEqual(proposal.memory_patch.metadata["revision_mode"], "memory_candidate")
        self.assertEqual(proposal.memory_patch.metadata["revision_of_proposal_id"], result["created"][0]["proposal_id"])
        self.assertEqual(proposal.memory_patch.source_refs[0].adapter, "hermes")
        audit = next(event for event in service.store.list_audit_events() if event.action == "review.revise")
        self.assertEqual(audit.metadata["revision_mode"], "memory_candidate")

    def test_conversation_memory_candidates_dedupe_existing_review(self):
        service = build_fake_service()
        payload = {
            "session_id": "sess-candidates",
            "messages": [{"message_id": "msg-1", "text": "Prefer concise PSKA review summaries."}],
            "candidates": [
                {
                    "text": "The user prefers concise PSKA review summaries.",
                    "memory_type": "preference",
                    "memory_scope": "project",
                    "behavior_delta": "Keep PSKA review summaries concise.",
                    "message_ids": ["msg-1"],
                }
            ],
        }

        first = service.conversation_memory_candidates_create(**payload)
        second = service.conversation_memory_candidates_create(**payload)

        self.assertEqual(first["created_count"], 1)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["skipped"][0]["reason"], "existing_review")

    def test_sourced_memory_candidate_includes_review_triage_metadata(self):
        corpus = [
            {
                "id": "uncertain-doc",
                "title": "Uncertain Source",
                "text": "Maybe the project prefers a Linux-first developer environment.",
            }
        ]
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            FakeMemoryAdapter(),
            SQLiteReviewStore(":memory:"),
        )
        run = service.start("triage sourced extraction", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "Linux-first", 1)

        proposal = service.propose(run.run_id, "memory_patch", "remember environment preference")

        metadata = proposal.memory_patch.metadata
        self.assertEqual(metadata["origin"], "durable")
        self.assertIn("created_at", metadata)
        self.assertIn("observed_at", metadata)
        self.assertEqual(metadata["source_count"], 1)
        triage = metadata["triage"]
        self.assertEqual(triage["route"], "manual_review")
        self.assertTrue(triage["review_recommended"])
        self.assertIn("maybe", triage["uncertainty_markers"])

    def test_sourced_memory_candidate_probes_existing_memory_conflicts(self):
        corpus = [
            {
                "id": "deployment-doc",
                "title": "Deployment Note",
                "text": "The project deployment target is Windows now.",
            }
        ]
        memory = FakeMemoryAdapter()
        memory.facts.append(
            MemoryFact(
                fact_id="existing-deployment",
                text="The project deployment target is Linux.",
                source_refs=[SourceRef(adapter="fake", source_id="old-deployment")],
                metadata={"created_at": "2025-01-01T00:00:00+00:00"},
            )
        )
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            memory,
            SQLiteReviewStore(":memory:"),
        )
        run = service.start("deployment conflict", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "deployment target", 1)

        proposal = service.propose(run.run_id, "memory_patch", "remember deployment target")

        probe = proposal.metadata["memory_conflict_probe"]
        self.assertEqual(probe["related_count"], 1)
        self.assertGreaterEqual(probe["max_conflict_score"], 0.6)
        self.assertEqual(probe["candidates"][0]["fact_id"], "existing-deployment")
        self.assertEqual(proposal.metadata["triage"]["route"], "manual_review")
        self.assertTrue(proposal.metadata["triage"]["review_recommended"])
        event = service.store.list_audit_events(action="memory.conflict_probe")[0]
        self.assertEqual(event.metadata["related_count"], 1)

    def test_memory_review_auto_apply_is_overridden_by_conflict_triage(self):
        corpus = [
            {
                "id": "deployment-doc",
                "title": "Deployment Note",
                "text": "The project deployment target is Windows now.",
            }
        ]
        memory = FakeMemoryAdapter()
        memory.facts.append(
            MemoryFact(
                fact_id="existing-deployment",
                text="The project deployment target is Linux.",
                source_refs=[SourceRef(adapter="fake", source_id="old-deployment")],
                metadata={"created_at": "2025-01-01T00:00:00+00:00"},
            )
        )
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            memory,
            SQLiteReviewStore(":memory:"),
        )
        run = service.start("deployment conflict", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "deployment target", 1)

        with patch.dict("os.environ", {"PSKA_GOVERNANCE_DURABLE_MEMORY": "auto_apply"}, clear=True):
            result = service.memory_review_from_workflow(run.run_id, "remember deployment target")

        self.assertEqual(result["governance"]["requested_action"], "auto_apply")
        self.assertEqual(result["governance"]["action"], "manual_review")
        self.assertTrue(result["governance"]["triage_override"])
        self.assertEqual(result["review"]["status"], "pending")
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(len(memory.facts), 1)

    def test_memory_conflict_probe_ignores_superseded_temporal_memory(self):
        corpus = [
            {
                "id": "deployment-doc",
                "title": "Deployment Note",
                "text": "The project deployment target is Windows now.",
            }
        ]
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-deployment",
                    text="The project deployment target is Linux.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-deployment")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-deployment",
                    text="The project deployment target is Windows now.",
                    source_refs=[SourceRef(adapter="fake", source_id="new-deployment")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-deployment",
                    },
                ),
            ]
        )
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            memory,
            SQLiteReviewStore(":memory:"),
        )
        run = service.start("deployment current fact", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "deployment target", 1)

        with patch.dict("os.environ", {"PSKA_GOVERNANCE_DURABLE_MEMORY": "auto_apply"}, clear=True):
            result = service.memory_review_from_workflow(run.run_id, "remember deployment target")

        self.assertEqual(result["governance"]["requested_action"], "auto_apply")
        self.assertEqual(result["governance"]["action"], "auto_apply")
        self.assertFalse(result["governance"]["triage_override"])
        probe = result["proposal"]["metadata"]["memory_conflict_probe"]
        self.assertEqual(probe["superseded_fact_ids"], ["old-deployment"])
        self.assertLess(probe["max_conflict_score"], 0.6)
        self.assertEqual([candidate["fact_id"] for candidate in probe["candidates"]], ["new-deployment"])
        event = service.store.list_audit_events(action="memory.conflict_probe")[0]
        self.assertEqual(event.metadata["superseded_fact_ids"], ["old-deployment"])

    def test_memory_search_prefers_newer_temporal_memory(self):
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old",
                    text="The project deploys on Linux laptops.",
                    source_refs=[SourceRef(adapter="fake", source_id="old")],
                    metadata={"created_at": "2024-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new",
                    text="The project deploys on Linux laptops.",
                    source_refs=[SourceRef(adapter="fake", source_id="new")],
                    metadata={"created_at": "2026-01-01T00:00:00+00:00"},
                ),
            ]
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        facts = service.memory_search("Linux laptops", {}, 10)

        self.assertEqual([fact.fact_id for fact in facts], ["new", "old"])

    def test_memory_search_filters_superseded_temporal_memory_by_default(self):
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text="The user's editor is VS Code.",
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        facts = service.memory_search("editor", {}, 10)

        self.assertEqual([fact.fact_id for fact in facts], ["new-editor"])
        event = service.store.list_audit_events(action="memory.search")[0]
        self.assertEqual(event.metadata["raw_count"], 2)
        self.assertEqual(event.metadata["superseded_count"], 1)
        self.assertEqual(event.metadata["superseded_fact_ids"], ["old-editor"])

    def test_memory_search_old_term_can_return_searchable_correction_episode(self):
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text=(
                        "Memory correction episode.\n"
                        "Current fact: The user's editor is VS Code.\n"
                        "Previous fact: The user's editor is Vim.\n"
                        "Supersedes memory fact: old-editor"
                    ),
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                        "previous_text": "The user's editor is Vim.",
                    },
                ),
            ]
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        facts = service.memory_search("Vim", {}, 10)

        self.assertEqual([fact.fact_id for fact in facts], ["new-editor"])
        self.assertIn("Current fact: The user's editor is VS Code.", facts[0].text)
        event = service.store.list_audit_events(action="memory.search")[0]
        self.assertEqual(event.metadata["superseded_fact_ids"], ["old-editor"])

    def test_memory_search_can_include_superseded_memory_for_diagnostics(self):
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text="The user's editor is VS Code.",
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        facts = service.memory_search("editor", {"include_superseded_memory": True}, 10)

        self.assertEqual([fact.fact_id for fact in facts], ["new-editor", "old-editor"])
        event = service.store.list_audit_events(action="memory.search")[0]
        self.assertTrue(event.metadata["include_superseded"])
        self.assertEqual(event.metadata["superseded_fact_ids"], ["old-editor"])

    def test_conversation_memory_change_updates_and_deletes_existing_fact(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            created = service.memory_change_from_conversation(
                user_message="Remember my laptop is a ThinkPad.",
                text="The user's laptop is a ThinkPad.",
                message_id="msg-create",
            )
            fact = service.memory_search("ThinkPad", {}, 10)[0]
            updated = service.memory_change_from_conversation(
                user_message="Correction: my laptop is a Framework, not a ThinkPad.",
                operation="correct",
                text="The user's laptop is a Framework.",
                memory_fact=fact,
                message_id="msg-update",
            )
            updated_fact = service.memory_search("Framework", {}, 10)[0]
            deleted = service.memory_change_from_conversation(
                user_message="Forget that laptop fact.",
                operation="forget",
                memory_fact=updated_fact,
                message_id="msg-delete",
            )

        self.assertEqual(created["status"], "applied")
        self.assertEqual(updated["status"], "applied")
        self.assertEqual(updated["operation"], "memory_update")
        self.assertEqual(updated["review"]["status"], "accepted")
        self.assertEqual(updated_fact.text, "The user's laptop is a Framework.")
        self.assertEqual(updated_fact.metadata["version"], 2)
        self.assertEqual(deleted["status"], "applied")
        self.assertEqual(deleted["operation"], "memory_delete")
        self.assertEqual(service.memory_search("Framework", {}, 10), [])
        lifecycle = service.memory_lifecycle(updated_fact.fact_id)
        self.assertEqual([event["action"] for event in lifecycle["events"]], ["memory.apply", "memory.update", "memory.delete"])

    def test_conversation_auto_forget_resolves_existing_fact_without_memory_fact(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            created = service.memory_change_from_conversation(
                user_message="Remember my laptop is a ThinkPad.",
                text="The user's laptop is a ThinkPad.",
                message_id="msg-auto-delete-create",
            )
            deleted = service.memory_change_from_conversation(
                user_message="Forget that my laptop is a ThinkPad.",
                operation="auto",
                message_id="msg-auto-delete",
            )

        self.assertEqual(created["status"], "applied")
        self.assertEqual(deleted["status"], "applied")
        self.assertEqual(deleted["operation"], "memory_delete")
        self.assertEqual(deleted["target_resolution"]["status"], "resolved")
        self.assertEqual(
            deleted["target_resolution"]["selected_fact_id"],
            created["memory_apply"]["target_id"],
        )
        self.assertEqual(service.memory_search("ThinkPad", {}, 10), [])
        self.assertEqual(service.store.list_reviews(status="pending"), [])

    def test_conversation_forget_without_target_returns_needs_target(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            result = service.memory_change_from_conversation(
                user_message="Forget that my favorite tea is oolong.",
                operation="forget",
                message_id="msg-missing-target",
            )

        self.assertEqual(result["status"], "needs_target")
        self.assertEqual(result["operation"], "memory_delete")
        self.assertEqual(result["governance"]["action"], "needs_target")
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(result["target_resolution"]["status"], "not_found")
        self.assertEqual(result["next_actions"][0]["tool"], "pska_memory_search")
        self.assertEqual(service.memory_search("oolong", {}, 10), [])
        self.assertEqual(service.store.list_reviews(status="pending"), [])

    def test_conversation_auto_correction_resolves_existing_fact_without_memory_fact(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            created = service.memory_change_from_conversation(
                user_message="Remember that my editor is Vim.",
                text="The user's editor is Vim.",
                message_id="msg-editor-create",
            )
            updated = service.memory_change_from_conversation(
                user_message="Correction: my editor is VS Code, not Vim.",
                operation="auto",
                text="The user's editor is VS Code.",
                message_id="msg-editor-update",
            )

        self.assertEqual(created["status"], "applied")
        self.assertEqual(updated["status"], "applied")
        self.assertEqual(updated["operation"], "memory_update")
        self.assertEqual(updated["target_resolution"]["status"], "resolved")
        self.assertEqual(
            updated["target_resolution"]["selected_fact_id"],
            created["memory_apply"]["target_id"],
        )
        self.assertEqual(service.memory_search("Vim", {}, 10), [])
        facts = service.memory_search("Code", {}, 10)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].metadata["version"], 2)

    def test_conversation_target_resolution_ignores_superseded_temporal_memory(self):
        memory = FakeMemoryAdapter()
        memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text="The user's editor is VS Code.",
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        with patch.dict("os.environ", {}, clear=True):
            result = service.memory_change_from_conversation(
                user_message="Correction: my editor is Emacs, not VS Code.",
                operation="auto",
                text="The user's editor is Emacs.",
                message_id="msg-editor-second-correction",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["operation"], "memory_update")
        self.assertEqual(result["target_resolution"]["status"], "resolved")
        self.assertEqual(result["target_resolution"]["selected_fact_id"], "new-editor")
        self.assertEqual(result["target_resolution"]["superseded_fact_ids"], ["old-editor"])
        facts = service.memory_search("editor", {}, 10)
        self.assertEqual([fact.fact_id for fact in facts], ["new-editor"])
        self.assertEqual(facts[0].text, "The user's editor is Emacs.")

    def test_conversation_correction_requires_explicit_append_strategy_when_update_unsupported(self):
        class NoUpdateMemory:
            backend_name = "no_update"
            memory_capabilities = {"search": True, "apply": True, "update": False, "delete": True}

            def search(self, query, scope, limit):
                return []

            def apply(self, reviewed_patch):
                raise AssertionError("unsupported update must not be silently written as memory_patch")

            def update(self, reviewed_update):
                raise AssertionError("unsupported update must be blocked before adapter update")

            def delete(self, reviewed_delete):
                raise AssertionError("delete is not part of this test")

        fact = MemoryFact(
            fact_id="editor-old",
            text="The user's editor is Vim.",
            source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
        )
        service = WorkflowService(FakeRetrievalAdapter(), NoUpdateMemory(), SQLiteReviewStore(":memory:"))

        with self.assertRaisesRegex(WorkflowError, "memory update is not supported by no_update"):
            service.memory_change_from_conversation(
                user_message="Correction: my editor is VS Code, not Vim.",
                operation="correct",
                text="The user's editor is VS Code.",
                memory_fact=fact,
            )

        self.assertEqual(service.store.list_reviews(), [])

    def test_durable_memory_review_acceptance_and_apply_require_source_trace(self):
        service = build_fake_service()
        run = service.start("source trace gate", {"dataset_ids": ["demo"]})
        proposal = Proposal(
            proposal_id="prop_source_less_memory",
            run_id=run.run_id,
            kind="memory_patch",
            intent="unsafe memory",
            title="Memory Patch: unsafe memory",
            body="source-less durable memory",
            source_refs=[],
            memory_patch=MemoryPatch(text="source-less durable memory", source_refs=[]),
        )
        service.store.save_proposal(proposal)

        with self.assertRaisesRegex(WorkflowError, "review creation requires source refs"):
            service.review_create(proposal.proposal_id)

        review = service.store.create_review(proposal.proposal_id)
        service.review_decide(review.review_id, "reject", "source trace missing")
        self.assertEqual(service.store.get_review(review.review_id)["status"], "rejected")

        bypassed = service.store.create_review(proposal.proposal_id)
        with self.assertRaisesRegex(WorkflowError, "review acceptance requires source refs"):
            service.review_decide(bypassed.review_id, "accept", "unsafe accept")

        service.store.decide_review(bypassed.review_id, "accept", "bypassed service gate")
        with self.assertRaisesRegex(WorkflowError, "memory apply requires source refs"):
            service.memory_apply(bypassed.review_id)

    def test_export_brief_uses_workflow_context(self):
        service = build_fake_service()
        run = service.start("brief workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        proposal = service.propose(run.run_id, "writing_brief", "explain adapter boundaries")

        brief = service.export_brief(run.run_id, "markdown")
        self.assertIn("PSKA-Essential Brief", brief)
        self.assertIn("Export audit event:", brief)
        self.assertIn("Export format: `markdown`", brief)
        self.assertIn("## Work Product", brief)
        self.assertIn(proposal.body, brief)
        self.assertIn("## Source Manifest", brief)
        self.assertIn("| # | Title | Adapter | Dataset | Document | Chunk/Source | Score |", brief)
        self.assertIn("## Supporting Context", brief)
        self.assertIn("Source [1]:", brief)

        json_export = service.export_brief(run.run_id, "json")
        self.assertEqual(json_export["latest_proposal"]["proposal_id"], proposal.proposal_id)
        self.assertEqual(json_export["traceability"]["context_count"], 1)
        self.assertEqual(json_export["traceability"]["proposal_count"], 1)
        self.assertEqual(json_export["traceability"]["source_count"], 1)
        self.assertEqual(json_export["traceability"]["export"]["action"], "workflow.export")
        self.assertEqual(json_export["traceability"]["export"]["target_id"], run.run_id)
        self.assertEqual(json_export["traceability"]["export"]["format"], "json")
        self.assertEqual(json_export["source_manifest"][0]["source_ref"]["adapter"], "fake")

        export_events = [
            event for event in service.store.list_audit_events() if event.action == "workflow.export"
        ]
        self.assertEqual(len(export_events), 2)
        self.assertEqual(
            json_export["traceability"]["export"]["audit_event_id"],
            export_events[-1].audit_event_id,
        )

    def test_export_requires_sourced_work_product(self):
        service = build_fake_service()
        empty = service.start("empty workflow", {"dataset_ids": ["demo"]})
        with self.assertRaisesRegex(WorkflowError, "sourced work product"):
            service.export_brief(empty.run_id, "markdown")

        retrieved = service.start("retrieval only workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(retrieved.run_id, "adapter", 1)
        with self.assertRaisesRegex(WorkflowError, "create a proposal"):
            service.export_brief(retrieved.run_id, "markdown")

        service.propose(retrieved.run_id, "writing_brief", "now exportable")
        exported = service.export_brief(retrieved.run_id, "markdown")
        self.assertIn("PSKA-Essential Brief", exported)

    def test_workflow_artifact_reads_work_product_without_export_audit(self):
        service = build_fake_service()
        run = service.start("artifact workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        proposal = service.propose(run.run_id, "writing_brief", "inspect without export")

        artifact = service.workflow_artifact(run.run_id)

        self.assertEqual(artifact["run"]["run_id"], run.run_id)
        self.assertEqual(artifact["latest_proposal"]["proposal_id"], proposal.proposal_id)
        self.assertEqual(artifact["traceability"]["context_count"], 1)
        self.assertEqual(artifact["traceability"]["proposal_count"], 1)
        self.assertEqual(artifact["traceability"]["source_count"], 1)
        self.assertNotIn("export", artifact["traceability"])
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_render_brief_does_not_create_export_audit(self):
        service = build_fake_service()
        run = service.start("render workflow", {"dataset_ids": ["demo"]})
        service.context_retrieve(run.run_id, "adapter", 1)
        service.propose(run.run_id, "writing_brief", "render without export")

        brief = service.render_brief(run.run_id, "markdown")

        self.assertIn("PSKA-Essential Brief", brief)
        self.assertIn("## Source Manifest", brief)
        self.assertNotIn("Export audit event:", brief)
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_source_read_writes_source_audit_record(self):
        service = build_fake_service()
        run = service.start("source workflow", {"dataset_ids": ["demo"]})
        packet = service.context_retrieve(run.run_id, "adapter", 1)[0]

        source = service.source_read(packet.source_ref)

        self.assertTrue(source.text)
        source_read = next(event for event in service.store.list_audit_events() if event.action == "source.read")
        self.assertEqual(source_read.target_type, "source")
        self.assertEqual(source_read.metadata["adapter"], "fake")
        self.assertEqual(source_read.metadata["document_id"], packet.source_ref.document_id)
        self.assertEqual(source_read.metadata["source_ref"]["adapter"], "fake")

    def test_context_retrieve_passes_use_kg_to_adapter_and_audit(self):
        retrieval = _RecordingRetrieval()
        service = WorkflowService(retrieval, FakeMemoryAdapter(), SQLiteReviewStore(":memory:"))
        run = service.start("graph-aware workflow", {"dataset_ids": ["demo"], "use_kg": True})

        service.context_retrieve(run.run_id, "adapter", 1)

        self.assertTrue(retrieval.options["use_kg"])
        context_event = next(event for event in service.store.list_audit_events() if event.action == "context.retrieve")
        self.assertTrue(context_event.metadata["use_kg"])

    def test_smoke_eval(self):
        service = build_fake_service()
        result = service.eval_run("smoke")
        self.assertTrue(result["ok"])
        self.assertTrue(result["blocked_before_review"])


if __name__ == "__main__":
    unittest.main()
