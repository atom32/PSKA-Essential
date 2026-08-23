from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pska_essential.audit import audit_event


CHATGPT_CONVERSATIONS_IMPORT_SCHEMA = "pska.chatgpt_conversations_import.v1"
CHATGPT_CONVERSATIONS_ARCHIVE_MANIFEST_SCHEMA = "pska.chatgpt_conversations_archive_manifest.v1"
DEFAULT_OUTPUT_ROOT = ".pska-essential/imports/chatgpt"
DEFAULT_CONVERSATION_LIMIT = 100
MAX_CONVERSATION_LIMIT = 5000
DEFAULT_SCAN_MAX_BYTES = 1_000_000
MAX_MESSAGE_CHARS = 30_000
MAX_CONVERSATION_CHARS = 200_000
MANIFEST_FILENAME = "PSKA_IMPORT_MANIFEST.json"
REPORT_FILENAME = "PSKA_IMPORT_REPORT.md"
CONVERSATION_MARKER = "<!-- PSKA:CHATGPT-CONVERSATION-IMPORT -->"
REPORT_MARKER = "<!-- PSKA:CHATGPT-CONVERSATION-ARCHIVE-REPORT -->"


class ChatGPTConversationsImportError(ValueError):
    """Raised when a ChatGPT conversations export cannot be imported."""


