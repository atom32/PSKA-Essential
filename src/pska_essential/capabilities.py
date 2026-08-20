from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from pska_essential.governance import MEMORY_PRIMARY_USER_PATH, REVIEW_QUEUE_ROLE


MEMORY_OPERATIONS = ("search", "list", "get", "apply", "update", "delete")
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
    "pska_agentic_context_brief": {
        "category": "assistant",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "generates_answer_text": False,
        "embedding_required": False,
        "composes": ["workspace_status", "source_recall", "memory_search", "trace_query"],
    },
    "pska_agentic_context_brief_list": {
        "category": "assistant",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "generates_answer_text": False,
        "embedding_required": False,
        "reads_workflow_ledger": True,
    },
    "pska_agentic_specialist_profiles": {
        "category": "assistant",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "generates_answer_text": False,
        "runs_tools": False,
        "starts_agents": False,
        "embedding_required": False,
    },
    "pska_hermes_answer_proofs": {
        "category": "assistant",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "generates_answer_text": False,
        "reads_audit_log": True,
        "stores_full_question": False,
        "stores_full_answer": False,
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
        "ranking": "sqlite_fts5_bm25_title_path_boost",
        "snippet_metadata": True,
    },
    "pska_search_index_evaluation": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "creates_index": False,
        "runs_external_service": False,
        "embedding_required": False,
        "evaluates_optional_adapters": True,
        "default_provider": "sqlite_fts5",
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
        "supports_modes": [
            "exact_hash",
            "size_name_version",
            "text_similarity",
            "media_metadata",
            "image_phash",
            "fclones_hash",
            "czkawka_hash",
        ],
    },
    "pska_duplicate_review_list": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_registry": False,
        "writes_source_files": False,
        "delete_move_merge_supported": False,
        "review_statuses": ["reported", "keep_reviewing", "reviewed", "ignored"],
    },
    "pska_duplicate_group_mark": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "delete_move_merge_supported": False,
        "review_statuses": ["reported", "keep_reviewing", "reviewed", "ignored"],
    },
    "pska_duplicate_cleanup_propose": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "delete_move_merge_supported": False,
        "apply_supported": False,
        "strategies": ["keep_largest", "keep_newest", "keep_first", "keep_selected"],
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
    "pska_source_extract_job_enqueue": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
        "writes_source_registry": True,
    },
    "pska_source_extract_job_list": {"category": "source_job", "access": "read", "durable": False},
    "pska_source_extract_job_run": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
        "writes_source_registry": True,
    },
    "pska_source_watch_once": {
        "category": "source_job",
        "access": "write",
        "durable": False,
        "watches_authorized_root_only": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "writes_job_metadata": True,
        "queues_jobs_only": True,
        "embedding_required": False,
        "optional_adapter": "watchdog",
    },
    "pska_saved_search_create": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
    },
    "pska_source_collection_create": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "embedding_required": False,
    },
    "pska_source_collection_list": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "embedding_required": False,
    },
    "pska_source_collection_resolve": {
        "category": "source",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "embedding_required": False,
        "returns_context_packets": True,
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
        "writes_source_files": "write_target_dependent",
        "writes_sidecar": "write_target_dependent",
        "requires_sidecar_permission_for": ["sidecar"],
        "supports_write_targets": ["sidecar", "obsidian_frontmatter"],
        "requires_native_permission_for": ["obsidian_frontmatter"],
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
        "writes_source_files": "write_target_dependent",
        "writes_sidecar": "write_target_dependent",
        "requires_sidecar_permission_for": ["sidecar"],
        "supports_write_targets": ["sidecar", "obsidian_markdown_comment"],
        "requires_native_permission_for": ["obsidian_markdown_comment"],
    },
    "pska_obsidian_moc_propose": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": True,
        "writes_source_files": False,
        "requires_apply": True,
        "requires_obsidian_vault": True,
        "supports_group_by": ["none", "folder", "tag", "topic", "project"],
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
    "pska_source_memory_candidates_from_audit": {
        "category": "source",
        "access": "write",
        "durable": False,
        "writes_source_registry": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": True,
        "dedupe_existing_reviews": True,
        "embedding_required": False,
    },
    "pska_eidolia_context_read": {
        "category": "thought_artifact",
        "access": "read",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_eidolia_memory_review_create": {
        "category": "thought_artifact",
        "access": "write",
        "durable": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": True,
        "requires_source_refs": True,
        "embedding_required": False,
    },
    "pska_eidolia_project_trace_import": {
        "category": "thought_artifact",
        "access": "write",
        "durable": False,
        "reads_project_files": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "embedding_required": False,
        "audit_backed": True,
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
    "pska_memory_card_list": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "provider_operation": "list",
    },
    "pska_memory_card_get": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "provider_operation": "get",
    },
    "pska_memory_health_scan": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "provider_operation": "list",
    },
    "pska_memory_briefing": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "writes_memory_directly": False,
    },
    "pska_memory_review_queue": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "writes_memory_directly": False,
        "groups_review_work": True,
    },
    "pska_review_decide_batch": {
        "category": "review",
        "access": "write",
        "durable": False,
        "audit_backed": True,
        "writes_memory_directly": False,
        "requires_apply_for_durable_memory": True,
        "provider_operation": "decide_batch",
    },
    "pska_memory_candidate_dedup": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "writes_memory_directly": False,
        "embedding_required": False,
        "groups_review_work": True,
    },
    "pska_memory_use_trace": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
    },
    "pska_memory_why_used": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
    },
    "pska_memory_timeline": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "audit_backed": True,
    },
    "pska_trace_query": {
        "category": "trace",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "embedding_required": False,
        "generates_answer_text": False,
    },
    "pska_trace_coverage": {
        "category": "trace",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "exports_external_trace": False,
        "embedding_required": False,
        "generates_answer_text": False,
    },
    "pska_observability_metrics": {
        "category": "trace",
        "access": "read",
        "durable": False,
        "audit_backed": True,
        "reads_audit_ledger": True,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "runs_jobs": False,
        "activates_due_jobs": False,
        "creates_review": False,
        "exports_external_trace": False,
        "embedding_required": False,
        "generates_answer_text": False,
    },
    "pska_memory_change_from_conversation": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_policy": "conversation_memory",
        "may_auto_apply": True,
    },
    "pska_conversation_memory_candidates_create": {
        "category": "memory",
        "access": "write",
        "durable": False,
        "review_required": True,
        "writes_memory_directly": False,
        "creates_review": True,
        "embedding_required": False,
    },
    "pska_memory_review_from_workflow": {
        "category": "memory",
        "access": "write",
        "durable": True,
        "review_required": True,
        "may_auto_apply": True,
    },
    "pska_workflow_memory_attribution": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "answer_level_trace": True,
    },
    "pska_workflow_memory_suggestions": {
        "category": "memory",
        "access": "read",
        "durable": False,
        "may_create_review": True,
        "writes_memory_directly": False,
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
        "durable": False,
        "review_required": True,
        "creates_review": True,
        "writes_memory_directly": False,
        "requires_apply_for_durable_memory": True,
    },
    "pska_memory_refresh_review": {
        "category": "memory",
        "access": "write",
        "durable": False,
        "review_required": True,
        "creates_review": True,
        "writes_memory_directly": False,
        "requires_apply_for_durable_memory": True,
        "provider_operation": "update",
    },
    "pska_memory_delete_review": {
        "category": "memory",
        "access": "write",
        "durable": False,
        "review_required": True,
        "creates_review": True,
        "writes_memory_directly": False,
        "requires_apply_for_durable_memory": True,
    },
    "pska_memory_lifecycle": {"category": "memory", "access": "read", "durable": False},
    "pska_review_create": {"category": "review", "access": "write", "durable": False},
    "pska_review_list": {"category": "review", "access": "read", "durable": False},
    "pska_review_get": {"category": "review", "access": "read", "durable": False},
    "pska_review_decide": {"category": "review", "access": "write", "durable": False},
    "pska_review_merge_candidates": {
        "category": "review",
        "access": "write",
        "durable": False,
        "audit_backed": True,
        "writes_memory_directly": False,
        "creates_review": True,
        "requires_apply_for_durable_memory": True,
    },
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
    "pska_job_health": {
        "category": "jobs",
        "access": "read",
        "durable": False,
        "reads_job_ledger": True,
        "runs_jobs": False,
        "activates_due_jobs": False,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_wakeup_plan": {
        "category": "jobs",
        "access": "read",
        "durable": False,
        "reads_job_ledger": True,
        "generates_scheduler_config": True,
        "installs_scheduler": False,
        "calls_tick_endpoint": False,
        "runs_jobs": False,
        "activates_due_jobs": False,
        "writes_launch_agent": False,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "embedding_required": False,
    },
    "pska_policy_get": {"category": "policy", "access": "read", "durable": False},
    "pska_capabilities_get": {"category": "policy", "access": "read", "durable": False},
    "pska_workspace_status": {"category": "status", "access": "read", "durable": False},
    "pska_alpha_readiness": {"category": "status", "access": "read", "durable": False},
    "pska_alpha_trial_guide": {"category": "status", "access": "read", "durable": False},
    "pska_alpha_recovery_plan": {"category": "status", "access": "read", "durable": False},
    "pska_alpha_first_run_session": {"category": "status", "access": "read", "durable": False},
    "pska_alpha_first_run_item_update": {
        "category": "status",
        "access": "write",
        "durable": False,
        "writes_checklist_state": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "executes_trial_step": False,
    },
    "pska_runtime_diagnostics": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_retrieval_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_memory_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_component_check": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_live_closed_loop_probe": {"category": "diagnostics", "access": "read", "durable": False},
    "pska_eval_run": {
        "category": "diagnostics",
        "access": "write",
        "durable": False,
        "supported_suites": ["smoke", "product_acceptance", "governed_context"],
    },
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
        "card_view": memory_card_view_contract(),
        "health_view": memory_health_view_contract(),
        "briefing_view": memory_briefing_view_contract(),
        "review_queue_view": memory_review_queue_view_contract(),
        "candidate_dedup_view": memory_candidate_dedup_view_contract(),
        "attribution_view": memory_attribution_view_contract(),
        "suggestion_view": memory_suggestion_view_contract(),
        "use_trace_view": memory_use_trace_view_contract(),
        "timeline_view": memory_timeline_view_contract(),
        "trace_view": trace_query_view_contract(),
        "interaction_model": memory_interaction_model_contract(),
    }


