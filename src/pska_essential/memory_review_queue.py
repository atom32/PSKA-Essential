from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.memory_briefing import build_memory_briefing
from pska_essential.memory_candidate_dedup import build_memory_candidate_dedup


MEMORY_REVIEW_QUEUE_SCHEMA = "pska.memory_review_queue.v1"
MEMORY_REVIEW_QUEUE_GROUP_SCHEMA = "pska.memory_review_queue_group.v1"

GROUP_DEFINITIONS = (
    ("accepted_unapplied", "Accepted Memory Waiting To Apply", "accepted memory reviews can be applied"),
    ("conversation_candidates", "Conversation Memory Candidates", "conversation-derived memory candidates need review"),
    ("candidate_quality", "Memory Candidate Quality Gate", "candidate reviews may be too vague or missing Memory Card fields"),
    ("duplicate_candidates", "Possible Duplicate Memory Candidates", "candidate reviews may describe the same durable memory"),
    ("related_candidates", "Related Memory Candidates", "candidate reviews may need scope or consolidation review"),
    ("pending_reviews", "Pending Durable Knowledge Reviews", "pending review decisions need user attention"),
    ("needs_edit", "Reviews Needing Revision", "reviews were marked needs_edit and require revision"),
    ("merged_replacements", "Merged Candidate Replacements", "candidate reviews were replaced by a merged review"),
    ("memory_health", "Memory Health Issues", "Memory Cards need quality/stale/conflict inspection"),
    ("memory_focus", "Memory Focus Items", "recent or risky memories should be inspected"),
)


def build_memory_review_queue(
    service: Any,
    *,
    scope: dict[str, Any] | None = None,
    review_limit: int = 50,
    health_limit: int = 20,
    focus_limit: int = 20,
    audit: bool = True,
) -> dict[str, Any]:
    normalized_scope = dict(scope or {})
    reviews = service.store.list_reviews(limit=max(0, int(review_limit)))
    briefing = build_memory_briefing(
        service,
        scope=normalized_scope,
        card_limit=max(0, int(focus_limit)),
        health_limit=max(0, int(health_limit)),
        trace_limit=max(0, int(focus_limit)),
        audit=False,
    )
    candidate_dedup = build_memory_candidate_dedup(
        service,
        scope=normalized_scope,
        review_limit=max(0, int(review_limit)),
        audit=False,
    )
    groups = _groups(reviews, briefing, candidate_dedup)
    summary = _summary(groups)
    result = {
        "schema": MEMORY_REVIEW_QUEUE_SCHEMA,
        "status": _status(summary),
        "created_at": utc_now_iso(),
        "scope": normalized_scope,
        "summary": summary,
        "groups": to_jsonable(groups),
        "next_actions": _next_actions(groups),
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "embedding_required": False,
            "generates_answer_text": False,
        },
        "limitations": [
            "Memory Review Queue is a read-only grouping view over Review records and Memory Briefing.",
            "It does not approve, revise, apply, or write durable memory directly.",
            "Health and focus groups are inspection queues; any durable change still goes through Review.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.review_queue",
                "memory_scope",
                str(normalized_scope.get("memory_namespace") or "workspace"),
                status=result["status"],
                group_count=len(groups),
                item_count=summary["item_count"],
                actionable_item_count=summary["actionable_item_count"],
                accepted_unapplied_count=summary["accepted_unapplied_count"],
                conversation_candidate_count=summary["conversation_candidate_count"],
                candidate_quality_issue_count=summary["candidate_quality_issue_count"],
                duplicate_candidate_group_count=summary["duplicate_candidate_group_count"],
                related_candidate_group_count=summary["related_candidate_group_count"],
                pending_review_count=summary["pending_review_count"],
                needs_edit_count=summary["needs_edit_count"],
                merged_replacement_count=summary["merged_replacement_count"],
                memory_health_count=summary["memory_health_count"],
                writes_memory_directly=False,
            )
        )
    return to_jsonable(result)


