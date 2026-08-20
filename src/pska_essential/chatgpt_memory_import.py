from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import SourceRef, to_jsonable, utc_now_iso


CHATGPT_MEMORY_IMPORT_SCHEMA = "pska.chatgpt_memory_summary_import.v1"
CHATGPT_MEMORY_SOURCE_ADAPTER = "chatgpt_memory_summary"
_MAX_IMPORT_CHARS = 200_000
_MAX_ENTRY_CHARS = 1400

_PRIVATE_MARKERS = (
    "老婆",
    "妻子",
    "女儿",
    "孩子",
    "孙辈",
    "岳父",
    "爷爷",
    "奶奶",
    "姥姥",
    "房子",
    "家庭",
    "亲密",
    "开房",
    "分手",
    "高晓茜",
    "窦宁",
    "带状疱疹",
    "新冠",
    "失禁",
    "老年痴呆",
    "身体",
    "情绪",
    "脾气",
    "记忆力",
)

_PROJECT_MARKERS = (
    "pska",
    "hermes",
    "eidolia",
    "gbrain",
    "ragflow",
    "rag",
    "graphrag",
    "deepseek harness",
    "知识图谱",
    "外部认知",
    "外挂智能",
)

_COMPANY_MARKERS = (
    "天大智图",
    "graph intelligence",
    "opengauss",
    "oggdb",
    "chatner",
    "海河岐伯",
    "公司",
    "产品",
)

_CREATIVE_MARKERS = (
    "小说",
    "创作",
    "群像",
    "母题",
    "故事",
    "角色",
    "世界观",
    "红头巾",
    "苏联电影",
)


class ChatGPTMemoryImportError(ValueError):
    """Raised when a ChatGPT memory summary import request is invalid."""


