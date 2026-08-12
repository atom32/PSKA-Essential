from __future__ import annotations

from typing import Any

from pska_essential.governance import MEMORY_PRIMARY_USER_PATH, REVIEW_QUEUE_ROLE


MEMORY_OPERATIONS = ("search", "apply", "update", "delete")
MEMORY_PROPOSAL_OPERATIONS = {
    "memory_patch": "apply",
    "memory_update": "update",
    "memory_delete": "delete",
}
APPEND_CORRECTION_EPISODE = "append_correction_episode"
MEMORY_DISPLAY_TEXT_KEYS = ("display_text", "current_text", "canonical_text")
MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS = ("include_superseded_memory", "include_superseded")
MEMORY_SUPERSESSION_TARGET_KEYS = (
    "target_fact_id",
    "target_fact_ids",
    "supersedes_fact_id",
    "supersedes_fact_ids",
)


TOOL_POLICY: dict[str, dict[str, Any]] = {
    "pska_workflow_start": {"category": "workflow", "access": "write", "durable": False},
    "pska_workflow_list": {"category": "workflow", "access": "read", "durable": False},
    "pska_workflow_state": {"category": "workflow", "access": "read", "durable": False},
    "pska_workflow_artifact": {"category": "workflow", "access": "read", "durable": False},
    "pska_workflow_brief": {"category": "workflow", "access": "read", "durable": False},
    "pska_jarvis_briefing": {
        "category": "assistant",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_context_retrieve": {"category": "retrieval", "access": "read", "durable": False},
    "pska_source_read": {"category": "retrieval", "access": "read", "durable": False},
    "pska_source_root_list": {"category": "source", "access": "read", "durable": False},
    "pska_source_root_register": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
    },
    "pska_source_scan": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "embedding_required": False,
    },
    "pska_source_search": {
        "category": "source",
        "access": "read",
        "durable": False,
        "embedding_required": False,
    },
    "pska_source_neighbors": {
        "category": "source",
        "access": "read",
        "durable": False,
        "embedding_required": False,
        "writes_source_files": False,
    },
    "pska_duplicate_report": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "delete_move_merge_supported": False,
    },
    "pska_source_audit_run": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_source_audit_job_enqueue": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_source_audit_schedule_create": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
        "wall_clock_schedule": True,
    },
    "pska_source_audit_job_list": {"category": "source_job", "access": "read", "durable": False},
    "pska_source_audit_job_tick": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
        "wall_clock_tick": True,
    },
    "pska_source_audit_job_run": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_saved_search_create": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
    },
    "pska_source_tag_propose": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "requires_apply": True,
    },
    "pska_source_tag_apply": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "writes_sidecar": True,
        "requires_sidecar_permission": True,
    },
    "pska_source_comment_propose": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "requires_apply": True,
    },
    "pska_source_comment_apply": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "writes_sidecar": True,
        "requires_sidecar_permission": True,
    },
    "pska_obsidian_moc_propose": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "requires_apply": True,
        "requires_obsidian_vault": True,
    },
    "pska_obsidian_moc_apply": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": True,
        "requires_native_permission": True,
        "requires_obsidian_vault": True,
    },
    "pska_source_memory_review_create": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": True,
        "requires_source_refs": True,
    },
    "pska_agentic_question_start": {
        "category": "ask",
        "access": "write",
        "durable": False,
        "requires_ready_scope": True,
        "may_create_review": True,
    },
    "pska_agentic_question_resumable": {"category": "ask", "access": "read", "durable": False},
    "pska_agentic_question_resume": {
        "category": "ask",
        "access": "write",
        "durable": False,
        "requires_ready_scope": True,
        "may_create_review": True,
    },
    "pska_digest_scope": {
        "category": "digest",
        "access": "write",
        "durable": False,
        "requires_ready_scope": True,
        "may_create_review": True,
    },
    "pska_digest_job_enqueue": {"category": "digest_job", "access": "write", "durable": False},
    "pska_digest_job_list": {"category": "digest_job", "access": "read", "durable": False},
    "pska_digest_job_run": {
        "category": "digest_job",
        "access": "write",
        "durable": False,
        "requires_ready_scope": True,
        "may_create_review": True,
    },
    "pska_memory_search": {"category": "memory", "access": "read", "durable": False},
    "pska_memory_change_from_conversation": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_policy": "conversation_memory",
        "may_auto_apply": True,
    },
    "pska_memory_review_from_workflow": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_required": True,
        "may_auto_apply": True,
    },
    "pska_memory_apply": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "requires_accepted_review": True,
        "writes_provider": True,
    },
    "pska_memory_update_review": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_required": True,
    },
    "pska_memory_delete_review": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_required": True,
    },
    "pska_memory_lifecycle": {"category": "memory", "access": "read", "durable": False},
    "pska_review_create": {"category": "review", "access": "write", "durable": False},
    "pska_review_list": {"category": "review", "access": "read", "durable": False},
    "pska_review_get": {"category": "review", "access": "read", "durable": False},
    "pska_review_decide": {"category": "review", "access": "write", "durable": False},
    "pska_review_revise": {"category": "review", "access": "write", "durable": False},
    "pska_kb_list": {"category": "kb", "access": "read", "durable": False},
    "pska_kb_document_status": {"category": "kb", "access": "read", "durable": False},
    "pska_kb_readiness": {"category": "kb", "access": "read", "durable": False},
    "pska_kb_ingestion_status": {"category": "kb", "access": "read", "durable": False},
    "pska_kb_graph_read": {"category": "kb", "access": "read", "durable": False},
    "pska_kb_create": {"category": "kb", "access": "write", "durable": False, "writes_provider": True},
    "pska_kb_delete": {"category": "kb", "access": "write", "durable": False, "writes_provider": True},
    "pska_kb_ingest_files": {
        "category": "kb",
        "access": "write",
        "durable": False,
        "writes_provider": True,
        "async_provider_job": True,
    },
    "pska_kb_parse_documents": {
        "category": "kb",
        "access": "write",
        "durable": False,
        "writes_provider": True,
        "async_provider_job": True,
    },
    "pska_ingest_loop": {
        "category": "kb",
        "access": "write",
        "durable": False,
        "writes_provider": True,
        "async_provider_job": True,
        "may_create_review": True,
    },
    "pska_ingest_loop_resume": {
        "category": "kb",
        "access": "write",
        "durable": False,
        "requires_ready_scope": True,
        "may_create_review": True,
    },
    "pska_export_brief": {"category": "export", "access": "read", "durable": False},
    "pska_audit_list": {"category": "audit", "access": "read", "durable": False},
    "pska_migration_manifest": {"category": "migration", "access": "read", "durable": False},
    "pska_provider_jobs": {"category": "jobs", "access": "read", "durable": False},
    "pska_policy_get": {"category": "policy", "access": "read", "durable": False},
    "pska_capabilities_get": {"category": "policy", "access": "read", "durable": False},
    "pska_workspace_status": {"category": "status", "access": "read", "durable": False},
    "pska_runtime_diagnostics": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_retrieval_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_memory_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_component_check": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_live_closed_loop_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_eval_run": {"category": "diagnostics", "access": "write", "durable": False},
    "pska_propose": {"category": "workflow", "access": "write", "durable": False, "may_create_review": False},
}