def product_capabilities(*, memory_adapter: Any) -> dict[str, Any]:
    """Return the public PSKA capability contract for callers."""

    return {
        "memory": memory_capabilities(memory_adapter),
        "source_layer": source_layer_contract(),
        "assistant_layer": assistant_layer_contract(),
        "adapter_slots": adapter_slots_contract(),
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
                "name": "conversation_memory_candidates",
                "trigger": "Hermes detects stable preferences, decisions, source routes, corrections, or working habits in conversation",
                "api": "/api/memory/conversation-candidates",
                "mcp": "pska_conversation_memory_candidates_create",
                "requires_ready_kb_scope": False,
                "writes_memory_provider_directly": False,
                "governance": "review_candidate_only",
                "visible_review_default": True,
                "target_when_clear": "pending_review",
                "target_when_unclear": "skip_or_ask_for_clarification",
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
        "status": "m36_observability_metrics",
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
                "pska_search_index_evaluation",
                "pska_source_read",
                "pska_source_neighbors",
                "pska_duplicate_report",
                "pska_duplicate_review_list",
                "pska_duplicate_group_mark",
                "pska_duplicate_cleanup_propose",
                "pska_source_audit_run",
                "pska_source_audit_job_enqueue",
                "pska_source_audit_schedule_create",
                "pska_wakeup_plan",
                "pska_observability_metrics",
                "pska_source_audit_job_list",
                "pska_source_audit_job_tick",
                "pska_source_audit_job_run",
                "pska_source_extract_job_enqueue",
                "pska_source_extract_job_list",
                "pska_source_extract_job_run",
                "pska_source_watch_once",
                "pska_saved_search_create",
                "pska_source_collection_create",
                "pska_source_collection_list",
                "pska_source_collection_resolve",
                "pska_source_tag_propose",
                "pska_source_tag_apply",
                "pska_source_comment_propose",
                "pska_source_comment_apply",
                "pska_obsidian_moc_propose",
                "pska_obsidian_moc_apply",
                "pska_source_memory_review_create",
                "pska_source_memory_candidates_from_audit",
            ],
            "planned": [],
        },
        "adapter_slots": {
            "extraction": [
                "builtin_text",
                "markitdown",
                "docling",
                "tika",
            ],
            "search_index": [
                "sqlite_fts5",
                "tantivy",
                "meilisearch",
                "recoll",
            ],
            "dedup": [
                "exact_hash",
                "size_name_version",
                "text_similarity",
                "media_metadata",
                "imagehash",
                "fclones",
                "czkawka",
                "dupeguru",
                "rmlint",
            ],
            "cloud_source": [
                "google_drive",
                "box",
                "sharepoint",
                "notion",
                "zotero",
            ],
        },
        "safety": {
            "scans_full_disk_by_default": False,
            "writes_source_files_by_default": False,
            "delete_move_merge_supported": False,
            "native_write_targets": ["obsidian_frontmatter_tags", "obsidian_markdown_comments", "obsidian_moc"],
        },
    }