def build_chatgpt_memory_summary_import(
    service: Any,
    *,
    text: str = "",
    source_path: str = "",
    source_label: str = "",
    scope: dict[str, Any] | None = None,
    candidate_limit: int = 12,
    dedupe_existing: bool = True,
    include_private: bool = False,
    create_privacy_boundary: bool = True,
) -> dict[str, Any]:
    """Turn a pasted/exported ChatGPT memory summary into governed Review candidates.

    This intentionally reuses the existing conversation candidate pathway so the
    import never writes durable memory directly. Private-looking chunks are
    source-archive material by default; the importer can create a single
    boundary candidate that says how those private records should be handled
    without copying the private details into memory.
    """

    raw_text, resolved_path = _load_import_text(text=text, source_path=source_path)
    label = source_label.strip() or (Path(resolved_path).name if resolved_path else "ChatGPT memory summary")
    normalized_scope = dict(scope or {})
    limit = max(1, min(int(candidate_limit or 12), 50))
    import_id = f"cgmem_{uuid4().hex}"
    source_id = _source_id(label=label, path=resolved_path, text=raw_text)
    entries = _parse_memory_entries(raw_text)

    messages: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    skipped_private: list[dict[str, Any]] = []
    skipped_low_signal: list[dict[str, Any]] = []
    private_count = 0

    for entry in entries:
        if len(candidates) >= limit:
            break
        sensitivity = _entry_sensitivity(entry["text"])
        if sensitivity == "private" and not include_private:
            private_count += 1
            skipped_private.append(_skipped_entry(entry, reason="private_source_archive_only"))
            continue
        if _is_low_signal_entry(entry["text"]):
            skipped_low_signal.append(_skipped_entry(entry, reason="low_signal"))
            continue

        message_id = f"{import_id}:entry-{entry['index']}"
        messages.append(
            {
                "message_id": message_id,
                "role": "chatgpt_memory_summary",
                "text": entry["text"],
                "created_at": "",
            }
        )
        candidates.append(
            _candidate_from_entry(
                entry,
                message_id=message_id,
                import_id=import_id,
                source_id=source_id,
                source_path=resolved_path,
                source_label=label,
                source_hash=_sha256(raw_text),
                sensitivity=sensitivity,
            )
        )

    if private_count and create_privacy_boundary and len(candidates) < limit:
        boundary_text = (
            "ChatGPT 记忆摘要导入中包含私密人生、家庭、健康或亲密经历材料；这是一条隐私边界。"
            "这些内容默认应作为个人 source archive 保存，只在用户明确要求个人档案、健康记录、"
            "自传复盘或创作母题时使用。"
        )
        message_id = f"{import_id}:privacy-boundary"
        messages.insert(
            0,
            {
                "message_id": message_id,
                "role": "chatgpt_memory_summary",
                "text": boundary_text,
                "created_at": "",
            },
        )
        candidates.insert(
            0,
            {
                "text": boundary_text,
                "memory_type": "exclusion",
                "memory_scope": "global",
                "behavior_delta": (
                    "回答无关的技术、公司、日常规划问题时，不主动暴露导入摘要中的私密人生、"
                    "家庭、健康或亲密经历细节，除非用户明确要求。"
                ),
                "reason": "Privacy boundary created from ChatGPT memory summary import.",
                "confidence": 0.9,
                "message_ids": [message_id],
                "evidence_quotes": [boundary_text],
                "source_refs": [
                    to_jsonable(
                        SourceRef(
                            adapter=CHATGPT_MEMORY_SOURCE_ADAPTER,
                            source_id=source_id,
                            external_id=f"{import_id}:privacy-boundary",
                            title=f"{label}: privacy boundary",
                            path=resolved_path or None,
                            metadata={
                                "origin": "chatgpt_memory_summary_import",
                                "import_id": import_id,
                                "entry_kind": "privacy_boundary",
                                "private_entry_count": private_count,
                                "source_sha256": _sha256(raw_text),
                                "contains_private_details": False,
                            },
                        )
                    )
                ],
            },
        )

    candidate_result = service.conversation_memory_candidates_create(
        messages=messages,
        candidates=candidates,
        session_id="",
        scope={
            **normalized_scope,
            "origin": "chatgpt_memory_summary_import",
            "import_id": import_id,
        },
        dedupe_existing=dedupe_existing,
        candidate_limit=limit,
    )

    result = {
        "schema": CHATGPT_MEMORY_IMPORT_SCHEMA,
        "status": "created" if candidate_result.get("created_count") else "empty",
        "import_id": import_id,
        "source": {
            "adapter": CHATGPT_MEMORY_SOURCE_ADAPTER,
            "source_id": source_id,
            "label": label,
            "path": resolved_path,
            "sha256": _sha256(raw_text),
            "character_count": len(raw_text),
        },
        "summary": {
            "entry_count": len(entries),
            "candidate_count": len(candidates),
            "created_count": int(candidate_result.get("created_count") or 0),
            "skipped_count": int(candidate_result.get("skipped_count") or 0)
            + len(skipped_private)
            + len(skipped_low_signal),
            "skipped_private_count": len(skipped_private),
            "skipped_low_signal_count": len(skipped_low_signal),
            "privacy_boundary_created": bool(private_count and create_privacy_boundary),
        },
        "candidate_result": candidate_result,
        "skipped_private": skipped_private,
        "skipped_low_signal": skipped_low_signal,
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "creates_review": bool(candidate_result.get("created_count")),
            "reads_source_path": bool(resolved_path),
            "stores_full_import_text": False,
            "embedding_required": False,
        },
    }
    service.store.add_audit_event(
        audit_event(
            "chatgpt.memory_summary.import",
            "memory",
            import_id,
            status=result["status"],
            source_id=source_id,
            source_label=label,
            has_source_path=bool(resolved_path),
            entry_count=result["summary"]["entry_count"],
            candidate_count=result["summary"]["candidate_count"],
            created_count=result["summary"]["created_count"],
            skipped_private_count=result["summary"]["skipped_private_count"],
            skipped_low_signal_count=result["summary"]["skipped_low_signal_count"],
            privacy_boundary_created=result["summary"]["privacy_boundary_created"],
            writes_memory_directly=False,
            writes_source_files=False,
            creates_review=result["data_flow"]["creates_review"],
            embedding_required=False,
        )
    )
    return result