def _groups(
    reviews: list[dict[str, Any]],
    briefing: dict[str, Any],
    candidate_dedup: dict[str, Any],
) -> list[dict[str, Any]]:
    pending = [review for review in reviews if review.get("status") == "pending"]
    conversation_candidates = [review for review in pending if _conversation_candidate_review(review)]
    candidate_quality_issues = _candidate_quality_issues(reviews)
    accepted_unapplied = [
        review
        for review in reviews
        if review.get("status") == "accepted"
        and not review.get("memory_apply")
        and _durable_review(review)
        and not _candidate_quality_issue(review)
    ]
    needs_edit_reviews = [review for review in reviews if review.get("status") == "needs_edit"]
    merged_replacements = [review for review in needs_edit_reviews if _merged_into_review_id(review)]
    needs_edit = [review for review in needs_edit_reviews if not _merged_into_review_id(review)]
    health_issues = ((briefing.get("health") or {}).get("top_issues") or [])[:10]
    focus_items = (briefing.get("focus_items") or [])[:10]
    grouped = [
        _review_group("accepted_unapplied", accepted_unapplied, "high"),
        _conversation_candidate_group(conversation_candidates),
        _candidate_quality_group(candidate_quality_issues),
        _candidate_duplicate_group(candidate_dedup.get("groups") or []),
        _candidate_related_group(candidate_dedup.get("related_groups") or []),
        _review_group("pending_reviews", pending, "medium"),
        _review_group("needs_edit", needs_edit, "medium"),
        _merged_replacement_group(merged_replacements),
        _health_group(health_issues),
        _focus_group(focus_items),
    ]
    return [group for group in grouped if group["count"]]


def _review_group(code: str, reviews: list[dict[str, Any]], severity: str) -> dict[str, Any]:
    group = _group(
        code,
        severity,
        [
            {
                "item_type": "review",
                "review_id": str(review.get("review_id") or ""),
                "status": str(review.get("status") or ""),
                "proposal_kind": str((review.get("proposal") or {}).get("kind") or ""),
                "title": str((review.get("proposal") or {}).get("title") or review.get("review_id") or ""),
                "reason": str((review.get("proposal") or {}).get("body") or ""),
                "source_count": int(review.get("source_count") or len(review.get("source_refs") or [])),
                "revision": review.get("revision") or {},
                "merged_into_review_id": _merged_into_review_id(review),
                "next_actions": _review_actions(review),
            }
            for review in reviews
        ],
    )
    return _with_review_batch_actions(group)


def _merged_replacement_group(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "merged_replacements",
        "low",
        [
            {
                "item_type": "merged_candidate_replacement",
                "review_id": str(review.get("review_id") or ""),
                "status": str(review.get("status") or ""),
                "proposal_kind": str((review.get("proposal") or {}).get("kind") or ""),
                "title": str((review.get("proposal") or {}).get("title") or review.get("review_id") or ""),
                "reason": str((review.get("proposal") or {}).get("body") or ""),
                "source_count": int(review.get("source_count") or len(review.get("source_refs") or [])),
                "revision": review.get("revision") or {},
                "merged_into_review_id": _merged_into_review_id(review),
                "next_actions": _merged_replacement_actions(review),
            }
            for review in reviews
        ],
    )


def _conversation_candidate_group(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    group = _group(
        "conversation_candidates",
        "medium",
        [
            {
                "item_type": "conversation_memory_candidate",
                "review_id": str(review.get("review_id") or ""),
                "status": str(review.get("status") or ""),
                "proposal_kind": str((review.get("proposal") or {}).get("kind") or ""),
                "title": _conversation_candidate_title(review),
                "reason": _conversation_candidate_reason(review),
                "source_count": int(review.get("source_count") or len(review.get("source_refs") or [])),
                "memory_type": str(_review_memory_metadata(review).get("memory_type") or ""),
                "memory_scope": str(_review_memory_metadata(review).get("memory_scope") or ""),
                "message_ids": [
                    str(message_id)
                    for message_id in _review_memory_metadata(review).get("message_ids") or []
                    if str(message_id)
                ],
                "next_actions": _review_actions(review),
            }
            for review in reviews
        ],
    )
    return _with_review_batch_actions(group)


def _candidate_quality_group(issues: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "candidate_quality",
        "high",
        [
            {
                "item_type": "memory_candidate_quality_issue",
                "review_id": str(issue.get("review_id") or ""),
                "status": str(issue.get("status") or ""),
                "proposal_kind": str(issue.get("proposal_kind") or ""),
                "title": str(issue.get("title") or ""),
                "reason": str(issue.get("reason") or ""),
                "issue_types": issue.get("issue_types") or [],
                "severity": str(issue.get("severity") or ""),
                "memory_type": str(issue.get("memory_type") or ""),
                "memory_scope": str(issue.get("memory_scope") or ""),
                "behavior_delta": str(issue.get("behavior_delta") or ""),
                "source_count": int(issue.get("source_count") or 0),
                "evidence": issue.get("evidence") or {},
                "next_actions": issue.get("next_actions") or [],
            }
            for issue in issues
        ],
    )


def _health_group(issues: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "memory_health",
        "medium",
        [
            {
                "item_type": "memory_health_issue",
                "issue_id": str(issue.get("issue_id") or ""),
                "issue_type": str(issue.get("type") or ""),
                "severity": str(issue.get("severity") or ""),
                "title": str(issue.get("title") or ""),
                "reason": str(issue.get("reason") or ""),
                "memory_ids": [str(memory_id) for memory_id in issue.get("memory_ids") or [] if str(memory_id)],
                "next_actions": issue.get("next_actions") or [],
            }
            for issue in issues
        ],
    )


def _focus_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "memory_focus",
        "low",
        [
            {
                "item_type": "memory_focus_item",
                "memory_id": str(item.get("memory_id") or ""),
                "title": str(item.get("display_text") or item.get("memory_id") or ""),
                "reason": ", ".join(item.get("reason_codes") or []),
                "attention_score": int(item.get("attention_score") or 0),
                "issue_types": item.get("issue_types") or [],
                "next_actions": item.get("next_actions") or [],
            }
            for item in items
        ],
    )


