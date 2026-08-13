from __future__ import annotations

import re
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.memory_cards import list_memory_cards


MEMORY_HEALTH_SCHEMA = "pska.memory_health.v1"
MEMORY_HEALTH_ISSUE_SCHEMA = "pska.memory_health_issue.v1"
MEMORY_HEALTH_ISSUE_TYPES = ("quality", "stale", "conflict")


class MemoryHealthError(ValueError):
    pass


def scan_memory_health(
    service: Any,
    *,
    scope: dict[str, Any] | None = None,
    issue_type: str = "",
    limit: int = 100,
    audit: bool = True,
) -> dict[str, Any]:
    selected_type = _normalize_issue_type(issue_type)
    requested_limit = max(0, int(limit))
    cards_result = list_memory_cards(
        service,
        scope=scope or {},
        limit=max(requested_limit, 1),
        status="active",
        audit=False,
    )
    cards = list(cards_result.get("cards") or [])
    issues = _memory_health_issues(cards)
    if selected_type:
        issues = [issue for issue in issues if issue["type"] == selected_type]
    issues = _rank_issues(issues)[:requested_limit]
    summary = _health_summary(issues)
    result = {
        "schema": MEMORY_HEALTH_SCHEMA,
        "status": "ok",
        "card_count": len(cards),
        "issue_count": len(issues),
        "summary": summary,
        "issues": to_jsonable(issues),
        "filters": {
            "issue_type": selected_type,
            "limit": requested_limit,
        },
        "scope": cards_result.get("scope") or {},
        "issue_types": list(MEMORY_HEALTH_ISSUE_TYPES),
        "next_actions": _health_next_actions(issues),
        "limitations": [
            "Conflict detection is conservative and provider-neutral.",
            "Stale detection depends on Memory Card refresh metadata.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.health.scan",
                "memory_scope",
                str((cards_result.get("scope") or {}).get("memory_namespace") or "workspace"),
                issue_type=selected_type,
                issue_count=len(issues),
                quality_count=summary["quality"],
                stale_count=summary["stale"],
                conflict_count=summary["conflict"],
                memory_ids=_issue_memory_ids(issues),
            )
        )
    return result