def _load_import_text(*, text: str, source_path: str) -> tuple[str, str]:
    value = str(text or "")
    resolved_path = ""
    if source_path.strip():
        path = Path(source_path).expanduser()
        if not path.exists():
            raise ChatGPTMemoryImportError(f"ChatGPT memory summary source_path does not exist: {source_path}")
        if not path.is_file():
            raise ChatGPTMemoryImportError(f"ChatGPT memory summary source_path must be a file: {source_path}")
        value = path.read_text(encoding="utf-8")
        resolved_path = str(path)
    value = value.strip()
    if not value:
        raise ChatGPTMemoryImportError("ChatGPT memory summary import requires text or source_path")
    if len(value) > _MAX_IMPORT_CHARS:
        raise ChatGPTMemoryImportError(f"ChatGPT memory summary is too large; limit is {_MAX_IMPORT_CHARS} characters")
    return value, resolved_path


def _parse_memory_entries(raw_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    heading = ""
    paragraph: list[str] = []

    def flush() -> None:
        nonlocal paragraph
        text = _clean_entry_text(" ".join(paragraph))
        paragraph = []
        if not text:
            return
        entries.append({"index": len(entries) + 1, "heading": heading, "text": text})

    for raw_line in raw_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if _is_heading(line):
            flush()
            heading = _clean_heading(line)
            continue
        if line.startswith(("-", "*", "•")):
            flush()
            item = line.lstrip("-*•").strip()
            if item:
                entries.append({"index": len(entries) + 1, "heading": heading, "text": _clean_entry_text(item)})
            continue
        if _starts_new_memory_sentence(line) and paragraph:
            flush()
        paragraph.append(line)
    flush()
    return _merge_short_entries(entries)


def _is_heading(line: str) -> bool:
    stripped = line.strip("# ").strip()
    if not stripped:
        return False
    if line.startswith("#"):
        return True
    if len(stripped) <= 24 and not stripped.endswith(("。", ".", "；", ";")):
        return True
    if stripped.endswith("：") and len(stripped) <= 40:
        return True
    return False


def _clean_heading(line: str) -> str:
    return line.strip().lstrip("#").strip().rstrip("：:")


def _starts_new_memory_sentence(line: str) -> bool:
    return line.startswith(("用户", "你")) and len(line) > 20


def _merge_short_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for entry in entries:
        text = str(entry["text"]).strip()
        if not text:
            continue
        if merged and len(text) < 18 and entry.get("heading") == merged[-1].get("heading"):
            merged[-1]["text"] = _clean_entry_text(f"{merged[-1]['text']} {text}")
            continue
        merged.append({"index": len(merged) + 1, "heading": entry.get("heading") or "", "text": text})
    return merged


def _clean_entry_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" .。")
    text = text.replace("用户", "用户", 1)
    if len(text) <= _MAX_ENTRY_CHARS:
        return text
    return text[: _MAX_ENTRY_CHARS - 1].rstrip() + "…"


def _entry_sensitivity(text: str) -> str:
    normalized = text.lower()
    if any(marker.lower() in normalized for marker in _PRIVATE_MARKERS):
        return "private"
    return "normal"