def import_chatgpt_conversations(
    service: Any,
    *,
    export_path: str,
    output_dir: str = "",
    source_label: str = "",
    conversation_limit: int = DEFAULT_CONVERSATION_LIMIT,
    scan: bool = True,
    scan_max_bytes: int = DEFAULT_SCAN_MAX_BYTES,
) -> dict[str, Any]:
    """Normalize ChatGPT conversation exports into searchable source files.

    The importer writes a PSKA-managed markdown archive, registers that archive
    as a normal local-folder source root, then scans it with the existing
    no-embedding source registry. It intentionally does not create memory
    candidates or write durable memory.
    """

    raw_bytes, export_file, member_name = _read_export(export_path)
    payload = _decode_conversations(raw_bytes)
    conversations = _conversation_list(payload)
    selected_limit = _normalize_limit(conversation_limit)
    selected = conversations if selected_limit == 0 else conversations[:selected_limit]
    export_hash = _sha256_bytes(raw_bytes)
    import_id = f"cgconv_{export_hash[:16]}"
    archive_dir = _resolve_output_dir(output_dir, import_id=import_id)
    archive_dir.mkdir(parents=True, exist_ok=True)
    cleanup = _remove_stale_managed_archive_files(archive_dir)

    label = source_label.strip() or "ChatGPT conversation archive"
    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warning_count = 0
    for index, conversation in enumerate(selected, start=1):
        normalized = _normalize_conversation(conversation, index=index)
        if not normalized["messages"]:
            skipped.append(
                {
                    "index": index,
                    "conversation_id": normalized["conversation_id"],
                    "title": normalized["title"],
                    "reason": "no_text_messages",
                }
            )
            continue
        markdown, warnings = _render_conversation_markdown(
            normalized,
            import_id=import_id,
            source_label=label,
            export_path=str(export_file),
            export_member=member_name,
        )
        warning_count += len(warnings)
        filename = f"conversation-{len(written) + 1:04d}-{_safe_stem(normalized['title'], normalized['conversation_id'])}.md"
        path = archive_dir / filename
        path.write_text(markdown, encoding="utf-8")
        written.append(
            {
                "index": index,
                "conversation_id": normalized["conversation_id"],
                "title": normalized["title"],
                "message_count": len(normalized["messages"]),
                "path": str(path),
                "relative_path": filename,
                "warning_count": len(warnings),
                "warnings": warnings,
            }
        )

    root = None
    scan_result = None
    import_report = None
    if scan and written:
        root = service.source_root_register(
            str(archive_dir),
            kind="local_folder",
            permission_mode="read_only",
            label=label,
        )
    if written:
        import_report = _write_import_report(
            archive_dir,
            import_id=import_id,
            label=label,
            export_file=export_file,
            export_member=member_name,
            export_hash=export_hash,
            conversations=conversations,
            selected=selected,
            written=written,
            skipped=skipped,
            warning_count=warning_count,
            root=root,
            scan_requested=scan,
            cleanup=cleanup,
        )
    if scan and written and root:
        scan_result = service.source_scan(
            root["root_id"],
            max_files=max(len(written) + 7, 10),
            max_bytes=max(1, int(scan_max_bytes or DEFAULT_SCAN_MAX_BYTES)),
            extractor="builtin_text",
        )

    result = {
        "schema": CHATGPT_CONVERSATIONS_IMPORT_SCHEMA,
        "status": "imported" if written else "empty",
        "import_id": import_id,
        "source": {
            "export_path": str(export_file),
            "export_member": member_name,
            "sha256": export_hash,
            "label": label,
        },
        "archive": {
            "output_dir": str(archive_dir),
            "file_count": len(written),
            "managed_file_count": len(written) + (2 if import_report else 0),
            "files": written[:20],
            "file_listing_truncated": len(written) > 20,
            "manifest_path": (import_report or {}).get("manifest_path", ""),
            "report_path": (import_report or {}).get("report_path", ""),
            "cleanup": cleanup,
        },
        "summary": {
            "conversation_count": len(conversations),
            "selected_conversation_count": len(selected),
            "imported_conversation_count": len(written),
            "skipped_conversation_count": len(skipped),
            "message_count": sum(int(item.get("message_count") or 0) for item in written),
            "warning_count": warning_count,
        },
        "skipped": skipped[:20],
        "skipped_truncated": len(skipped) > 20,
        "root": root,
        "scan": scan_result,
        "data_flow": {
            "writes_original_export_files": False,
            "writes_normalized_archive_files": bool(written),
            "writes_import_report_files": bool(import_report),
            "removes_stale_managed_archive_files": bool(cleanup["removed_count"]),
            "writes_source_registry": bool(scan_result),
            "writes_memory_directly": False,
            "creates_review": False,
            "embedding_required": False,
        },
        "next_actions": _next_actions(root, written),
    }
    service.store.add_audit_event(
        audit_event(
            "chatgpt.conversations.import",
            "source_import",
            import_id,
            status=result["status"],
            export_path=str(export_file),
            export_member=member_name,
            output_dir=str(archive_dir),
            manifest_path=(import_report or {}).get("manifest_path", ""),
            report_path=(import_report or {}).get("report_path", ""),
            removed_stale_file_count=cleanup["removed_count"],
            conversation_count=result["summary"]["conversation_count"],
            imported_conversation_count=result["summary"]["imported_conversation_count"],
            skipped_conversation_count=result["summary"]["skipped_conversation_count"],
            message_count=result["summary"]["message_count"],
            root_id=(root or {}).get("root_id", ""),
            writes_original_export_files=False,
            writes_normalized_archive_files=bool(written),
            writes_import_report_files=bool(import_report),
            removes_stale_managed_archive_files=bool(cleanup["removed_count"]),
            writes_source_registry=bool(scan_result),
            writes_memory_directly=False,
            creates_review=False,
            embedding_required=False,
        )
    )
    return result


