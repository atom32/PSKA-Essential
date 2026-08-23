from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pska_essential.audit import audit_event
from pska_essential.chatgpt_conversations_import import (
    _conversation_list,
    _decode_conversations,
    _normalize_conversation,
    _normalize_limit,
    _read_export,
    _sha256_bytes,
)


CHATGPT_CONVERSATION_HISTORY_IMPORT_SCHEMA = "pska.chatgpt_conversation_history_import.v1"
DEFAULT_HISTORY_CONVERSATION_LIMIT = 20
MAX_HISTORY_CONVERSATION_LIMIT = 200

UrlopenFn = Callable[..., Any]


class ChatGPTConversationHistoryImportError(ValueError):
    """Raised when ChatGPT history cannot be imported into Hermes conversations."""


def import_chatgpt_conversations_to_hermes_history(
    service: Any,
    *,
    export_path: str,
    source_label: str = "",
    conversation_limit: int = DEFAULT_HISTORY_CONVERSATION_LIMIT,
    hermes_base_url: str = "",
    recall_token: str = "",
    overwrite: bool = False,
    read_only: bool = True,
    timeout_seconds: int = 30,
    urlopen_fn: UrlopenFn | None = None,
) -> dict[str, Any]:
    """Import a bounded ChatGPT export slice as ordinary Hermes history.

    PSKA does not write Hermes session files directly. It normalizes the export,
    then asks the Hermes backend provider to create read-only history sessions.
    Runtime recall remains query-based through /api/conversation/context-pack.
    """

    raw_bytes, export_file, member_name = _read_export(export_path)
    payload = _decode_conversations(raw_bytes)
    conversations = _conversation_list(payload)
    selected_limit = min(_normalize_limit(conversation_limit), MAX_HISTORY_CONVERSATION_LIMIT)
    selected = conversations[:selected_limit] if selected_limit else conversations[:MAX_HISTORY_CONVERSATION_LIMIT]
    export_hash = _sha256_bytes(raw_bytes)
    import_id = f"cgconv_{export_hash[:16]}"
    normalized = [_history_conversation_payload(item, index=index) for index, item in enumerate(selected, start=1)]
    normalized = [item for item in normalized if item["messages"]]
    base_url = (hermes_base_url or os.getenv("PSKA_HERMES_WEBUI_BASE_URL") or os.getenv("HERMES_WEBUI_BASE_URL") or "").strip().rstrip("/")
    token = (recall_token or os.getenv("PSKA_HERMES_RECALL_TOKEN") or os.getenv("HERMES_WEBUI_PSKA_RECALL_TOKEN") or "").strip()
    if not base_url:
        raise ChatGPTConversationHistoryImportError("Set PSKA_HERMES_WEBUI_BASE_URL before importing ChatGPT history into Hermes.")
    if not token:
        raise ChatGPTConversationHistoryImportError("Set PSKA_HERMES_RECALL_TOKEN before importing ChatGPT history into Hermes.")

    hermes_result = _post_hermes_history_import(
        base_url=base_url,
        token=token,
        payload={
            "source": {
                "kind": "chatgpt_export",
                "label": source_label.strip() or "ChatGPT imported conversation history",
                "export_path": str(export_file),
                "export_member": member_name,
                "sha256": export_hash,
                "import_id": import_id,
            },
            "conversations": normalized,
            "conversation_limit": len(normalized),
            "overwrite": overwrite,
            "read_only": read_only,
        },
        timeout_seconds=timeout_seconds,
        urlopen_fn=urlopen_fn,
    )
    summary = dict(hermes_result.get("summary") or {})
    result = {
        "schema": CHATGPT_CONVERSATION_HISTORY_IMPORT_SCHEMA,
        "status": hermes_result.get("status") or ("imported" if summary.get("imported_conversation_count") else "empty"),
        "import_id": import_id,
        "source": {
            "export_path": str(export_file),
            "export_member": member_name,
            "sha256": export_hash,
            "label": source_label.strip() or "ChatGPT imported conversation history",
        },
        "target": {
            "kind": "hermes_history",
            "base_url": base_url,
            "endpoint": f"{base_url}/api/pska/conversations/import",
            "response_schema": hermes_result.get("schema") or "",
            "active_profile": hermes_result.get("active_profile") or "",
        },
        "summary": {
            "conversation_count": len(conversations),
            "selected_conversation_count": len(selected),
            "normalized_conversation_count": len(normalized),
            "imported_conversation_count": int(summary.get("imported_conversation_count") or 0),
            "skipped_conversation_count": int(summary.get("skipped_conversation_count") or 0),
            "message_count": int(summary.get("message_count") or 0),
        },
        "imported": list(hermes_result.get("imported") or [])[:20],
        "imported_truncated": bool(hermes_result.get("imported_truncated")) or len(hermes_result.get("imported") or []) > 20,
        "skipped": list(hermes_result.get("skipped") or [])[:20],
        "skipped_truncated": bool(hermes_result.get("skipped_truncated")) or len(hermes_result.get("skipped") or []) > 20,
        "data_flow": {
            "writes_original_export_files": False,
            "writes_normalized_archive_files": False,
            "writes_source_registry": False,
            "writes_hermes_history": True,
            "writes_memory_directly": False,
            "creates_review": False,
            "embedding_required": False,
            "runtime_special_chatgpt_channel": False,
            "query_based_recall_after_import": True,
        },
        "next_actions": [
            {
                "action": "ask_with_context_pack",
                "label": "Ask in Hermes WebUI",
                "reason": "Imported conversations are now ordinary Hermes history and will be recalled by PSKA context-pack when relevant.",
                "api": "POST /api/conversation/context-pack",
            }
        ],
    }
    service.store.add_audit_event(
        audit_event(
            "chatgpt.conversations.import_to_hermes_history",
            "conversation_import",
            import_id,
            status=result["status"],
            export_path=str(export_file),
            export_member=member_name,
            hermes_base_url=base_url,
            conversation_count=result["summary"]["conversation_count"],
            selected_conversation_count=result["summary"]["selected_conversation_count"],
            normalized_conversation_count=result["summary"]["normalized_conversation_count"],
            imported_conversation_count=result["summary"]["imported_conversation_count"],
            skipped_conversation_count=result["summary"]["skipped_conversation_count"],
            message_count=result["summary"]["message_count"],
            writes_original_export_files=False,
            writes_normalized_archive_files=False,
            writes_source_registry=False,
            writes_hermes_history=True,
            writes_memory_directly=False,
            creates_review=False,
            embedding_required=False,
            runtime_special_chatgpt_channel=False,
            query_based_recall_after_import=True,
        )
    )
    return result


