from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.sqlite import SQLiteMemoryAdapter
from pska_essential.contracts import MemoryApplyResult, MemoryFact, SourceRef
from pska_essential.memory_cards import get_memory_card, list_memory_cards
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService, build_fake_service


class _LineageDroppingMemoryAdapter:
    backend_name = "lineage-dropping"
    memory_capabilities = {
        "search": True,
        "list": True,
        "get": True,
        "apply": True,
        "update": False,
        "delete": False,
    }

    def __init__(self) -> None:
        self.fact: MemoryFact | None = None

    def apply(self, reviewed_patch: Any) -> MemoryApplyResult:
        self.fact = MemoryFact(
            fact_id="lineage-1",
            text=reviewed_patch.text,
            source_refs=[
                SourceRef(
                    adapter="gbrain",
                    source_id="pska_review:rev-lineage",
                    external_id="lineage-1",
                    title="GBrain fact",
                    metadata={"kind": "memory_fact"},
                )
            ],
            metadata={"protocol_version": "test"},
        )
        return MemoryApplyResult(
            applied=True,
            target_id="lineage-1",
            backend=self.backend_name,
            message="remembered without PSKA envelope",
        )

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        if self.fact is None:
            return []
        normalized = str(query or "").strip().lower()
        if normalized and normalized not in self.fact.text.lower():
            return []
        return [self.fact][: max(0, int(limit))]

    def list_facts(self, scope: dict[str, Any], limit: int, *, include_inactive: bool = False) -> list[MemoryFact]:
        return [self.fact][: max(0, int(limit))] if self.fact is not None else []

    def get_fact(self, fact_id: str, scope: dict[str, Any]) -> MemoryFact | None:
        if self.fact is not None and self.fact.fact_id == fact_id:
            return self.fact
        return None


class MemoryCardTests(unittest.TestCase):
    def test_fake_memory_cards_wrap_active_facts_with_envelope_quality(self):
        service = build_fake_service()
        service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-route",
                    text="Use the PSKA architecture note before broad source search.",
                    source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                    metadata={
                        "memory_type": "source_route",
                        "memory_scope": "project",
                        "behavior_delta": "Route future PSKA architecture questions to the architecture note first.",
                        "display_text": "PSKA architecture questions should start from the architecture note.",
                        "confidence": 0.92,
                        "created_at": "2026-01-01T00:00:00+00:00",
                    },
                ),
                MemoryFact(
                    fact_id="mem-raw",
                    text="Raw durable memory without PSKA envelope.",
                    source_refs=[SourceRef(adapter="fake", source_id="note-2")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
            ]
        )

        result = list_memory_cards(service, limit=10)
        card = next(item for item in result["cards"] if item["memory_id"] == "mem-route")
        raw = next(item for item in result["cards"] if item["memory_id"] == "mem-raw")

        self.assertEqual(result["schema"], "pska.memory_card_collection.v1")
        self.assertEqual(result["count"], 2)
        self.assertEqual(card["schema"], "pska.memory_card.v1")
        self.assertEqual(card["memory_type"], "source_route")
        self.assertEqual(card["memory_scope"], "project")
        self.assertEqual(card["agent_view"]["why_use"], card["behavior_delta"])
        self.assertFalse(card["quality"]["needs_review"])
        self.assertEqual(card["next_actions"][1]["tool"], "pska_memory_refresh_review")
        self.assertEqual(card["next_actions"][1]["api"], "POST /api/memory/cards/mem-route/refresh-review")
        self.assertTrue(raw["quality"]["needs_review"])
        self.assertIn("behavior_delta", raw["quality"]["missing_fields"])
        self.assertEqual(result["next_actions"][0]["tool"], "pska_memory_card_list")
        self.assertIn("memory.card.list", [event.action for event in service.store.list_audit_events()])

    def test_memory_card_supersession_status_filters_old_fact(self):
        service = build_fake_service()
        service.memory.facts.extend(
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
                        "memory_type": "preference",
                        "memory_scope": "global",
                        "behavior_delta": "Use VS Code as the user's editor preference.",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )

        active = list_memory_cards(service, limit=10, status="active")
        superseded = list_memory_cards(service, limit=10, status="superseded")
        all_cards = list_memory_cards(service, limit=10, status="all")

        self.assertEqual([card["memory_id"] for card in active["cards"]], ["new-editor"])
        self.assertEqual(superseded["cards"][0]["memory_id"], "old-editor")
        self.assertEqual(superseded["cards"][0]["superseded_by"], "new-editor")
        self.assertEqual({card["memory_id"] for card in all_cards["cards"]}, {"old-editor", "new-editor"})

    def test_sqlite_memory_card_get_reads_applied_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(Path(temp_dir) / "memory.sqlite3"),
                SQLiteReviewStore(Path(temp_dir) / "review.sqlite3"),
            )
            created = service.memory_change_from_conversation(
                user_message="Remember my editor preference.",
                operation="remember",
                text="The user's editor is VS Code.",
                source_refs=[SourceRef(adapter="conversation", source_id="msg-1")],
            )

            card = get_memory_card(service, created["memory_apply"]["target_id"])["card"]

        self.assertEqual(card["memory_id"], created["memory_apply"]["target_id"])
        self.assertEqual(card["status"], "active")
        self.assertEqual(card["display_text"], "The user's editor is VS Code.")
        self.assertEqual(card["source_refs"][0]["adapter"], "conversation")

    def test_pska_lineage_restores_memory_card_envelope_when_provider_drops_it(self):
        service = WorkflowService(
            FakeRetrievalAdapter(),
            _LineageDroppingMemoryAdapter(),
            SQLiteReviewStore(":memory:"),
        )
        source_ref = SourceRef(
            adapter="ragflow",
            dataset_id="finance-demo",
            document_id="doc-finance-1",
            chunk_id="chunk-1",
            title="Finance source",
        )
        created = service.memory_change_from_conversation(
            user_message="记住这个 PSKA 项目财报研究规则。",
            operation="remember",
            text="PSKA 项目财报研究要优先使用已审查财报来源。",
            source_refs=[source_ref],
        )

        facts = service.memory_search("财报研究", {}, 10)
        cards = list_memory_cards(service, limit=10)
        card = cards["cards"][0]

        self.assertEqual(facts[0].fact_id, created["memory_apply"]["target_id"])
        self.assertEqual(facts[0].source_refs[0].adapter, "ragflow")
        self.assertEqual(facts[0].metadata["memory_type"], "project_state")
        self.assertEqual(facts[0].metadata["lineage_status"], "resolved")
        self.assertEqual(card["memory_id"], "lineage-1")
        self.assertEqual(card["source_refs"][0]["adapter"], "ragflow")
        self.assertEqual(card["memory_type"], "project_state")
        self.assertFalse(card["quality"]["needs_review"])
        self.assertEqual(card["metadata"]["pska_lineage"]["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
