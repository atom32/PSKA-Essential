from __future__ import annotations

from typing import Any

from pska_essential.contracts import Proposal, SourceRef, to_jsonable, utc_now_iso
from pska_essential.runtime_context import build_runtime_workspace_context


MANIFEST_SCHEMA = "pska.migration_manifest.v1"


def build_migration_manifest(service: Any, *, limit: int = 200) -> dict[str, Any]:
    """Build a provider-owned migration manifest.

    The manifest is deliberately a control-plane inventory. It lists PSKA
    workflow/review/audit records and provider coordinates, but it does not dump
    raw documents, chunks, embeddings, memory graph facts, or provider-native
    tables.
    """

    if limit < 1:
        raise ValueError("limit must be greater than 0")
    workflows = service.store.list_workflows(limit=limit)
    reviews = service.store.list_reviews(limit=limit)
    audit_events = service.store.list_audit_events(limit=limit, descending=True)
    proposals = _collect_proposals(service, workflows, reviews, limit=limit)
    source_refs = _unique_source_refs(
        [
            *[
                packet.source_ref
                for workflow in workflows
                for packet in workflow.context_packets
            ],
            *[
                ref
                for proposal in proposals
                for ref in proposal.source_refs
            ],
            *[
                ref
                for review in reviews
                for ref in _source_refs_from_value(review)
            ],
            *[
                ref
                for event in audit_events
                for ref in _source_refs_from_value(event.metadata)
            ],
        ]
    )
    memory_targets = _memory_targets(reviews, audit_events)
    adapter_groups = _source_refs_by_adapter(source_refs)
    return {
        "kind": "migration_manifest",
        "schema": MANIFEST_SCHEMA,
        "generated_at": utc_now_iso(),
        "workspace": build_runtime_workspace_context().to_dict(),
        "limits": {"record_limit": limit},
        "components": {
            "pska": _pska_component(workflows, proposals, reviews, audit_events),
            "retrieval_providers": _retrieval_provider_components(adapter_groups),
            "memory_providers": _memory_provider_components(memory_targets, source_refs),
            "agent_hosts": _agent_host_components(adapter_groups),
        },
        "provider_source_refs": [_safe_source_ref(ref) for ref in source_refs],
        "memory_targets": memory_targets,
        "migration_plan": _migration_plan(),
        "exclusions": [
            "raw_documents",
            "chunks",
            "embeddings",
            "provider_native_indexes",
            "graph_nodes",
            "graph_edges",
            "hermes_messages",
            "artifact_binaries",
        ],
    }


def _collect_proposals(service: Any, workflows: list[Any], reviews: list[dict[str, Any]], *, limit: int) -> list[Proposal]:
    proposal_ids: list[str] = []
    seen: set[str] = set()
    for workflow in workflows:
        for proposal_id in workflow.proposal_ids:
            normalized = str(proposal_id or "")
            if normalized and normalized not in seen:
                seen.add(normalized)
                proposal_ids.append(normalized)
    for review in reviews:
        normalized = str(review.get("proposal_id") or "")
        if normalized and normalized not in seen:
            seen.add(normalized)
            proposal_ids.append(normalized)
    proposals: list[Proposal] = []
    for proposal_id in proposal_ids[:limit]:
        try:
            proposals.append(service.store.get_proposal(proposal_id))
        except KeyError:
            continue
    return proposals


