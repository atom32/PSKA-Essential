from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.contracts import SourceRef
from pska_essential.jarvis import build_jarvis_briefing
from pska_essential.workflow import build_fake_service


class _Gateway:
    backend_name = "test"

    def list_datasets(self, *, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": "demo",
                "name": "Demo",
                "document_count": 1,
                "chunk_count": 1,
            }
        ]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "test",
                "dataset_id": dataset_id,
                "document_id": "doc-1",
                "name": "demo.txt",
                "chunk_count": 1,
                "progress": 1.0,
                "progress_msg": "ready",
                "run": "DONE",
                "status": "ready",
            }
        ]


class JarvisBriefingTests(unittest.TestCase):
    def test_briefing_prioritizes_obsidian_source_audit_next_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "Index.md").write_text(
                "# Index\n\nLinks [[Missing Note]] and [[Evidence]].\n",
                encoding="utf-8",
            )
            (vault / "Evidence.md").write_text("# Evidence\n\nLinked evidence.\n", encoding="utf-8")
            duplicate_text = "# Duplicate\n\nSame exact source body.\n"
            (vault / "dup-a.md").write_text(duplicate_text, encoding="utf-8")
            (vault / "dup-b.md").write_text(duplicate_text, encoding="utf-8")
            service = build_fake_service()
            root = service.source_root_register(str(vault), kind="auto", label="Vault")
            service.source_scan(root["root_id"])

            briefing = build_jarvis_briefing(
                service=service,
                gateway=_Gateway(),
                source_scope={"root_ids": [root["root_id"]]},
                audit_limit=10,
            )

        self.assertEqual(briefing["schema"], "pska.jarvis_briefing.v1")
        self.assertEqual(briefing["agent"]["primary"], "Hermes")
        self.assertEqual(briefing["status"], "action_required")
        self.assertEqual(briefing["workspace_status"]["status"], "ready")
        self.assertEqual(briefing["memory_layer"]["review_queue"]["schema"], "pska.memory_review_queue.v1")
        self.assertIn("memory_review_queue_item_count", briefing["summary"])
        self.assertEqual(briefing["source_layer"]["root_count"], 1)
        self.assertEqual(briefing["source_layer"]["audit"]["duplicate_preview"]["group_count"], 1)
        self.assertEqual(briefing["source_layer"]["audit"]["unresolved_links"]["count"], 1)
        priority_codes = {item["code"] for item in briefing["priorities"]}
        self.assertIn("review_duplicates", priority_codes)
        self.assertIn("inspect_unresolved_links", priority_codes)
        self.assertIn("create_source_memory_candidates_from_audit", priority_codes)
        actions = {item["action"]: item for item in briefing["next_actions"]}
        self.assertEqual(actions["review_duplicates"]["api"], "POST /api/sources/duplicates")
        self.assertEqual(actions["inspect_unresolved_links"]["tool"], "pska_source_audit_run")
        self.assertEqual(
            actions["create_source_memory_candidates_from_audit"]["api"],
            "POST /api/sources/memory-candidates/from-audit",
        )
        self.assertFalse(briefing["data_flow"]["writes_source_files"])
        self.assertFalse(briefing["data_flow"]["writes_memory_directly"])
        self.assertFalse(briefing["data_flow"]["embedding_required"])
        self.assertFalse(briefing["data_flow"]["generates_answer_text"])
        audit_actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("source.audit.run", audit_actions)
        self.assertIn("jarvis.briefing.build", audit_actions)

    def test_briefing_prioritizes_conversation_memory_candidates(self):
        service = build_fake_service()
        created = service.conversation_memory_candidates_create(
            session_id="sess-jarvis-memory",
            messages=[
                {
                    "message_id": "msg-jarvis-memory",
                    "role": "user",
                    "text": "For PSKA memory, Hermes should review stable conversation candidates.",
                }
            ],
            candidates=[
                {
                    "text": "Hermes should review stable PSKA conversation memory candidates.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When stable PSKA memory candidates appear in conversation, send them through review.",
                    "message_ids": ["msg-jarvis-memory"],
                }
            ],
        )

        briefing = build_jarvis_briefing(service=service, gateway=_Gateway())
        priority_codes = {item["code"] for item in briefing["priorities"]}
        actions = {item["action"]: item for item in briefing["next_actions"]}

        self.assertEqual(briefing["status"], "action_required")
        self.assertIn("review_conversation_memory_candidates", priority_codes)
        self.assertEqual(briefing["summary"]["conversation_memory_candidate_count"], 1)
        self.assertEqual(
            briefing["memory_layer"]["review_queue"]["summary"]["conversation_candidate_count"],
            1,
        )
        self.assertEqual(
            actions["review_conversation_memory_candidate"]["params"]["review_id"],
            created["created"][0]["review_id"],
        )

    def test_briefing_surfaces_related_memory_candidate_groups(self):
        service = build_fake_service()
        service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-global", title="Conversation")],
            text="The user prefers concise memory review summaries.",
            memory_type="preference",
            memory_scope="global",
            behavior_delta="Keep memory review summaries concise.",
            reason="global preference candidate",
        )
        service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-project", title="Conversation")],
            text="For PSKA, the user prefers concise memory review summaries.",
            memory_type="preference",
            memory_scope="project",
            behavior_delta="Keep PSKA memory review summaries concise.",
            reason="project preference candidate",
        )

        briefing = build_jarvis_briefing(service=service, gateway=_Gateway())
        priority_codes = {item["code"] for item in briefing["priorities"]}
        actions = {item["action"]: item for item in briefing["next_actions"]}

        self.assertIn("inspect_related_memory_candidates", priority_codes)
        self.assertEqual(briefing["summary"]["related_memory_candidate_group_count"], 1)
        self.assertEqual(
            briefing["memory_layer"]["review_queue"]["summary"]["related_candidate_group_count"],
            1,
        )
        self.assertEqual(actions["inspect_related_memory_candidates"]["tool"], "pska_memory_candidate_dedup")


if __name__ == "__main__":
    unittest.main()
