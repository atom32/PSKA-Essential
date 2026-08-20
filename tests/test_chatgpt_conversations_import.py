from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from pska_essential.chatgpt_conversations_import import import_chatgpt_conversations
from pska_essential.workflow import build_fake_service


def _chatgpt_export_payload() -> list[dict]:
    return [
        {
            "id": "conv-pska",
            "title": "PSKA source recall design",
            "create_time": 1787000000,
            "update_time": 1787000600,
            "current_node": "msg-2",
            "mapping": {
                "root": {"id": "root", "message": None, "parent": None, "children": ["msg-1"]},
                "msg-1": {
                    "id": "msg-1",
                    "parent": "root",
                    "children": ["msg-2"],
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "create_time": 1787000001,
                        "content": {
                            "content_type": "text",
                            "parts": ["PSKA should recall ChatGPT conversations as source archive, not durable memory."],
                        },
                    },
                },
                "msg-2": {
                    "id": "msg-2",
                    "parent": "msg-1",
                    "children": [],
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "create_time": 1787000002,
                        "content": {
                            "content_type": "text",
                            "parts": ["Use SourceRef and Review before promoting anything to Memory Card."],
                        },
                    },
                },
            },
        },
        {
            "id": "conv-eidolia",
            "title": "Eidolia writing continuation",
            "messages": [
                {
                    "id": "msg-e1",
                    "role": "user",
                    "content": "Use Eidolia thought and artifact context to continue the novel scene.",
                }
            ],
        },
    ]


class ChatGPTConversationsImportTests(unittest.TestCase):
    def test_import_json_export_writes_searchable_source_archive_without_memory(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "conversations.json"
            output_dir = Path(temp_dir) / "archive"
            export_path.write_text(json.dumps(_chatgpt_export_payload(), ensure_ascii=False), encoding="utf-8")

            result = import_chatgpt_conversations(
                service,
                export_path=str(export_path),
                output_dir=str(output_dir),
                source_label="ChatGPT full export",
                conversation_limit=0,
            )

            packets = service.source_search(
                "SourceRef Review Memory Card",
                {"root_ids": [result["root"]["root_id"]]},
                limit=3,
            )
            source = service.source_read(packets[0].source_ref)
            manifest_path = Path(result["archive"]["manifest_path"])
            report_path = Path(result["archive"]["report_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            report_text = report_path.read_text(encoding="utf-8")

        self.assertEqual(result["schema"], "pska.chatgpt_conversations_import.v1")
        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["summary"]["conversation_count"], 2)
        self.assertEqual(result["summary"]["imported_conversation_count"], 2)
        self.assertEqual(result["archive"]["file_count"], 2)
        self.assertEqual(result["archive"]["managed_file_count"], 4)
        self.assertTrue(result["archive"]["manifest_path"].endswith("PSKA_IMPORT_MANIFEST.json"))
        self.assertTrue(result["archive"]["report_path"].endswith("PSKA_IMPORT_REPORT.md"))
        self.assertFalse(result["data_flow"]["writes_original_export_files"])
        self.assertTrue(result["data_flow"]["writes_normalized_archive_files"])
        self.assertTrue(result["data_flow"]["writes_import_report_files"])
        self.assertTrue(result["data_flow"]["writes_source_registry"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["creates_review"])
        self.assertEqual(manifest["schema"], "pska.chatgpt_conversations_archive_manifest.v1")
        self.assertEqual(manifest["import_id"], result["import_id"])
        self.assertEqual(manifest["root"]["root_id"], result["root"]["root_id"])
        self.assertEqual(manifest["summary"]["imported_conversation_count"], 2)
        self.assertTrue(manifest["data_flow"]["writes_import_report_files"])
        self.assertIn("Durable memory was not written", report_text)
        self.assertIn("Memory Review items were not created", report_text)
        self.assertTrue(packets)
        self.assertEqual(packets[0].source_ref.adapter, "local_folder")
        self.assertIn("SourceRef and Review", source.text)
        self.assertEqual(service.memory_search("ChatGPT conversations", {}, 10), [])
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("chatgpt.conversations.import", actions)
        self.assertIn("source.root.register", actions)
        self.assertIn("source.scan", actions)

    def test_import_zip_export_finds_conversations_json(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "chatgpt-export.zip"
            output_dir = Path(temp_dir) / "archive"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "export/conversations.json",
                    json.dumps(_chatgpt_export_payload(), ensure_ascii=False),
                )

            result = import_chatgpt_conversations(
                service,
                export_path=str(zip_path),
                output_dir=str(output_dir),
                source_label="ChatGPT zip export",
                conversation_limit=1,
            )

        self.assertEqual(result["source"]["export_member"], "export/conversations.json")
        self.assertEqual(result["summary"]["selected_conversation_count"], 1)
        self.assertEqual(result["summary"]["imported_conversation_count"], 1)
        self.assertTrue(result["archive"]["manifest_path"].endswith("PSKA_IMPORT_MANIFEST.json"))
        self.assertTrue(result["data_flow"]["writes_import_report_files"])


if __name__ == "__main__":
    unittest.main()
