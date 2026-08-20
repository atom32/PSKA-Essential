from __future__ import annotations

from typing import Any

from pska_essential.contracts import to_jsonable


AGENTIC_SPECIALIST_PROFILE_SCHEMA = "pska.agentic_specialist_profile.v1"
AGENTIC_SPECIALIST_PROFILE_LIST_SCHEMA = "pska.agentic_specialist_profile_list.v1"


SPECIALIST_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "recall_specialist",
        "role_id": "recall_agent",
        "label": "Recall Specialist",
        "purpose": "Recover bounded source and KB context before Hermes answers.",
        "trigger_terms": [
            "source",
            "recall",
            "rag",
            "file",
            "folder",
            "kb",
            "dataset",
            "evidence",
            "来源",
            "资料",
            "召回",
            "文件",
            "知识库",
            "证据",
        ],
        "tool_profile": {
            "read_tools": ["pska_source_search", "pska_source_read", "pska_context_retrieve", "pska_trace_query"],
            "review_tools": [],
            "forbidden_tools": ["pska_memory_apply", "pska_source_tag_apply", "pska_source_comment_apply"],
            "sequence": ["search", "read_top_sources", "report_gaps"],
        },
        "output_contract": {
            "sections": ["found_sources", "missing_context", "recommended_reads"],
            "must_include": ["source_refs", "confidence"],
        },
        "baseline_priority": 8,
    },
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "memory_curator",
        "role_id": "memory_curator",
        "label": "Memory Curator",
        "purpose": "Separate durable memory from temporary source notes and candidate drafts.",
        "trigger_terms": [
            "memory",
            "remember",
            "forget",
            "candidate",
            "review",
            "gbrain",
            "记忆",
            "记住",
            "忘记",
            "候选",
            "审核",
            "长期",
        ],
        "tool_profile": {
            "read_tools": [
                "pska_memory_search",
                "pska_memory_card_get",
                "pska_memory_review_queue",
                "pska_memory_candidate_dedup",
                "pska_memory_health_scan",
            ],
            "review_tools": ["pska_memory_change_from_conversation", "pska_review_revise"],
            "forbidden_tools": ["pska_memory_apply"],
            "sequence": ["search_memory", "check_review_queue", "draft_review_only"],
        },
        "output_contract": {
            "sections": ["relevant_memories", "candidate_changes", "do_not_memorize"],
            "must_include": ["memory_scope", "behavior_delta", "source_refs"],
        },
        "baseline_priority": 7,
    },
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "trace_auditor",
        "role_id": "trace_explainer",
        "label": "Trace Auditor",
        "purpose": "Explain provenance, answer proofs, and memory-use traces without claiming hidden model causality.",
        "trigger_terms": [
            "trace",
            "proof",
            "audit",
            "why",
            "citation",
            "lineage",
            "轨迹",
            "证明",
            "审计",
            "为什么",
            "引用",
            "来源链",
        ],
        "tool_profile": {
            "read_tools": [
                "pska_trace_query",
                "pska_memory_use_trace",
                "pska_memory_why_used",
                "pska_hermes_answer_proofs",
            ],
            "review_tools": [],
            "forbidden_tools": ["pska_review_decide", "pska_memory_apply"],
            "sequence": ["query_trace", "separate_observed_from_inferred", "report_limits"],
        },
        "output_contract": {
            "sections": ["observed_events", "inferences", "limits"],
            "must_include": ["audit_event_ids", "source_refs"],
        },
        "baseline_priority": 6,
    },
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "decision_ledger_specialist",
        "role_id": "decision_ledger",
        "label": "Decision Ledger Specialist",
        "purpose": "Turn choices, tradeoffs, and reversals into reviewable decision records.",
        "trigger_terms": [
            "decision",
            "tradeoff",
            "architecture",
            "design",
            "plan",
            "risk",
            "决策",
            "取舍",
            "架构",
            "设计",
            "计划",
            "风险",
        ],
        "tool_profile": {
            "read_tools": ["pska_source_search", "pska_trace_query", "pska_memory_search"],
            "review_tools": ["pska_memory_change_from_conversation"],
            "forbidden_tools": ["pska_memory_apply", "pska_source_comment_apply"],
            "sequence": ["recover_prior_decisions", "state_options", "draft_review_candidate"],
        },
        "output_contract": {
            "sections": ["background", "options", "current_decision", "validation_plan"],
            "must_include": ["evidence", "risk", "review_needed"],
        },
        "baseline_priority": 4,
    },
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "eidolia_creation_specialist",
        "role_id": "eidolia_specialist",
        "label": "Eidolia Creation Specialist",
        "purpose": "Bridge Eidolia thoughts/artifacts into sourced creative continuation without changing canvas files.",
        "trigger_terms": [
            "eidolia",
            "canvas",
            "thought",
            "artifact",
            "novel",
            "creative",
            "writing",
            "画布",
            "创作",
            "小说",
            "续写",
            "设定",
        ],
        "tool_profile": {
            "read_tools": ["pska_eidolia_context_read", "pska_source_search", "pska_memory_search", "pska_trace_query"],
            "review_tools": ["pska_eidolia_memory_review_create"],
            "forbidden_tools": ["pska_memory_apply"],
            "sequence": ["read_thought_or_artifact", "recall_motifs", "draft_continuation_or_review"],
        },
        "output_contract": {
            "sections": ["source_motifs", "continuation_options", "memory_candidates"],
            "must_include": ["eidolia_source_refs", "privacy_boundary"],
        },
        "baseline_priority": 2,
    },
    {
        "schema": AGENTIC_SPECIALIST_PROFILE_SCHEMA,
        "profile_id": "verifier_specialist",
        "role_id": "verifier",
        "label": "Verifier Specialist",
        "purpose": "Check whether the answer plan is supported, scoped, and safe to act on.",
        "trigger_terms": [
            "verify",
            "test",
            "check",
            "risk",
            "safe",
            "demo",
            "alpha",
            "验证",
            "测试",
            "检查",
            "安全",
            "演示",
        ],
        "tool_profile": {
            "read_tools": ["pska_workspace_status", "pska_source_search", "pska_memory_health_scan", "pska_trace_query"],
            "review_tools": [],
            "forbidden_tools": ["pska_memory_apply", "pska_review_decide"],
            "sequence": ["check_scope", "find_contradictions", "state_residual_risk"],
        },
        "output_contract": {
            "sections": ["supported_claims", "unsupported_claims", "residual_risk"],
            "must_include": ["checks", "missing_evidence"],
        },
        "baseline_priority": 5,
    },
)


