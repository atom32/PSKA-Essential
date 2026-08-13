from __future__ import annotations

from typing import Any

from pska_essential.contracts import SourceRef, to_jsonable, utc_now_iso


MEMORY_ATTRIBUTION_SCHEMA = "pska.memory_attribution.v1"
MEMORY_SUGGESTIONS_SCHEMA = "pska.memory_suggestions.v1"
MEMORY_SUGGESTION_SCHEMA = "pska.memory_suggestion.v1"


def build_memory_attribution(
    *,
    run_id: str,
    question: str,
    status: str,
    memory_facts: list[Any],
    context_packets: list[Any],
    proposal: Any = None,
) -> dict[str, Any]:
    used = _memory_use_records(memory_facts, context_packets)
    return {
        "schema": MEMORY_ATTRIBUTION_SCHEMA,
        "run_id": run_id,
        "question": question,
        "status": status,
        "used_memory_ids": [item["memory_id"] for item in used],
        "used_memory_count": len(used),
        "used_memories": used,
        "proposal_id": _proposal_id(proposal),
        "proposal_kind": _proposal_kind(proposal),
        "confidence": "answer_context" if used else "no_memory_context",
        "method": "agentic_loop_memory_context",
        "generated_at": utc_now_iso(),
        "limitations": [
            "This is answer-level context attribution from PSKA's agentic loop.",
            "It records memories supplied to the final work product context, not a neural causal proof.",
        ],
    }


def build_memory_suggestions(
    *,
    run_id: str,
    question: str,
    status: str,
    context_packets: list[Any],
    memory_facts: list[Any],
    proposal: Any = None,
) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    if status == "ready":
        source_refs = _unique_source_refs(
            [
                *_source_refs_from_context(context_packets),
                *_source_refs_from_memory_facts(memory_facts),
                *_source_refs_from_proposal(proposal),
            ]
        )
        if source_refs and _proposal_body(proposal):
            suggestions.append(
                {
                    "schema": MEMORY_SUGGESTION_SCHEMA,
                    "suggestion_id": f"mem_suggest_{run_id}_workflow",
                    "type": "workflow_memory_review",
                    "status": "candidate",
                    "title": "Create governed Memory Card from this answer",
                    "reason": "The workflow produced a sourced answer that may be worth preserving as durable memory.",
                    "confidence": 0.72,
                    "run_id": run_id,
                    "source_count": len(source_refs),
                    "used_memory_ids": [_memory_fact_id(fact) for fact in memory_facts if _memory_fact_id(fact)],
                    "evidence": {
                        "question": question,
                        "proposal_id": _proposal_id(proposal),
                        "proposal_kind": _proposal_kind(proposal),
                        "source_refs": to_jsonable(source_refs),
                    },
                    "next_actions": [
                        {
                            "action": "create_memory_review_from_workflow",
                            "label": "Create Memory Review",
                            "api": f"POST /api/workflows/{run_id}/memory-review",
                            "tool": "pska_memory_review_from_workflow",
                            "view": "review",
                            "params": {"run_id": run_id},
                        }
                    ],
                }
            )
    return {
        "schema": MEMORY_SUGGESTIONS_SCHEMA,
        "run_id": run_id,
        "status": "has_suggestions" if suggestions else "none",
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
        "generated_at": utc_now_iso(),
        "limitations": [
            "Suggestions are review candidates only.",
            "PSKA never writes durable memory from suggestions without the governed review path.",
        ],
    }


def build_attribution_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    run = artifact.get("run") or {}
    latest = artifact.get("latest_proposal")
    return build_memory_attribution(
        run_id=str(run.get("run_id") or ""),
        question=str(run.get("intent") or ""),
        status=str(run.get("status") or ""),
        memory_facts=list(artifact.get("memory_facts") or []),
        context_packets=list(artifact.get("context_packets") or []),
        proposal=latest,
    )


def build_suggestions_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    run = artifact.get("run") or {}
    latest = artifact.get("latest_proposal")
    return build_memory_suggestions(
        run_id=str(run.get("run_id") or ""),
        question=str(run.get("intent") or ""),
        status="ready" if latest else str(run.get("status") or ""),
        context_packets=list(artifact.get("context_packets") or []),
        memory_facts=list(artifact.get("memory_facts") or []),
        proposal=latest,
    )


