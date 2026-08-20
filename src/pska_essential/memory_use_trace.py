from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import AuditEvent, MemoryFact, to_jsonable
from pska_essential.memory_cards import get_memory_card


MEMORY_USE_TRACE_SCHEMA = "pska.memory_use_trace.v1"
MEMORY_WHY_USED_SCHEMA = "pska.memory_why_used.v1"
MEMORY_USE_TRACE_ACTIONS = ("memory.search", "memory.card.get", "memory.card.list")


class MemoryUseTraceError(ValueError):
    pass


def list_memory_use_traces(
    service: Any,
    *,
    memory_id: str = "",
    query: str = "",
    action: str = "",
    limit: int = 50,
    audit: bool = True,
) -> dict[str, Any]:
    selected_memory_id = str(memory_id or "").strip()
    selected_query = str(query or "").strip()
    selected_action = _normalize_action(action)
    requested_limit = max(0, int(limit))

    events = _trace_events(service, action=selected_action, limit=max(requested_limit * 4, requested_limit, 50))
    traces = [_trace_from_event(event) for event in events]
    if selected_memory_id:
        traces = [trace for trace in traces if selected_memory_id in trace["memory_ids"]]
    if selected_query:
        query_lc = selected_query.lower()
        traces = [trace for trace in traces if query_lc in str(trace.get("query") or "").lower()]
    traces = traces[:requested_limit]

    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.use_trace.list",
                "memory",
                selected_memory_id or "workspace",
                memory_id=selected_memory_id,
                query=selected_query,
                trace_action=selected_action,
                count=len(traces),
            )
        )

    return {
        "schema": MEMORY_USE_TRACE_SCHEMA,
        "status": "ok",
        "memory_id": selected_memory_id,
        "query": selected_query,
        "action": selected_action,
        "traces": to_jsonable(traces),
        "count": len(traces),
        "trace_actions": list(MEMORY_USE_TRACE_ACTIONS),
        "limitations": [
            "Trace records prove candidate retrieval or explicit card inspection.",
            "Hermes answer proofs can attach observed answer-side PSKA tool use, but still do not expose hidden model causality.",
        ],
        "next_actions": _trace_collection_next_actions(traces, selected_memory_id),
    }


def explain_memory_why_used(
    service: Any,
    memory_id: str,
    *,
    scope: dict[str, Any] | None = None,
    limit: int = 20,
    audit: bool = True,
) -> dict[str, Any]:
    selected_memory_id = str(memory_id or "").strip()
    if not selected_memory_id:
        raise MemoryUseTraceError("memory_id is required")
    card = get_memory_card(service, selected_memory_id, scope=scope or {}, audit=False)["card"]
    traces_result = list_memory_use_traces(
        service,
        memory_id=selected_memory_id,
        limit=limit,
        audit=False,
    )
    traces = traces_result["traces"]
    explanation = _why_used_explanation(card, traces)
    result = {
        "schema": MEMORY_WHY_USED_SCHEMA,
        "status": "ok",
        "memory_id": selected_memory_id,
        "card": card,
        "trace_count": len(traces),
        "traces": traces,
        "why_use": card.get("agent_view", {}).get("why_use") or card.get("behavior_delta") or "",
        "explanation": explanation,
        "confidence": _trace_confidence(traces),
        "limitations": [
            "This is an audit-backed explanation of candidate retrieval and inspection.",
            "Hermes answer proofs can attach final response ids and used_memory_ids when the caller records them.",
        ],
        "next_actions": _why_used_next_actions(selected_memory_id, traces),
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.why_used",
                "memory",
                selected_memory_id,
                trace_count=len(traces),
                confidence=result["confidence"],
            )
        )
    return to_jsonable(result)