def memory_capabilities(adapter: Any) -> dict[str, Any]:
    """Return PSKA-level memory operation capabilities for an adapter."""

    raw = getattr(adapter, "memory_capabilities", {}) or {}
    operations = {
        operation: _operation_capability(adapter, raw, operation)
        for operation in MEMORY_OPERATIONS
    }
    return {
        "backend": str(getattr(adapter, "backend_name", "custom")),
        "operations": operations,
        "conversation_update_strategies": _conversation_update_strategies(raw),
        "inflow": memory_inflow_contract(),
        "lineage": memory_lineage_contract(),
        "search_view": memory_search_view_contract(),
        "interaction_model": memory_interaction_model_contract(),
    }


def product_capabilities(*, memory_adapter: Any) -> dict[str, Any]:
    """Return the public PSKA capability contract for callers."""

    return {
        "memory": memory_capabilities(memory_adapter),
        "source_layer": source_layer_contract(),
        "assistant_layer": assistant_layer_contract(),
        "tool_policy": tool_policy(),
    }


def tool_policy() -> dict[str, Any]:
    return {
        "mode": "soft_constraints",
        "note": (
            "Tool policy is a product-level soft constraint for agents and UI. "
            "It is not authentication or authorization."
        ),
        "tools": {name: dict(policy) for name, policy in sorted(TOOL_POLICY.items())},
    }


def memory_operation_capability(adapter: Any, operation: str) -> dict[str, Any]:
    return memory_capabilities(adapter)["operations"].get(operation, {"supported": False})


def memory_operation_supported(adapter: Any, operation: str) -> bool:
    return bool(memory_operation_capability(adapter, operation).get("supported", False))