def _candidate_duplicate_group(groups: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "duplicate_candidates",
        "medium",
        [
            {
                "item_type": "memory_candidate_duplicate_group",
                "group_id": str(group.get("group_id") or ""),
                "title": f"{group.get('count') or 0} possible duplicate memory candidate(s)",
                "reason": ", ".join(group.get("match_types") or []) or "possible duplicate candidate reviews",
                "score": float(group.get("score") or 0.0),
                "memory_type": str(group.get("memory_type") or ""),
                "memory_scope": str(group.get("memory_scope") or ""),
                "review_ids": [
                    str(item.get("review_id") or "")
                    for item in group.get("items") or []
                    if str(item.get("review_id") or "")
                ],
                "candidate_items": group.get("items") or [],
                "source_paths": group.get("shared_paths") or [],
                "next_actions": group.get("next_actions") or _duplicate_group_actions(group),
            }
            for group in groups
        ],
    )


def _candidate_related_group(groups: list[dict[str, Any]]) -> dict[str, Any]:
    return _group(
        "related_candidates",
        "medium",
        [
            {
                "item_type": "memory_candidate_related_group",
                "group_id": str(group.get("group_id") or ""),
                "title": f"{group.get('count') or 0} related memory candidate(s)",
                "reason": ", ".join(group.get("match_types") or []) or "related candidate reviews",
                "score": float(group.get("score") or 0.0),
                "memory_type": str(group.get("memory_type") or ""),
                "memory_scopes": group.get("memory_scopes") or [],
                "review_ids": [
                    str(item.get("review_id") or "")
                    for item in group.get("items") or []
                    if str(item.get("review_id") or "")
                ],
                "candidate_items": group.get("items") or [],
                "source_paths": group.get("shared_paths") or [],
                "next_actions": group.get("next_actions") or _related_group_actions(group),
            }
            for group in groups
        ],
    )


def _duplicate_group_actions(group: dict[str, Any]) -> list[dict[str, Any]]:
    first = ((group.get("items") or [{}])[0]) or {}
    review_id = str(first.get("review_id") or "")
    return [
        {
            "action": "inspect_duplicate_memory_candidates",
            "label": "Inspect duplicate memory candidates",
            "tool": "pska_memory_candidate_dedup",
            "api": "GET /api/memory/candidate-dedup",
            "view": "review",
            "params": {"review_id": review_id} if review_id else {},
        }
    ]


def _related_group_actions(group: dict[str, Any]) -> list[dict[str, Any]]:
    first = ((group.get("items") or [{}])[0]) or {}
    review_id = str(first.get("review_id") or "")
    return [
        {
            "action": "inspect_related_memory_candidates",
            "label": "Inspect related memory candidates",
            "tool": "pska_memory_candidate_dedup",
            "api": "GET /api/memory/candidate-dedup",
            "view": "review",
            "params": {"review_id": review_id} if review_id else {},
        }
    ]


