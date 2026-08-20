from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from pska_essential.agentic_loop import (
    list_resumable_agentic_questions,
    resume_agentic_question,
    run_digest_scope,
    run_agentic_question_with_readiness,
)
from pska_essential.agentic_context_brief import build_agentic_context_brief, list_agentic_context_briefs
from pska_essential.agentic_specialists import build_agentic_specialist_profiles
from pska_essential.alpha_readiness import (
    build_alpha_readiness,
    build_alpha_recovery_plan,
    build_alpha_trial_guide,
    build_alpha_first_run_session,
    update_alpha_first_run_session,
)
from pska_essential.capabilities import product_capabilities
from pska_essential.component_check import run_component_check
from pska_essential.config import build_service_from_env
from pska_essential.contracts import SourceRef, to_jsonable
from pska_essential.diagnostics import (
    add_live_closed_loop_probe_audit,
    add_memory_probe_audit,
    add_retrieval_probe_audit,
    build_runtime_diagnostics,
    run_live_closed_loop_probe,
    run_memory_probe,
    run_retrieval_probe,
)
from pska_essential.digest_jobs import enqueue_digest_job, list_digest_jobs, run_digest_job
from pska_essential.eidolia_import import import_eidolia_project_traces
from pska_essential.env_file import env_file_arg_parser, load_env_file
from pska_essential.eval import run_eval
from pska_essential.governance import build_workspace_policy_from_env
from pska_essential.hermes_answer_trace import list_hermes_answer_proofs
from pska_essential.ingest_loop import resume_ingest_loop, run_ingest_loop
from pska_essential.jarvis import build_jarvis_briefing
from pska_essential.kb_audit import (
    add_kb_dataset_create_audit,
    add_kb_dataset_delete_audit,
    add_kb_graph_read_audit,
    add_kb_ingest_audit,
    add_kb_parse_audit,
)
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.memory_cards import get_memory_card, list_memory_cards
from pska_essential.memory_briefing import build_memory_briefing
from pska_essential.memory_candidate_dedup import build_memory_candidate_dedup
from pska_essential.memory_health import scan_memory_health
from pska_essential.memory_review_queue import build_memory_review_queue
from pska_essential.memory_timeline import build_memory_timeline
from pska_essential.memory_use_trace import explain_memory_why_used, list_memory_use_traces
from pska_essential.migration_manifest import build_migration_manifest
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.source_audit_jobs import (
    activate_due_source_audit_jobs,
    enqueue_source_audit_job,
    list_source_audit_jobs,
    run_source_audit_job,
    schedule_source_audit_job,
)
from pska_essential.source_extraction_jobs import (
    enqueue_source_extraction_job,
    list_source_extraction_jobs,
    run_source_extraction_job,
)
from pska_essential.source_watch import watch_source_once
from pska_essential.trace_query import build_trace_query
from pska_essential.workspace_status import build_workspace_status, compact_workspace_status