def memory_conversation_update_strategy_supported(adapter: Any, strategy: str) -> bool:
    return strategy in memory_capabilities(adapter).get("conversation_update_strategies", [])


def memory_inflow_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_inflow.v1",
        "principle": "source_documents_enter_kb_once_memory_provider_receives_governed_projections_only",
        "upload_behavior": {
            "api": "/api/kb/ingest",
            "mcp": "pska_kb_ingest_files",
            "target": "kb_provider",
            "stores_source_documents": True,
            "writes_memory_provider": False,
            "creates_graph_projection": False,
            "next_explicit_paths": [
                "conversation_memory",
                "digest_job",
                "workflow_memory_review",
            ],
        },
        "paths": [
            {
                "name": "conversation_memory",
                "trigger": "user says remember, correct, clarify, or forget in chat",
                "api": "/api/memory/conversation-change",
                "mcp": "pska_memory_change_from_conversation",
                "requires_ready_kb_scope": False,
                "writes_memory_provider_directly": False,
                "governance": "conversation_memory_policy",
                "visible_review_default": False,
                "target_when_clear": "memory_provider",
                "target_when_unclear": "memory_search_or_clarifying_question",
            },
            {
                "name": "digest_job",
                "trigger": "operator queues digest over a selected ready KB scope",
                "api": "/api/digest-jobs",
                "run_api": "/api/digest-jobs/{run_id}/run",
                "mcp": "pska_digest_job_enqueue",
                "run_mcp": "pska_digest_job_run",
                "requires_ready_kb_scope": True,
                "writes_memory_provider_directly": False,
                "governance": "digest_memory_policy",
                "visible_review_default": True,
                "target_when_clear": "exception_review_or_digest_artifact",
            },
            {
                "name": "workflow_memory_review",
                "trigger": "sourced Ask or digest artifact is promoted to durable memory",
                "api": "/api/workflows/{run_id}/memory-review",
                "mcp": "pska_memory_review_from_workflow",
                "requires_ready_kb_scope": False,
                "writes_memory_provider_directly": False,
                "governance": "durable_memory_policy",
                "visible_review_default": True,
                "target_when_clear": "accepted_review_then_memory_provider",
            },
        ],
        "non_paths": [
            {
                "name": "kb_upload",
                "reason": "uploading, chunking, embedding, and indexing source documents does not create durable memory",
            },
            {
                "name": "ask_retrieval",
                "reason": "retrieval and source inspection are read-only unless a separate memory path is invoked",
            },
        ],
    }


def source_layer_contract() -> dict[str, Any]:
    return {
        "schema": "pska.source_layer.v1",
        "status": "m10_obsidian_moc_writeback",
        "source_kinds": ["local_folder", "obsidian_vault"],
        "default_permission_mode": "read_only",
        "permission_modes": ["read_only", "sidecar_write", "native_write", "managed"],
        "canonical_content_owner": "user_owned_source_root",
        "index_owner": "pska_rebuildable_metadata_fts",
        "embedding_required": False,
        "mcp_tools": {
            "implemented": [
                "pska_source_root_list",
                "pska_source_root_register",
                "pska_source_scan",
                "pska_source_search",
                "pska_source_read",
                "pska_source_neighbors",
                "pska_duplicate_report",
                "pska_source_audit_run",
                "pska_source_audit_job_enqueue",
                "pska_source_audit_schedule_create",
                "pska_source_audit_job_list",
                "pska_source_audit_job_tick",
                "pska_source_audit_job_run",
                "pska_saved_search_create",
                "pska_source_tag_propose",
                "pska_source_tag_apply",
                "pska_source_comment_propose",
                "pska_source_comment_apply",
                "pska_obsidian_moc_propose",
                "pska_obsidian_moc_apply",
                "pska_source_memory_review_create",
            ],
            "planned": [],
        },
        "safety": {
            "scans_full_disk_by_default": False,
            "writes_source_files_by_default": False,
            "delete_move_merge_supported": False,
        },
    }