def _read_export(export_path: str) -> tuple[bytes, Path, str]:
    if not str(export_path or "").strip():
        raise ChatGPTConversationsImportError("ChatGPT conversations import requires export_path")
    path = Path(export_path).expanduser()
    if not path.exists():
        raise ChatGPTConversationsImportError(f"ChatGPT conversations export_path does not exist: {export_path}")
    if path.is_dir():
        single_path = path / "conversations.json"
        if single_path.is_file():
            path = single_path
        else:
            split_paths = _split_conversations_paths(path)
            if split_paths:
                return _read_split_conversations_blobs(
                    [(item.name, item.read_bytes()) for item in split_paths],
                    export_file=path,
                )
    if not path.is_file():
        raise ChatGPTConversationsImportError(f"ChatGPT conversations export_path must be a file or directory: {export_path}")
    suffix = path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            member = _find_conversations_member(names)
            if member:
                return archive.read(member), path, member
            split_members = _split_conversations_members(names)
            if split_members:
                return _read_split_conversations_blobs(
                    [(member, archive.read(member)) for member in split_members],
                    export_file=path,
                )
            raise ChatGPTConversationsImportError(
                "ChatGPT export zip does not contain conversations.json or conversations-*.json"
            )
    return path.read_bytes(), path, path.name


def _find_conversations_member(names: list[str]) -> str:
    candidates = [name for name in names if name.endswith("conversations.json")]
    if not candidates:
        return ""
    return sorted(candidates, key=lambda value: (value.count("/"), value))[0]


def _split_conversations_paths(path: Path) -> list[Path]:
    return sorted(
        [item for item in path.iterdir() if item.is_file() and _is_split_conversations_name(item.name)],
        key=lambda item: (_split_conversations_index(item.name), item.name),
    )


def _split_conversations_members(names: list[str]) -> list[str]:
    return sorted(
        [name for name in names if _is_split_conversations_name(Path(name).name)],
        key=lambda value: (value.count("/"), _split_conversations_index(Path(value).name), value),
    )


def _is_split_conversations_name(name: str) -> bool:
    return re.fullmatch(r"conversations-\d+\.json", name) is not None


def _split_conversations_index(name: str) -> int:
    match = re.fullmatch(r"conversations-(\d+)\.json", name)
    return int(match.group(1)) if match else 999_999


