from __future__ import annotations

from typing import Any

from pska_essential.contracts import to_jsonable


def memory_candidate_quality_issue(
    review: dict[str, Any],
    *,
    include_actions: bool = True,
) -> dict[str, Any] | None:
    if not memory_candidate_quality_review(review):
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
    if _text_too_vague(text, has_behavior_delta=bool(behavior_delta)):
        issue_types.append("vague_candidate_text")
    if behavior_delta and _behavior_delta_too_vague(behavior_delta, text):
        issue_types.append("vague_behavior_delta")
    if not issue_types:
        return None
    review_id = str(review.get("review_id") or "")
    severity = "high" if "missing_memory_card_fields" in issue_types else "medium"
    issue = {
        "review_id": review_id,
        "status": str(review.get("status") or ""),
        "proposal_kind": str(proposal.get("kind") or ""),
        "title": str(proposal.get("title") or review_id or ""),
        "reason": _candidate_quality_reason(issue_types, missing_fields),
        "issue_types": issue_types,
        "severity": severity,
        "memory_type": memory_type,
        "memory_scope": memory_scope,
        "text": text,
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
    }
    if include_actions:
        issue["next_actions"] = _candidate_quality_actions(review)
    return to_jsonable(issue)


def memory_candidate_quality_review(review: dict[str, Any]) -> bool:
    if str(review.get("status") or "") not in {"pending", "accepted"}:
        return False
    if review.get("memory_apply"):
        return False
    proposal = review.get("proposal") or {}
    return str(proposal.get("kind") or "") == "memory_patch"


def review_record_for_quality(
    *,
    review_id: str,
    status: str,
    proposal: Any,
    memory_apply: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proposal_payload = _proposal_payload(proposal)
    return {
        "review_id": review_id,
        "status": status,
        "proposal": proposal_payload,
        "source_refs": proposal_payload.get("source_refs") or [],
        "source_count": len(proposal_payload.get("source_refs") or []),
        "memory_apply": memory_apply,
    }


def quality_issue_message(issue: dict[str, Any]) -> str:
    issue_types = ", ".join(str(item) for item in issue.get("issue_types") or [] if str(item))
    reason = str(issue.get("reason") or "candidate fails Memory Card quality gate").strip()
    if issue_types:
        return f"memory candidate quality gate failed: {reason} ({issue_types})"
    return f"memory candidate quality gate failed: {reason}"


def _proposal_payload(proposal: Any) -> dict[str, Any]:
    if isinstance(proposal, dict):
        return dict(proposal)
    if hasattr(proposal, "__dataclass_fields__"):
        return to_jsonable(proposal)
    return dict(proposal or {})


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


def _text_too_vague(text: str, *, has_behavior_delta: bool) -> bool:
    normalized = " ".join(text.lower().split())
    if len(normalized) < 18 and not has_behavior_delta:
        return True
    generic_phrases = {
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
    }
    if normalized in generic_phrases:
        return True
    generic_prefixes = (
        "remember this:",
        "remember that:",
        "important memory:",
        "useful information:",
        "general note:",
        "summary:",
        "摘要：",
        "总结：",
    )
    return any(normalized.startswith(prefix) for prefix in generic_prefixes)


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