def memory_search_trace_metadata(
    *,
    facts: list[MemoryFact],
    raw_facts: list[MemoryFact],
    superseded: list[dict[str, Any]],
    trace_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(trace_context or {})
    return {
        "returned_fact_ids": [fact.fact_id for fact in facts],
        "raw_fact_ids": [fact.fact_id for fact in raw_facts],
        "superseded_fact_ids": [item["fact_id"] for item in superseded],
        "superseded_by": {
            str(item["fact_id"]): str(item.get("superseded_by_fact_id") or "")
            for item in superseded
            if item.get("fact_id")
        },
        "trace_context": to_jsonable(context),
        "caller": str(context.get("caller") or ""),
        "run_id": str(context.get("run_id") or ""),
        "message_id": str(context.get("message_id") or ""),
        "response_id": str(context.get("response_id") or ""),
        "purpose": str(context.get("purpose") or ""),
        "used_as": str(context.get("used_as") or "candidate_memory"),
        "usage_stage": str(context.get("usage_stage") or "retrieval"),
    }


def _trace_events(service: Any, *, action: str, limit: int) -> list[AuditEvent]:
    requested_limit = max(0, int(limit))
    if requested_limit <= 0:
        return []
    if action:
        return service.store.list_audit_events(action=action, limit=requested_limit, descending=True)
    events: list[AuditEvent] = []
    seen: set[str] = set()
    for trace_action in MEMORY_USE_TRACE_ACTIONS:
        for event in service.store.list_audit_events(action=trace_action, limit=requested_limit, descending=True):
            if event.audit_event_id in seen:
                continue
            events.append(event)
            seen.add(event.audit_event_id)
    events.sort(key=lambda event: event.created_at, reverse=True)
    return events[:requested_limit]


def _trace_from_event(event: AuditEvent) -> dict[str, Any]:
    metadata = dict(event.metadata or {})
    memory_ids = _event_memory_ids(event, metadata)
    return {
        "trace_id": event.audit_event_id,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "created_at": event.created_at,
        "memory_ids": memory_ids,
        "returned_fact_ids": _string_list(metadata.get("returned_fact_ids")),
        "raw_fact_ids": _string_list(metadata.get("raw_fact_ids")),
        "superseded_fact_ids": _string_list(metadata.get("superseded_fact_ids")),
        "query": str(metadata.get("query") or ""),
        "scope": to_jsonable(metadata.get("scope") or {}),
        "caller": str(metadata.get("caller") or ""),
        "run_id": str(metadata.get("run_id") or ""),
        "message_id": str(metadata.get("message_id") or ""),
        "response_id": str(metadata.get("response_id") or ""),
        "purpose": str(metadata.get("purpose") or ""),
        "used_as": str(metadata.get("used_as") or ""),
        "usage_stage": str(metadata.get("usage_stage") or ""),
        "count": int(metadata.get("count") or 0),
        "raw_count": int(metadata.get("raw_count") or 0),
        "superseded_count": int(metadata.get("superseded_count") or 0),
        "trace_context": to_jsonable(metadata.get("trace_context") or {}),
        "metadata": to_jsonable(metadata),
        "interpretation": _trace_interpretation(event.action, memory_ids),
    }


def _event_memory_ids(event: AuditEvent, metadata: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    ids.extend(_string_list(metadata.get("returned_fact_ids")))
    ids.extend(_string_list(metadata.get("memory_ids")))
    ids.extend(_string_list(metadata.get("memory_id")))
    if event.target_type == "memory":
        ids.append(event.target_id)
    ids.extend(_string_list(metadata.get("raw_fact_ids")))
    ids.extend(_string_list(metadata.get("superseded_fact_ids")))
    return _unique_strings(ids)


def _trace_interpretation(action: str, memory_ids: list[str]) -> str:
    if action == "memory.search":
        if memory_ids:
            return "The memory appeared in a provider-backed candidate retrieval."
        return "A memory search ran but returned no tracked memory ids."
    if action == "memory.card.get":
        return "The memory card was explicitly inspected."
    if action == "memory.card.list":
        return "The memory appeared in a card inventory view."
    return "The memory appeared in a memory-related audit event."


def _why_used_explanation(card: dict[str, Any], traces: list[dict[str, Any]]) -> str:
    display_text = str(card.get("display_text") or card.get("text") or card.get("memory_id") or "This memory")
    why_use = str(card.get("agent_view", {}).get("why_use") or card.get("behavior_delta") or "").strip()
    recent_searches = [trace for trace in traces if trace["action"] == "memory.search" and trace.get("query")]
    if recent_searches:
        query = recent_searches[0]["query"]
        basis = why_use or "it matched the retrieval query and was returned by the configured memory provider"
        return f"{display_text} was surfaced for '{query}' because {basis}."
    if traces:
        basis = why_use or "it was explicitly inspected through the Memory Card interface"
        return f"{display_text} has audit-backed usage traces because {basis}."
    basis = why_use or "its card metadata describes when an agent should consider it"
    return f"{display_text} has no recorded use trace yet; future agents should consider it because {basis}."


def _trace_confidence(traces: list[dict[str, Any]]) -> str:
    if any(trace["action"] == "memory.search" for trace in traces):
        return "candidate_retrieval"
    if traces:
        return "inspected"
    return "no_trace"


def _why_used_next_actions(memory_id: str, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "inspect_memory_use_trace",
            "label": "Inspect memory use trace",
            "tool": "pska_memory_use_trace",
            "api": f"GET /api/memory/{memory_id}/use-trace",
            "memory_id": memory_id,
        }
    ]
    if not traces:
        actions.append(
            {
                "action": "search_memory_to_create_trace",
                "label": "Search memory to create a candidate-use trace",
                "tool": "pska_memory_search",
                "api": "POST /api/memory/search",
                "memory_id": memory_id,
            }
        )
    return actions


def _trace_collection_next_actions(traces: list[dict[str, Any]], memory_id: str) -> list[dict[str, Any]]:
    if memory_id:
        return [
            {
                "action": "explain_memory_why_used",
                "label": "Explain why this memory was used",
                "tool": "pska_memory_why_used",
                "api": f"GET /api/memory/{memory_id}/why-used",
                "memory_id": memory_id,
            }
        ]
    if traces:
        first_id = next((memory_id for trace in traces for memory_id in trace["memory_ids"]), "")
        if first_id:
            return [
                {
                    "action": "explain_memory_why_used",
                    "label": "Explain why a traced memory appeared",
                    "tool": "pska_memory_why_used",
                    "api": f"GET /api/memory/{first_id}/why-used",
                    "memory_id": first_id,
                }
            ]
    return []


def _normalize_action(action: str) -> str:
    normalized = str(action or "").strip()
    if not normalized:
        return ""
    if normalized not in MEMORY_USE_TRACE_ACTIONS:
        raise MemoryUseTraceError(f"unsupported memory trace action: {normalized}")
    return normalized


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
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            unique.append(value)
            seen.add(value)
    return unique