def _candidate_quality_issues(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = [
        issue
        for review in reviews
        if _candidate_quality_review(review)
        for issue in [_candidate_quality_issue(review)]
        if issue is not None
    ]
    return sorted(
        issues,
        key=lambda issue: (
            -_severity_rank(str(issue.get("severity") or "")),
            str(issue.get("status") or ""),
            str(issue.get("review_id") or ""),
        ),
    )


def _candidate_quality_review(review: dict[str, Any]) -> bool:
    if str(review.get("status") or "") not in {"pending", "accepted"}:
        return False
    if review.get("memory_apply"):
        return False
    proposal = review.get("proposal") or {}
    return str(proposal.get("kind") or "") == "memory_patch"


def _candidate_quality_issue(review: dict[str, Any]) -> dict[str, Any] | None:
    if not _candidate_quality_review(review):
        return None
    proposal = review.get("proposal") or {}
    payload = proposal.get("memory_patch") or {}
    metadata = payload.get("metadata") or proposal.get("metadata") or {}
    text = str(payload.get("text") or proposal.get("body") or "").strip()
    behavior_delta = str(metadata.get("behavior_delta") or "").strip()
    memory_type = str(metadata.get("memory_type") or "").strip()
    memory_scope = str(metadata.get("memory_scope") or "").strip()
    source_refs = payload.get("source_refs") or proposal.get("source_refs") or review.get("source_refs") or []
    source_count = int(review.get("source_count") or len(source_refs or []))
    issue_types: list[str] = []
    missing_fields = []
    for field_name, field_value in (
        ("memory_type", memory_type),
        ("memory_scope", memory_scope),
        ("behavior_delta", behavior_delta),
    ):
        if not field_value:
            missing_fields.append(field_name)
    if missing_fields:
        issue_types.append("missing_memory_card_fields")
    if source_count <= 0:
        issue_types.append("weak_evidence")
    if _text_too_vague(text):
        issue_types.append("vague_candidate_text")
    if behavior_delta and _behavior_delta_too_vague(behavior_delta, text):
        issue_types.append("vague_behavior_delta")
    if not issue_types:
        return None
    review_id = str(review.get("review_id") or "")
    severity = "high" if "missing_memory_card_fields" in issue_types else "medium"
    reason = _candidate_quality_reason(issue_types, missing_fields)
    return {
        "review_id": review_id,
        "status": str(review.get("status") or ""),
        "proposal_kind": str(proposal.get("kind") or ""),
        "title": str(proposal.get("title") or review_id or ""),
        "reason": reason,
        "issue_types": issue_types,
        "severity": severity,
        "memory_type": memory_type,
        "memory_scope": memory_scope,
        "behavior_delta": behavior_delta,
        "source_count": source_count,
        "evidence": {
            "missing_fields": missing_fields,
            "text_length": len(text),
            "behavior_delta_length": len(behavior_delta),
            "source_count": source_count,
            "origin": str(metadata.get("origin") or ""),
            "candidate_origin": str(metadata.get("candidate_origin") or ""),
        },
        "next_actions": _candidate_quality_actions(review),
    }


def _candidate_quality_reason(issue_types: list[str], missing_fields: list[str]) -> str:
    reasons = []
    if missing_fields:
        reasons.append(f"missing Memory Card fields: {', '.join(missing_fields)}")
    if "weak_evidence" in issue_types:
        reasons.append("no source evidence is attached")
    if "vague_candidate_text" in issue_types:
        reasons.append("candidate text looks like a generic summary")
    if "vague_behavior_delta" in issue_types:
        reasons.append("behavior_delta does not clearly change future agent behavior")
    return "; ".join(reasons) or "candidate needs quality review"


def _candidate_quality_actions(review: dict[str, Any]) -> list[dict[str, Any]]:
    review_id = str(review.get("review_id") or "")
    actions = [
        {
            "action": "review_memory_candidate_quality",
            "label": "Review candidate quality",
            "tool": "pska_review_get",
            "api": f"GET /api/reviews/{review_id}",
            "view": "review",
            "params": {"review_id": review_id},
        }
    ]
    if str(review.get("status") or "") == "pending":
        actions.append(
            {
                "action": "mark_memory_candidate_needs_edit",
                "label": "Mark candidate needs edit",
                "tool": "pska_review_decide",
                "api": f"POST /api/reviews/{review_id}/decision",
                "view": "review",
                "params": {
                    "review_id": review_id,
                    "decision": "edit",
                    "reason": "Memory Card candidate needs clearer behavior_delta, scope, type, or evidence.",
                },
            }
        )
    return actions


def _text_too_vague(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if len(normalized) < 18:
        return True
    generic_markers = (
        "remember this",
        "remember that",
        "important memory",
        "useful information",
        "general note",
        "summary",
        "摘要",
        "总结",
        "记住这个",
        "有用信息",
        "重要信息",
    )
    return any(marker in normalized for marker in generic_markers)


def _behavior_delta_too_vague(behavior_delta: str, text: str) -> bool:
    normalized = " ".join(behavior_delta.lower().split())
    if len(normalized) < 24:
        return True
    generic_markers = (
        "remember",
        "keep in mind",
        "note this",
        "be aware",
        "记住",
        "注意",
        "以后知道",
    )
    if normalized in {"remember this", "keep in mind", "记住这个"}:
        return True
    return normalized == " ".join(text.lower().split()) or any(marker == normalized for marker in generic_markers)


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _group(code: str, severity: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    title, reason = _definition(code)
    review_ids = [
        str(item.get("review_id") or "")
        for item in items
        if str(item.get("review_id") or "")
    ]
    return {
        "schema": MEMORY_REVIEW_QUEUE_GROUP_SCHEMA,
        "code": code,
        "title": title,
        "reason": reason,
        "severity": severity,
        "count": len(items),
        "review_ids": review_ids,
        "items": to_jsonable(items),
    }


def _with_review_batch_actions(group: dict[str, Any]) -> dict[str, Any]:
    if group["code"] not in {"conversation_candidates", "pending_reviews"}:
        return group
    review_ids = group.get("review_ids") or []
    if not review_ids:
        return group
    group["batch_actions"] = [
        {
            "action": "accept_review_group",
            "label": "Accept review group",
            "tool": "pska_review_decide_batch",
            "api": "POST /api/reviews/batch-decision",
            "view": "review",
            "params": {"review_ids": review_ids, "decision": "accept"},
        },
        {
            "action": "reject_review_group",
            "label": "Reject review group",
            "tool": "pska_review_decide_batch",
            "api": "POST /api/reviews/batch-decision",
            "view": "review",
            "params": {"review_ids": review_ids, "decision": "reject"},
        },
    ]
    return group


def _definition(code: str) -> tuple[str, str]:
    for item_code, title, reason in GROUP_DEFINITIONS:
        if item_code == code:
            return title, reason
    return code, code


def _summary(groups: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {group["code"]: group["count"] for group in groups}
    actionable_item_count = sum(
        counts.get(code, 0)
        for code in (
            "accepted_unapplied",
            "conversation_candidates",
            "candidate_quality",
            "duplicate_candidates",
            "related_candidates",
            "pending_reviews",
            "needs_edit",
            "memory_health",
        )
    )
    return {
        "group_count": len(groups),
        "item_count": sum(group["count"] for group in groups),
        "actionable_item_count": actionable_item_count,
        "accepted_unapplied_count": counts.get("accepted_unapplied", 0),
        "conversation_candidate_count": counts.get("conversation_candidates", 0),
        "candidate_quality_issue_count": counts.get("candidate_quality", 0),
        "duplicate_candidate_group_count": counts.get("duplicate_candidates", 0),
        "related_candidate_group_count": counts.get("related_candidates", 0),
        "pending_review_count": counts.get("pending_reviews", 0),
        "needs_edit_count": counts.get("needs_edit", 0),
        "merged_replacement_count": counts.get("merged_replacements", 0),
        "memory_health_count": counts.get("memory_health", 0),
        "memory_focus_count": counts.get("memory_focus", 0),
    }


def _status(summary: dict[str, Any]) -> str:
    if summary["accepted_unapplied_count"]:
        return "apply_ready"
    if (
        summary["conversation_candidate_count"]
        or summary["candidate_quality_issue_count"]
        or summary["duplicate_candidate_group_count"]
        or summary["related_candidate_group_count"]
        or summary["pending_review_count"]
        or summary["needs_edit_count"]
        or summary["memory_health_count"]
    ):
        return "action_required"
    if summary["memory_focus_count"]:
        return "review"
    return "ready"


def _next_actions(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for group in groups:
        first = (group.get("items") or [{}])[0]
        if group["code"] == "accepted_unapplied" and first.get("review_id"):
            actions.append(
                {
                    "action": "apply_accepted_memory",
                    "label": "Apply accepted memory",
                    "tool": "pska_memory_apply",
                    "api": f"POST /api/reviews/{first['review_id']}/apply-memory",
                    "view": "review",
                    "params": {"review_id": first["review_id"]},
                }
            )
        elif group["code"] in {"conversation_candidates", "pending_reviews", "needs_edit"} and first.get("review_id"):
            actions.append(
                {
                    "action": (
                        "review_conversation_memory_candidate"
                        if group["code"] == "conversation_candidates"
                        else "review_pending_durable_knowledge"
                    ),
                    "label": "Review conversation candidate" if group["code"] == "conversation_candidates" else "Open review",
                    "tool": "pska_review_get",
                    "api": f"GET /api/reviews/{first['review_id']}",
                    "view": "review",
                    "params": {"review_id": first["review_id"]},
                }
            )
        elif group["code"] == "candidate_quality" and first.get("review_id"):
            actions.extend((first.get("next_actions") or [])[:1])
        elif group["code"] == "duplicate_candidates":
            actions.extend(first.get("next_actions") or [])
        elif group["code"] == "related_candidates":
            actions.extend(first.get("next_actions") or [])
        elif group["code"] == "memory_health":
            actions.append(
                {
                    "action": "inspect_memory_health",
                    "label": "Inspect memory health",
                    "tool": "pska_memory_health_scan",
                    "api": "GET /api/memory/health",
                    "view": "memory",
                }
            )
        elif group["code"] == "memory_focus" and first.get("memory_id"):
            actions.append(
                {
                    "action": "inspect_memory_timeline",
                    "label": "Inspect memory timeline",
                    "tool": "pska_memory_timeline",
                    "api": f"GET /api/memory/{first['memory_id']}/timeline",
                    "view": "memory",
                    "params": {"memory_id": first["memory_id"]},
                }
            )
    return actions


def _merged_replacement_actions(review: dict[str, Any]) -> list[dict[str, Any]]:
    merged_into_review_id = _merged_into_review_id(review)
    if not merged_into_review_id:
        return _review_actions(review)
    return [
        {
            "action": "open_merged_review",
            "label": "Open merged review",
            "tool": "pska_review_get",
            "api": f"GET /api/reviews/{merged_into_review_id}",
            "view": "review",
            "params": {"review_id": merged_into_review_id},
        }
    ]


def _review_actions(review: dict[str, Any]) -> list[dict[str, Any]]:
    review_id = str(review.get("review_id") or "")
    is_conversation_candidate = _conversation_candidate_review(review)
    actions = [
        {
            "action": "review_conversation_memory_candidate" if is_conversation_candidate else "open_review",
            "label": "Review conversation candidate" if is_conversation_candidate else "Open review",
            "tool": "pska_review_get",
            "api": f"GET /api/reviews/{review_id}",
            "view": "review",
            "params": {"review_id": review_id},
        }
    ]
    if review.get("status") == "accepted" and not review.get("memory_apply") and _durable_review(review):
        actions.append(
            {
                "action": "apply_accepted_memory",
                "label": "Apply accepted memory",
                "tool": "pska_memory_apply",
                "api": f"POST /api/reviews/{review_id}/apply-memory",
                "view": "review",
                "params": {"review_id": review_id},
            }
        )
    return actions


def _durable_review(review: dict[str, Any]) -> bool:
    kind = str((review.get("proposal") or {}).get("kind") or "")
    return kind in {"memory_patch", "memory_update", "memory_delete"}


def _conversation_candidate_review(review: dict[str, Any]) -> bool:
    metadata = _review_memory_metadata(review)
    return str(metadata.get("candidate_origin") or "") in {"conversation_candidate", "conversation"}


def _review_memory_metadata(review: dict[str, Any]) -> dict[str, Any]:
    proposal = review.get("proposal") or {}
    for key in ("memory_patch", "memory_update", "memory_delete"):
        payload = proposal.get(key) or {}
        metadata = payload.get("metadata") or {}
        if metadata:
            return metadata
    return proposal.get("metadata") or {}


def _merged_into_review_id(review: dict[str, Any]) -> str:
    revision = review.get("revision") or {}
    return str(revision.get("merged_into_review_id") or "")


def _conversation_candidate_title(review: dict[str, Any]) -> str:
    metadata = _review_memory_metadata(review)
    display = str(metadata.get("display_text") or "").strip()
    if display:
        return display
    proposal = review.get("proposal") or {}
    return str(proposal.get("body") or proposal.get("title") or review.get("review_id") or "")


def _conversation_candidate_reason(review: dict[str, Any]) -> str:
    metadata = _review_memory_metadata(review)
    behavior_delta = str(metadata.get("behavior_delta") or "").strip()
    reason = str(metadata.get("reason") or "").strip()
    if behavior_delta and reason:
        return f"{behavior_delta} | {reason}"
    return behavior_delta or reason or str((review.get("proposal") or {}).get("body") or "")