def assistant_layer_contract() -> dict[str, Any]:
    return {
        "schema": "pska.assistant_layer.v1",
        "status": "m38_observability_metrics",
        "primary_agent": "Hermes",
        "role": "compose PSKA status, source audits, memory/review cues, and next actions for agent orchestration",
        "mcp_tools": {
            "implemented": [
                "pska_workspace_status",
                "pska_jarvis_briefing",
                "pska_agentic_context_brief",
                "pska_agentic_context_brief_list",
                "pska_agentic_specialist_profiles",
                "pska_hermes_answer_proofs",
                "pska_alpha_readiness",
                "pska_alpha_trial_guide",
                "pska_alpha_recovery_plan",
                "pska_alpha_first_run_session",
                "pska_alpha_first_run_item_update",
                "pska_source_audit_run",
                "pska_duplicate_review_list",
                "pska_duplicate_group_mark",
                "pska_duplicate_cleanup_propose",
                "pska_source_audit_job_enqueue",
                "pska_source_audit_schedule_create",
                "pska_wakeup_plan",
                "pska_source_audit_job_list",
                "pska_source_audit_job_tick",
                "pska_source_audit_job_run",
                "pska_source_extract_job_enqueue",
                "pska_source_extract_job_list",
                "pska_source_extract_job_run",
                "pska_source_watch_once",
                "pska_search_index_evaluation",
                "pska_obsidian_moc_propose",
                "pska_obsidian_moc_apply",
                "pska_memory_card_list",
                "pska_memory_card_get",
                "pska_memory_health_scan",
                "pska_memory_briefing",
                "pska_memory_review_queue",
                "pska_memory_candidate_dedup",
                "pska_review_merge_candidates",
                "pska_memory_use_trace",
                "pska_memory_why_used",
                "pska_memory_timeline",
                "pska_workflow_memory_attribution",
                "pska_workflow_memory_suggestions",
                "pska_memory_change_from_conversation",
                "pska_conversation_memory_candidates_create",
                "pska_memory_refresh_review",
                "pska_source_memory_review_create",
                "pska_source_memory_candidates_from_audit",
                "pska_eidolia_context_read",
                "pska_eidolia_memory_review_create",
                "pska_trace_query",
                "pska_trace_coverage",
                "pska_observability_metrics",
                "pska_job_health",
                "pska_eidolia_project_trace_import",
            ],
            "planned": [
                "approximate_duplicate_report",
            ],
        },
        "adapter_slots": {
            "thought_artifact": [
                "eidolia_project_files",
                "eidolia_product_api",
            ],
            "observability": [
                "sqlite_audit",
                "opentelemetry",
                "phoenix",
                "ragas",
                "deepeval",
            ],
            "workflow": [
                "sqlite_jobs",
                "watchdog_tick",
                "system_cron_launchd",
                "temporal",
            ],
        },
        "safety": {
            "owns_generation": False,
            "writes_source_files_by_default": False,
            "writes_memory_directly": False,
            "follows_pska_next_actions": True,
        },
    }


