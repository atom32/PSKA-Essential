from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.memory_cards import list_memory_cards
from pska_essential.memory_health import scan_memory_health
from pska_essential.memory_use_trace import list_memory_use_traces


MEMORY_BRIEFING_SCHEMA = "pska.memory_briefing.v1"
MEMORY_BRIEFING_ITEM_SCHEMA = "pska.memory_briefing_item.v1"


def build_memory_briefing(
    service: Any,
    *,
    scope: dict[str, Any] | None = None,
    card_limit: int = 30,
    health_limit: int = 20,
    trace_limit: int = 30,
    audit: bool = True,
) -> dict[str, Any]:
    """Compose the memory attention surface for Hermes/Jarvis."""

    normalized_scope = dict(scope or {})
    cards_result, cards_error = _safe_cards(service, normalized_scope, card_limit)
    health_result, health_error = _safe_health(service, normalized_scope, health_limit)
    traces_result, traces_error = _safe_traces(service, trace_limit)
    cards = list((cards_result or {}).get("cards") or [])
    issues = list((health_result or {}).get("issues") or [])
    traces = list((traces_result or {}).get("traces") or [])
    focus_items = _focus_items(cards=cards, issues=issues, traces=traces)[: max(0, int(card_limit))]
    summary = _summary(cards=cards, issues=issues, traces=traces, focus_items=focus_items)
    briefing_id = f"mem_brief_{uuid4().hex}"
    status = _briefing_status(cards_error, health_error, traces_error, summary)
    result = {
        "schema": MEMORY_BRIEFING_SCHEMA,
        "briefing_id": briefing_id,
        "created_at": utc_now_iso(),
        "status": status,
        "scope": normalized_scope,
        "summary": summary,
        "focus_items": to_jsonable(focus_items),
        "health": {
            "summary": (health_result or {}).get("summary") or {},
            "issue_count": (health_result or {}).get("issue_count", 0),
            "top_issues": to_jsonable(issues[:5]),
            "error": health_error,
        },
        "recent_use": {
            "trace_count": len(traces),
            "traces": to_jsonable(traces[:10]),
            "error": traces_error,
        },
        "cards": {
            "count": len(cards),
            "top_cards": to_jsonable(cards[:10]),
            "error": cards_error,
        },
        "next_actions": _next_actions(focus_items, summary),
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "embedding_required": False,
            "generates_answer_text": False,
        },
        "limitations": [
            "Memory Briefing is a derived attention view over Memory Cards, health scan, and use traces.",
            "It does not create a second memory store or claim hidden model causality.",
            "It recommends inspection/review actions; durable memory changes still go through Review or conversation memory policy.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.briefing",
                "memory_scope",
                str(normalized_scope.get("memory_namespace") or "workspace"),
                status=status,
                focus_count=len(focus_items),
                card_count=len(cards),
                issue_count=summary["issue_count"],
                recent_use_count=summary["recent_use_count"],
                writes_memory_directly=False,
                embedding_required=False,
            )
        )
    return to_jsonable(result)


def _safe_cards(service: Any, scope: dict[str, Any], limit: int) -> tuple[dict[str, Any] | None, str]:
    try:
        return list_memory_cards(service, scope=scope, limit=max(0, int(limit)), status="active", audit=False), ""
    except Exception as exc:  # noqa: BLE001 - briefing should surface provider gaps.
        return None, str(exc)


def _safe_health(service: Any, scope: dict[str, Any], limit: int) -> tuple[dict[str, Any] | None, str]:
    try:
        return scan_memory_health(service, scope=scope, limit=max(0, int(limit)), audit=False), ""
    except Exception as exc:  # noqa: BLE001 - briefing should surface provider gaps.
        return None, str(exc)


def _safe_traces(service: Any, limit: int) -> tuple[dict[str, Any] | None, str]:
    try:
        return list_memory_use_traces(service, limit=max(0, int(limit)), audit=False), ""
    except Exception as exc:  # noqa: BLE001 - briefing should surface audit gaps.
        return None, str(exc)


def _focus_items(
    *,
    cards: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(card.get("memory_id") or ""): card for card in cards if str(card.get("memory_id") or "")}
    trace_counts = Counter(memory_id for trace in traces for memory_id in trace.get("memory_ids") or [])
    issue_by_id: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        for memory_id in issue.get("memory_ids") or []:
            if memory_id:
                issue_by_id.setdefault(str(memory_id), []).append(issue)
    ids = set(by_id) | set(trace_counts) | set(issue_by_id)
    items = [_focus_item(memory_id, by_id.get(memory_id), issue_by_id.get(memory_id, []), trace_counts[memory_id]) for memory_id in ids]
    items.sort(key=lambda item: (-int(item["attention_score"]), str(item.get("memory_id") or "")))
    return items