def _history_conversation_payload(conversation: dict[str, Any], *, index: int) -> dict[str, Any]:
    normalized = _normalize_conversation(conversation, index=index)
    return {
        "external_id": normalized["conversation_id"],
        "title": normalized["title"],
        "created_at": normalized["create_time"],
        "updated_at": normalized["update_time"],
        "messages": [
            {
                "id": message["message_id"],
                "role": message["role"],
                "content": message["text"],
                "created_at": message["created_at"],
                "content_type": message["content_type"],
            }
            for message in normalized["messages"]
            if message.get("text")
        ],
    }


def _post_hermes_history_import(
    *,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    urlopen_fn: UrlopenFn | None,
) -> dict[str, Any]:
    selected_urlopen = urlopen_fn or urlopen
    endpoint = f"{base_url}/api/pska/conversations/import"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-PSKA-Recall-Token": token,
        },
        method="POST",
    )
    try:
        with selected_urlopen(request, timeout=max(1, int(timeout_seconds or 30))) as response:
            raw = response.read().decode("utf-8")
            status = int(getattr(response, "status", 200) or 200)
    except HTTPError as exc:
        raise ChatGPTConversationHistoryImportError(_hermes_import_http_error_message(exc)) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ChatGPTConversationHistoryImportError(f"Hermes conversation import failed: {exc}") from exc
    if status >= 400:
        raise ChatGPTConversationHistoryImportError(f"Hermes conversation import failed with HTTP {status}.")
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ChatGPTConversationHistoryImportError("Hermes conversation import returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise ChatGPTConversationHistoryImportError("Hermes conversation import returned non-object JSON.")
    if data.get("schema") != "hermes.pska_conversation_history_import.v1":
        raise ChatGPTConversationHistoryImportError("Hermes conversation import returned an unexpected schema.")
    return data


def _hermes_import_http_error_message(exc: HTTPError) -> str:
    if exc.code == 401:
        return "Hermes conversation import rejected the PSKA token."
    if exc.code == 404:
        return "Hermes conversation import endpoint is missing; update the PSKA Hermes provider patch."
    return f"Hermes conversation import failed with HTTP {exc.code}."
