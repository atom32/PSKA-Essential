from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.capabilities import product_capabilities
from pska_essential.contracts import ContextPacket, MemoryFact, SourceRef, to_jsonable, utc_now_iso
from pska_essential.jarvis import build_jarvis_briefing
from pska_essential.memory_use_trace import list_memory_use_traces
from pska_essential.trace_query import build_trace_query


AGENTIC_CONTEXT_BRIEF_SCHEMA = "pska.agentic_context_brief.v1"


class AgenticContextBriefError(ValueError):
    pass


def build_agentic_context_brief(
    *,
    service: Any,
    gateway: Any,
    objective: str = "",
    question: str = "",
    project_hint: str = "",
    scope: dict[str, Any] | None = None,
    source_scope: dict[str, Any] | None = None,
    evidence_limit: int = 5,
    source_limit: int = 5,
    memory_limit: int = 5,
    trace_limit: int = 8,
    audit: bool = True,
) -> dict[str, Any]:
    """Build a read-only context brief for Hermes before it answers or acts."""

    selected_objective = _normalized_text(objective)
    selected_question = _normalized_text(question)
    prompt = _brief_prompt(selected_objective, selected_question, project_hint)
    if not prompt:
        raise AgenticContextBriefError("objective or question is required")

    selected_scope = dict(scope or {})
    selected_source_scope = _source_scope(selected_scope, source_scope)
    requested_evidence_limit = _bounded_limit(evidence_limit, default=5, maximum=20)
    requested_source_limit = _bounded_limit(source_limit, default=5, maximum=20)
    requested_memory_limit = _bounded_limit(memory_limit, default=5, maximum=20)
    requested_trace_limit = _bounded_limit(trace_limit, default=8, maximum=30)
    brief_id = f"agentic_brief_{uuid4().hex}"

    warnings: list[dict[str, Any]] = []
    jarvis, jarvis_error = _safe_jarvis_briefing(
        service=service,
        gateway=gateway,
        scope=selected_scope,
        source_scope=selected_source_scope,
    )
    if jarvis_error:
        warnings.append(jarvis_error)

    run, evidence_packets, evidence_error = _safe_retrieve_evidence(
        service=service,
        prompt=prompt,
        scope=selected_scope,
        limit=requested_evidence_limit,
    )
    if evidence_error:
        warnings.append(evidence_error)
    evidence_blocks = [_evidence_block(packet, index) for index, packet in enumerate(evidence_packets, start=1)]

    source_packets, source_error = _safe_source_search(
        service=service,
        prompt=prompt,
        scope=selected_source_scope,
        limit=requested_source_limit,
    )
    if source_error:
        warnings.append(source_error)
    source_blocks = [_source_recall_block(packet, index) for index, packet in enumerate(source_packets, start=1)]

    memory_facts, memory_error = _safe_memory_search(
        service=service,
        prompt=prompt,
        scope=selected_scope,
        limit=requested_memory_limit,
        run_id=getattr(run, "run_id", ""),
    )
    if memory_error:
        warnings.append(memory_error)
    memory_notes = [_memory_note(fact, index) for index, fact in enumerate(memory_facts, start=1)]

    trace = _trace_layer(
        service,
        memory_facts=memory_facts,
        source_refs=_unique_source_refs(evidence_packets, source_packets, memory_facts),
        limit=requested_trace_limit,
        warnings=warnings,
    )
    next_actions = _next_actions(
        question=selected_question or selected_objective or prompt,
        scope=selected_scope,
        evidence_blocks=evidence_blocks,
        source_blocks=source_blocks,
        memory_notes=memory_notes,
        trace=trace,
        jarvis=jarvis,
    )
    status = _brief_status(
        warnings=warnings,
        evidence_blocks=evidence_blocks,
        source_blocks=source_blocks,
        memory_notes=memory_notes,
        trace=trace,
        jarvis=jarvis,
    )
    summary = _summary(
        status=status,
        evidence_blocks=evidence_blocks,
        source_blocks=source_blocks,
        memory_notes=memory_notes,
        trace=trace,
        next_actions=next_actions,
        warnings=warnings,
    )
    result = {
        "schema": AGENTIC_CONTEXT_BRIEF_SCHEMA,
        "brief_id": brief_id,
        "created_at": utc_now_iso(),
        "status": status,
        "objective": selected_objective,
        "question": selected_question,
        "project_hint": _normalized_text(project_hint),
        "scope": selected_scope,
        "source_scope": selected_source_scope,
        "run_id": getattr(run, "run_id", ""),
        "summary": summary,
        "agentic_roles": _agentic_roles(),
        "recall": {
            "query": prompt,
            "evidence_blocks": evidence_blocks,
            "source_recall": source_blocks,
            "counts": {
                "evidence": len(evidence_blocks),
                "source_recall": len(source_blocks),
            },
        },
        "memory": {
            "relevant_memories": memory_notes,
            "count": len(memory_notes),
            "search_supported": _memory_search_supported(service),
        },
        "trace": trace,
        "jarvis": jarvis,
        "warnings": warnings,
        "next_actions": next_actions,
        "data_flow": {
            "writes_source_files": False,
            "writes_memory_directly": False,
            "creates_review": False,
            "generates_answer_text": False,
            "embedding_required": False,
            "writes_audit_log": bool(audit),
            "writes_workflow_record": True,
        },
        "limitations": [
            "This brief prepares context for Hermes or another agent; it does not generate the final answer.",
            "Trace entries are audit/review evidence and memory-use candidates, not hidden model causality.",
            "Source recall is bounded by registered PSKA source indexes and selected KB scope.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "agentic_context.brief.build",
                "assistant_briefing",
                brief_id,
                status=status,
                run_id=getattr(run, "run_id", ""),
                objective=selected_objective,
                question=selected_question,
                evidence_count=len(evidence_blocks),
                source_recall_count=len(source_blocks),
                memory_count=len(memory_notes),
                trace_signal_count=trace["signal_count"],
                next_action_count=len(next_actions),
                warning_count=len(warnings),
                writes_source_files=False,
                writes_memory_directly=False,
                generates_answer_text=False,
                embedding_required=False,
            )
        )
    return to_jsonable(result)