def adapter_slots_contract() -> dict[str, Any]:
    """Return planned adapter slots without loading optional heavy dependencies."""

    slots = {
        "extraction": {
            "contract": "ExtractionPort",
            "purpose": "Convert source files into PSKA sections and source-safe text.",
            "default_provider": "builtin_text",
            "providers": [
                _provider(
                    "builtin_text",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["markdown", "text", "code"],
                ),
                _python_provider(
                    "markitdown",
                    module="markitdown",
                    extra="extract-markitdown",
                    maturity="implemented",
                    supports=["office", "pdf", "html", "audio_transcript_candidates"],
                ),
                _python_provider(
                    "docling",
                    module="docling",
                    extra="extract-docling",
                    maturity="implemented",
                    supports=["pdf_layout", "tables", "ocr_candidates"],
                ),
                _python_provider(
                    "tika",
                    module="tika",
                    extra="extract-tika",
                    maturity="planned",
                    supports=["broad_enterprise_file_types"],
                ),
            ],
        },
        "search_index": {
            "contract": "SearchIndexPort",
            "purpose": "Index and search source sections behind PSKA scope and SourceRef contracts.",
            "default_provider": "sqlite_fts5",
            "providers": [
                _provider(
                    "sqlite_fts5",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["metadata", "bm25", "snippet", "title_path_boost", "like_fallback", "local_first"],
                ),
                _python_provider(
                    "tantivy",
                    module="tantivy",
                    extra="search-tantivy",
                    maturity="evaluated_candidate",
                    supports=["large_local_full_text_index", "local_first_candidate"],
                ),
                _service_provider(
                    "meilisearch",
                    env_keys=["MEILISEARCH_URL", "MEILI_MASTER_KEY"],
                    maturity="planned",
                    supports=["typo_tolerant_search", "server_mode"],
                ),
                _cli_provider(
                    "recoll",
                    command="recoll",
                    maturity="planned",
                    supports=["desktop_full_text_search"],
                ),
            ],
        },
        "dedup": {
            "contract": "DedupPort",
            "purpose": "Produce normalized duplicate reports without destructive file actions.",
            "default_provider": "exact_hash",
            "providers": [
                _provider(
                    "exact_hash",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["exact_content_hash"],
                    safety={"delete_move_merge_supported": False},
                ),
                _provider(
                    "size_name_version",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["normalized_filename", "version_suffix", "copy_suffix", "similar_size_candidates"],
                    safety={"delete_move_merge_supported": False},
                ),
                _provider(
                    "text_similarity",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["indexed_text_tokens", "jaccard_similarity", "no_embedding_candidates"],
                    safety={"delete_move_merge_supported": False},
                ),
                _provider(
                    "media_metadata",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["media_family", "normalized_filename", "similar_size_candidates", "no_embedding_candidates"],
                    safety={"delete_move_merge_supported": False},
                ),
                _python_provider(
                    "imagehash",
                    module="imagehash",
                    extra="image-phash",
                    maturity="implemented",
                    supports=["image_perceptual_hash", "phash", "hamming_distance", "no_embedding_candidates"],
                    safety={"delete_move_merge_supported": False},
                ),
                _cli_provider(
                    "fclones",
                    command="fclones",
                    env_key="PSKA_FCLONES_BIN",
                    maturity="implemented",
                    supports=["hash_duplicate_groups", "json_report"],
                    safety={"delete_move_merge_supported": False},
                ),
                _cli_provider(
                    "czkawka",
                    command="czkawka_cli",
                    env_key="PSKA_CZKAWKA_BIN",
                    maturity="implemented",
                    supports=["hash_duplicate_groups", "json_report", "media_similarity_candidates"],
                    safety={"delete_move_merge_supported": False},
                ),
                _cli_provider(
                    "dupeguru",
                    command="dupeguru",
                    maturity="planned",
                    supports=["fuzzy_filename_content_review"],
                    safety={"delete_move_merge_supported": False},
                ),
                _cli_provider(
                    "rmlint",
                    command="rmlint",
                    maturity="planned",
                    supports=["advanced_duplicate_lint_report"],
                    safety={"delete_move_merge_supported": False},
                ),
            ],
        },
        "thought_artifact": {
            "contract": "ThoughtArtifactPort",
            "purpose": "Expose Eidolia thought/artifact refs as source-safe PSKA context and trace inputs.",
            "default_provider": "",
            "providers": [
                _provider(
                    "eidolia_source_ref_bridge",
                    status="implemented",
                    maturity="partial",
                    integration="pska_payload_adapter",
                    supports=["thought_refs", "artifact_refs", "memory_review_creation"],
                    safety={"writes_canvas": False, "writes_memory_directly": False},
                ),
                _provider(
                    "eidolia_project_files",
                    status="implemented",
                    maturity="partial",
                    integration="file_adapter",
                    supports=["canvas_workspace_json", "agentic_trace_json", "source_ref_import", "audit_trace"],
                    safety={"writes_canvas": False, "writes_memory_directly": False},
                ),
                _service_provider(
                    "eidolia_product_api",
                    env_keys=["EIDOLIA_API_BASE_URL"],
                    maturity="planned",
                    supports=["live_canvas_context"],
                ),
            ],
        },
        "brain_provider": {
            "contract": "BrainProvider",
            "purpose": "Attach external long-term brain substrates behind PSKA review, provenance, audit, and trace boundaries.",
            "default_provider": "",
            "providers": [
                _provider(
                    "gbrain_http_mcp",
                    status="candidate",
                    maturity="candidate",
                    integration="optional_http_mcp_adapter",
                    supports=["recall", "entity", "context_pack", "delta", "remember_after_review"],
                    safety={
                        "direct_hermes_mcp_allowed": False,
                        "stdio_product_flow_allowed": False,
                        "durable_memory": "review_gate_required",
                        "provenance_required": True,
                        "writes_memory_directly": False,
                    },
                    reason="GBrain source is tracked as a PSKA-Components candidate, but no governed PSKA adapter is wired yet.",
                    install_hint="Expose GBrain over HTTP MCP, then wire it through a PSKA BrainProvider adapter instead of direct Hermes MCP.",
                ),
            ],
        },
        "observability": {
            "contract": "ObservabilityPort",
            "purpose": "Export PSKA audit/trace/eval signals without replacing PSKA audit.",
            "default_provider": "sqlite_audit",
            "providers": [
                _provider(
                    "sqlite_audit",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["governance_audit"],
                ),
                _python_provider(
                    "opentelemetry",
                    module="opentelemetry",
                    extra="observability",
                    maturity="planned",
                    supports=["trace_export", "metrics"],
                ),
                _python_provider(
                    "phoenix",
                    module="phoenix",
                    extra="observability",
                    maturity="planned",
                    supports=["llm_rag_tracing"],
                ),
                _python_provider(
                    "ragas",
                    module="ragas",
                    extra="eval",
                    maturity="planned",
                    supports=["rag_evaluation"],
                ),
                _python_provider(
                    "deepeval",
                    module="deepeval",
                    extra="eval",
                    maturity="planned",
                    supports=["llm_workflow_evaluation"],
                ),
            ],
        },
        "workflow": {
            "contract": "WorkflowPort",
            "purpose": "Run source audit, extraction, digest, and future long jobs safely.",
            "default_provider": "sqlite_jobs",
            "providers": [
                _provider(
                    "sqlite_jobs",
                    status="available",
                    maturity="implemented",
                    integration="core",
                    supports=["job_ledger", "explicit_tick", "recurring_source_audit"],
                ),
                _python_provider(
                    "watchdog_tick",
                    module="watchdog",
                    extra="watch",
                    maturity="implemented",
                    supports=["authorized_root_file_events", "bounded_watch_once", "job_enqueue_only"],
                ),
                _provider(
                    "system_cron_launchd",
                    status="available",
                    maturity="implemented",
                    integration="external_scheduler",
                    supports=["periodic_tick_plan", "launchd_plist_generation", "cron_line_generation", "manual_install"],
                ),
                _python_provider(
                    "temporal",
                    module="temporalio",
                    extra="workflow-temporal",
                    maturity="future",
                    supports=["durable_execution", "long_running_jobs"],
                ),
            ],
        },
        "cloud_source": {
            "contract": "CloudSourcePort",
            "purpose": "Normalize cloud connectors into PSKA source roots and SourceRefs.",
            "default_provider": "",
            "providers": [
                _connector_provider("google_drive"),
                _connector_provider("box"),
                _connector_provider("sharepoint"),
                _connector_provider("notion"),
                _connector_provider("zotero"),
            ],
        },
    }
    return {
        "schema": "pska.adapter_slots.v1",
        "principle": "optional_components_do_not_define_pska_semantics_or_bypass_policy",
        "core_owns": [
            "SourceRef",
            "Memory Card envelope",
            "Review",
            "Policy",
            "Audit",
            "Trace",
            "provider-neutral contracts",
        ],
        "default_dependency_policy": "stdlib_first_optional_adapters",
        "slots": slots,
        "summary": _adapter_slots_summary(slots),
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


def memory_card_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_card_view.v1",
        "apis": {
            "list": "GET /api/memory/cards",
            "get": "GET /api/memory/cards/{memory_id}",
            "refresh_review": "POST /api/memory/cards/{memory_id}/refresh-review",
        },
        "mcp_tools": {
            "list": "pska_memory_card_list",
            "get": "pska_memory_card_get",
            "refresh_review": "pska_memory_refresh_review",
        },
        "card_schema": "pska.memory_card.v1",
        "statuses": ["active", "superseded", "deleted", "all"],
        "provider_operations": {
            "list": "required for unqueried card inventory",
            "get": "required for direct card lookup",
            "search": "used for queried card inventory",
        },
        "agent_facing_fields": [
            "display_text",
            "memory_type",
            "memory_scope",
            "behavior_delta",
            "agent_view.why_use",
            "source_refs",
            "quality",
            "lifecycle",
        ],
        "review_actions": [
            "create_memory_refresh_review",
            "create_memory_update_review",
            "create_memory_delete_review",
        ],
        "writes_memory_directly": False,
    }