def assistant_layer_contract() -> dict[str, Any]:
    return {
        "schema": "pska.assistant_layer.v1",
        "status": "m10_jarvis_obsidian_moc_writeback",
        "primary_agent": "Hermes",
        "role": "compose PSKA status, source audits, memory/review cues, and next actions for agent orchestration",
        "mcp_tools": {
            "implemented": [
                "pska_workspace_status",
                "pska_jarvis_briefing",
                "pska_source_audit_run",
                "pska_source_audit_job_enqueue",
                "pska_source_audit_schedule_create",
                "pska_source_audit_job_list",
                "pska_source_audit_job_tick",
                "pska_source_audit_job_run",
                "pska_obsidian_moc_propose",
                "pska_obsidian_moc_apply",
                "pska_memory_change_from_conversation",
                "pska_source_memory_review_create",
            ],
            "planned": [
                "approximate_duplicate_report",
            ],
        },
        "safety": {
            "owns_generation": False,
            "writes_source_files_by_default": False,
            "writes_memory_directly": False,
            "follows_pska_next_actions": True,
        },
    }


def memory_lineage_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_lineage.v1",
        "authoritative_lineage_store": "memory_provider_object_metadata",
        "pska_authoritative_mapping_table": False,
        "provider_carriers": [
            "episode_metadata",
            "fact_or_edge_metadata",
            "source_description",
        ],
        "source_ref_field": "source_refs",
        "resolved_status": "resolved",
        "unresolved_status": "unresolved",
        "unresolved_behavior": (
            "Return empty source_refs and lineage_status=unresolved instead of "
            "inventing a provider mapping."
        ),
    }


def memory_search_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_search_view.v1",
        "default_filters_superseded": True,
        "include_superseded_scope_keys": list(MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS),
        "supersession": {
            "semantic_operation": "memory_update",
            "strategy": APPEND_CORRECTION_EPISODE,
            "target_keys": list(MEMORY_SUPERSESSION_TARGET_KEYS),
        },
        "agent_facing_text": {
            "metadata_keys": list(MEMORY_DISPLAY_TEXT_KEYS),
            "fallback_field": "text",
        },
        "audit": {
            "action": "memory.search",
            "fields": [
                "raw_count",
                "superseded_count",
                "superseded_fact_ids",
                "include_superseded",
            ],
        },
    }


def memory_interaction_model_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_interaction_model.v1",
        "primary_user_path": MEMORY_PRIMARY_USER_PATH,
        "conversation_change_tool": "pska_memory_change_from_conversation",
        "conversation_change_api": "/api/memory/conversation-change",
        "visible_memory_editor": "conversation",
        "agent_decides_operation": True,
        "target_resolution": {
            "status_values": ["provided", "resolved", "not_found", "ambiguous"],
            "missing_target_behavior": "search_or_ask_clarifying_question",
            "creates_review_item": False,
        },
        "conversation_explicit_user_changes": {
            "remember": "conversation_policy",
            "correct_clear_target": "conversation_policy",
            "forget_specific_fact": "conversation_policy",
            "missing_or_ambiguous_target": "needs_target_no_review",
            "force_review": "exception_review",
        },
        "review_queue_role": REVIEW_QUEUE_ROLE,
        "visible_review_role": "exception_only",
        "review_queue_triggers": [
            "uncertain",
            "risky",
            "conflicting",
            "ambiguous_destructive",
            "broad_destructive",
            "batch_derived",
            "force_review",
        ],
        "internal_governance_records": [
            "proposal",
            "decision",
            "memory_apply",
            "audit",
        ],
        "agent_guidance": (
            "For ordinary user-driven remember/correct/forget requests, handle "
            "the change in conversation, choose add/update/delete/clarify intent, "
            "and call PSKA conversation memory. If the target is unclear, search "
            "or ask a clarifying question. Create pending Review items only for "
            "exception cases; a clear user-requested forget/correction is not an "
            "exception by itself."
        ),
    }


def memory_operation_for_proposal_kind(proposal_kind: str) -> str:
    return MEMORY_PROPOSAL_OPERATIONS.get(str(proposal_kind or ""), "")


def _operation_capability(adapter: Any, raw: dict[str, Any], operation: str) -> dict[str, Any]:
    entry = raw.get(operation)
    if isinstance(entry, dict):
        supported = bool(entry.get("supported", False))
        reason = str(entry.get("reason") or "")
    elif isinstance(entry, bool):
        supported = entry
        reason = ""
    else:
        supported = callable(getattr(adapter, operation, None))
        reason = "" if supported else f"adapter does not expose {operation}"
    payload: dict[str, Any] = {"supported": supported}
    if reason:
        payload["reason"] = reason
    return payload


def _conversation_update_strategies(raw: dict[str, Any]) -> list[str]:
    values = raw.get("conversation_update_strategies") or raw.get("conversation_update_strategy") or []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    strategies: list[str] = []
    for value in values:
        strategy = str(value or "").strip()
        if strategy and strategy not in strategies:
            strategies.append(strategy)
    return strategies