def _brief_prompt(objective: str, question: str, project_hint: str) -> str:
    parts = [
        ("Objective", objective),
        ("Question", question),
        ("Project", _normalized_text(project_hint)),
    ]
    return "\n".join(f"{label}: {value}" for label, value in parts if value)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_limit(value: Any, *, default: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0), maximum)


def _source_scope(scope: dict[str, Any], source_scope: dict[str, Any] | None) -> dict[str, Any]:
    if source_scope is not None:
        return dict(source_scope)
    selected: dict[str, Any] = {}
    for key in ("root_id", "root_ids", "source_kind", "source_kinds", "permission_mode"):
        if key in scope:
            selected[key] = scope[key]
    nested = scope.get("source_scope")
    if isinstance(nested, dict):
        selected.update(nested)
    return selected


def _safe_jarvis_briefing(
    *,
    service: Any,
    gateway: Any,
    scope: dict[str, Any],
    source_scope: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return (
            build_jarvis_briefing(
                service=service,
                gateway=gateway,
                scope=scope,
                source_scope=source_scope,
                audit_limit=12,
                dataset_page_size=20,
                review_limit=30,
                workflow_limit=30,
            ),
            None,
        )
    except Exception as exc:  # noqa: BLE001 - brief must degrade gracefully.
        return None, _warning("jarvis_briefing_failed", exc)


def _safe_retrieve_evidence(
    *,
    service: Any,
    prompt: str,
    scope: dict[str, Any],
    limit: int,
) -> tuple[Any | None, list[ContextPacket], dict[str, Any] | None]:
    run = service.start(f"agentic-context-brief: {prompt[:160]}", {**scope, "agentic_context_brief": True})
    if limit <= 0:
        return run, [], None
    try:
        return run, list(service.context_retrieve(run.run_id, prompt, limit)), None
    except Exception as exc:  # noqa: BLE001 - evidence is useful but optional for the brief.
        return run, [], _warning("evidence_retrieval_failed", exc)


def _safe_source_search(
    *,
    service: Any,
    prompt: str,
    scope: dict[str, Any],
    limit: int,
) -> tuple[list[ContextPacket], dict[str, Any] | None]:
    if limit <= 0:
        return [], None
    search = getattr(service, "source_search", None)
    if not callable(search):
        return [], {"code": "source_search_unavailable", "message": "service does not expose source_search"}
    try:
        return list(search(prompt, scope, limit=limit, filters={})), None
    except Exception as exc:  # noqa: BLE001 - local source indexes may not be configured yet.
        return [], _warning("source_search_failed", exc)


def _safe_memory_search(
    *,
    service: Any,
    prompt: str,
    scope: dict[str, Any],
    limit: int,
    run_id: str,
) -> tuple[list[MemoryFact], dict[str, Any] | None]:
    if limit <= 0:
        return [], None
    if not _memory_search_supported(service):
        return [], {
            "code": "memory_search_unsupported",
            "message": "configured memory adapter does not support PSKA memory search",
        }
    try:
        facts = service.memory_search(
            prompt,
            scope,
            limit,
            trace_context={
                "caller": "agentic_context_brief",
                "run_id": run_id,
                "purpose": "pre_answer_context_brief",
                "used_as": "candidate_memory",
                "usage_stage": "agentic_context_brief",
            },
        )
        return list(facts), None
    except Exception as exc:  # noqa: BLE001 - memory should not block source recall.
        return [], _warning("memory_search_failed", exc)


def _memory_search_supported(service: Any) -> bool:
    try:
        capabilities = product_capabilities(memory_adapter=service.memory)
    except Exception:  # noqa: BLE001 - capability contract can fail on experimental adapters.
        return True
    search_capability = capabilities["memory"]["operations"].get("search", {})
    return search_capability.get("supported") is not False


def _evidence_block(packet: ContextPacket, index: int) -> dict[str, Any]:
    source_ref = packet.source_ref
    return {
        "type": "evidence",
        "index": index,
        "context_id": packet.context_id,
        "title": packet.title or source_ref.title or packet.context_id,
        "text": packet.text,
        "score": packet.score,
        "source_ref": to_jsonable(source_ref),
        "metadata": to_jsonable(packet.metadata),
    }


def _source_recall_block(packet: ContextPacket, index: int) -> dict[str, Any]:
    block = _evidence_block(packet, index)
    block["type"] = "source_recall"
    return block


def _memory_note(fact: MemoryFact, index: int) -> dict[str, Any]:
    metadata = dict(getattr(fact, "metadata", {}) or {})
    return {
        "type": "memory",
        "index": index,
        "fact_id": fact.fact_id,
        "text": fact.text,
        "confidence": metadata.get("confidence"),
        "valid_at": fact.valid_at or "",
        "invalid_at": fact.invalid_at or "",
        "source_refs": to_jsonable(fact.source_refs),
        "metadata": to_jsonable(metadata),
    }


def _trace_layer(
    service: Any,
    *,
    memory_facts: list[MemoryFact],
    source_refs: list[SourceRef],
    limit: int,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    memory_traces = _memory_use_trace_summaries(service, memory_facts, limit=limit, warnings=warnings)
    source_traces = _source_trace_summaries(service, source_refs, limit=limit, warnings=warnings)
    signal_count = sum(item.get("trace_count", 0) for item in memory_traces) + sum(
        item.get("entry_count", 0) for item in source_traces
    )
    return {
        "status": "found" if signal_count else "empty",
        "signal_count": signal_count,
        "memory_use_traces": memory_traces,
        "source_traces": source_traces,
    }


def _memory_use_trace_summaries(
    service: Any,
    memory_facts: list[MemoryFact],
    *,
    limit: int,
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    if limit <= 0:
        return summaries
    for fact in memory_facts[:limit]:
        try:
            trace = list_memory_use_traces(service, memory_id=fact.fact_id, limit=max(1, min(limit, 5)), audit=False)
        except Exception as exc:  # noqa: BLE001 - trace is an overlay.
            warnings.append({"code": "memory_use_trace_failed", "memory_id": fact.fact_id, "message": str(exc)})
            continue
        summaries.append(
            {
                "memory_id": fact.fact_id,
                "status": trace.get("status") or "ok",
                "trace_count": trace.get("count", 0),
                "traces": (trace.get("traces") or [])[:3],
                "confidence": "candidate_retrieval" if trace.get("count") else "no_trace",
            }
        )
    return summaries


def _source_trace_summaries(
    service: Any,
    source_refs: list[SourceRef],
    *,
    limit: int,
    warnings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries = []
    if limit <= 0:
        return summaries
    for source_ref in source_refs[:limit]:
        try:
            trace = build_trace_query(service, source_ref=source_ref, limit=max(1, min(limit, 5)), audit=False)
        except Exception as exc:  # noqa: BLE001 - a source may simply have no ledger coverage.
            warnings.append({"code": "source_trace_failed", "source_ref": to_jsonable(source_ref), "message": str(exc)})
            continue
        summaries.append(
            {
                "source_ref": to_jsonable(source_ref),
                "status": trace.get("status") or "empty",
                "entry_count": trace.get("entry_count", 0),
                "summary": trace.get("summary") or {},
                "entries": (trace.get("entries") or [])[:3],
            }
        )
    return summaries


def _unique_source_refs(
    evidence_packets: list[ContextPacket],
    source_packets: list[ContextPacket],
    memory_facts: list[MemoryFact],
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    refs.extend(packet.source_ref for packet in evidence_packets)
    refs.extend(packet.source_ref for packet in source_packets)
    for fact in memory_facts:
        refs.extend(fact.source_refs)
    result: list[SourceRef] = []
    seen: set[str] = set()
    for ref in refs:
        key = json.dumps(to_jsonable(ref), sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _summary(
    *,
    status: str,
    evidence_blocks: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]],
    memory_notes: list[dict[str, Any]],
    trace: dict[str, Any],
    next_actions: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "evidence_count": len(evidence_blocks),
        "source_recall_count": len(source_blocks),
        "memory_count": len(memory_notes),
        "trace_signal_count": trace.get("signal_count", 0),
        "next_action_count": len(next_actions),
        "warning_count": len(warnings),
        "lead": (
            f"Prepared {len(evidence_blocks)} KB evidence block(s), "
            f"{len(source_blocks)} source recall item(s), "
            f"{len(memory_notes)} memory note(s), and "
            f"{trace.get('signal_count', 0)} trace signal(s)."
        ),
    }


def _brief_status(
    *,
    warnings: list[dict[str, Any]],
    evidence_blocks: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]],
    memory_notes: list[dict[str, Any]],
    trace: dict[str, Any],
    jarvis: dict[str, Any] | None,
) -> str:
    has_context = bool(evidence_blocks or source_blocks or memory_notes or trace.get("signal_count"))
    has_operational_context = bool(jarvis and jarvis.get("status") != "error")
    if warnings and has_context:
        return "degraded"
    if warnings and not (has_context or has_operational_context):
        return "error"
    if has_context or has_operational_context:
        return "ready"
    return "needs_more_context"


def _agentic_roles() -> list[dict[str, Any]]:
    return [
        {
            "role_id": "recall_agent",
            "label": "Recall Agent",
            "purpose": "Select evidence and source recall before answer generation.",
            "entry_tools": ["pska_agentic_context_brief", "pska_context_retrieve", "pska_source_search"],
        },
        {
            "role_id": "memory_curator",
            "label": "Memory Curator",
            "purpose": "Separate relevant durable memory from new memory candidates and corrections.",
            "entry_tools": ["pska_memory_search", "pska_memory_card_get", "pska_memory_review_queue"],
        },
        {
            "role_id": "trace_explainer",
            "label": "Trace Explainer",
            "purpose": "Explain where recalled memories and sources came from without claiming hidden model causality.",
            "entry_tools": ["pska_trace_query", "pska_memory_use_trace", "pska_memory_why_used"],
        },
    ]


def _next_actions(
    *,
    question: str,
    scope: dict[str, Any],
    evidence_blocks: list[dict[str, Any]],
    source_blocks: list[dict[str, Any]],
    memory_notes: list[dict[str, Any]],
    trace: dict[str, Any],
    jarvis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    dataset_ids = [str(item) for item in scope.get("dataset_ids") or [] if str(item).strip()]
    document_ids = [str(item) for item in scope.get("document_ids") or [] if str(item).strip()]
    if dataset_ids:
        actions.append(
            {
                "action": "run_agentic_question",
                "label": "Run Sourced Ask",
                "reason": "Use this brief as pre-answer context, then let Hermes run the PSKA Ask loop over the selected ready scope.",
                "tool": "pska_agentic_question_start",
                "api": "POST /api/ask",
                "view": "ask",
                "params": {"question": question, "dataset_ids": dataset_ids, "document_ids": document_ids},
            }
        )
    top_source = (source_blocks or evidence_blocks or [{}])[0].get("source_ref")
    if isinstance(top_source, dict) and top_source:
        actions.append(
            {
                "action": "inspect_source",
                "label": "Inspect Top Source",
                "reason": "Read the strongest recalled source before turning it into an answer or memory candidate.",
                "tool": "pska_source_read",
                "api": "POST /api/sources/read",
                "view": "reader",
                "params": {"source_ref": top_source},
            }
        )
    if memory_notes:
        memory_id = str(memory_notes[0].get("fact_id") or "")
        actions.append(
            {
                "action": "inspect_memory_card",
                "label": "Inspect Memory Card",
                "reason": "Open the most relevant durable memory before using it as behavioral context.",
                "tool": "pska_memory_card_get",
                "api": f"GET /api/memory/cards/{memory_id}",
                "view": "memory",
                "params": {"memory_id": memory_id},
            }
        )
    if memory_notes and trace.get("signal_count", 0) <= 0:
        actions.append(
            {
                "action": "explain_memory_use",
                "label": "Explain Memory Use",
                "reason": "Trace why the top memory appeared in this context brief.",
                "tool": "pska_memory_why_used",
                "api": f"GET /api/memory/{memory_notes[0].get('fact_id')}/why-used",
                "view": "memory",
                "params": {"memory_id": str(memory_notes[0].get("fact_id") or "")},
            }
        )
    actions.extend((jarvis or {}).get("next_actions") or [])
    return _dedupe_actions(actions)[:8]


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen: set[str] = set()
    for action in actions:
        key = "|".join(
            [
                str(action.get("action") or ""),
                str(action.get("tool") or ""),
                json.dumps(action.get("params") or {}, sort_keys=True, ensure_ascii=False),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _warning(code: str, exc: Exception) -> dict[str, Any]:
    return {"code": code, "message": str(exc), "type": exc.__class__.__name__}