def memory_use_trace_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_use_trace_view.v1",
        "apis": {
            "list": "GET /api/memory/use-traces",
            "for_memory": "GET /api/memory/{memory_id}/use-trace",
            "why_used": "GET /api/memory/{memory_id}/why-used",
        },
        "mcp_tools": {
            "list": "pska_memory_use_trace",
            "why_used": "pska_memory_why_used",
        },
        "audit_actions": [
            "memory.search",
            "memory.card.get",
            "memory.card.list",
        ],
        "evidence_fields": [
            "returned_fact_ids",
            "raw_fact_ids",
            "superseded_fact_ids",
            "query",
            "scope",
            "caller",
            "run_id",
            "message_id",
            "purpose",
        ],
        "limitation": "candidate retrieval or card inspection only; answer-side tool use is attached through hermes.answer_proof audit records",
    }


def memory_timeline_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_timeline_view.v1",
        "api": "GET /api/memory/{memory_id}/timeline",
        "mcp_tool": "pska_memory_timeline",
        "output_schema": "pska.memory_timeline.v1",
        "entry_types": ["card_snapshot", "lifecycle_change", "usage_trace", "source_anchor"],
        "evidence_sources": ["Memory Card envelope", "PSKA audit lifecycle", "memory use trace", "SourceRef"],
        "principle": "timeline is a derived ledger view and does not create a second memory store",
        "limitation": "provider-neutral timeline; hidden model causality and provider-native graph state are out of scope",
    }