def _is_low_signal_entry(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 18:
        return True
    if stripped in {"概览", "教育与职业背景", "长期项目", "技术环境", "研究兴趣", "兴趣爱好"}:
        return True
    return False


def _candidate_from_entry(
    entry: dict[str, Any],
    *,
    message_id: str,
    import_id: str,
    source_id: str,
    source_path: str,
    source_label: str,
    source_hash: str,
    sensitivity: str,
) -> dict[str, Any]:
    text = str(entry["text"]).strip()
    memory_type = _memory_type_for_entry(text, str(entry.get("heading") or ""))
    memory_scope = _memory_scope_for_entry(text, memory_type)
    return {
        "text": text,
        "memory_type": memory_type,
        "memory_scope": memory_scope,
        "behavior_delta": _behavior_delta(memory_type, text),
        "reason": f"Imported from ChatGPT memory summary section: {entry.get('heading') or 'memory'}",
        "confidence": 0.82 if sensitivity == "normal" else 0.72,
        "message_ids": [message_id],
        "evidence_quotes": [_compact(text, 500)],
        "source_refs": [
            to_jsonable(
                SourceRef(
                    adapter=CHATGPT_MEMORY_SOURCE_ADAPTER,
                    source_id=source_id,
                    external_id=f"{import_id}:entry-{entry['index']}",
                    title=f"{source_label}: {entry.get('heading') or 'memory'}",
                    path=source_path or None,
                    metadata={
                        "origin": "chatgpt_memory_summary_import",
                        "import_id": import_id,
                        "entry_index": entry["index"],
                        "heading": entry.get("heading") or "",
                        "sensitivity": sensitivity,
                        "source_sha256": source_hash,
                        "entry_sha256": _sha256(text),
                    },
                )
            )
        ],
    }


def _memory_type_for_entry(text: str, heading: str) -> str:
    normalized = f"{heading} {text}".lower()
    if any(marker in normalized for marker in ("不要", "不应该", "默认不", "avoid", "do not")):
        return "exclusion"
    if any(marker in normalized for marker in ("偏好", "喜欢", "兴趣", "希望", "追求", "爱好")):
        return "preference"
    if any(marker in normalized for marker in ("经常", "习惯", "长期关注", "喜欢亲自", "持续完善")):
        return "working_habit"
    if any(marker.lower() in normalized for marker in _PROJECT_MARKERS + _CREATIVE_MARKERS):
        return "project_state"
    if any(marker.lower() in normalized for marker in _COMPANY_MARKERS):
        return "project_state"
    if any(marker in normalized for marker in ("你叫", "用户名", "博士", "工程师", "教育", "职业", "出生", "成长")):
        return "identity"
    return "project_state"


def _memory_scope_for_entry(text: str, memory_type: str) -> str:
    normalized = text.lower()
    if memory_type == "exclusion":
        return "global"
    if any(marker.lower() in normalized for marker in _PROJECT_MARKERS + _CREATIVE_MARKERS):
        return "project"
    if any(marker.lower() in normalized for marker in _COMPANY_MARKERS):
        return "workspace"
    if memory_type in {"identity", "preference", "working_habit"}:
        return "global"
    return "workspace"


def _behavior_delta(memory_type: str, text: str) -> str:
    claim = _compact(text, 180)
    if memory_type == "identity":
        return f"当个人背景与任务有关时，使用这条经过审核的身份或背景信息：{claim}"
    if memory_type == "preference":
        return f"当提供建议、默认选择或创作方向时，考虑这条经过审核的偏好：{claim}"
    if memory_type == "working_habit":
        return f"当协助类似工作时，按这条经过审核的工作习惯调整帮助方式：{claim}"
    if memory_type == "exclusion":
        return f"当相关话题出现时，遵守这条经过审核的使用边界：{claim}"
    return f"当后续任务涉及相同项目或主题时，用这条经过审核的信息恢复上下文和边界：{claim}"


def _skipped_entry(entry: dict[str, Any], *, reason: str) -> dict[str, Any]:
    preview = "[private source archive entry redacted]" if reason == "private_source_archive_only" else _compact(str(entry.get("text") or ""), 160)
    return {
        "index": entry.get("index"),
        "heading": entry.get("heading") or "",
        "reason": reason,
        "preview": preview,
    }


def _source_id(*, label: str, path: str, text: str) -> str:
    return "chatgpt_memory_" + _sha256(f"{label}\n{path}\n{_sha256(text)}")[:16]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compact(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
