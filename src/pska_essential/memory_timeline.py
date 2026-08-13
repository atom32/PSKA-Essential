from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.memory_cards import get_memory_card
from pska_essential.memory_use_trace import list_memory_use_traces


MEMORY_TIMELINE_SCHEMA = "pska.memory_timeline.v1"
MEMORY_TIMELINE_ENTRY_SCHEMA = "pska.memory_timeline_entry.v1"


class MemoryTimelineError(ValueError):
    pass


def build_memory_timeline(
    service: Any,
    memory_id: str,
    *,
    scope: dict[str, Any] | None = None,
    limit: int = 50,
    include_usage: bool = True,
    include_sources: bool = True,
    audit: bool = True,
) -> dict[str, Any]:
    selected_id = str(memory_id or "").strip()
    if not selected_id:
        raise MemoryTimelineError("memory_id is required")
    requested_limit = max(0, int(limit))
    card_result = get_memory_card(service, selected_id, scope=scope or {}, audit=False)
    card = dict(card_result.get("card") or {})
    entries = [_card_snapshot_entry(card)]
    entries.extend(_lifecycle_entries(card))
    if include_usage:
        traces = list_memory_use_traces(service, memory_id=selected_id, limit=max(requested_limit, 20), audit=False)
        entries.extend(_usage_entries(traces.get("traces") or []))
    if include_sources:
        entries.extend(_source_entries(card))
    entries = _rank_entries(entries)[:requested_limit]
    summary = _timeline_summary(entries, card)
    result = {
        "schema": MEMORY_TIMELINE_SCHEMA,
        "status": "ok",
        "memory_id": selected_id,
        "card": to_jsonable(_card_summary(card)),
        "summary": summary,
        "entries": to_jsonable(entries),
        "entry_count": len(entries),
        "filters": {
            "limit": requested_limit,
            "include_usage": bool(include_usage),
            "include_sources": bool(include_sources),
        },
        "limitations": [
            "This is a PSKA-derived ledger view over Memory Card, audit, and SourceRef records.",
            "It does not claim to reconstruct hidden model causality or provider-native graph state.",
        ],
        "next_actions": _timeline_next_actions(selected_id, summary),
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.timeline",
                "memory",
                selected_id,
                entry_count=len(entries),
                lifecycle_count=summary["lifecycle_change_count"],
                usage_count=summary["usage_trace_count"],
                source_count=summary["source_anchor_count"],
            )
        )
    return result


def _card_snapshot_entry(card: dict[str, Any]) -> dict[str, Any]:
    memory_id = str(card.get("memory_id") or "")
    created_at = _timestamp(card.get("created_at"), card.get("valid_at"), card.get("updated_at"))
    return _entry(
        entry_type="card_snapshot",
        occurred_at=created_at,
        title="Memory Card snapshot",
        summary=str(card.get("display_text") or card.get("text") or memory_id),
        evidence={
            "status": str(card.get("status") or ""),
            "memory_type": str(card.get("memory_type") or ""),
            "memory_scope": str(card.get("memory_scope") or ""),
            "behavior_delta": str(card.get("behavior_delta") or ""),
            "quality": card.get("quality") or {},
        },
        memory_ids=[memory_id],
        source_refs=card.get("source_refs") or [],
        confidence="provider_card",
    )


def _lifecycle_entries(card: dict[str, Any]) -> list[dict[str, Any]]:
    memory_id = str(card.get("memory_id") or "")
    lifecycle = dict(card.get("lifecycle") or {})
    entries = []
    for event in lifecycle.get("events") or []:
        metadata = dict(event.get("metadata") or {})
        action = str(event.get("action") or "memory.change")
        entries.append(
            _entry(
                entry_type="lifecycle_change",
                occurred_at=_timestamp(event.get("created_at"), metadata.get("applied_at"), metadata.get("updated_at")),
                title=_lifecycle_title(action),
                summary=str(metadata.get("message") or metadata.get("reason") or action),
                evidence={
                    "audit_event_id": str(event.get("audit_event_id") or ""),
                    "action": action,
                    "proposal_id": str(metadata.get("proposal_id") or ""),
                    "review_id": str(metadata.get("review_id") or ""),
                    "backend": str(metadata.get("backend") or ""),
                    "operation": str(metadata.get("operation") or metadata.get("proposal_kind") or ""),
                    "metadata": metadata,
                },
                memory_ids=[memory_id, str(metadata.get("memory_target_id") or "")],
                source_refs=metadata.get("source_refs") or [],
                confidence="governance_audit",
            )
        )
    return entries