def _pska_component(workflows: list[Any], proposals: list[Proposal], reviews: list[dict[str, Any]], audit_events: list[Any]) -> dict[str, Any]:
    return {
        "role": "control_plane",
        "owns": [
            "workflows",
            "proposals",
            "reviews",
            "memory_apply_records",
            "audit_events",
            "policy_decisions",
        ],
        "does_not_own": [
            "raw_documents",
            "chunks",
            "embeddings",
            "graph_facts",
            "agent_sessions",
        ],
        "counts": {
            "workflows": len(workflows),
            "proposals": len(proposals),
            "reviews": len(reviews),
            "memory_applies": sum(1 for review in reviews if review.get("memory_apply")),
            "audit_events": len(audit_events),
        },
        "workflow_ids": [workflow.run_id for workflow in workflows],
        "proposal_ids": [proposal.proposal_id for proposal in proposals],
        "review_ids": [str(review.get("review_id") or "") for review in reviews if review.get("review_id")],
        "audit_actions": sorted({event.action for event in audit_events}),
        "migration_unit": "scoped SQLite review/audit store plus provider-owned coordinates",
    }


def _retrieval_provider_components(adapter_groups: dict[str, list[SourceRef]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for adapter, refs in adapter_groups.items():
        if adapter in _AGENT_SOURCE_ADAPTERS:
            continue
        result[adapter] = {
            "role": "source_evidence_provider",
            "owns": ["datasets", "documents", "chunks", "embeddings", "indexes"],
            "source_ref_count": len(refs),
            "dataset_ids": sorted({ref.dataset_id for ref in refs if ref.dataset_id}),
            "document_ids": sorted({ref.document_id for ref in refs if ref.document_id}),
            "source_ids": sorted({_source_display_id(ref) for ref in refs if _source_display_id(ref)}),
            "migration_unit": "provider-native dataset/document export plus preserved PSKA source refs",
        }
    return result


def _memory_provider_components(memory_targets: list[dict[str, Any]], source_refs: list[SourceRef]) -> dict[str, Any]:
    backends = sorted({str(target.get("backend") or "") for target in memory_targets if target.get("backend")})
    result: dict[str, Any] = {}
    for backend in backends:
        targets = [target for target in memory_targets if target.get("backend") == backend]
        result[backend] = {
            "role": "temporal_memory_provider",
            "owns": ["episodes", "facts", "entities", "relations", "invalidations"],
            "memory_target_count": len(targets),
            "target_ids": [target["target_id"] for target in targets if target.get("target_id")],
            "upstream_source_ref_count": len([ref for ref in source_refs if ref.adapter not in _AGENT_SOURCE_ADAPTERS]),
            "migration_unit": "provider-native memory/graph export with embedded PSKA provenance",
        }
    return result


def _agent_host_components(adapter_groups: dict[str, list[SourceRef]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for adapter in sorted(_AGENT_SOURCE_ADAPTERS & set(adapter_groups)):
        refs = adapter_groups[adapter]
        result[adapter] = {
            "role": "agent_host",
            "owns": ["sessions", "messages", "artifacts", "agent_runtime_config"],
            "source_ref_count": len(refs),
            "session_ids": sorted({ref.external_id for ref in refs if ref.external_id}),
            "message_ids": sorted({ref.source_id for ref in refs if ref.source_id}),
            "migration_unit": "agent-host session/artifact export plus PSKA MCP/API configuration",
        }
    return result


def _memory_targets(reviews: list[dict[str, Any]], audit_events: list[Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for review in reviews:
        apply = review.get("memory_apply") or {}
        key = _memory_target_key(apply)
        if key and key not in seen:
            seen.add(key)
            targets.append(
                {
                    "target_id": str(apply.get("target_id") or ""),
                    "backend": str(apply.get("backend") or ""),
                    "review_id": str(review.get("review_id") or ""),
                    "source": "review.memory_apply",
                    "metadata": _safe_metadata(apply.get("metadata") or {}),
                }
            )
    for event in audit_events:
        if event.action not in {"memory.apply", "memory.update", "memory.delete"}:
            continue
        metadata = event.metadata or {}
        payload = {
            "target_id": str(metadata.get("memory_target_id") or ""),
            "backend": str(metadata.get("backend") or ""),
        }
        key = _memory_target_key(payload)
        if key and key not in seen:
            seen.add(key)
            targets.append(
                {
                    "target_id": payload["target_id"],
                    "backend": payload["backend"],
                    "review_id": str(event.target_id or ""),
                    "source": f"audit.{event.action}",
                    "metadata": {
                        key: value
                        for key, value in metadata.items()
                        if key in {"proposal_id", "run_id", "proposal_kind", "layer", "version"}
                    },
                }
            )
    return targets


def _source_refs_from_value(value: Any) -> list[SourceRef]:
    refs: list[SourceRef] = []
    if isinstance(value, SourceRef):
        return [value]
    if isinstance(value, dict):
        if _looks_like_source_ref(value):
            try:
                refs.append(SourceRef.from_dict(value))
            except TypeError:
                pass
        for item in value.values():
            refs.extend(_source_refs_from_value(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_source_refs_from_value(item))
    return refs


def _looks_like_source_ref(value: dict[str, Any]) -> bool:
    if not value.get("adapter"):
        return False
    return any(
        value.get(key)
        for key in ("dataset_id", "document_id", "chunk_id", "source_id", "external_id", "url", "path")
    )


def _unique_source_refs(refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    result: list[SourceRef] = []
    for ref in refs:
        key = "|".join(
            [
                ref.adapter,
                ref.dataset_id or "",
                ref.document_id or "",
                ref.chunk_id or "",
                ref.source_id or "",
                ref.external_id or "",
                str((ref.metadata or {}).get("content_hash") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _source_refs_by_adapter(refs: list[SourceRef]) -> dict[str, list[SourceRef]]:
    result: dict[str, list[SourceRef]] = {}
    for ref in refs:
        adapter = ref.adapter or "unknown"
        result.setdefault(adapter, []).append(ref)
    return result


def _safe_source_ref(ref: SourceRef) -> dict[str, Any]:
    payload = to_jsonable(ref)
    payload["metadata"] = _safe_metadata(ref.metadata or {})
    return payload


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "origin",
        "schema",
        "content_hash",
        "excerpt_hash",
        "created_at",
        "observed_at",
        "source_published_at",
        "ingested_at",
        "workspace_id",
        "tenant_id",
        "memory_namespace",
        "run_id",
        "proposal_id",
        "review_id",
        "version",
        "operation",
    }
    return {key: value for key, value in metadata.items() if key in allowed}


def _source_display_id(ref: SourceRef) -> str:
    parts: list[str] = []
    if ref.document_id:
        parts.append(f"doc:{ref.document_id}")
    if ref.chunk_id:
        parts.append(f"chunk:{ref.chunk_id}")
    if ref.source_id:
        parts.append(f"source:{ref.source_id}")
    if ref.external_id and ref.external_id not in {ref.document_id, ref.chunk_id, ref.source_id}:
        parts.append(f"external:{ref.external_id}")
    return " / ".join(parts)


def _memory_target_key(payload: dict[str, Any]) -> str:
    target_id = str(payload.get("target_id") or "")
    backend = str(payload.get("backend") or "")
    if not target_id:
        return ""
    return f"{backend}|{target_id}"


def _migration_plan() -> list[dict[str, Any]]:
    return [
        {
            "component": "pska",
            "action": "Export scoped workflows, proposals, reviews, memory apply records, audit events, and policy decisions.",
        },
        {
            "component": "retrieval_providers",
            "action": "Use provider-native dataset/document/chunk export and preserve PSKA SourceRef coordinates or content hashes.",
        },
        {
            "component": "memory_providers",
            "action": "Use provider-native graph/memory export and preserve embedded PSKA provenance envelopes.",
        },
        {
            "component": "agent_hosts",
            "action": "Export sessions, messages, artifacts, and MCP/API configuration from the agent host.",
        },
        {
            "component": "verification",
            "action": "After import, run PSKA component checks, readiness checks, retrieval probes, and memory probes.",
        },
    ]


_AGENT_SOURCE_ADAPTERS = {"conversation", "hermes"}