def _read_split_conversations_blobs(blobs: list[tuple[str, bytes]], *, export_file: Path) -> tuple[bytes, Path, str]:
    conversations: list[dict[str, Any]] = []
    for name, raw_bytes in blobs:
        try:
            payload = _decode_conversations(raw_bytes)
            conversations.extend(_conversation_list(payload))
        except ChatGPTConversationsImportError as exc:
            raise ChatGPTConversationsImportError(f"{exc} in split export member: {name}") from exc
    raw_bytes = json.dumps(conversations, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return raw_bytes, export_file, _split_export_member_name([name for name, _ in blobs])


def _split_export_member_name(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{names[0]}..{names[-1]} ({len(names)} files)"


def _decode_conversations(raw_bytes: bytes) -> Any:
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ChatGPTConversationsImportError("ChatGPT conversations export must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ChatGPTConversationsImportError("ChatGPT conversations export is not valid JSON") from exc


def _conversation_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get("conversations") or payload.get("items") or []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise ChatGPTConversationsImportError("ChatGPT conversations export must be a JSON list or contain conversations")


def _normalize_limit(limit: int) -> int:
    value = DEFAULT_CONVERSATION_LIMIT if limit is None else int(limit)
    if value < 0:
        raise ChatGPTConversationsImportError("conversation_limit must be zero or positive")
    return min(value, MAX_CONVERSATION_LIMIT)


def _resolve_output_dir(output_dir: str, *, import_id: str) -> Path:
    base = Path(output_dir).expanduser() if str(output_dir or "").strip() else Path(DEFAULT_OUTPUT_ROOT) / import_id
    if not base.is_absolute():
        base = Path.cwd() / base
    return base.resolve()


def _remove_stale_managed_archive_files(archive_dir: Path) -> dict[str, Any]:
    removed: list[str] = []
    for path in sorted(archive_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        if _is_managed_archive_file(path):
            path.unlink()
            removed.append(path.name)
    return {
        "removed_count": len(removed),
        "removed_files": removed[:20],
        "removed_listing_truncated": len(removed) > 20,
    }


def _is_managed_archive_file(path: Path) -> bool:
    if path.name == MANIFEST_FILENAME:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        return payload.get("schema") == CHATGPT_CONVERSATIONS_ARCHIVE_MANIFEST_SCHEMA
    if path.name == REPORT_FILENAME:
        try:
            return REPORT_MARKER in path.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            return False
    if re.fullmatch(r"conversation-\d{4}-.+\.md", path.name):
        try:
            return CONVERSATION_MARKER in path.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            return False
    return False


def _normalize_conversation(conversation: dict[str, Any], *, index: int) -> dict[str, Any]:
    conversation_id = str(conversation.get("id") or conversation.get("conversation_id") or f"conversation-{index}").strip()
    title = _clean_title(str(conversation.get("title") or conversation_id or f"Conversation {index}"))
    messages = _conversation_messages(conversation)
    return {
        "conversation_id": conversation_id,
        "title": title,
        "create_time": _timestamp(conversation.get("create_time") or conversation.get("created_at")),
        "update_time": _timestamp(conversation.get("update_time") or conversation.get("updated_at")),
        "messages": messages,
    }


def _conversation_messages(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conversation.get("mapping")
    if isinstance(mapping, dict):
        nodes = _mainline_nodes(conversation, mapping)
        return _messages_from_nodes(nodes)
    raw_messages = conversation.get("messages") or []
    if isinstance(raw_messages, list):
        return _messages_from_nodes([
            {"id": str(index + 1), "message": item}
            for index, item in enumerate(raw_messages)
            if isinstance(item, dict)
        ])
    return []


def _mainline_nodes(conversation: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    current = str(conversation.get("current_node") or "").strip()
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    while current and current in mapping and current not in seen:
        seen.add(current)
        node = mapping[current]
        if isinstance(node, dict):
            chain.append({"id": current, **node})
            current = str(node.get("parent") or "").strip()
        else:
            break
    if chain:
        return list(reversed(chain))
    return [
        {"id": str(node_id), **node}
        for node_id, node in mapping.items()
        if isinstance(node, dict)
    ]


def _messages_from_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages = []
    for ordinal, node in enumerate(nodes, start=1):
        raw = node.get("message") if "message" in node else node
        if not isinstance(raw, dict):
            continue
        text = _message_text(raw)
        if not text:
            continue
        role = str((raw.get("author") or {}).get("role") or raw.get("role") or "unknown").strip() or "unknown"
        messages.append(
            {
                "ordinal": ordinal,
                "message_id": str(raw.get("id") or node.get("id") or ordinal),
                "role": role,
                "created_at": _timestamp(raw.get("create_time") or raw.get("created_at")),
                "content_type": _message_content_type(raw),
                "text": text,
            }
        )
    return messages


def _message_content_type(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        return str(content.get("content_type") or message.get("content_type") or "")
    return str(message.get("content_type") or ("text" if isinstance(content, str) else ""))


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            rendered_parts = [_part_text(part) for part in parts]
            return _compact_message_text("\n\n".join(part for part in rendered_parts if part))
        text = content.get("text") or content.get("result")
        if isinstance(text, str):
            return _compact_message_text(text)
    if isinstance(content, str):
        return _compact_message_text(content)
    text = message.get("text")
    return _compact_message_text(text if isinstance(text, str) else "")


def _part_text(part: Any) -> str:
    if isinstance(part, str):
        return part.strip()
    if isinstance(part, dict):
        for key in ("text", "content", "result"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(part, ensure_ascii=False, sort_keys=True)[:2000]
    return ""


def _compact_message_text(text: str) -> str:
    value = str(text or "").strip()
    if len(value) <= MAX_MESSAGE_CHARS:
        return value
    return value[: MAX_MESSAGE_CHARS - 80].rstrip() + "\n\n[Message truncated by PSKA import for source-index safety.]"


def _render_conversation_markdown(
    conversation: dict[str, Any],
    *,
    import_id: str,
    source_label: str,
    export_path: str,
    export_member: str,
) -> tuple[str, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    lines = [
        f"# {conversation['title']}",
        "",
        CONVERSATION_MARKER,
        "",
        f"- Import ID: `{import_id}`",
        f"- Source label: {source_label}",
        f"- Conversation ID: `{conversation['conversation_id']}`",
        f"- Created: {conversation['create_time'] or 'unknown'}",
        f"- Updated: {conversation['update_time'] or 'unknown'}",
        f"- Export path: `{export_path}`",
        f"- Export member: `{export_member}`",
        "",
        "## Messages",
    ]
    for message in conversation["messages"]:
        lines.extend(
            [
                "",
                f"### {message['ordinal']}. {message['role']}",
                "",
                f"- Message ID: `{message['message_id']}`",
                f"- Created: {message['created_at'] or 'unknown'}",
                f"- Content type: {message['content_type'] or 'unknown'}",
                "",
                message["text"],
            ]
        )
    markdown = "\n".join(lines).strip() + "\n"
    if len(markdown) > MAX_CONVERSATION_CHARS:
        markdown = markdown[: MAX_CONVERSATION_CHARS - 90].rstrip() + "\n\n[Conversation truncated by PSKA import for source-index safety.]\n"
        warnings.append({"code": "conversation_truncated", "message": "Conversation markdown exceeded import safety limit."})
    return markdown, warnings


def _write_import_report(
    archive_dir: Path,
    *,
    import_id: str,
    label: str,
    export_file: Path,
    export_member: str,
    export_hash: str,
    conversations: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    written: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    warning_count: int,
    root: dict[str, Any] | None,
    scan_requested: bool,
    cleanup: dict[str, Any],
) -> dict[str, str]:
    manifest_path = archive_dir / MANIFEST_FILENAME
    report_path = archive_dir / REPORT_FILENAME
    manifest = _build_archive_manifest(
        import_id=import_id,
        label=label,
        export_file=export_file,
        export_member=export_member,
        export_hash=export_hash,
        archive_dir=archive_dir,
        conversations=conversations,
        selected=selected,
        written=written,
        skipped=skipped,
        warning_count=warning_count,
        root=root,
        scan_requested=scan_requested,
        cleanup=cleanup,
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(_render_import_report_markdown(manifest), encoding="utf-8")
    return {
        "manifest_path": str(manifest_path),
        "report_path": str(report_path),
        "relative_manifest_path": MANIFEST_FILENAME,
        "relative_report_path": REPORT_FILENAME,
    }


def _build_archive_manifest(
    *,
    import_id: str,
    label: str,
    export_file: Path,
    export_member: str,
    export_hash: str,
    archive_dir: Path,
    conversations: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    written: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    warning_count: int,
    root: dict[str, Any] | None,
    scan_requested: bool,
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": CHATGPT_CONVERSATIONS_ARCHIVE_MANIFEST_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "import_id": import_id,
        "source": {
            "label": label,
            "export_path": str(export_file),
            "export_member": export_member,
            "sha256": export_hash,
        },
        "archive": {
            "output_dir": str(archive_dir),
            "conversation_file_count": len(written),
            "managed_file_count": len(written) + 2,
            "manifest_file": MANIFEST_FILENAME,
            "report_file": REPORT_FILENAME,
        },
        "summary": {
            "conversation_count": len(conversations),
            "selected_conversation_count": len(selected),
            "imported_conversation_count": len(written),
            "skipped_conversation_count": len(skipped),
            "message_count": sum(int(item.get("message_count") or 0) for item in written),
            "warning_count": warning_count,
        },
        "root": _manifest_root(root),
        "scan_requested": bool(scan_requested),
        "cleanup": cleanup,
        "conversation_files": written[:1000],
        "conversation_file_listing_truncated": len(written) > 1000,
        "skipped": skipped[:1000],
        "skipped_truncated": len(skipped) > 1000,
        "data_flow": {
            "writes_original_export_files": False,
            "writes_normalized_archive_files": True,
            "writes_import_report_files": True,
            "removes_stale_managed_archive_files": bool(cleanup.get("removed_count")),
            "writes_source_registry": bool(root),
            "writes_memory_directly": False,
            "creates_review": False,
            "embedding_required": False,
        },
    }


def _manifest_root(root: dict[str, Any] | None) -> dict[str, Any] | None:
    if not root:
        return None
    return {
        "root_id": root.get("root_id", ""),
        "label": root.get("label", ""),
        "kind": root.get("kind", ""),
        "permission_mode": root.get("permission_mode", ""),
        "absolute_path": root.get("absolute_path", ""),
    }


def _render_import_report_markdown(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    root = manifest.get("root") or {}
    lines = [
        "# PSKA ChatGPT Conversation Import Report",
        "",
        REPORT_MARKER,
        "",
        f"- Import ID: `{manifest['import_id']}`",
        f"- Source label: {manifest['source']['label']}",
        f"- Export path: `{manifest['source']['export_path']}`",
        f"- Export member: `{manifest['source']['export_member']}`",
        f"- Archive folder: `{manifest['archive']['output_dir']}`",
        f"- Source root: `{root.get('root_id') or 'not registered'}`",
        f"- Permission: `{root.get('permission_mode') or 'not registered'}`",
        "",
        "## Summary",
        "",
        f"- Conversations in export: {summary['conversation_count']}",
        f"- Conversations selected: {summary['selected_conversation_count']}",
        f"- Conversations imported: {summary['imported_conversation_count']}",
        f"- Conversations skipped: {summary['skipped_conversation_count']}",
        f"- Messages imported: {summary['message_count']}",
        f"- Warnings: {summary['warning_count']}",
        f"- Stale PSKA-managed files removed before import: {manifest.get('cleanup', {}).get('removed_count', 0)}",
        "",
        "## Data Flow",
        "",
        "- Original ChatGPT export files were not modified.",
        "- Normalized markdown archive files were written under this folder.",
        "- Durable memory was not written.",
        "- Memory Review items were not created.",
        "- Embeddings were not required.",
        "",
        "## Conversation Files",
        "",
    ]
    for item in manifest.get("conversation_files", [])[:200]:
        lines.append(f"- `{item['relative_path']}` - {item['title']} ({item['message_count']} messages)")
    if manifest.get("conversation_file_listing_truncated"):
        lines.append("- Conversation file list truncated in this report.")
    skipped = manifest.get("skipped") or []
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for item in skipped[:100]:
            lines.append(f"- {item.get('title') or item.get('conversation_id') or item.get('index')} - {item.get('reason')}")
        if manifest.get("skipped_truncated"):
            lines.append("- Skipped list truncated in this report.")
    lines.extend(
        [
            "",
            "## Next Actions",
            "",
            "- Use source search/read over this source root to recall the archive.",
            "- Promote only stable, behavior-changing claims through governed memory review.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _next_actions(root: dict[str, Any] | None, written: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not root or not written:
        return []
    return [
        {
            "action": "search_chatgpt_archive",
            "tool": "pska_source_search",
            "params": {"scope": {"root_ids": [root["root_id"]]}, "limit": 5},
            "reason": "The normalized ChatGPT archive is indexed as a local source root.",
        },
        {
            "action": "create_memory_candidates_after_review",
            "tool": "pska_conversation_memory_candidates_create",
            "reason": "Only promote stable, behavior-changing claims after inspecting source evidence.",
        },
    ]


def _timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)
    return str(value)


def _clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value).strip()
    return title or "Untitled conversation"


def _safe_stem(title: str, fallback: str) -> str:
    digest = hashlib.sha256(f"{title}\n{fallback}".encode("utf-8")).hexdigest()[:8]
    ascii_words = re.findall(r"[A-Za-z0-9]+", title.lower())
    stem = "-".join(ascii_words[:6])
    return f"{stem + '-' if stem else ''}{digest}"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