DEFAULT_SPECIALIST_PROFILE_IDS = ("recall_specialist", "memory_curator", "trace_auditor", "verifier_specialist")


def build_agentic_specialist_profiles(
    *,
    objective: str = "",
    question: str = "",
    project_hint: str = "",
    profile_ids: list[str] | tuple[str, ...] | None = None,
    limit: int = 4,
) -> dict[str, Any]:
    selected_ids = _profile_ids(profile_ids)
    profiles = [_profile_copy(profile) for profile in SPECIALIST_PROFILES]
    by_id = {profile["profile_id"]: profile for profile in profiles}
    warnings: list[dict[str, Any]] = []

    if selected_ids:
        recommended = []
        for profile_id in selected_ids:
            profile = by_id.get(profile_id)
            if profile is None:
                warnings.append({"code": "unknown_specialist_profile", "profile_id": profile_id})
                continue
            recommended.append(profile)
        selection_mode = "explicit"
    else:
        recommended = _recommend_profiles(
            profiles,
            prompt=" ".join(str(item or "") for item in (objective, question, project_hint)),
            limit=_bounded_limit(limit, default=4, maximum=len(profiles)),
        )
        selection_mode = "deterministic_keyword"

    bounded = _bounded_limit(limit, default=4, maximum=len(profiles))
    recommended = recommended[:bounded]
    return to_jsonable(
        {
            "schema": AGENTIC_SPECIALIST_PROFILE_LIST_SCHEMA,
            "status": "ready",
            "selection_mode": selection_mode,
            "profile_count": len(profiles),
            "selected_profile_ids": [profile["profile_id"] for profile in recommended],
            "recommended_profiles": recommended,
            "profiles": profiles,
            "warnings": warnings,
            "data_flow": {
                "starts_agents": False,
                "runs_tools": False,
                "writes_source_files": False,
                "writes_memory_directly": False,
                "creates_review": False,
                "generates_answer_text": False,
            },
            "limitations": [
                "Profiles are deterministic tool-boundary hints for Hermes; they are not independent resident agents.",
                "Review-capable tools still require PSKA Review and explicit apply for durable memory changes.",
                "Forbidden tools document the profile boundary; enforcement still comes from PSKA tool policy and API permissions.",
            ],
        }
    )


def _recommend_profiles(profiles: list[dict[str, Any]], *, prompt: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    normalized = prompt.lower()
    scored = []
    for index, profile in enumerate(profiles):
        terms = [str(term).lower() for term in profile.get("trigger_terms") or []]
        matches = [term for term in terms if term and term in normalized]
        score = int(profile.get("baseline_priority") or 0) + len(matches) * 10
        scored.append((score, -index, matches, profile))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, _index, matches, profile in scored:
        if score <= 0 and len(selected) >= len(DEFAULT_SPECIALIST_PROFILE_IDS):
            continue
        enriched = _profile_copy(profile)
        enriched["selection"] = {
            "score": score,
            "matched_terms": matches[:8],
        }
        selected.append(enriched)
        seen.add(str(profile["profile_id"]))
        if len(selected) >= limit:
            break
    for profile_id in DEFAULT_SPECIALIST_PROFILE_IDS:
        if len(selected) >= limit or profile_id in seen:
            continue
        profile = next((item for item in profiles if item.get("profile_id") == profile_id), None)
        if profile is None:
            continue
        enriched = _profile_copy(profile)
        enriched["selection"] = {"score": int(enriched.get("baseline_priority") or 0), "matched_terms": []}
        selected.append(enriched)
        seen.add(profile_id)
    return selected


def _profile_ids(value: list[str] | tuple[str, ...] | None) -> list[str]:
    result = []
    for item in value or []:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _bounded_limit(value: Any, *, default: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0), maximum)


def _profile_copy(profile: dict[str, Any]) -> dict[str, Any]:
    return dict(profile)