def trace_query_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.trace_query_view.v1",
        "api": "GET /api/trace/query",
        "mcp_tool": "pska_trace_query",
        "output_schema": "pska.trace_query.v1",
        "selectors": ["target_type", "target_id", "review_id", "proposal_id", "memory_id", "source_ref", "action"],
        "entry_types": ["audit_event", "review_record"],
        "evidence_sources": [
            "PSKA audit events",
            "review records",
            "Memory Card source refs",
            "Eidolia SourceRefs",
            "Hermes answer proofs",
        ],
        "answer_proof": {
            "record_api": "POST /api/hermes/answer-proofs",
            "list_api": "GET /api/hermes/answer-proofs",
            "audit_action": "hermes.answer_proof",
            "stores_full_question": False,
            "stores_full_answer": False,
            "text_storage": "preview_and_sha256",
            "recording_owner": "deterministic_webui_harness_or_extension_bridge",
            "mcp_query_path": "pska_trace_query(action='hermes.answer_proof')",
        },
        "principle": "trace query is a derived view over existing ledgers and does not create a second trace store",
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "embedding_required": False,
            "generates_answer_text": False,
        },
        "limitation": "does not reconstruct hidden model causality or provider-native conversation history",
    }


def memory_health_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_health_view.v1",
        "api": "GET /api/memory/health",
        "mcp_tool": "pska_memory_health_scan",
        "issue_types": ["quality", "stale", "conflict"],
        "inputs": ["scope", "issue_type", "limit"],
        "issue_schema": "pska.memory_health_issue.v1",
        "next_actions": [
            "inspect_memory_health",
            "inspect_memory_card_quality",
            "inspect_memory_staleness",
            "inspect_memory_conflict",
            "create_memory_refresh_review",
            "create_memory_update_review",
        ],
        "limitation": "provider-neutral health scan; conflict detection is conservative and does not auto-resolve memory",
    }