def tool_registry(service=None) -> dict[str, Callable[..., Any]]:
    service = service or build_service_from_env()

    def pska_workflow_start(intent: str, scope: dict[str, Any] | None = None):
        return to_jsonable(service.start(intent, scope or {}))

    def pska_workflow_list(limit: int = 50):
        return to_jsonable(service.store.list_workflows(limit=limit))

    def pska_workflow_state(run_id: str):
        return to_jsonable(service.state(run_id))

    def pska_workflow_artifact(run_id: str):
        return service.workflow_artifact(run_id)

    def pska_workflow_brief(run_id: str, format: str = "markdown"):
        return service.render_brief(run_id, format)

    def pska_context_retrieve(
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 5,
        run_id: str | None = None,
    ):
        if not run_id:
            run_id = service.start(query, scope or {}).run_id
        if scope:
            run = service.state(run_id)
            run.scope.update(scope)
            service.store.save_workflow(run)
        return to_jsonable(service.context_retrieve(run_id, query, limit))

    def pska_source_read(source_ref: dict[str, Any]):
        return to_jsonable(service.source_read(SourceRef.from_dict(source_ref)))

    def pska_source_root_list():
        return service.source_root_list()

    def pska_source_root_register(
        path: str,
        kind: str = "local_folder",
        permission_mode: str = "read_only",
        label: str = "",
    ):
        return service.source_root_register(
            path,
            kind=kind,
            permission_mode=permission_mode,
            label=label or None,
        )

    def pska_source_scan(
        root_id: str,
        max_files: int = 1000,
        max_bytes: int = 1_000_000,
        extractor: str = "auto",
    ):
        return service.source_scan(root_id, max_files=max_files, max_bytes=max_bytes, extractor=extractor)

    def pska_source_search(
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ):
        return to_jsonable(service.source_search(query, scope or {}, limit=limit, filters=filters or {}))

    def pska_source_neighbors(
        source_ref: dict[str, Any],
        strategy: str = "auto",
        limit: int = 10,
    ):
        return to_jsonable(
            service.source_neighbors(
                SourceRef.from_dict(source_ref),
                strategy=strategy,
                limit=limit,
            )
        )

    def pska_duplicate_report(
        scope: dict[str, Any] | None = None,
        mode: str = "exact_hash",
        limit: int = 50,
    ):
        return to_jsonable(service.duplicate_report(scope or {}, mode=mode, limit=limit))

    def pska_duplicate_review_list(
        scope: dict[str, Any] | None = None,
        status: str = "",
        limit: int = 50,
    ):
        return to_jsonable(service.duplicate_review_list(scope or {}, status=status, limit=limit))

    def pska_duplicate_group_mark(
        group_id: str,
        status: str,
        note: str = "",
    ):
        return to_jsonable(service.duplicate_group_mark(group_id, status=status, note=note))

    def pska_duplicate_cleanup_propose(
        group_id: str,
        strategy: str = "keep_largest",
        keep_object_id: str = "",
        reason: str = "",
    ):
        return to_jsonable(
            service.duplicate_cleanup_propose(
                group_id,
                strategy=strategy,
                keep_object_id=keep_object_id,
                reason=reason,
            )
        )

    def pska_source_audit_run(scope: dict[str, Any] | None = None, limit: int = 20):
        return to_jsonable(service.source_audit_run(scope or {}, limit=limit))

    def pska_source_audit_job_enqueue(
        scope: dict[str, Any] | None = None,
        label: str = "",
        priority: int = 0,
        limit: int = 20,
        cadence: str = "manual",
        due_at: str = "",
    ):
        return enqueue_source_audit_job(
            service,
            scope=scope or {},
            label=label,
            priority=priority,
            limit=limit,
            cadence=cadence,
            due_at=due_at,
        )

    def pska_source_audit_schedule_create(
        scope: dict[str, Any] | None = None,
        label: str = "",
        priority: int = 0,
        limit: int = 20,
        cadence: str = "daily",
        due_at: str = "",
        now: str = "",
    ):
        return schedule_source_audit_job(
            service,
            scope=scope or {},
            label=label,
            priority=priority,
            limit=limit,
            cadence=cadence,
            due_at=due_at,
            now=now,
        )

    def pska_source_audit_job_list(status: str | None = None, limit: int = 50):
        return list_source_audit_jobs(service, status=status or None, limit=limit)

    def pska_source_audit_job_tick(now: str = "", limit: int = 20):
        return activate_due_source_audit_jobs(service, now=now, limit=limit)

    def pska_source_audit_job_run(run_id: str = ""):
        return run_source_audit_job(service, run_id=run_id)

    def pska_source_extract_job_enqueue(
        root_id: str,
        label: str = "",
        priority: int = 0,
        max_files: int = 1000,
        max_bytes: int = 1_000_000,
        extractor: str = "auto",
    ):
        return enqueue_source_extraction_job(
            service,
            root_id=root_id,
            label=label,
            priority=priority,
            max_files=max_files,
            max_bytes=max_bytes,
            extractor=extractor,
        )

    def pska_source_extract_job_list(status: str | None = None, limit: int = 50):
        return list_source_extraction_jobs(service, status=status or None, limit=limit)

    def pska_source_extract_job_run(run_id: str = ""):
        return run_source_extraction_job(service, run_id=run_id)

    def pska_source_watch_once(
        root_id: str,
        duration_seconds: float = 5.0,
        quiet_seconds: float = 0.25,
        max_events: int = 100,
        recursive: bool = True,
        enqueue_extraction: bool = True,
        enqueue_audit: bool = False,
        label: str = "",
        priority: int = 0,
        extractor: str = "auto",
        max_files: int = 1000,
        max_bytes: int = 1_000_000,
        audit_limit: int = 20,
    ):
        return watch_source_once(
            service,
            root_id=root_id,
            duration_seconds=duration_seconds,
            quiet_seconds=quiet_seconds,
            max_events=max_events,
            recursive=recursive,
            enqueue_extraction=enqueue_extraction,
            enqueue_audit=enqueue_audit,
            label=label,
            priority=priority,
            extractor=extractor,
            max_files=max_files,
            max_bytes=max_bytes,
            audit_limit=audit_limit,
        )

    def pska_saved_search_create(
        label: str,
        query: str,
        scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        sort: str = "relevance",
    ):
        return service.saved_search_create(label, query, scope or {}, filters or {}, sort=sort)

    def pska_source_collection_create(
        label: str,
        description: str = "",
        selector: dict[str, Any] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
    ):
        return service.source_collection_create(
            label,
            description=description,
            selector=selector or {},
            source_refs=source_refs or [],
        )

    def pska_source_collection_list():
        return service.source_collection_list()

    def pska_source_collection_resolve(collection_id: str, limit: int = 10):
        return to_jsonable(service.source_collection_resolve(collection_id, limit=limit))

    def pska_source_tag_propose(
        target_ref: dict[str, Any],
        tag: str,
        reason: str = "",
        write_target: str = "sidecar",
    ):
        return service.source_tag_propose(
            SourceRef.from_dict(target_ref),
            tag,
            reason=reason,
            write_target=write_target,
        )

    def pska_source_tag_apply(proposal_id: str):
        return service.source_tag_apply(proposal_id)

    def pska_source_comment_propose(
        target_ref: dict[str, Any],
        body: str,
        reason: str = "",
        write_target: str = "sidecar",
    ):
        return service.source_comment_propose(
            SourceRef.from_dict(target_ref),
            body,
            reason=reason,
            write_target=write_target,
        )

    def pska_source_comment_apply(proposal_id: str):
        return service.source_comment_apply(proposal_id)

    def pska_obsidian_moc_propose(
        root_id: str,
        source_refs: list[dict[str, Any]],
        moc_path: str = "PSKA MOC.md",
        title: str = "",
        reason: str = "",
        group_by: str = "none",
    ):
        return service.source_obsidian_moc_propose(
            root_id,
            source_refs,
            moc_path=moc_path,
            title=title,
            reason=reason,
            group_by=group_by,
        )

    def pska_obsidian_moc_apply(proposal_id: str):
        return service.source_obsidian_moc_apply(proposal_id)

    def pska_policy_get():
        return build_workspace_policy_from_env().to_dict()

    def pska_capabilities_get():
        return product_capabilities(memory_adapter=service.memory)

    def pska_migration_manifest(limit: int = 200):
        return build_migration_manifest(service, limit=limit)

    def pska_provider_jobs(
        dataset_page_size: int = 50,
        digest_limit: int = 50,
        source_audit_limit: int = 50,
        audit_limit: int = 50,
        include_ready: bool = True,
    ):
        return build_provider_job_status(
            service,
            build_kb_gateway_from_env(),
            dataset_page_size=dataset_page_size,
            digest_limit=digest_limit,
            source_audit_limit=source_audit_limit,
            audit_limit=audit_limit,
            include_ready=include_ready,
        )

    def pska_workspace_status(
        dataset_page_size: int = 30,
        review_limit: int = 50,
        workflow_limit: int = 50,
        compact: bool = False,
        view: str = "",
        next_action_limit: int = 8,
    ):
        status = build_workspace_status(
            service=service,
            gateway=build_kb_gateway_from_env(),
            dataset_page_size=dataset_page_size,
            review_limit=review_limit,
            workflow_limit=workflow_limit,
        )
        response_view = str(view or "").strip().lower()
        if compact or response_view in {"compact", "agent", "webui", "extension"}:
            return compact_workspace_status(status, next_action_limit=next_action_limit)
        return status

    def pska_jarvis_briefing(
        scope: dict[str, Any] | None = None,
        source_scope: dict[str, Any] | None = None,
        audit_limit: int = 20,
        dataset_page_size: int = 30,
        review_limit: int = 50,
        workflow_limit: int = 50,
    ):
        return build_jarvis_briefing(
            service=service,
            gateway=build_kb_gateway_from_env(),
            scope=scope or {},
            source_scope=source_scope or None,
            audit_limit=audit_limit,
            dataset_page_size=dataset_page_size,
            review_limit=review_limit,
            workflow_limit=workflow_limit,
        )

    def pska_agentic_context_brief(
        objective: str = "",
        question: str = "",
        project_hint: str = "",
        scope: dict[str, Any] | None = None,
        source_scope: dict[str, Any] | None = None,
        evidence_limit: int = 5,
        source_limit: int = 5,
        memory_limit: int = 5,
        trace_limit: int = 8,
        specialist_profile_ids: list[str] | None = None,
    ):
        return build_agentic_context_brief(
            service=service,
            gateway=build_kb_gateway_from_env(),
            objective=objective,
            question=question,
            project_hint=project_hint,
            scope=scope or {},
            source_scope=source_scope or None,
            evidence_limit=evidence_limit,
            source_limit=source_limit,
            memory_limit=memory_limit,
            trace_limit=trace_limit,
            specialist_profile_ids=specialist_profile_ids or None,
        )

    def pska_agentic_context_brief_list(limit: int = 10, scan_limit: int | None = None):
        return list_agentic_context_briefs(service=service, limit=limit, scan_limit=scan_limit)

    def pska_agentic_specialist_profiles(
        objective: str = "",
        question: str = "",
        project_hint: str = "",
        profile_ids: list[str] | None = None,
        limit: int = 4,
    ):
        return build_agentic_specialist_profiles(
            objective=objective,
            question=question,
            project_hint=project_hint,
            profile_ids=profile_ids or None,
            limit=limit,
        )

    def pska_hermes_answer_proofs(
        proof_id: str = "",
        session_id: str = "",
        response_id: str = "",
        read_only: bool | None = None,
        limit: int = 20,
    ):
        return list_hermes_answer_proofs(
            service,
            proof_id=proof_id,
            session_id=session_id,
            response_id=response_id,
            read_only=read_only,
            limit=limit,
            audit=False,
        )

    def pska_runtime_diagnostics():
        return build_runtime_diagnostics(
            service=service,
            kb_gateway_factory=build_kb_gateway_from_env,
        )

    def pska_alpha_readiness(
        dataset_page_size: int = 30,
        review_limit: int = 50,
        workflow_limit: int = 50,
    ):
        gateway = build_kb_gateway_from_env()
        return build_alpha_readiness(
            service=service,
            gateway=gateway,
            kb_gateway_factory=lambda: gateway,
            dataset_page_size=dataset_page_size,
            review_limit=review_limit,
            workflow_limit=workflow_limit,
        )

    def pska_alpha_trial_guide(
        dataset_page_size: int = 30,
        review_limit: int = 50,
        workflow_limit: int = 50,
    ):
        gateway = build_kb_gateway_from_env()
        return build_alpha_trial_guide(
            service=service,
            gateway=gateway,
            kb_gateway_factory=lambda: gateway,
            dataset_page_size=dataset_page_size,
            review_limit=review_limit,
            workflow_limit=workflow_limit,
        )

    def pska_alpha_recovery_plan():
        return build_alpha_recovery_plan(
            service=service,
            gateway=build_kb_gateway_from_env(),
        )

    def pska_alpha_first_run_session(session_id: str = "default"):
        return build_alpha_first_run_session(
            service=service,
            gateway=build_kb_gateway_from_env(),
            session_id=session_id,
        )

    def pska_alpha_first_run_item_update(
        item_id: str,
        status: str,
        note: str = "",
        session_id: str = "default",
    ):
        return update_alpha_first_run_session(
            service=service,
            gateway=build_kb_gateway_from_env(),
            session_id=session_id,
            item_id=item_id,
            status=status,
            note=note,
        )

    def pska_propose(run_id: str, kind: str, intent: str = ""):
        return to_jsonable(service.propose(run_id, kind, intent))

    def pska_review_create(proposal_id: str):
        return to_jsonable(service.review_create(proposal_id))

    def pska_review_list(status: str | None = None, limit: int = 50):
        return service.store.list_reviews(status=status or None, limit=limit)

    def pska_review_get(review_id: str):
        return service.store.get_review_record(review_id)

    def pska_review_decide(review_id: str, decision: str, reason: str = ""):
        return to_jsonable(service.review_decide(review_id, decision, reason))

    def pska_review_decide_batch(review_ids: list[str], decision: str, reason: str = ""):
        return service.review_decide_batch(review_ids, decision, reason)

    def pska_review_merge_candidates(
        review_ids: list[str],
        memory_candidate: dict[str, Any],
        intent: str = "",
        reason: str = "",
    ):
        return service.review_merge_candidates(
            review_ids,
            memory_candidate=memory_candidate,
            intent=intent,
            reason=reason,
        )

    def pska_review_revise(
        review_id: str,
        intent: str = "",
        memory_candidate: dict[str, Any] | None = None,
    ):
        return service.review_revise(review_id, intent, memory_candidate=memory_candidate or None)

    def pska_memory_search(
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 10,
        trace_context: dict[str, Any] | None = None,
    ):
        context = {"caller": "mcp_tool", "purpose": "memory_search_tool"}
        context.update(trace_context or {})
        return to_jsonable(service.memory_search(query, scope or {}, limit, trace_context=context))

    def pska_memory_card_list(
        scope: dict[str, Any] | None = None,
        limit: int = 50,
        query: str = "",
        status: str = "active",
        memory_type: str = "",
    ):
        return list_memory_cards(
            service,
            scope=scope or {},
            limit=limit,
            query=query,
            status=status,
            memory_type=memory_type,
        )

    def pska_memory_card_get(memory_id: str, scope: dict[str, Any] | None = None):
        return get_memory_card(service, memory_id, scope=scope or {})

    def pska_memory_health_scan(
        scope: dict[str, Any] | None = None,
        issue_type: str = "",
        limit: int = 100,
    ):
        return scan_memory_health(
            service,
            scope=scope or {},
            issue_type=issue_type,
            limit=limit,
        )

    def pska_memory_briefing(
        scope: dict[str, Any] | None = None,
        card_limit: int = 30,
        health_limit: int = 20,
        trace_limit: int = 30,
    ):
        return build_memory_briefing(
            service,
            scope=scope or {},
            card_limit=card_limit,
            health_limit=health_limit,
            trace_limit=trace_limit,
        )

    def pska_memory_review_queue(
        scope: dict[str, Any] | None = None,
        review_limit: int = 50,
        health_limit: int = 20,
        focus_limit: int = 20,
    ):
        return build_memory_review_queue(
            service,
            scope=scope or {},
            review_limit=review_limit,
            health_limit=health_limit,
            focus_limit=focus_limit,
        )

    def pska_memory_candidate_dedup(
        scope: dict[str, Any] | None = None,
        review_limit: int = 100,
        similarity_threshold: float = 0.82,
        related_threshold: float = 0.72,
    ):
        return build_memory_candidate_dedup(
            service,
            scope=scope or {},
            review_limit=review_limit,
            similarity_threshold=similarity_threshold,
            related_threshold=related_threshold,
        )

    def pska_memory_use_trace(
        memory_id: str = "",
        query: str = "",
        action: str = "",
        limit: int = 50,
    ):
        return list_memory_use_traces(
            service,
            memory_id=memory_id,
            query=query,
            action=action,
            limit=limit,
        )

    def pska_memory_why_used(memory_id: str, scope: dict[str, Any] | None = None, limit: int = 20):
        return explain_memory_why_used(service, memory_id, scope=scope or {}, limit=limit)

    def pska_memory_timeline(
        memory_id: str,
        scope: dict[str, Any] | None = None,
        limit: int = 50,
        include_usage: bool = True,
        include_sources: bool = True,
    ):
        return build_memory_timeline(
            service,
            memory_id,
            scope=scope or {},
            limit=limit,
            include_usage=include_usage,
            include_sources=include_sources,
        )

    def pska_memory_apply(review_id: str):
        return to_jsonable(service.memory_apply(review_id))

    def pska_memory_review_from_workflow(run_id: str, intent: str = ""):
        return service.memory_review_from_workflow(run_id, intent)

    def pska_workflow_memory_attribution(run_id: str):
        return service.workflow_artifact(run_id)["memory_attribution"]

    def pska_workflow_memory_suggestions(run_id: str):
        return service.workflow_artifact(run_id)["memory_suggestions"]

    def pska_source_memory_review_create(
        source_refs: list[dict[str, Any]],
        text: str,
        memory_type: str = "source_route",
        behavior_delta: str = "",
        memory_scope: str = "workspace",
        reason: str = "",
        confidence: float = 0.82,
        scope: dict[str, Any] | None = None,
    ):
        return service.source_memory_review_create(
            source_refs,
            text=text,
            memory_type=memory_type,
            behavior_delta=behavior_delta,
            memory_scope=memory_scope,
            reason=reason,
            confidence=confidence,
            scope=scope or {},
        )

    def pska_source_memory_candidates_from_audit(
        scope: dict[str, Any] | None = None,
        audit_limit: int = 20,
        candidate_limit: int = 5,
        memory_scope: str = "project",
        dedupe_existing: bool = True,
    ):
        return service.source_memory_candidates_from_audit(
            scope or {},
            audit_limit=audit_limit,
            candidate_limit=candidate_limit,
            memory_scope=memory_scope,
            dedupe_existing=dedupe_existing,
        )

    def pska_eidolia_context_read(
        project_id: str,
        node_id: str,
        node_type: str = "thought",
        text: str = "",
        title: str = "",
        canvas_path: str = "",
        role: str = "",
        artifact_kind: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        return service.eidolia_context_read(
            project_id=project_id,
            node_id=node_id,
            node_type=node_type,
            text=text,
            title=title,
            canvas_path=canvas_path,
            role=role,
            artifact_kind=artifact_kind,
            metadata=metadata or {},
        )

    def pska_eidolia_memory_review_create(
        project_id: str,
        node_id: str,
        text: str,
        behavior_delta: str,
        node_type: str = "thought",
        title: str = "",
        canvas_path: str = "",
        role: str = "",
        artifact_kind: str = "",
        memory_type: str = "project_state",
        memory_scope: str = "project",
        reason: str = "",
        confidence: float = 0.82,
        scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        return service.eidolia_memory_review_create(
            project_id=project_id,
            node_id=node_id,
            text=text,
            behavior_delta=behavior_delta,
            node_type=node_type,
            title=title,
            canvas_path=canvas_path,
            role=role,
            artifact_kind=artifact_kind,
            memory_type=memory_type,
            memory_scope=memory_scope,
            reason=reason,
            confidence=confidence,
            scope=scope or {},
            metadata=metadata or {},
        )

    def pska_trace_query(
        target_type: str = "",
        target_id: str = "",
        review_id: str = "",
        proposal_id: str = "",
        memory_id: str = "",
        source_ref: dict[str, Any] | None = None,
        action: str = "",
        limit: int = 50,
    ):
        return build_trace_query(
            service,
            target_type=target_type,
            target_id=target_id,
            review_id=review_id,
            proposal_id=proposal_id,
            memory_id=memory_id,
            source_ref=source_ref or None,
            action=action,
            limit=limit,
        )

    def pska_eidolia_project_trace_import(
        project_path: str = "",
        workspace_path: str = "",
        trace_paths: list[str] | None = None,
        node_limit: int = 100,
        trace_limit: int = 50,
    ):
        return import_eidolia_project_traces(
            service,
            project_path=project_path,
            workspace_path=workspace_path,
            trace_paths=trace_paths or [],
            node_limit=node_limit,
            trace_limit=trace_limit,
        )

    def pska_memory_change_from_conversation(
        user_message: str,
        operation: str = "auto",
        text: str = "",
        memory_fact: dict[str, Any] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        session_id: str = "",
        message_id: str = "",
        reason: str = "",
        scope: dict[str, Any] | None = None,
        force_review: bool = False,
        confidence: float = 0.95,
    ):
        return service.memory_change_from_conversation(
            user_message=user_message,
            operation=operation,
            text=text,
            memory_fact=memory_fact,
            source_refs=source_refs or [],
            session_id=session_id,
            message_id=message_id,
            reason=reason,
            scope=scope or {},
            force_review=force_review,
            confidence=confidence,
        )

    def pska_conversation_memory_candidates_create(
        messages: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        session_id: str = "",
        scope: dict[str, Any] | None = None,
        dedupe_existing: bool = True,
        candidate_limit: int = 5,
    ):
        return service.conversation_memory_candidates_create(
            messages=messages,
            candidates=candidates,
            session_id=session_id,
            scope=scope or {},
            dedupe_existing=dedupe_existing,
            candidate_limit=candidate_limit,
        )

    def pska_memory_delete_review(memory_fact: dict[str, Any], reason: str = ""):
        return service.memory_delete_review(memory_fact, reason)

    def pska_memory_update_review(memory_fact: dict[str, Any], text: str, reason: str = ""):
        return service.memory_update_review(memory_fact, text, reason)

    def pska_memory_refresh_review(
        memory_id: str,
        text: str = "",
        reason: str = "",
        scope: dict[str, Any] | None = None,
    ):
        return service.memory_refresh_review(memory_id, text=text, reason=reason, scope=scope or {})

    def pska_memory_lifecycle(memory_target_id: str, limit: int = 50):
        return service.memory_lifecycle(memory_target_id, limit)

    def pska_export_brief(run_id: str, format: str = "markdown"):
        return service.export_brief(run_id, format)

    def pska_audit_list(action: str | None = None, limit: int = 50, descending: bool = True):
        return to_jsonable(
            service.store.list_audit_events(
                action=action or None,
                limit=limit,
                descending=descending,
            )
        )

    def pska_retrieval_probe(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 1,
        use_kg: bool = False,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        probe = run_retrieval_probe(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=limit,
            use_kg=use_kg,
        )
        add_retrieval_probe_audit(service.store, probe)
        return probe

    def pska_memory_probe(
        query: str = "PSKA memory probe",
        scope: dict[str, Any] | None = None,
        limit: int = 1,
        require_live: bool = True,
    ):
        probe = run_memory_probe(
            service,
            query=query,
            scope=scope or {},
            limit=limit,
            require_live=require_live,
        )
        add_memory_probe_audit(service.store, probe)
        return probe

    def pska_component_check(
        question: str = "PSKA component check",
        dataset_ids: list[str] | None = None,
        dataset_names: list[str] | None = None,
        document_ids: list[str] | None = None,
        memory_query: str = "PSKA component memory probe",
        limit: int = 3,
        retrieval_limit: int = 1,
        proposal_kind: str = "writing_brief",
        use_kg: bool = False,
        export_format: str = "json",
        source_inspection_limit: int = 1,
        require_memory: bool = True,
        run_closed_loop: bool = True,
    ):
        return run_component_check(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=_optional_strings(dataset_ids),
            dataset_names=_optional_strings(dataset_names),
            document_ids=_optional_strings(document_ids),
            memory_query=memory_query,
            limit=limit,
            retrieval_limit=retrieval_limit,
            proposal_kind=proposal_kind,
            use_kg=use_kg,
            export_format=export_format,
            source_inspection_limit=source_inspection_limit,
            require_memory=require_memory,
            run_closed_loop=run_closed_loop,
        )

    def pska_live_closed_loop_probe(
        question: str,
        dataset_ids: list[str] | None = None,
        dataset_names: list[str] | None = None,
        document_ids: list[str] | None = None,
        limit: int = 3,
        proposal_kind: str = "writing_brief",
        use_kg: bool = False,
        export_format: str = "json",
        source_inspection_limit: int = 1,
    ):
        selected_dataset_ids = _optional_strings(dataset_ids)
        selected_dataset_names = _optional_strings(dataset_names)
        if not selected_dataset_ids and not selected_dataset_names:
            raise ValueError("dataset_ids or dataset_names is required")
        selected_document_ids = _optional_strings(document_ids)
        probe = run_live_closed_loop_probe(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            dataset_names=selected_dataset_names,
            document_ids=selected_document_ids,
            limit=limit,
            proposal_kind=proposal_kind,
            use_kg=use_kg,
            export_format=export_format,
            source_inspection_limit=source_inspection_limit,
        )
        add_live_closed_loop_probe_audit(service.store, probe)
        return probe

    def pska_ingest_loop(
        file_paths: list[str],
        dataset_name: str | None = None,
        dataset_id: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
        parse: bool = True,
        wait_ready: bool = True,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 2.0,
        question: str = "Summarize the uploaded documents with sources.",
        limit: int = 5,
        proposal_kind: str = "writing_brief",
        create_review: bool | None = None,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
        export_format: str = "markdown",
    ):
        selected_file_paths = _required_strings(file_paths, "file_paths", dedupe=False)
        return run_ingest_loop(
            service,
            build_kb_gateway_from_env(),
            file_paths=selected_file_paths,
            dataset_name=dataset_name or "",
            dataset_id=dataset_id or "",
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
            parse=parse,
            wait_ready=wait_ready,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            question=question,
            limit=limit,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
            export_format=export_format,
        )

    def pska_ingest_loop_resume(run_id: str, export_format: str = ""):
        selected_run_id = _required_string(run_id, "run_id")
        return resume_ingest_loop(
            service,
            build_kb_gateway_from_env(),
            run_id=selected_run_id,
            export_format=export_format,
        )

    def pska_eval_run(suite: str = "smoke"):
        return run_eval(suite, service, gateway_factory=build_kb_gateway_from_env)

    def pska_kb_list(name: str | None = None, page_size: int = 30):
        return build_kb_gateway_from_env().list_datasets(name=name, page_size=page_size)

    def pska_kb_create(
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
    ):
        dataset = build_kb_gateway_from_env().create_dataset(
            name=name,
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
        )
        add_kb_dataset_create_audit(service.store, dataset)
        return dataset

    def pska_kb_delete(
        dataset_ids: list[str] | None = None,
        dataset_names: list[str] | None = None,
        delete_all: bool = False,
    ):
        selected_dataset_ids = _optional_strings(dataset_ids)
        selected_dataset_names = _optional_strings(dataset_names)
        if not delete_all and not selected_dataset_ids and not selected_dataset_names:
            raise ValueError("dataset_ids or dataset_names is required unless delete_all is true")
        result = build_kb_gateway_from_env().delete_datasets(
            dataset_ids=selected_dataset_ids,
            dataset_names=selected_dataset_names,
            delete_all=delete_all,
        )
        add_kb_dataset_delete_audit(service.store, result)
        return result

    def pska_kb_ingest_files(
        file_paths: list[str],
        dataset_name: str | None = None,
        dataset_id: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
        parse: bool = True,
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        selected_file_paths = _required_strings(file_paths, "file_paths", dedupe=False)
        gateway = build_kb_gateway_from_env()
        result = gateway.ingest_files(
            file_paths=selected_file_paths,
            dataset_name=dataset_name,
            dataset_id=dataset_id,
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
            parse=parse,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_ingest_audit(service.store, result)
        return {
            **result,
            **_kb_operation_status_payload(gateway, result),
            "note": (
                "Upload accepted. Use ingestion_status/readiness before asking; "
                "uploaded or processing scopes are not retrieval-ready yet."
            ),
        }

    def pska_kb_document_status(
        dataset_id: str,
        document_id: str | None = None,
        name: str | None = None,
        page_size: int = 30,
    ):
        return build_kb_gateway_from_env().list_documents(
            dataset_id=dataset_id,
            document_id=document_id,
            name=name,
            page_size=page_size,
        )

    def pska_kb_readiness(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        return evaluate_kb_readiness(
            build_kb_gateway_from_env(),
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )

    def pska_kb_ingestion_status(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        payload = _kb_status_payload(
            build_kb_gateway_from_env(),
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )
        return {
            **payload,
            "note": (
                "Use readiness.ready before retrieval. If ingestion_status is not ready, "
                "wait, parse listed documents, or inspect failure reasons instead of asking."
            ),
        }

    def pska_kb_parse_documents(
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        selected_dataset_id = _required_string(dataset_id, "dataset_id")
        selected_document_ids = _required_strings(document_ids, "document_ids")
        gateway = build_kb_gateway_from_env()
        result = gateway.parse_documents(
            dataset_id=selected_dataset_id,
            document_ids=selected_document_ids,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_parse_audit(service.store, result)
        return {
            **result,
            **_kb_status_payload(gateway, dataset_ids=[selected_dataset_id], document_ids=selected_document_ids),
            "note": "Parse started. Use ingestion_status/readiness before asking over this scope.",
        }

    def pska_kb_graph_read(dataset_id: str, document_id: str):
        selected_dataset_id = _required_string(dataset_id, "dataset_id")
        selected_document_id = _required_string(document_id, "document_id")
        graph = build_kb_gateway_from_env().document_graph(dataset_id=selected_dataset_id, document_id=selected_document_id)
        add_kb_graph_read_audit(service.store, graph, dataset_id=selected_dataset_id, document_id=selected_document_id)
        return graph

    def pska_agentic_question_start(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 5,
        proposal_kind: str = "writing_brief",
        create_review: bool | None = None,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
        model_context_tokens: int | None = None,
        model_profile: str = "",
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        result = run_agentic_question_with_readiness(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=limit,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
            model_context_tokens=model_context_tokens,
            model_profile=model_profile,
        )
        if result["status"] == "not_ready":
            result["note"] = (
                "Selected knowledge scope is not ready for retrieval. "
                "Check pska_kb_readiness or pska_kb_document_status before asking again."
            )
            return result
        result["note"] = (
            "Agent should answer from returned context and brief. "
            "Transient work products do not require review by default. "
            "Use pska_memory_change_from_conversation for normal user-driven memory corrections; "
            "explicit pska_memory_apply still requires an accepted review."
        )
        return result

    def pska_agentic_question_resume(run_id: str):
        selected_run_id = _required_string(run_id, "run_id")
        result = resume_agentic_question(
            service,
            build_kb_gateway_from_env(),
            run_id=selected_run_id,
        )
        if result["status"] == "not_ready":
            result["note"] = (
                "Selected knowledge scope is still not ready for retrieval. "
                "Check pska_kb_readiness or pska_kb_document_status before resuming again."
            )
            return result
        result["note"] = (
            "Resumed Ask created a new workflow run. "
            "Use returned context/brief and keep durable memory changes behind review."
        )
        return result

    def pska_agentic_question_resumable(limit: int = 50):
        return list_resumable_agentic_questions(
            service,
            build_kb_gateway_from_env(),
            limit=limit,
        )

    def pska_digest_scope(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        question: str = "Digest the selected ready knowledge into concise candidate knowledge.",
        limit: int = 5,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
        model_context_tokens: int | None = None,
        model_profile: str = "",
        create_memory_review: bool = False,
        memory_intent: str = "",
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        result = run_digest_scope(
            service,
            build_kb_gateway_from_env(),
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            question=question,
            limit=limit,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
            model_context_tokens=model_context_tokens,
            model_profile=model_profile,
            create_memory_review=create_memory_review,
            memory_intent=memory_intent,
        )
        result["note"] = (
            "Digest is a sourced candidate workflow. It does not write Graphiti memory directly; "
            "create_memory_review routes the digest through PSKA review/governance."
        )
        return result

    def pska_digest_job_enqueue(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        question: str = "Digest the selected ready knowledge into concise candidate knowledge.",
        priority: int = 0,
        limit: int = 5,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
        create_memory_review: bool = False,
        memory_intent: str = "",
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        result = enqueue_digest_job(
            service,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            question=question,
            priority=priority,
            limit=limit,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
            create_memory_review=create_memory_review,
            memory_intent=memory_intent,
        )
        result["note"] = (
            "Digest job queued inside PSKA workflow metadata. It will not write Graphiti memory "
            "unless a later run creates and applies a governed memory review."
        )
        return result

    def pska_digest_job_list(status: str | None = None, limit: int = 50):
        return list_digest_jobs(service, status=status or None, limit=limit)

    def pska_digest_job_run(run_id: str = ""):
        result = run_digest_job(
            service,
            build_kb_gateway_from_env(),
            run_id=run_id,
        )
        result["note"] = (
            "Digest job runner respects KB readiness and review policy; it does not run provider APIs directly."
        )
        return result

    return {
        "pska_workflow_start": pska_workflow_start,
        "pska_workflow_list": pska_workflow_list,
        "pska_workflow_state": pska_workflow_state,
        "pska_workflow_artifact": pska_workflow_artifact,
        "pska_workflow_brief": pska_workflow_brief,
        "pska_context_retrieve": pska_context_retrieve,
        "pska_source_read": pska_source_read,
        "pska_source_root_list": pska_source_root_list,
        "pska_source_root_register": pska_source_root_register,
        "pska_source_scan": pska_source_scan,
        "pska_source_search": pska_source_search,
        "pska_source_neighbors": pska_source_neighbors,
        "pska_duplicate_report": pska_duplicate_report,
        "pska_duplicate_review_list": pska_duplicate_review_list,
        "pska_duplicate_group_mark": pska_duplicate_group_mark,
        "pska_duplicate_cleanup_propose": pska_duplicate_cleanup_propose,
        "pska_source_audit_run": pska_source_audit_run,
        "pska_source_audit_job_enqueue": pska_source_audit_job_enqueue,
        "pska_source_audit_schedule_create": pska_source_audit_schedule_create,
        "pska_source_audit_job_list": pska_source_audit_job_list,
        "pska_source_audit_job_tick": pska_source_audit_job_tick,
        "pska_source_audit_job_run": pska_source_audit_job_run,
        "pska_source_extract_job_enqueue": pska_source_extract_job_enqueue,
        "pska_source_extract_job_list": pska_source_extract_job_list,
        "pska_source_extract_job_run": pska_source_extract_job_run,
        "pska_source_watch_once": pska_source_watch_once,
        "pska_saved_search_create": pska_saved_search_create,
        "pska_source_collection_create": pska_source_collection_create,
        "pska_source_collection_list": pska_source_collection_list,
        "pska_source_collection_resolve": pska_source_collection_resolve,
        "pska_source_tag_propose": pska_source_tag_propose,
        "pska_source_tag_apply": pska_source_tag_apply,
        "pska_source_comment_propose": pska_source_comment_propose,
        "pska_source_comment_apply": pska_source_comment_apply,
        "pska_obsidian_moc_propose": pska_obsidian_moc_propose,
        "pska_obsidian_moc_apply": pska_obsidian_moc_apply,
        "pska_policy_get": pska_policy_get,
        "pska_capabilities_get": pska_capabilities_get,
        "pska_migration_manifest": pska_migration_manifest,
        "pska_provider_jobs": pska_provider_jobs,
        "pska_workspace_status": pska_workspace_status,
        "pska_jarvis_briefing": pska_jarvis_briefing,
        "pska_agentic_context_brief": pska_agentic_context_brief,
        "pska_agentic_context_brief_list": pska_agentic_context_brief_list,
        "pska_agentic_specialist_profiles": pska_agentic_specialist_profiles,
        "pska_hermes_answer_proofs": pska_hermes_answer_proofs,
        "pska_runtime_diagnostics": pska_runtime_diagnostics,
        "pska_alpha_readiness": pska_alpha_readiness,
        "pska_alpha_trial_guide": pska_alpha_trial_guide,
        "pska_alpha_recovery_plan": pska_alpha_recovery_plan,
        "pska_alpha_first_run_session": pska_alpha_first_run_session,
        "pska_alpha_first_run_item_update": pska_alpha_first_run_item_update,
        "pska_propose": pska_propose,
        "pska_review_create": pska_review_create,
        "pska_review_list": pska_review_list,
        "pska_review_get": pska_review_get,
        "pska_review_decide": pska_review_decide,
        "pska_review_decide_batch": pska_review_decide_batch,
        "pska_review_merge_candidates": pska_review_merge_candidates,
        "pska_review_revise": pska_review_revise,
        "pska_memory_search": pska_memory_search,
        "pska_memory_card_list": pska_memory_card_list,
        "pska_memory_card_get": pska_memory_card_get,
        "pska_memory_briefing": pska_memory_briefing,
        "pska_memory_review_queue": pska_memory_review_queue,
        "pska_memory_candidate_dedup": pska_memory_candidate_dedup,
        "pska_memory_health_scan": pska_memory_health_scan,
        "pska_memory_use_trace": pska_memory_use_trace,
        "pska_memory_why_used": pska_memory_why_used,
        "pska_memory_timeline": pska_memory_timeline,
        "pska_memory_apply": pska_memory_apply,
        "pska_source_memory_review_create": pska_source_memory_review_create,
        "pska_source_memory_candidates_from_audit": pska_source_memory_candidates_from_audit,
        "pska_eidolia_context_read": pska_eidolia_context_read,
        "pska_eidolia_memory_review_create": pska_eidolia_memory_review_create,
        "pska_trace_query": pska_trace_query,
        "pska_eidolia_project_trace_import": pska_eidolia_project_trace_import,
        "pska_memory_change_from_conversation": pska_memory_change_from_conversation,
        "pska_conversation_memory_candidates_create": pska_conversation_memory_candidates_create,
        "pska_memory_review_from_workflow": pska_memory_review_from_workflow,
        "pska_workflow_memory_attribution": pska_workflow_memory_attribution,
        "pska_workflow_memory_suggestions": pska_workflow_memory_suggestions,
        "pska_memory_delete_review": pska_memory_delete_review,
        "pska_memory_update_review": pska_memory_update_review,
        "pska_memory_refresh_review": pska_memory_refresh_review,
        "pska_memory_lifecycle": pska_memory_lifecycle,
        "pska_export_brief": pska_export_brief,
        "pska_audit_list": pska_audit_list,
        "pska_retrieval_probe": pska_retrieval_probe,
        "pska_memory_probe": pska_memory_probe,
        "pska_component_check": pska_component_check,
        "pska_live_closed_loop_probe": pska_live_closed_loop_probe,
        "pska_ingest_loop": pska_ingest_loop,
        "pska_ingest_loop_resume": pska_ingest_loop_resume,
        "pska_digest_scope": pska_digest_scope,
        "pska_digest_job_enqueue": pska_digest_job_enqueue,
        "pska_digest_job_list": pska_digest_job_list,
        "pska_digest_job_run": pska_digest_job_run,
        "pska_eval_run": pska_eval_run,
        "pska_kb_list": pska_kb_list,
        "pska_kb_create": pska_kb_create,
        "pska_kb_delete": pska_kb_delete,
        "pska_kb_ingest_files": pska_kb_ingest_files,
        "pska_kb_document_status": pska_kb_document_status,
        "pska_kb_readiness": pska_kb_readiness,
        "pska_kb_ingestion_status": pska_kb_ingestion_status,
        "pska_kb_parse_documents": pska_kb_parse_documents,
        "pska_kb_graph_read": pska_kb_graph_read,
        "pska_agentic_question_start": pska_agentic_question_start,
        "pska_agentic_question_resumable": pska_agentic_question_resumable,
        "pska_agentic_question_resume": pska_agentic_question_resume,
    }


def _kb_status_payload(
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
    selected_document_ids = _optional_strings(document_ids)
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=selected_dataset_ids,
        document_ids=selected_document_ids,
    )
    return {"readiness": readiness, "ingestion_status": readiness.get("ingestion_status") or {}}


def _kb_operation_status_payload(gateway: Any, result: dict[str, Any]) -> dict[str, Any]:
    dataset = result.get("dataset") or {}
    dataset_id = str(dataset.get("dataset_id") or "")
    if not dataset_id:
        return {"readiness": {}, "ingestion_status": {}}
    document_ids = [
        str(document.get("document_id") or "").strip()
        for document in result.get("documents") or []
        if document.get("document_id")
    ]
    return _kb_status_payload(gateway, dataset_ids=[dataset_id], document_ids=document_ids)


def _required_string(value: Any, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _required_strings(values: list[str] | None, name: str, *, dedupe: bool = True) -> list[str]:
    result = _optional_strings(values, dedupe=dedupe)
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _optional_strings(values: list[str] | None, *, dedupe: bool = True) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        if dedupe:
            if normalized in seen:
                continue
            seen.add(normalized)
        result.append(normalized)
    return result


def _http_path(value: str) -> str:
    normalized = str(value or "").strip() or "/mcp"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def build_fastmcp(
    service=None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = "/mcp",
):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install optional dependency with `uv sync --extra mcp` to run MCP") from exc

    http_path = _http_path(path)
    mcp = FastMCP(
        "pska-essential",
        instructions=(
            "PSKA-Essential is an agent knowledge workflow gate. Use its tools "
            "to retrieve context, propose candidate knowledge, review it, and "
            "apply reviewed memory. Use pska_workspace_status to choose the "
            "next workflow action. Do not call backend RAGFlow or Graphiti MCP "
            "servers directly. Do not use case-specific shortcuts or fallback "
            "answers when retrieval/backend calls fail."
        ),
        host=host,
        port=port,
        streamable_http_path=http_path,
        sse_path=http_path,
    )
    for name, func in tool_registry(service).items():
        mcp.add_tool(func, name=name)
    return mcp


def main(argv: list[str] | None = None) -> int:
    cli_args = list(sys.argv[1:] if argv is None else argv)
    env_parser = env_file_arg_parser()
    env_parser.add_argument("--list-tools", action="store_true", help="Print registered MCP tool names and exit.")
    env_parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("PSKA_MCP_TRANSPORT", "streamable-http"),
        help="MCP transport to run. Defaults to streamable-http; use --transport stdio only for isolated registry checks.",
    )
    env_parser.add_argument(
        "--host",
        default=os.getenv("PSKA_MCP_HOST", "127.0.0.1"),
        help="Host for HTTP MCP transports.",
    )
    env_parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PSKA_MCP_PORT", "8766")),
        help="Port for HTTP MCP transports.",
    )
    env_parser.add_argument(
        "--path",
        default=os.getenv("PSKA_MCP_PATH", "/mcp"),
        help="URL path for streamable HTTP/SSE MCP transports.",
    )
    if any(arg in {"-h", "--help"} for arg in cli_args):
        env_parser.print_help()
        return 0
    env_args, remaining = env_parser.parse_known_args(cli_args)
    if env_args.env_file:
        load_env_file(env_args.env_file)

    if env_args.list_tools:
        print(json.dumps(sorted(tool_registry().keys()), ensure_ascii=False, indent=2))
        return 0
    original_argv = sys.argv
    sys.argv = [original_argv[0], *remaining]
    try:
        server = build_fastmcp(host=env_args.host, port=env_args.port, path=env_args.path)
        server.run(env_args.transport)
    finally:
        sys.argv = original_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