def _usage_entries(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for trace in traces:
        entries.append(
            _entry(
                entry_type="usage_trace",
                occurred_at=_timestamp(trace.get("created_at")),
                title=_usage_title(str(trace.get("action") or "")),
                summary=str(trace.get("interpretation") or trace.get("query") or trace.get("action") or ""),
                evidence={
                    "trace_id": str(trace.get("trace_id") or ""),
                    "action": str(trace.get("action") or ""),
                    "query": str(trace.get("query") or ""),
                    "caller": str(trace.get("caller") or ""),
                    "run_id": str(trace.get("run_id") or ""),
                    "purpose": str(trace.get("purpose") or ""),
                    "used_as": str(trace.get("used_as") or ""),
                    "usage_stage": str(trace.get("usage_stage") or ""),
                },
                memory_ids=trace.get("memory_ids") or [],
                source_refs=[],
                confidence="candidate_trace",
            )
        )
    return entries


def _source_entries(card: dict[str, Any]) -> list[dict[str, Any]]:
    memory_id = str(card.get("memory_id") or "")
    occurred_at = _timestamp(card.get("created_at"), card.get("valid_at"), card.get("updated_at"))
    entries = []
    for index, source_ref in enumerate(card.get("source_refs") or [], start=1):
        source_id = str(source_ref.get("source_id") or source_ref.get("uri") or source_ref.get("path") or index)
        entries.append(
            _entry(
                entry_type="source_anchor",
                occurred_at=occurred_at,
                title="Memory source anchor",
                summary=f"SourceRef {source_id} anchors this memory.",
                evidence={"source_ref": source_ref},
                memory_ids=[memory_id],
                source_refs=[source_ref],
                confidence="source_ref",
            )
        )
    return entries


def _entry(
    *,
    entry_type: str,
    occurred_at: str,
    title: str,
    summary: str,
    evidence: dict[str, Any],
    memory_ids: list[str],
    source_refs: list[Any],
    confidence: str,
) -> dict[str, Any]:
    return {
        "schema": MEMORY_TIMELINE_ENTRY_SCHEMA,
        "entry_id": f"{entry_type}:{occurred_at}:{':'.join(_unique_strings(memory_ids)) or 'memory'}:{title}",
        "type": entry_type,
        "occurred_at": occurred_at,
        "title": title,
        "summary": summary,
        "memory_ids": _unique_strings(memory_ids),
        "source_refs": to_jsonable(source_refs),
        "evidence": to_jsonable(evidence),
        "confidence": confidence,
    }


def _rank_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda entry: (str(entry.get("occurred_at") or ""), str(entry.get("type") or "")))


def _timeline_summary(entries: list[dict[str, Any]], card: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entry in entries:
        entry_type = str(entry.get("type") or "")
        counts[entry_type] = counts.get(entry_type, 0) + 1
    return {
        "memory_status": str(card.get("status") or ""),
        "memory_type": str(card.get("memory_type") or ""),
        "memory_scope": str(card.get("memory_scope") or ""),
        "first_seen_at": entries[0]["occurred_at"] if entries else "",
        "latest_seen_at": entries[-1]["occurred_at"] if entries else "",
        "card_snapshot_count": counts.get("card_snapshot", 0),
        "lifecycle_change_count": counts.get("lifecycle_change", 0),
        "usage_trace_count": counts.get("usage_trace", 0),
        "source_anchor_count": counts.get("source_anchor", 0),
    }


def _card_summary(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": str(card.get("memory_id") or ""),
        "status": str(card.get("status") or ""),
        "display_text": str(card.get("display_text") or card.get("text") or ""),
        "memory_type": str(card.get("memory_type") or ""),
        "memory_scope": str(card.get("memory_scope") or ""),
        "behavior_delta": str(card.get("behavior_delta") or ""),
        "source_count": int(card.get("source_count") or 0),
        "quality": to_jsonable(card.get("quality") or {}),
    }


def _timeline_next_actions(memory_id: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "inspect_memory_card",
            "label": "Inspect Memory Card",
            "tool": "pska_memory_card_get",
            "api": f"GET /api/memory/cards/{memory_id}",
            "memory_id": memory_id,
        },
        {
            "action": "inspect_memory_why_used",
            "label": "Explain why this memory was used",
            "tool": "pska_memory_why_used",
            "api": f"GET /api/memory/{memory_id}/why-used",
            "memory_id": memory_id,
        },
    ]
    if not summary.get("usage_trace_count"):
        actions.append(
            {
                "action": "search_memory_to_create_trace",
                "label": "Search memory to create a usage trace",
                "tool": "pska_memory_search",
                "api": "POST /api/memory/search",
                "memory_id": memory_id,
            }
        )
    return actions


def _lifecycle_title(action: str) -> str:
    return {
        "memory.apply": "Memory applied",
        "memory.update": "Memory updated",
        "memory.delete": "Memory deleted",
    }.get(action, "Memory changed")


def _usage_title(action: str) -> str:
    return {
        "memory.search": "Memory surfaced in search",
        "memory.card.get": "Memory Card inspected",
        "memory.card.list": "Memory appeared in inventory",
    }.get(action, "Memory usage trace")


def _timestamp(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return utc_now_iso()


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result