def memory_briefing_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_briefing_view.v1",
        "api": "GET /api/memory/briefing",
        "mcp_tool": "pska_memory_briefing",
        "output_schema": "pska.memory_briefing.v1",
        "inputs": ["scope", "card_limit", "health_limit", "trace_limit"],
        "evidence_sources": ["Memory Card envelope", "memory health scan", "memory use trace"],
        "focus_item_schema": "pska.memory_briefing_item.v1",
        "principle": "derived memory attention view for Hermes/Jarvis; no second memory store",
        "writes_memory_directly": False,
        "next_actions": [
            "inspect_memory_health",
            "inspect_memory_timeline",
            "inspect_memory_why_used",
            "create_memory_update_review",
        ],
    }


def memory_review_queue_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_review_queue_view.v1",
        "api": "GET /api/memory/review-queue",
        "mcp_tool": "pska_memory_review_queue",
        "output_schema": "pska.memory_review_queue.v1",
        "group_schema": "pska.memory_review_queue_group.v1",
        "groups": [
            "accepted_unapplied",
            "refresh_reviews",
            "conversation_candidates",
            "candidate_quality",
            "duplicate_candidates",
            "related_candidates",
            "pending_reviews",
            "needs_edit",
            "merged_replacements",
            "revised_replacements",
            "memory_health",
            "memory_focus",
        ],
        "principle": "read-only grouping view over Review records and Memory Briefing",
        "refresh_review_item_fields": [
            "review_id",
            "status",
            "source_memory_id",
            "target_id",
            "previous_text",
            "proposed_text",
            "no_text_change",
            "source_count",
        ],
        "candidate_quality_item_fields": [
            "review_id",
            "status",
            "issue_types",
            "missing_fields",
            "text",
            "memory_type",
            "memory_scope",
            "behavior_delta",
            "source_count",
        ],
        "candidate_quality_summary_fields": [
            "issue_types",
            "missing_fields",
            "statuses",
            "severities",
            "top_issue_type",
            "top_missing_field",
        ],
        "needs_edit_memory_candidate_fields": [
            "operation",
            "text",
            "previous_text",
            "behavior_delta",
            "memory_type",
            "memory_scope",
            "origin",
            "confidence",
            "target_id",
            "message_ids",
            "evidence_quotes",
            "source_refs",
        ],
        "writes_memory_directly": False,
        "next_actions": [
            "open_review",
            "review_memory_refresh",
            "review_conversation_memory_candidate",
            "review_memory_candidate_quality",
            "mark_memory_candidate_needs_edit",
            "mark_quality_group_needs_edit",
            "accept_review_group",
            "reject_review_group",
            "apply_accepted_memory",
            "inspect_duplicate_memory_candidates",
            "inspect_related_memory_candidates",
            "open_revised_review",
            "inspect_memory_health",
            "inspect_memory_timeline",
        ],
    }


def memory_candidate_dedup_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_candidate_dedup_view.v1",
        "api": "GET /api/memory/candidate-dedup",
        "mcp_tool": "pska_memory_candidate_dedup",
        "output_schema": "pska.memory_candidate_dedup.v1",
        "group_schema": "pska.memory_candidate_dedup_group.v1",
        "related_group_schema": "pska.memory_candidate_related_group.v1",
        "inputs": ["scope", "review_limit", "similarity_threshold", "related_threshold"],
        "signals": [
            "normalized_text",
            "token_jaccard",
            "SourceRef fingerprint",
            "behavior_delta fingerprint",
            "cross-scope scope collision",
        ],
        "principle": "embedding-free duplicate and related-candidate hints before human review decisions",
        "writes_memory_directly": False,
        "embedding_required": False,
        "next_actions": [
            "open_review",
            "review_pending_durable_knowledge",
            "inspect_related_memory_candidates",
            "merge_candidate_group",
        ],
    }


