from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import SourceRef, to_jsonable, utc_now_iso


HERMES_ANSWER_PROOF_ACTION = "hermes.answer_proof"
HERMES_ANSWER_PROOF_LIST_ACTION = "hermes.answer_proof.list"
HERMES_ANSWER_PROOF_SCHEMA = "pska.hermes_answer_proof.v1"
HERMES_ANSWER_PROOF_LIST_SCHEMA = "pska.hermes_answer_proof_list.v1"

MAX_TEXT_PREVIEW_CHARS = 600
MAX_TOOL_ARG_PREVIEW_CHARS = 1000
MAX_TOOL_EVENTS = 80
MAX_CHECKS = 80
MAX_ARTIFACTS = 20

_WRITE_LIKE_RE = re.compile(
    r"(?:memory|review|source|file|kanban|task|digest).*?"
    r"(?:apply|write|save|create|update|patch|delete|remove|decision|archive)"
    r"|(?:apply|write|save|create|update|patch|delete|remove|decision|archive).*?"
    r"(?:memory|review|source|file|kanban|task|digest)",
    re.IGNORECASE,
)


class HermesAnswerProofError(ValueError):
    pass


def record_hermes_answer_proof(
    service: Any,
    *,
    session_id: str,
    proof_id: str = "",
    message_id: str = "",
    response_id: str = "",
    caller: str = "",
    question: str = "",
    question_preview: str = "",
    question_sha256: str = "",
    answer: str = "",
    answer_preview: str = "",
    answer_sha256: str = "",
    answer_length: int = 0,
    dataset_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    source_root_ids: list[str] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    proof_summary: dict[str, Any] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
    checks: list[dict[str, Any]] | None = None,
    artifacts: dict[str, Any] | None = None,
    webui: str = "",
    started_at: str = "",
    finished_at: str = "",
    read_only: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_session_id = _clean_text(session_id)
    if not selected_session_id:
        raise HermesAnswerProofError("session_id is required")

    summary = dict(proof_summary or {})
    selected_proof_id = _clean_text(proof_id) or f"hproof_{uuid4().hex}"
    selected_dataset_ids = _string_list(dataset_ids)
    selected_document_ids = _string_list(document_ids)
    selected_source_root_ids = _string_list(source_root_ids)
    selected_source_refs = _source_refs(
        source_refs or [],
        dataset_ids=selected_dataset_ids,
        document_ids=selected_document_ids,
        source_root_ids=selected_source_root_ids,
    )
    selected_tool_events = _tool_events(tool_events if tool_events is not None else summary.get("tool_events"))
    tool_names = _unique_strings(
        _string_list(summary.get("tool_names"))
        + [event["name"] for event in selected_tool_events if event.get("name")]
    )
    completed_pska_tools = _unique_strings(
        _string_list(summary.get("completed_pska_tools"))
        + [
            event["name"]
            for event in selected_tool_events
            if event.get("type") == "tool_complete"
            and "pska" in str(event.get("name") or "").lower()
            and not event.get("is_error")
        ]
    )
    write_like_tools = _unique_strings(
        _string_list(summary.get("write_like_tools"))
        + [name for name in tool_names if _WRITE_LIKE_RE.search(name)]
    )
    selected_read_only = bool(read_only) if read_only is not None else not write_like_tools
    selected_checks = _checks(checks)
    passed_check_count = len([check for check in selected_checks if check.get("ok")])
    answer_length_value = _int_value(answer_length or summary.get("answer_length") or len(str(answer or answer_preview or "")))

    extra_metadata = dict(metadata or {})
    used_memory_ids = _unique_strings(
        _string_list(extra_metadata.get("used_memory_ids"))
        + _string_list(extra_metadata.get("memory_ids"))
        + _string_list(summary.get("used_memory_ids"))
        + _string_list(summary.get("memory_ids"))
    )

    metadata_payload = {
        "schema": HERMES_ANSWER_PROOF_SCHEMA,
        "proof_id": selected_proof_id,
        "session_id": selected_session_id,
        "message_id": _clean_text(message_id),
        "response_id": _clean_text(response_id),
        "caller": _clean_text(caller),
        "webui": _clean_text(webui),
        "started_at": _clean_text(started_at),
        "finished_at": _clean_text(finished_at) or utc_now_iso(),
        "question_preview": _preview(question_preview or question),
        "question_sha256": _sha256_text(question_sha256, question),
        "answer_preview": _preview(answer_preview or answer),
        "answer_sha256": _sha256_text(answer_sha256, answer),
        "answer_length": answer_length_value,
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "source_root_ids": selected_source_root_ids,
        "source_refs": selected_source_refs,
        "used_memory_ids": used_memory_ids,
        "memory_ids": used_memory_ids,
        "tool_names": tool_names,
        "completed_pska_tools": completed_pska_tools,
        "pska_tool_count": len([name for name in tool_names if "pska" in name.lower()]),
        "completed_pska_tool_count": len(completed_pska_tools),
        "write_like_tools": write_like_tools,
        "write_like_tool_count": len(write_like_tools),
        "tool_events": selected_tool_events,
        "tool_event_count": len(selected_tool_events),
        "tool_events_truncated": _is_truncated(tool_events if tool_events is not None else summary.get("tool_events"), MAX_TOOL_EVENTS),
        "checks": selected_checks,
        "check_count": len(selected_checks),
        "passed_check_count": passed_check_count,
        "failed_check_count": len(selected_checks) - passed_check_count,
        "artifacts": _artifacts(artifacts),
        "read_only": selected_read_only,
        "writes_memory_directly": False,
        "writes_source_files": False,
        "embedding_required": False,
        "generates_answer_text": False,
        "stores_full_question": False,
        "stores_full_answer": False,
        "stored_text_mode": "preview_and_sha256",
        "data_flow": answer_proof_data_flow(),
        "metadata": to_jsonable(extra_metadata),
    }
    event = service.store.add_audit_event(
        audit_event(
            HERMES_ANSWER_PROOF_ACTION,
            "hermes_turn",
            selected_proof_id,
            **metadata_payload,
        )
    )
    proof = _proof_from_event(event)
    return {
        "schema": HERMES_ANSWER_PROOF_SCHEMA,
        "status": "recorded",
        "proof": proof,
        "audit_event_id": event.audit_event_id,
        "data_flow": answer_proof_data_flow(),
    }


def list_hermes_answer_proofs(
    service: Any,
    *,
    proof_id: str = "",
    session_id: str = "",
    response_id: str = "",
    read_only: bool | None = None,
    limit: int = 20,
    audit: bool = True,
) -> dict[str, Any]:
    requested_limit = max(0, int(limit))
    events = service.store.list_audit_events(
        action=HERMES_ANSWER_PROOF_ACTION,
        descending=True,
        limit=max(requested_limit * 4, requested_limit, 50) if requested_limit else None,
    )
    selected_proof_id = _clean_text(proof_id)
    selected_session_id = _clean_text(session_id)
    selected_response_id = _clean_text(response_id)
    proofs = []
    for event in events:
        metadata = dict(event.metadata or {})
        if selected_proof_id and selected_proof_id != str(metadata.get("proof_id") or event.target_id or ""):
            continue
        if selected_session_id and selected_session_id != str(metadata.get("session_id") or ""):
            continue
        if selected_response_id and selected_response_id != str(metadata.get("response_id") or ""):
            continue
        if read_only is not None and bool(metadata.get("read_only")) is not bool(read_only):
            continue
        proofs.append(_proof_from_event(event))
    if requested_limit:
        proofs = proofs[:requested_limit]

    result = {
        "schema": HERMES_ANSWER_PROOF_LIST_SCHEMA,
        "status": "found" if proofs else "empty",
        "proofs": to_jsonable(proofs),
        "proof_count": len(proofs),
        "query": {
            "proof_id": selected_proof_id,
            "session_id": selected_session_id,
            "response_id": selected_response_id,
            "read_only": read_only,
            "limit": requested_limit,
        },
        "data_flow": answer_proof_data_flow(),
        "limitations": [
            "Answer proofs are audit records captured by a caller such as the Hermes WebUI proof harness.",
            "They prove observed PSKA tool calls and checks, not hidden model causality.",
            "Question and answer text are stored only as previews and SHA-256 hashes.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                HERMES_ANSWER_PROOF_LIST_ACTION,
                "hermes_turn",
                selected_proof_id or selected_session_id or selected_response_id or "answer_proofs",
                proof_id=selected_proof_id,
                session_id=selected_session_id,
                response_id=selected_response_id,
                read_only=read_only,
                proof_count=len(proofs),
                writes_memory_directly=False,
                writes_source_files=False,
            )
        )
    return to_jsonable(result)


def answer_proof_data_flow() -> dict[str, Any]:
    return {
        "writes_audit_metadata": True,
        "writes_memory_directly": False,
        "writes_source_files": False,
        "embedding_required": False,
        "generates_answer_text": False,
        "stores_full_question": False,
        "stores_full_answer": False,
    }


def _proof_from_event(event: Any) -> dict[str, Any]:
    metadata = dict(getattr(event, "metadata", {}) or {})
    tool_names = _string_list(metadata.get("tool_names"))
    completed_pska_tools = _string_list(metadata.get("completed_pska_tools"))
    write_like_tools = _string_list(metadata.get("write_like_tools"))
    return {
        "schema": HERMES_ANSWER_PROOF_SCHEMA,
        "proof_id": str(metadata.get("proof_id") or getattr(event, "target_id", "") or ""),
        "audit_event_id": str(getattr(event, "audit_event_id", "") or ""),
        "created_at": str(getattr(event, "created_at", "") or ""),
        "session_id": str(metadata.get("session_id") or ""),
        "message_id": str(metadata.get("message_id") or ""),
        "response_id": str(metadata.get("response_id") or ""),
        "caller": str(metadata.get("caller") or ""),
        "webui": str(metadata.get("webui") or ""),
        "started_at": str(metadata.get("started_at") or ""),
        "finished_at": str(metadata.get("finished_at") or ""),
        "question": {
            "preview": str(metadata.get("question_preview") or ""),
            "sha256": str(metadata.get("question_sha256") or ""),
            "stored_full_text": False,
        },
        "answer": {
            "preview": str(metadata.get("answer_preview") or ""),
            "sha256": str(metadata.get("answer_sha256") or ""),
            "length": int(metadata.get("answer_length") or 0),
            "stored_full_text": False,
        },
        "scope": {
            "dataset_ids": _string_list(metadata.get("dataset_ids")),
            "document_ids": _string_list(metadata.get("document_ids")),
            "source_root_ids": _string_list(metadata.get("source_root_ids")),
            "memory_ids": _string_list(metadata.get("used_memory_ids") or metadata.get("memory_ids")),
            "source_refs": to_jsonable(metadata.get("source_refs") or []),
        },
        "tool_summary": {
            "tool_names": tool_names,
            "completed_pska_tools": completed_pska_tools,
            "pska_tool_count": int(metadata.get("pska_tool_count") or 0),
            "completed_pska_tool_count": int(metadata.get("completed_pska_tool_count") or len(completed_pska_tools)),
            "write_like_tools": write_like_tools,
            "write_like_tool_count": int(metadata.get("write_like_tool_count") or len(write_like_tools)),
            "tool_event_count": int(metadata.get("tool_event_count") or 0),
            "tool_events_truncated": bool(metadata.get("tool_events_truncated")),
        },
        "tool_events": to_jsonable(metadata.get("tool_events") or []),
        "checks": to_jsonable(metadata.get("checks") or []),
        "check_summary": {
            "check_count": int(metadata.get("check_count") or 0),
            "passed_check_count": int(metadata.get("passed_check_count") or 0),
            "failed_check_count": int(metadata.get("failed_check_count") or 0),
        },
        "artifacts": to_jsonable(metadata.get("artifacts") or {}),
        "read_only": bool(metadata.get("read_only")),
        "data_flow": to_jsonable(metadata.get("data_flow") or answer_proof_data_flow()),
        "metadata": to_jsonable(metadata.get("metadata") or {}),
    }


def _source_refs(
    refs: list[dict[str, Any]],
    *,
    dataset_ids: list[str],
    document_ids: list[str],
    source_root_ids: list[str],
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for ref in refs or []:
        if not isinstance(ref, dict) or not ref.get("adapter"):
            continue
        try:
            values.append(to_jsonable(SourceRef.from_dict(ref)))
        except TypeError:
            continue
    for dataset_id in dataset_ids:
        values.append(
            to_jsonable(
                SourceRef(
                    adapter="ragflow",
                    dataset_id=dataset_id,
                    source_id=dataset_id,
                    metadata={"created_from": "hermes_answer_proof_scope"},
                )
            )
        )
    for document_id in document_ids:
        values.append(
            to_jsonable(
                SourceRef(
                    adapter="ragflow",
                    document_id=document_id,
                    source_id=document_id,
                    metadata={"created_from": "hermes_answer_proof_scope"},
                )
            )
        )
    for root_id in source_root_ids:
        values.append(
            to_jsonable(
                SourceRef(
                    adapter="source_registry",
                    source_id=root_id,
                    external_id=root_id,
                    metadata={"created_from": "hermes_answer_proof_scope"},
                )
            )
        )
    return _unique_dicts(values)


def _tool_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    events = []
    for item in value[:MAX_TOOL_EVENTS]:
        if not isinstance(item, dict):
            continue
        events.append(
            {
                "type": _clean_text(item.get("type")),
                "name": _clean_text(item.get("name") or item.get("tool") or item.get("function_name")),
                "is_error": bool(item.get("is_error")),
                "args_preview": _preview(item.get("args_preview") or item.get("arguments") or "", MAX_TOOL_ARG_PREVIEW_CHARS),
            }
        )
    return events


def _checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    checks = []
    for item in value[:MAX_CHECKS]:
        if not isinstance(item, dict):
            continue
        checks.append(
            {
                "name": _clean_text(item.get("name")),
                "ok": bool(item.get("ok")),
                "detail": to_jsonable(item.get("detail") or {}),
            }
        )
    return checks


def _artifacts(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= MAX_ARTIFACTS:
            break
        result[_clean_text(key)] = _preview(item, MAX_TEXT_PREVIEW_CHARS)
    return result


def _preview(value: Any, limit: int = MAX_TEXT_PREVIEW_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _sha256_text(provided_hash: str, text: str) -> str:
    value = _clean_text(provided_hash).lower()
    if re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    if not text:
        return ""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _unique_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for value in values:
        key = repr(sorted(to_jsonable(value).items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_truncated(value: Any, limit: int) -> bool:
    return isinstance(value, list) and len(value) > limit