def _focus_item(
    memory_id: str,
    card: dict[str, Any] | None,
    issues: list[dict[str, Any]],
    trace_count: int,
) -> dict[str, Any]:
    issue_types = _unique(str(issue.get("type") or "") for issue in issues)
    severity = _highest_severity([str(issue.get("severity") or "") for issue in issues])
    card_quality = dict((card or {}).get("quality") or {})
    source_count = int((card or {}).get("source_count") or 0)
    attention_score = _attention_score(
        issue_types=issue_types,
        severity=severity,
        trace_count=trace_count,
        needs_review=bool(card_quality.get("needs_review")),
        source_count=source_count,
    )
    return {
        "schema": MEMORY_BRIEFING_ITEM_SCHEMA,
        "memory_id": memory_id,
        "display_text": str((card or {}).get("display_text") or (card or {}).get("text") or memory_id),
        "memory_type": str((card or {}).get("memory_type") or ""),
        "memory_scope": str((card or {}).get("memory_scope") or ""),
        "status": str((card or {}).get("status") or ""),
        "attention_score": attention_score,
        "reason_codes": _reason_codes(issue_types, trace_count, card_quality, source_count),
        "issue_types": issue_types,
        "severity": severity,
        "trace_count": int(trace_count),
        "source_count": source_count,
        "behavior_delta": str((card or {}).get("behavior_delta") or ""),
        "next_actions": _item_actions(memory_id, bool(issues)),
    }


def _summary(
    *,
    cards: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    focus_items: list[dict[str, Any]],
) -> dict[str, Any]:
    issue_types = Counter(str(issue.get("type") or "") for issue in issues)
    recent_memory_ids = _unique(memory_id for trace in traces for memory_id in trace.get("memory_ids") or [])
    return {
        "active_card_count": len(cards),
        "issue_count": len(issues),
        "quality_issue_count": issue_types.get("quality", 0),
        "stale_issue_count": issue_types.get("stale", 0),
        "conflict_issue_count": issue_types.get("conflict", 0),
        "recent_use_count": len(traces),
        "recent_memory_count": len(recent_memory_ids),
        "focus_count": len(focus_items),
        "top_focus_memory_ids": [item["memory_id"] for item in focus_items[:5]],
    }


def _briefing_status(cards_error: str, health_error: str, traces_error: str, summary: dict[str, Any]) -> str:
    if cards_error:
        return "degraded"
    if summary["conflict_issue_count"]:
        return "action_required"
    if summary["issue_count"]:
        return "needs_review"
    if health_error or traces_error:
        return "partial"
    return "ready"


def _attention_score(
    *,
    issue_types: list[str],
    severity: str,
    trace_count: int,
    needs_review: bool,
    source_count: int,
) -> int:
    score = min(int(trace_count), 5) * 2
    score += len(issue_types) * 4
    if severity == "high":
        score += 6
    elif severity == "medium":
        score += 4
    elif severity == "low":
        score += 2
    if needs_review:
        score += 3
    if source_count <= 0:
        score += 2
    return score


def _reason_codes(issue_types: list[str], trace_count: int, quality: dict[str, Any], source_count: int) -> list[str]:
    codes = list(issue_types)
    if trace_count:
        codes.append("recently_used")
    if quality.get("needs_review"):
        codes.append("needs_envelope_review")
    if source_count <= 0:
        codes.append("missing_source_refs")
    return _unique(codes)


def _item_actions(memory_id: str, has_issue: bool) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "inspect_memory_timeline",
            "label": "Inspect memory timeline",
            "tool": "pska_memory_timeline",
            "api": f"GET /api/memory/{memory_id}/timeline",
            "memory_id": memory_id,
            "view": "memory",
        },
        {
            "action": "inspect_memory_why_used",
            "label": "Explain why this memory was used",
            "tool": "pska_memory_why_used",
            "api": f"GET /api/memory/{memory_id}/why-used",
            "memory_id": memory_id,
            "view": "memory",
        },
    ]
    if has_issue:
        actions.append(
            {
                "action": "create_memory_update_review",
                "label": "Create memory update review",
                "tool": "pska_memory_update_review",
                "api": "POST /api/memory/update-review",
                "memory_id": memory_id,
                "view": "review",
            }
        )
    return actions


def _next_actions(focus_items: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "inspect_memory_health",
            "label": "Scan memory health",
            "tool": "pska_memory_health_scan",
            "api": "GET /api/memory/health",
            "view": "memory",
        }
    ]
    for item in focus_items[:3]:
        actions.extend(item.get("next_actions") or [])
    if not summary["active_card_count"]:
        actions.append(
            {
                "action": "create_memory_from_sourced_work",
                "label": "Promote sourced work into reviewed memory",
                "tool": "pska_memory_review_from_workflow",
                "api": "POST /api/workflows/{run_id}/memory-review",
                "view": "writing",
                "requires_input": ["run_id"],
            }
        )
    return _unique_actions(actions)


def _highest_severity(values: list[str]) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    ranked = sorted((value for value in values if value), key=lambda value: order.get(value, 0), reverse=True)
    return ranked[0] if ranked else ""


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _unique_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        key = (str(action.get("action") or ""), str(action.get("memory_id") or action.get("api") or action.get("tool") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result