def memory_attribution_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_attribution_view.v1",
        "api": "GET /api/workflows/{run_id}/memory-attribution",
        "mcp_tool": "pska_workflow_memory_attribution",
        "output_schema": "pska.memory_attribution.v1",
        "fields": ["run_id", "used_memory_ids", "used_memories", "proposal_id", "confidence", "limitations"],
        "principle": "answer-level memory context attribution is explicit and separate from provider retrieval traces",
        "limitation": "records context supplied to the answer/work product, not hidden model causality",
    }


def memory_suggestion_view_contract() -> dict[str, Any]:
    return {
        "schema": "pska.memory_suggestion_view.v1",
        "api": "GET /api/workflows/{run_id}/memory-suggestions",
        "mcp_tool": "pska_workflow_memory_suggestions",
        "output_schema": "pska.memory_suggestions.v1",
        "suggestion_schema": "pska.memory_suggestion.v1",
        "next_actions": ["create_memory_review_from_workflow"],
        "writes_memory_directly": False,
        "review_tool": "pska_memory_review_from_workflow",
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


def _provider(
    name: str,
    *,
    status: str,
    maturity: str,
    integration: str,
    supports: list[str],
    safety: dict[str, Any] | None = None,
    reason: str = "",
    install_hint: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": status,
        "available": status == "available",
        "maturity": maturity,
        "integration": integration,
        "supports": list(supports),
    }
    if reason:
        payload["reason"] = reason
    if install_hint:
        payload["install_hint"] = install_hint
    if safety:
        payload["safety"] = dict(safety)
    return payload


def _python_provider(
    name: str,
    *,
    module: str,
    extra: str,
    maturity: str,
    supports: list[str],
    safety: dict[str, Any] | None = None,
) -> dict[str, Any]:
    available = importlib.util.find_spec(module) is not None
    payload = _provider(
        name,
        status="available" if available else "unavailable",
        maturity=maturity,
        integration="python_optional_extra",
        supports=supports,
        safety=safety,
        reason="" if available else f"Python module `{module}` is not installed.",
        install_hint=f"Install PSKA optional extra `{extra}`.",
    )
    payload["optional_extra"] = extra
    payload["python_module"] = module
    return payload


def _cli_provider(
    name: str,
    *,
    command: str,
    env_key: str = "",
    maturity: str,
    supports: list[str],
    safety: dict[str, Any] | None = None,
) -> dict[str, Any]:
    override = _env_command_path(env_key) if env_key else ""
    path = override or shutil.which(command)
    payload = _provider(
        name,
        status="available" if path else "unavailable",
        maturity=maturity,
        integration="external_cli",
        supports=supports,
        safety=safety,
        reason="" if path else _cli_missing_reason(command, env_key),
        install_hint=_cli_install_hint(command, env_key),
    )
    payload["command"] = command
    if env_key:
        payload["env_key"] = env_key
    if path:
        payload["path"] = path
        if override:
            payload["path_source"] = "env"
    return payload


def _env_command_path(env_key: str) -> str:
    if not env_key:
        return ""
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    return str(path) if path.is_file() and os.access(path, os.X_OK) else ""


def _cli_missing_reason(command: str, env_key: str) -> str:
    if not env_key:
        return f"CLI command `{command}` was not found on PATH."
    return f"CLI command `{command}` was not found on PATH and `{env_key}` does not point to an executable file."


def _cli_install_hint(command: str, env_key: str) -> str:
    if not env_key:
        return f"Install `{command}` and keep it on PATH."
    return f"Install `{command}` and keep it on PATH, or set `{env_key}`."


def _service_provider(
    name: str,
    *,
    env_keys: list[str],
    maturity: str,
    supports: list[str],
    safety: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _provider(
        name,
        status="planned",
        maturity=maturity,
        integration="external_service",
        supports=supports,
        safety=safety,
        reason="Service adapters are planned; availability is not inferred without a concrete adapter.",
        install_hint="Configure the future service adapter and required environment variables.",
    ) | {"env_keys": list(env_keys)}


def _connector_provider(name: str) -> dict[str, Any]:
    return _provider(
        name,
        status="planned",
        maturity="future",
        integration="mcp_or_plugin_connector",
        supports=["cloud_source_root", "source_ref_mapping"],
        reason="Cloud connector slot is planned; no PSKA adapter is installed yet.",
        install_hint="Use an approved connector/plugin later and normalize it through CloudSourcePort.",
    )


def _adapter_slots_summary(slots: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for slot_name, slot in slots.items():
        providers = list(slot.get("providers") or [])
        summary[slot_name] = {
            "contract": slot.get("contract"),
            "default_provider": slot.get("default_provider") or "",
            "available": [provider["name"] for provider in providers if provider.get("available")],
            "candidate": [
                provider["name"]
                for provider in providers
                if provider.get("status") == "candidate"
            ],
            "planned": [
                provider["name"]
                for provider in providers
                if provider.get("status") in {"planned", "unavailable"}
            ],
        }
    return summary
