from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pska_essential.chatgpt_conversation_history_import import import_chatgpt_conversations_to_hermes_history
from pska_essential.workflow import build_fake_service


def _chatgpt_export_payload() -> list[dict]:
    return [
        {
            "id": "conv-pska-history",
            "title": "PSKA history import",
            "create_time": 1787000000,
            "update_time": 1787000600,
            "messages": [
                {
                    "id": "msg-user-1",
                    "role": "user",
                    "content": "ChatGPT conversations should become ordinary Hermes history.",
                    "created_at": "2026-08-20T10:00:00Z",
                },
                {
                    "id": "msg-assistant-1",
                    "role": "assistant",
                    "content": "PSKA should recall them through the normal history provider.",
                    "created_at": "2026-08-20T10:01:00Z",
                },
            ],
        }
    ]


class _HermesImportResponse:
    status = 201

    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ChatGPTConversationHistoryImportTests(unittest.TestCase):
    def test_import_posts_normalized_conversations_to_hermes_history_without_token_leak(self):
        service = build_fake_service()
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["token"] = request.headers.get("X-pska-recall-token") or request.headers.get("X-PSKA-Recall-Token")
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _HermesImportResponse(
                {
                    "ok": True,
                    "schema": "hermes.pska_conversation_history_import.v1",
                    "status": "imported",
                    "summary": {
                        "received_conversation_count": 1,
                        "selected_conversation_count": 1,
                        "imported_conversation_count": 1,
                        "skipped_conversation_count": 0,
                        "message_count": 2,
                    },
                    "imported": [
                        {
                            "session_id": "pska_cg_demo",
                            "title": "PSKA history import",
                            "message_count": 2,
                            "read_only": True,
                            "profile": "default",
                        }
                    ],
                    "active_profile": "default",
                    "returns_full_messages": False,
                }
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "conversations.json"
            export_path.write_text(json.dumps(_chatgpt_export_payload()), encoding="utf-8")

            result = import_chatgpt_conversations_to_hermes_history(
                service,
                export_path=str(export_path),
                source_label="ChatGPT partial history",
                conversation_limit=10,
                hermes_base_url="http://127.0.0.1:8787",
                recall_token="secret-token",
                urlopen_fn=fake_urlopen,
            )

        self.assertEqual(result["schema"], "pska.chatgpt_conversation_history_import.v1")
        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["target"]["kind"], "hermes_history")
        self.assertEqual(result["target"]["response_schema"], "hermes.pska_conversation_history_import.v1")
        self.assertEqual(result["summary"]["imported_conversation_count"], 1)
        self.assertEqual(result["summary"]["message_count"], 2)
        self.assertEqual(captured["url"], "http://127.0.0.1:8787/api/pska/conversations/import")
        self.assertEqual(captured["token"], "secret-token")
        self.assertEqual(captured["payload"]["source"]["kind"], "chatgpt_export")
        self.assertEqual(captured["payload"]["source"]["selection"], "recent")
        self.assertEqual(captured["payload"]["conversation_limit"], 1)
        self.assertEqual(result["summary"]["selection"], "recent")
        self.assertEqual(captured["payload"]["conversations"][0]["messages"][0]["role"], "user")
        self.assertEqual(captured["payload"]["conversations"][0]["messages"][0]["content"], "ChatGPT conversations should become ordinary Hermes history.")
        self.assertTrue(result["data_flow"]["writes_hermes_history"])
        self.assertFalse(result["data_flow"]["writes_source_registry"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["runtime_special_chatgpt_channel"])
        self.assertTrue(result["data_flow"]["query_based_recall_after_import"])
        self.assertNotIn("secret-token", json.dumps(result))
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("chatgpt.conversations.import_to_hermes_history", actions)

    def test_import_defaults_to_recent_conversations(self):
        service = build_fake_service()
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _HermesImportResponse(
                {
                    "ok": True,
                    "schema": "hermes.pska_conversation_history_import.v1",
                    "status": "imported",
                    "summary": {
                        "received_conversation_count": 1,
                        "selected_conversation_count": 1,
                        "imported_conversation_count": 1,
                        "skipped_conversation_count": 0,
                        "message_count": 1,
                    },
                    "imported": [{"session_id": "pska_cg_recent", "message_count": 1}],
                    "active_profile": "default",
                    "returns_full_messages": False,
                }
            )

        export_payload = [
            {
                "id": "older",
                "title": "Older conversation",
                "update_time": 100,
                "messages": [{"role": "user", "content": "older content"}],
            },
            {
                "id": "newer",
                "title": "Newer conversation",
                "update_time": 200,
                "messages": [{"role": "user", "content": "newer content"}],
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "conversations.json"
            export_path.write_text(json.dumps(export_payload), encoding="utf-8")

            result = import_chatgpt_conversations_to_hermes_history(
                service,
                export_path=str(export_path),
                conversation_limit=1,
                hermes_base_url="http://127.0.0.1:8787",
                recall_token="secret-token",
                urlopen_fn=fake_urlopen,
            )

        self.assertEqual(result["summary"]["selection"], "recent")
        self.assertEqual(captured["payload"]["conversations"][0]["external_id"], "newer")
        self.assertEqual(captured["payload"]["conversations"][0]["messages"][0]["content"], "newer content")

    def test_import_can_preserve_export_order(self):
        service = build_fake_service()
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _HermesImportResponse(
                {
                    "ok": True,
                    "schema": "hermes.pska_conversation_history_import.v1",
                    "status": "imported",
                    "summary": {
                        "received_conversation_count": 1,
                        "selected_conversation_count": 1,
                        "imported_conversation_count": 1,
                        "skipped_conversation_count": 0,
                        "message_count": 1,
                    },
                    "imported": [{"session_id": "pska_cg_export_order", "message_count": 1}],
                    "active_profile": "default",
                    "returns_full_messages": False,
                }
            )

        export_payload = [
            {
                "id": "older",
                "title": "Older conversation",
                "update_time": 100,
                "messages": [{"role": "user", "content": "older content"}],
            },
            {
                "id": "newer",
                "title": "Newer conversation",
                "update_time": 200,
                "messages": [{"role": "user", "content": "newer content"}],
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "conversations.json"
            export_path.write_text(json.dumps(export_payload), encoding="utf-8")

            result = import_chatgpt_conversations_to_hermes_history(
                service,
                export_path=str(export_path),
                conversation_limit=1,
                selection="export_order",
                hermes_base_url="http://127.0.0.1:8787",
                recall_token="secret-token",
                urlopen_fn=fake_urlopen,
            )

        self.assertEqual(result["summary"]["selection"], "export_order")
        self.assertEqual(captured["payload"]["conversations"][0]["external_id"], "older")


if __name__ == "__main__":
    unittest.main()