def _memory_health_issues(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for card in cards:
        quality_issue = _quality_issue(card)
        if quality_issue:
            issues.append(quality_issue)
        stale_issue = _stale_issue(card)
        if stale_issue:
            issues.append(stale_issue)
        metadata_issue = _metadata_conflict_issue(card)
        if metadata_issue:
            issues.append(metadata_issue)
    issues.extend(_pairwise_conflict_issues(cards))
    return issues


def _quality_issue(card: dict[str, Any]) -> dict[str, Any] | None:
    quality = dict(card.get("quality") or {})
    missing = [str(item) for item in quality.get("missing_fields") or [] if str(item)]
    if not quality.get("needs_review") and not missing:
        return None
    memory_id = str(card.get("memory_id") or "")
    return _issue(
        issue_type="quality",
        severity="medium" if missing else "low",
        memory_ids=[memory_id],
        title="Memory Card is missing envelope fields",
        reason=f"Missing fields: {', '.join(missing) if missing else 'quality metadata flagged review'}",
        cards=[card],
        evidence={"missing_fields": missing},
        next_actions=[
            _action(
                "inspect_memory_card_quality",
                "Inspect memory card quality",
                f"GET /api/memory/cards/{memory_id}",
                "pska_memory_card_get",
                memory_id,
            ),
            _action(
                "create_memory_update_review",
                "Create memory update review",
                "POST /api/memory/update-review",
                "pska_memory_update_review",
                memory_id,
            ),
        ],
    )


def _stale_issue(card: dict[str, Any]) -> dict[str, Any] | None:
    quality = dict(card.get("quality") or {})
    metadata = dict(card.get("metadata") or {})
    review_after = str(metadata.get("review_after") or metadata.get("review_after_date") or "").strip()
    refresh_rule = str(card.get("refresh_rule") or metadata.get("refresh_rule") or "").strip()
    stale_candidate = bool(quality.get("stale_candidate") or metadata.get("stale_candidate") or metadata.get("stale"))
    due = bool(review_after and review_after < utc_now_iso())
    until_project_done = refresh_rule == "until_project_done"
    missing_review_date = refresh_rule == "review_after_date" and not review_after
    explicit_stale = bool(metadata.get("stale") or metadata.get("stale_candidate"))
    if not due and not until_project_done and not missing_review_date and not explicit_stale:
        return None
    memory_id = str(card.get("memory_id") or "")
    reason = "Memory Card refresh metadata marks it as a stale candidate."
    if due:
        reason = f"Memory Card review date is due: {review_after}."
    elif until_project_done:
        reason = "Memory Card should be reviewed when the project state changes or completes."
    elif missing_review_date:
        reason = "Memory Card uses review_after_date but has no review_after date."
    return _issue(
        issue_type="stale",
        severity="medium" if due or until_project_done else "low",
        memory_ids=[memory_id],
        title="Memory Card may need refresh",
        reason=reason,
        cards=[card],
        evidence={"refresh_rule": refresh_rule, "review_after": review_after, "stale_candidate": stale_candidate},
        next_actions=[
            _action(
                "inspect_memory_staleness",
                "Inspect stale memory",
                f"GET /api/memory/cards/{memory_id}",
                "pska_memory_card_get",
                memory_id,
            ),
            _action(
                "create_memory_update_review",
                "Create memory update review",
                "POST /api/memory/update-review",
                "pska_memory_update_review",
                memory_id,
            ),
        ],
    )


def _metadata_conflict_issue(card: dict[str, Any]) -> dict[str, Any] | None:
    metadata = dict(card.get("metadata") or {})
    triage = metadata.get("triage") if isinstance(metadata.get("triage"), dict) else {}
    triage_conflict = _float(triage.get("conflict"))
    explicit_conflict = (
        _truthy_marker(metadata.get("conflict"))
        or bool(_string_list(metadata.get("conflict_with")))
        or bool(_string_list(metadata.get("conflict_fact_ids")))
    )
    if not explicit_conflict and triage_conflict < 0.6:
        return None
    memory_id = str(card.get("memory_id") or "")
    related_ids = _string_list(metadata.get("conflict_with")) + _string_list(metadata.get("conflict_fact_ids"))
    return _issue(
        issue_type="conflict",
        severity="high",
        memory_ids=[memory_id, *related_ids],
        title="Memory Card metadata declares a conflict",
        reason="Memory metadata or triage marks this card as conflicting.",
        cards=[card],
        evidence={
            "metadata_keys": ["conflict", "conflict_with", "conflict_fact_ids", "triage.conflict"],
            "triage_conflict": triage_conflict,
        },
        next_actions=[
            _action(
                "inspect_memory_conflict",
                "Inspect memory conflict",
                f"GET /api/memory/cards/{memory_id}",
                "pska_memory_card_get",
                memory_id,
            ),
            _action(
                "create_memory_update_review",
                "Create memory update review",
                "POST /api/memory/update-review",
                "pska_memory_update_review",
                memory_id,
            ),
        ],
    )


def _pairwise_conflict_issues(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_cards = [card for card in cards if str(card.get("status") or "") == "active"]
    issues: list[dict[str, Any]] = []
    for index, left in enumerate(active_cards):
        for right in active_cards[index + 1:]:
            if not _same_memory_domain(left, right):
                continue
            relatedness, overlap = _relatedness(_claim_text(left), _claim_text(right))
            if relatedness < 0.55:
                continue
            if not _claim_differs(_claim_text(left), _claim_text(right)):
                continue
            left_id = str(left.get("memory_id") or "")
            right_id = str(right.get("memory_id") or "")
            issues.append(
                _issue(
                    issue_type="conflict",
                    severity="medium",
                    memory_ids=[left_id, right_id],
                    title="Memory Cards may conflict",
                    reason="Two active Memory Cards share scope/type and high token overlap but make different claims.",
                    cards=[left, right],
                    evidence={
                        "relatedness": round(relatedness, 3),
                        "overlap_tokens": overlap[:10],
                        "memory_type": str(left.get("memory_type") or ""),
                        "memory_scope": str(left.get("memory_scope") or ""),
                    },
                    next_actions=[
                        _action(
                            "inspect_memory_conflict",
                            "Inspect first memory",
                            f"GET /api/memory/cards/{left_id}",
                            "pska_memory_card_get",
                            left_id,
                        ),
                        _action(
                            "inspect_memory_conflict",
                            "Inspect second memory",
                            f"GET /api/memory/cards/{right_id}",
                            "pska_memory_card_get",
                            right_id,
                        ),
                        _action(
                            "create_memory_update_review",
                            "Create memory update review",
                            "POST /api/memory/update-review",
                            "pska_memory_update_review",
                            left_id,
                        ),
                    ],
                )
            )
    return issues


def _issue(
    *,
    issue_type: str,
    severity: str,
    memory_ids: list[str],
    title: str,
    reason: str,
    cards: list[dict[str, Any]],
    evidence: dict[str, Any],
    next_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    ids = _unique_strings(memory_ids)
    return {
        "schema": MEMORY_HEALTH_ISSUE_SCHEMA,
        "issue_id": f"{issue_type}_{'_'.join(ids) or 'memory'}",
        "type": issue_type,
        "severity": severity,
        "memory_ids": ids,
        "title": title,
        "reason": reason,
        "cards": [_card_summary(card) for card in cards],
        "evidence": to_jsonable(evidence),
        "next_actions": next_actions,
    }


def _card_summary(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": str(card.get("memory_id") or ""),
        "status": str(card.get("status") or ""),
        "display_text": str(card.get("display_text") or card.get("text") or ""),
        "memory_type": str(card.get("memory_type") or ""),
        "memory_scope": str(card.get("memory_scope") or ""),
        "behavior_delta": str(card.get("behavior_delta") or ""),
        "updated_at": str(card.get("updated_at") or ""),
        "source_count": int(card.get("source_count") or 0),
    }


def _action(action: str, label: str, api: str, tool: str, memory_id: str) -> dict[str, Any]:
    return {
        "action": action,
        "label": label,
        "api": api,
        "tool": tool,
        "view": "memory" if "card" in api else "review",
        "params": {"memory_id": memory_id},
    }


def _health_next_actions(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not issues:
        return []
    first = issues[0]
    first_action = dict((first.get("next_actions") or [{}])[0])
    return [
        {
            "action": "inspect_memory_health",
            "label": "Inspect memory health issues",
            "api": "GET /api/memory/health",
            "tool": "pska_memory_health_scan",
            "view": "memory",
            "params": {
                "issue_count": len(issues),
                "first_issue_id": first.get("issue_id") or "",
                "first_memory_id": (first.get("memory_ids") or [""])[0],
            },
        },
        first_action,
    ]


def _health_summary(issues: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {issue_type: 0 for issue_type in MEMORY_HEALTH_ISSUE_TYPES}
    severity = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        if issue["type"] in summary:
            summary[issue["type"]] += 1
        if issue["severity"] in severity:
            severity[issue["severity"]] += 1
    return {**summary, "severity": severity}


def _rank_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    type_rank = {"conflict": 3, "stale": 2, "quality": 1}
    return sorted(
        issues,
        key=lambda issue: (
            severity_rank.get(str(issue.get("severity") or ""), 0),
            type_rank.get(str(issue.get("type") or ""), 0),
            str(issue.get("issue_id") or ""),
        ),
        reverse=True,
    )


def _same_memory_domain(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("memory_type") or "") != str(right.get("memory_type") or ""):
        return False
    if str(left.get("memory_scope") or "") != str(right.get("memory_scope") or ""):
        return False
    if str(left.get("memory_type") or "unspecified") == "unspecified":
        return False
    return bool(_claim_text(left) and _claim_text(right))


def _claim_text(card: dict[str, Any]) -> str:
    return str(card.get("display_text") or card.get("text") or "").strip()


def _relatedness(left_text: str, right_text: str) -> tuple[float, list[str]]:
    left_tokens = set(_significant_tokens(left_text))
    right_tokens = set(_significant_tokens(right_text))
    if not left_tokens or not right_tokens:
        return 0.0, []
    overlap = sorted(left_tokens & right_tokens)
    if len(overlap) < 2:
        return 0.0, overlap
    denominator = max(1, min(len(left_tokens), len(right_tokens)))
    return min(1.0, len(overlap) / denominator), overlap


def _claim_differs(left_text: str, right_text: str) -> bool:
    if _has_negation(left_text) != _has_negation(right_text):
        return True
    left_tokens = set(_significant_tokens(left_text))
    right_tokens = set(_significant_tokens(right_text))
    return bool(left_tokens - right_tokens and right_tokens - left_tokens)


def _has_negation(text: str) -> bool:
    normalized = text.lower()
    padded = f" {normalized} "
    markers = (" not ", " no ", " never ", " without ", "不是", "不再", "不要", "没有", "并非")
    return any(marker in padded for marker in markers)


def _significant_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]{2,}", text.lower()):
        if token in _MEMORY_HEALTH_STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _normalize_issue_type(issue_type: str) -> str:
    normalized = str(issue_type or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in MEMORY_HEALTH_ISSUE_TYPES:
        raise MemoryHealthError("memory health issue_type must be quality, stale, or conflict")
    return normalized


def _truthy_marker(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) > 0
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"", "0", "false", "no", "none", "null"}:
        return False
    return True


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


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


def _issue_memory_ids(issues: list[dict[str, Any]]) -> list[str]:
    return _unique_strings([memory_id for issue in issues for memory_id in issue.get("memory_ids") or []])


_MEMORY_HEALTH_STOPWORDS = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "not",
    "that",
    "the",
    "this",
    "with",
    "reviewed",
    "memory",
    "candidate",
    "evidence",
    "source",
    "summary",
    "prior",
    "context",
    "remember",
    "forget",
    "delete",
    "remove",
    "correct",
    "correction",
    "wrong",
    "actually",
    "replace",
    "instead",
    "rather",
    "than",
    "durable",
    "workspace",
    "project",
    "user",
    "users",
    "fact",
    "prefers",
    "preference",
    "should",
    "route",
}