def _memory_use_records(memory_facts: list[Any], context_packets: list[Any]) -> list[dict[str, Any]]:
    source_fact_ids = _memory_ids_from_context(context_packets)
    records: list[dict[str, Any]] = []
    for index, fact in enumerate(memory_facts, start=1):
        memory_id = _memory_fact_id(fact)
        if not memory_id:
            continue
        metadata = _memory_metadata(fact)
        source_refs = _memory_source_refs(fact)
        records.append(
            {
                "memory_id": memory_id,
                "index": index,
                "display_text": _memory_display_text(fact),
                "memory_type": str(metadata.get("memory_type") or "unspecified"),
                "memory_scope": str(metadata.get("memory_scope") or ""),
                "source_count": len(source_refs),
                "source_refs": to_jsonable(source_refs),
                "used_as": "memory_context",
                "evidence_status": "federated_source_context" if memory_id in source_fact_ids else "memory_fact_context",
            }
        )
    return records


def _memory_ids_from_context(context_packets: list[Any]) -> set[str]:
    ids: set[str] = set()
    for packet in context_packets:
        metadata = _packet_metadata(packet)
        for memory_id in metadata.get("memory_fact_ids") or []:
            if str(memory_id).strip():
                ids.add(str(memory_id).strip())
    return ids


def _packet_metadata(packet: Any) -> dict[str, Any]:
    if isinstance(packet, dict):
        return dict(packet.get("metadata") or {})
    return dict(getattr(packet, "metadata", {}) or {})


def _source_refs_from_context(context_packets: list[Any]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for packet in context_packets:
        ref = packet.get("source_ref") if isinstance(packet, dict) else getattr(packet, "source_ref", None)
        parsed = _source_ref_from_value(ref)
        if parsed:
            refs.append(parsed)
    return refs


def _source_refs_from_memory_facts(memory_facts: list[Any]) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for fact in memory_facts:
        refs.extend(_memory_source_refs(fact))
    return refs


def _source_refs_from_proposal(proposal: Any) -> list[SourceRef]:
    if not proposal:
        return []
    raw_refs = proposal.get("source_refs") if isinstance(proposal, dict) else getattr(proposal, "source_refs", [])
    refs: list[SourceRef] = []
    for raw in raw_refs or []:
        parsed = _source_ref_from_value(raw)
        if parsed:
            refs.append(parsed)
    return refs


def _memory_source_refs(fact: Any) -> list[SourceRef]:
    raw_refs = fact.get("source_refs") if isinstance(fact, dict) else getattr(fact, "source_refs", [])
    refs: list[SourceRef] = []
    for raw in raw_refs or []:
        parsed = _source_ref_from_value(raw)
        if parsed:
            refs.append(parsed)
    return refs


def _source_ref_from_value(value: Any) -> SourceRef | None:
    if isinstance(value, SourceRef):
        return value
    if isinstance(value, dict) and value.get("adapter"):
        return SourceRef.from_dict(value)
    return None


def _unique_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    result: list[SourceRef] = []
    for ref in source_refs:
        key = "|".join(
            [
                ref.adapter,
                ref.dataset_id or "",
                ref.document_id or "",
                ref.chunk_id or "",
                ref.source_id or "",
                ref.external_id or "",
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _memory_fact_id(fact: Any) -> str:
    if isinstance(fact, dict):
        return str(fact.get("fact_id") or "")
    return str(getattr(fact, "fact_id", "") or "")


def _memory_metadata(fact: Any) -> dict[str, Any]:
    if isinstance(fact, dict):
        return dict(fact.get("metadata") or {})
    return dict(getattr(fact, "metadata", {}) or {})


def _memory_display_text(fact: Any) -> str:
    metadata = _memory_metadata(fact)
    for key in ("display_text", "current_text", "summary"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(fact, dict):
        return str(fact.get("text") or "").strip()
    return str(getattr(fact, "text", "") or "").strip()


def _proposal_id(proposal: Any) -> str:
    if not proposal:
        return ""
    if isinstance(proposal, dict):
        return str(proposal.get("proposal_id") or "")
    return str(getattr(proposal, "proposal_id", "") or "")


def _proposal_kind(proposal: Any) -> str:
    if not proposal:
        return ""
    if isinstance(proposal, dict):
        return str(proposal.get("kind") or "")
    return str(getattr(proposal, "kind", "") or "")


def _proposal_body(proposal: Any) -> str:
    if not proposal:
        return ""
    if isinstance(proposal, dict):
        return str(proposal.get("body") or "")
    return str(getattr(proposal, "body", "") or "")
