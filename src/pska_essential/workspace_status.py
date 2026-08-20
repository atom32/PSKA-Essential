from __future__ import annotations

import os
from typing import Any

from pska_essential.agentic_loop import list_resumable_agentic_questions
from pska_essential.capabilities import memory_capabilities, memory_operation_for_proposal_kind
from pska_essential.gbrain_component import build_gbrain_component_status
from pska_essential.governance import DURABLE_PROPOSAL_KINDS, build_workspace_policy_from_env
from pska_essential.memory_candidate_quality import memory_candidate_quality_issue
from pska_essential.memory_cards import list_memory_cards
from pska_essential.memory_health import scan_memory_health
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.runtime_context import build_runtime_workspace_context


def build_workspace_status(
    *,
    service: Any,
    gateway: Any,
    dataset_page_size: int = 30,
    review_limit: int = 50,
    workflow_limit: int = 50,
) -> dict[str, Any]:
    """Return product-level workspace state and next actions.

    This is an operational summary for users and agents. It uses PSKA product
    boundaries only and never substitutes fake data when a backend reports an
    error.
    """

    datasets, readiness, dataset_readiness, kb_error = _kb_state(gateway, page_size=dataset_page_size)
    reviews = service.store.list_reviews(limit=review_limit)
    pending_reviews = [review for review in reviews if review.get("status") == "pending"]
    accepted_unapplied = [
        review
        for review in reviews
        if review.get("status") == "accepted"
        and not review.get("memory_apply")
        and str((review.get("proposal") or {}).get("kind") or "") in DURABLE_PROPOSAL_KINDS
        and not memory_candidate_quality_issue(review, include_actions=False)
    ]
    memory_candidate_quality_issues = [
        issue
        for review in reviews
        if review.get("status") in {"pending", "accepted"} and not review.get("memory_apply")
        for issue in [memory_candidate_quality_issue(review)]
        if issue is not None
    ]
    workflows = service.store.list_workflows(limit=workflow_limit)
    resumable, resumable_error = _resumable_state(service, gateway, limit=workflow_limit)
    provider_jobs, provider_jobs_error = _provider_jobs_state(service, gateway, dataset_page_size=dataset_page_size)
    memory_caps = memory_capabilities(service.memory)
    memory_cards, memory_cards_error = _memory_cards_state(service, memory_caps)
    memory_health, memory_health_error = _memory_health_state(service, memory_caps)
    next_actions = _next_actions(
        datasets=datasets,
        readiness=readiness,
        dataset_readiness=dataset_readiness,
        kb_error=kb_error,
        pending_reviews=pending_reviews,
        accepted_unapplied=accepted_unapplied,
        memory_candidate_quality_issues=memory_candidate_quality_issues,
        memory_caps=memory_caps,
        memory_cards=memory_cards,
        memory_cards_error=memory_cards_error,
        memory_health=memory_health,
        memory_health_error=memory_health_error,
        resumable=resumable,
        resumable_error=resumable_error,
        provider_jobs=provider_jobs,
    )
    ready_dataset_ids = _dataset_ids_for_scopes(
        [scope for scope in dataset_readiness if scope.get("ready")]
    )
    blocked_dataset_ids = _dataset_ids_for_scopes(
        [scope for scope in dataset_readiness if not scope.get("ready")]
    )

    return {
        "kind": "workspace_status",
        "status": _workspace_status(next_actions, readiness, kb_error, resumable_error),
        "providers": {
            "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", "").strip().lower()
            or str(getattr(service.retrieval, "backend_name", "custom")),
            "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower()
            or str(getattr(gateway, "backend_name", "custom")),
            "memory": os.getenv("PSKA_MEMORY_PROVIDER", "").strip().lower()
            or str(getattr(service.memory, "backend_name", "custom")),
            "dev_fake": _env_enabled("PSKA_DEV_FAKE"),
        },
        "workspace": build_runtime_workspace_context().to_dict(),
        "governance": build_workspace_policy_from_env().to_dict(),
        "capabilities": {
            "memory": memory_caps,
        },
        "components": {
            "gbrain": build_gbrain_component_status(),
        },
        "memory": {
            "cards": memory_cards,
            "cards_error": memory_cards_error,
            "health": memory_health,
            "health_error": memory_health_error,
        },
        "kb": {
            "status": "error" if kb_error else (readiness or {}).get("status", "empty"),
            "dataset_count": len(datasets),
            "ready_dataset_count": len(ready_dataset_ids),
            "blocked_dataset_count": len(blocked_dataset_ids),
            "ready_dataset_ids": ready_dataset_ids,
            "blocked_dataset_ids": blocked_dataset_ids,
            "usable": bool(ready_dataset_ids),
            "datasets": datasets,
            "readiness": readiness,
            "dataset_readiness": dataset_readiness,
            "error": kb_error,
        },
        "reviews": {
            "pending_count": len(pending_reviews),
            "accepted_unapplied_count": len(accepted_unapplied),
            "candidate_quality_issue_count": len(memory_candidate_quality_issues),
            "pending": pending_reviews[:10],
            "accepted_unapplied": accepted_unapplied[:10],
            "candidate_quality": memory_candidate_quality_issues[:10],
        },
        "workflows": {
            "recent_count": len(workflows),
            "last_run": workflows[0].run_id if workflows else "",
            "resumable_ask_count": len(resumable),
            "resumable_asks": resumable[:10],
            "resumable_error": resumable_error,
        },
        "jobs": {
            "status": "error" if provider_jobs_error else (provider_jobs or {}).get("status", "empty"),
            "summary": (provider_jobs or {}).get("summary") or {},
            "recent": (provider_jobs or {}).get("jobs", [])[:10],
            "error": provider_jobs_error,
        },
        "next_actions": next_actions,
    }


def compact_workspace_status(
    status: dict[str, Any],
    *,
    next_action_limit: int = 8,
    dataset_id_limit: int = 20,
) -> dict[str, Any]:
    """Return an agent-facing summary without bulky provider/detail lists."""

    kb = dict(status.get("kb") or {})
    memory = dict(status.get("memory") or {})
    reviews = dict(status.get("reviews") or {})
    workflows = dict(status.get("workflows") or {})
    jobs = dict(status.get("jobs") or {})
    capabilities = dict(status.get("capabilities") or {})
    memory_caps = dict(capabilities.get("memory") or {})
    cards = dict(memory.get("cards") or {})
    health = dict(memory.get("health") or {})
    components = dict(status.get("components") or {})
    gbrain = dict(components.get("gbrain") or {})

    return {
        "kind": "workspace_status_compact",
        "source_kind": status.get("kind"),
        "status": status.get("status"),
        "providers": dict(status.get("providers") or {}),
        "workspace": _compact_workspace(dict(status.get("workspace") or {})),
        "governance": _compact_governance(dict(status.get("governance") or {})),
        "capabilities": {
            "memory": _compact_memory_capabilities(memory_caps),
        },
        "components": {
            "gbrain": _compact_gbrain(gbrain),
        },
        "memory": {
            "backend": str(memory_caps.get("backend") or ""),
            "card_count": _memory_card_count(cards, health),
            "cards_status": cards.get("status"),
            "cards_error": memory.get("cards_error"),
            "health": _compact_memory_health(health),
            "health_error": memory.get("health_error"),
        },
        "kb": {
            "status": kb.get("status"),
            "dataset_count": _as_int(kb.get("dataset_count")),
            "ready_dataset_count": _as_int(kb.get("ready_dataset_count")),
            "blocked_dataset_count": _as_int(kb.get("blocked_dataset_count")),
            "usable": bool(kb.get("usable")),
            "ready_dataset_ids": _limited_strings(kb.get("ready_dataset_ids"), dataset_id_limit),
            "blocked_dataset_ids": _limited_strings(kb.get("blocked_dataset_ids"), dataset_id_limit),
            "readiness": _compact_readiness(kb.get("readiness")),
            "error": kb.get("error"),
        },
        "reviews": {
            "pending_count": _as_int(reviews.get("pending_count")),
            "accepted_unapplied_count": _as_int(reviews.get("accepted_unapplied_count")),
            "candidate_quality_issue_count": _as_int(reviews.get("candidate_quality_issue_count")),
        },
        "workflows": {
            "recent_count": _as_int(workflows.get("recent_count")),
            "last_run": workflows.get("last_run") or "",
            "resumable_ask_count": _as_int(workflows.get("resumable_ask_count")),
            "resumable_error": workflows.get("resumable_error"),
        },
        "jobs": {
            "status": jobs.get("status"),
            "summary": dict(jobs.get("summary") or {}),
            "error": jobs.get("error"),
        },
        "next_actions": _compact_next_actions(status.get("next_actions"), next_action_limit),
        "omitted": {
            "kb.datasets": _list_len(kb.get("datasets")),
            "kb.dataset_readiness": _list_len(kb.get("dataset_readiness")),
            "memory.cards": _list_len(cards.get("cards")),
            "memory.health.issues": _list_len(health.get("issues")),
            "reviews.pending": _list_len(reviews.get("pending")),
            "reviews.accepted_unapplied": _list_len(reviews.get("accepted_unapplied")),
            "reviews.candidate_quality": _list_len(reviews.get("candidate_quality")),
            "workflows.resumable_asks": _list_len(workflows.get("resumable_asks")),
            "jobs.recent": _list_len(jobs.get("recent")),
        },
    }


def _compact_workspace(workspace: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_id": workspace.get("workspace_id") or "",
        "tenant_configured": bool(workspace.get("tenant_configured")),
        "workspace_configured": bool(workspace.get("workspace_configured")),
        "memory_namespace": workspace.get("memory_namespace") or "",
    }


def _compact_governance(governance: dict[str, Any]) -> dict[str, Any]:
    return {
        "durable_memory": governance.get("durable_memory") or "",
        "conversation_memory": governance.get("conversation_memory") or "",
        "digest_memory": governance.get("digest_memory") or "",
        "memory_primary_user_path": governance.get("memory_primary_user_path") or "",
        "review_queue_role": governance.get("review_queue_role") or "",
        "visible_memory_editor": governance.get("visible_memory_editor") or "",
        "visible_review_role": governance.get("visible_review_role") or "",
    }


def _compact_memory_capabilities(memory_caps: dict[str, Any]) -> dict[str, Any]:
    operations = {}
    for name, capability in (memory_caps.get("operations") or {}).items():
        item = dict(capability or {})
        operations[str(name)] = {
            "supported": item.get("supported") is not False,
            "reason": str(item.get("reason") or ""),
        }
    return {
        "backend": str(memory_caps.get("backend") or ""),
        "operations": operations,
        "conversation_update_strategies": list(memory_caps.get("conversation_update_strategies") or []),
    }


def _compact_gbrain(gbrain: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(gbrain.get("runtime") or {})
    transport = dict(gbrain.get("transport") or {})
    package = dict(gbrain.get("package") or {})
    return {
        "schema": gbrain.get("schema"),
        "name": gbrain.get("name"),
        "status": gbrain.get("status"),
        "mode": gbrain.get("mode"),
        "version": package.get("version") or "",
        "selected_as_memory_provider": bool((gbrain.get("pska") or {}).get("selected_as_memory_provider")),
        "transport": {
            "preferred": transport.get("preferred") or "",
            "mcp_url_configured": bool(transport.get("mcp_url_configured")),
            "stdio_product_flow_allowed": bool(transport.get("stdio_product_flow_allowed")),
        },
        "runtime": {
            "product_flow_status": runtime.get("product_flow_status") or "",
            "participates_in_memory_search": bool(runtime.get("participates_in_memory_search")),
            "participates_in_agentic_context_brief": bool(runtime.get("participates_in_agentic_context_brief")),
            "participates_in_jarvis_briefing": bool(runtime.get("participates_in_jarvis_briefing")),
        },
    }


def _compact_memory_health(health: dict[str, Any]) -> dict[str, Any]:
    if not health:
        return {}
    return {
        "schema": health.get("schema"),
        "status": health.get("status"),
        "card_count": _as_int(health.get("card_count")),
        "issue_count": _as_int(health.get("issue_count")),
        "summary": dict(health.get("summary") or {}),
        "next_actions": _compact_next_actions(health.get("next_actions"), 5),
    }


def _compact_readiness(readiness: Any) -> dict[str, Any] | None:
    if not isinstance(readiness, dict):
        return None
    ingestion = dict(readiness.get("ingestion_status") or {})
    compact: dict[str, Any] = {
        "status": readiness.get("status"),
        "ready": bool(readiness.get("ready")),
        "message": readiness.get("message") or "",
        "dataset_ids": _limited_strings(readiness.get("dataset_ids"), 20),
        "document_ids": _limited_strings(readiness.get("document_ids"), 20),
        "ingestion_status": {
            "status": ingestion.get("status"),
            "phase": ingestion.get("phase"),
            "progress": ingestion.get("progress"),
            "message": ingestion.get("message") or "",
            "failure_code": ingestion.get("failure_code") or "",
            "next_actions": _limited_strings(ingestion.get("next_actions"), 10),
        },
    }
    blocking = readiness.get("blocking")
    if isinstance(blocking, list):
        compact["blocking"] = [str(item) for item in blocking[:10]]
    return compact


def _compact_next_actions(actions: Any, limit: int) -> list[dict[str, Any]]:
    compact_actions: list[dict[str, Any]] = []
    for action in list(actions or [])[: max(0, int(limit))]:
        item = dict(action or {})
        compact_actions.append(
            {
                "action": str(item.get("action") or ""),
                "label": str(item.get("label") or ""),
                "reason": str(item.get("reason") or ""),
                "tool": str(item.get("tool") or ""),
                "api": str(item.get("api") or ""),
                "view": str(item.get("view") or ""),
                "params": dict(item.get("params") or {}),
                "requires_input": list(item.get("requires_input") or []),
            }
        )
    return compact_actions


def _memory_card_count(cards: dict[str, Any], health: dict[str, Any]) -> int:
    count = _as_int(cards.get("count"), default=-1)
    if count >= 0:
        return count
    health_count = _as_int(health.get("card_count"), default=-1)
    if health_count >= 0:
        return health_count
    return _list_len(cards.get("cards"))


def _limited_strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value[: max(0, int(limit))]]


def _list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _kb_state(
    gateway: Any,
    *,
    page_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]], dict[str, str] | None]:
    try:
        datasets = gateway.list_datasets(page_size=page_size)
        dataset_ids = [str(dataset.get("dataset_id") or "") for dataset in datasets if dataset.get("dataset_id")]
        readiness = evaluate_kb_readiness(gateway, dataset_ids=dataset_ids) if dataset_ids else None
        dataset_readiness = [
            evaluate_kb_readiness(gateway, dataset_ids=[dataset_id])
            for dataset_id in dataset_ids
        ]
        return datasets, readiness, dataset_readiness, None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return [], None, [], {"type": exc.__class__.__name__, "message": str(exc)}


def _resumable_state(service: Any, gateway: Any, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    try:
        return list_resumable_agentic_questions(service, gateway, limit=limit), None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return [], {"type": exc.__class__.__name__, "message": str(exc)}


def _provider_jobs_state(service: Any, gateway: Any, *, dataset_page_size: int) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        jobs = build_provider_job_status(
            service,
            gateway,
            dataset_page_size=dataset_page_size,
            include_ready=False,
        )
        return jobs, None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _memory_cards_state(service: Any, memory_caps: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    list_capability = (memory_caps.get("operations") or {}).get("list") or {}
    if list_capability.get("supported") is False:
        return None, None
    try:
        return list_memory_cards(service, limit=20, status="active", audit=False), None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _memory_health_state(service: Any, memory_caps: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    list_capability = (memory_caps.get("operations") or {}).get("list") or {}
    if list_capability.get("supported") is False:
        return None, None
    try:
        return scan_memory_health(service, limit=20, audit=False), None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _next_actions(
    *,
    datasets: list[dict[str, Any]],
    readiness: dict[str, Any] | None,
    dataset_readiness: list[dict[str, Any]],
    kb_error: dict[str, str] | None,
    pending_reviews: list[dict[str, Any]],
    accepted_unapplied: list[dict[str, Any]],
    memory_candidate_quality_issues: list[dict[str, Any]],
    memory_caps: dict[str, Any],
    memory_cards: dict[str, Any] | None,
    memory_cards_error: dict[str, str] | None,
    memory_health: dict[str, Any] | None,
    memory_health_error: dict[str, str] | None,
    resumable: list[dict[str, Any]],
    resumable_error: dict[str, str] | None,
    provider_jobs: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if kb_error:
        actions.append(
            _action(
                "fix_kb_gateway",
                "Fix KB connection",
                kb_error["message"],
                view="settings",
            )
        )
    elif not datasets:
        actions.append(
            _action(
                "run_file_to_work_product_loop",
                "Upload and ask",
                "No knowledge base datasets are available; start by uploading source material through the PSKA loop.",
                api="POST /api/ingest-loop",
                tool="pska_ingest_loop",
                view="kb",
                params={"parse": True, "wait_ready": False, "proposal_kind": "writing_brief", "export_format": "markdown"},
                requires_input=["files", "dataset_name", "question"],
            )
        )
        actions.append(
            _action(
                "create_or_upload_knowledge_base",
                "Create or upload knowledge",
                "Use this for manual KB setup when the full upload-to-work-product loop is not needed.",
                api="POST /api/kb/ingest",
                tool="pska_kb_ingest_files",
                view="kb",
                requires_input=["files", "dataset_name_or_id"],
            )
        )
    elif dataset_readiness:
        ready_scopes = [item for item in dataset_readiness if item.get("ready")]
        blocked_scopes = [item for item in dataset_readiness if not item.get("ready")]
        if ready_scopes:
            ready_dataset_ids = [
                dataset_id
                for scope in ready_scopes
                for dataset_id in scope.get("dataset_ids") or []
            ]
            actions.append(
                _action(
                    "run_agentic_question",
                    "Ask over ready knowledge",
                    f"{len(ready_dataset_ids)} dataset(s) are ready for retrieval.",
                    api="POST /api/ask",
                    tool="pska_agentic_question_start",
                    view="ask",
                    params={"dataset_ids": ready_dataset_ids, "document_ids": []},
                    requires_input=["question"],
                )
            )
        for blocked in blocked_scopes:
            actions.extend(_readiness_actions(blocked))
    elif readiness and not readiness.get("ready"):
        actions.extend(_readiness_actions(readiness))
    elif readiness and readiness.get("ready"):
        actions.append(
            _action(
                "run_agentic_question",
                "Ask over ready knowledge",
                "At least one selected dataset is ready for retrieval.",
                api="POST /api/ask",
                tool="pska_agentic_question_start",
                view="ask",
                params=_scope_params(readiness),
                requires_input=["question"],
            )
        )

    ready_resumable = [item for item in resumable if item.get("can_resume")]
    if ready_resumable:
        resumable_run = ready_resumable[0]["run"]
        run_id = resumable_run["run_id"]
        is_ingest_loop = isinstance((resumable_run.get("metadata") or {}).get("ingest_loop"), dict)
        resume_path = "resume-ingest-loop" if is_ingest_loop else "resume-ask"
        resume_api = f"POST /api/workflows/{run_id}/{resume_path}"
        resume_tool = "pska_ingest_loop_resume" if is_ingest_loop else "pska_agentic_question_resume"
        actions.append(
            _action(
                "resume_blocked_ask",
                "Resume blocked upload loop" if is_ingest_loop else "Resume blocked Ask",
                f"{len(ready_resumable)} blocked Ask workflow(s) can resume.",
                api=resume_api,
                tool=resume_tool,
                view="ask",
                params={"run_id": run_id},
            )
        )
    elif resumable:
        actions.append(
            _action(
                "wait_for_resumable_ask",
                "Wait for blocked Ask",
                f"{len(resumable)} blocked Ask workflow(s) are still waiting on readiness.",
                api="GET /api/workflows/resumable-asks",
                tool="pska_agentic_question_resumable",
                view="activity",
                params={"run_id": resumable[0]["run"]["run_id"]},
            )
        )
    elif resumable_error and not kb_error:
        actions.append(
            _action(
                "inspect_resumable_ask_error",
                "Inspect blocked Ask status",
                resumable_error["message"],
                api="GET /api/workflows/resumable-asks",
                tool="pska_agentic_question_resumable",
                view="activity",
            )
        )

    supported_accepted = [
        review for review in accepted_unapplied if _review_memory_operation_supported(review, memory_caps)
    ]
    unsupported_accepted = [
        review for review in accepted_unapplied if not _review_memory_operation_supported(review, memory_caps)
    ]
    if supported_accepted:
        review_id = str(supported_accepted[0].get("review_id") or "")
        actions.append(
            _action(
                "apply_accepted_memory",
                "Apply accepted memory",
                f"{len(supported_accepted)} accepted durable review(s) can be applied.",
                api=f"POST /api/reviews/{review_id}/apply-memory" if review_id else "POST /api/reviews/{review_id}/apply-memory",
                tool="pska_memory_apply",
                view="review",
                params={"review_id": review_id} if review_id else {},
            )
        )
    if memory_candidate_quality_issues:
        issue = memory_candidate_quality_issues[0]
        review_id = str(issue.get("review_id") or "")
        actions.append(
            _action(
                "review_memory_candidate_quality",
                "Review memory candidate quality",
                f"{len(memory_candidate_quality_issues)} memory candidate(s) need quality review before apply.",
                api=f"GET /api/reviews/{review_id}" if review_id else "GET /api/memory/review-queue",
                tool="pska_review_get" if review_id else "pska_memory_review_queue",
                view="review",
                params={"review_id": review_id} if review_id else {},
            )
        )
    if unsupported_accepted:
        review = unsupported_accepted[0]
        review_id = str(review.get("review_id") or "")
        operation = _review_memory_operation(review)
        reason = _memory_capability_reason(memory_caps, operation)
        actions.append(
            _action(
                "inspect_unsupported_memory_operation",
                "Inspect unsupported memory operation",
                (
                    f"{len(unsupported_accepted)} accepted durable review(s) cannot be applied "
                    f"because memory {operation or 'operation'} is unsupported."
                    + (f" {reason}" if reason else "")
                ),
                api=f"GET /api/reviews/{review_id}" if review_id else "GET /api/reviews",
                tool="pska_review_get",
                view="review",
                params={"review_id": review_id, "operation": operation} if review_id else {"operation": operation},
            )
        )
    if pending_reviews:
        review_id = str(pending_reviews[0].get("review_id") or "")
        actions.append(
            _action(
                "review_pending_durable_knowledge",
                "Review durable knowledge",
                f"{len(pending_reviews)} review item(s) are pending.",
                api=f"GET /api/reviews/{review_id}" if review_id else "GET /api/reviews",
                tool="pska_review_get",
                view="review",
                params={"review_id": review_id} if review_id else {},
            )
        )

    due_source_audit_jobs = _due_source_audit_jobs(provider_jobs)
    if due_source_audit_jobs:
        job = due_source_audit_jobs[0]
        actions.append(
            _action(
                "activate_due_source_audit_jobs",
                "Activate due source audits",
                (
                    f"{len(due_source_audit_jobs)} scheduled source audit job(s) are due. "
                    "Ticking the scheduler only updates PSKA job metadata; it does not scan, write source files, or write memory."
                ),
                api="POST /api/sources/audit-jobs/tick",
                tool="pska_source_audit_job_tick",
                view="sources",
                params={"run_id": str(job.get("job_id") or ""), "due_at": str(job.get("due_at") or "")},
            )
        )

    source_audit_jobs = _pending_source_audit_jobs(provider_jobs)
    if source_audit_jobs:
        job = source_audit_jobs[0]
        job_id = str(job.get("job_id") or "")
        actions.append(
            _action(
                "run_source_audit_job",
                "Run source audit job",
                (
                    f"{len(source_audit_jobs)} source audit job(s) are queued. "
                    "Source audit is read-only, requires no embeddings, and never writes source files or memory directly."
                ),
                api=f"POST /api/sources/audit-jobs/{job_id}/run" if job_id else "POST /api/sources/audit-jobs/run-next",
                tool="pska_source_audit_job_run",
                view="sources",
                params={"run_id": job_id} if job_id else {},
            )
        )

    source_extraction_jobs = _pending_source_extraction_jobs(provider_jobs)
    if source_extraction_jobs:
        job = source_extraction_jobs[0]
        job_id = str(job.get("job_id") or "")
        extractor = str(job.get("extractor") or "auto")
        actions.append(
            _action(
                "run_source_extraction_job",
                "Run source extraction job",
                (
                    f"{len(source_extraction_jobs)} source extraction job(s) are queued. "
                    f"Extractor={extractor}; the job writes PSKA index metadata only, not source files or memory."
                ),
                api=f"POST /api/sources/extraction-jobs/{job_id}/run"
                if job_id
                else "POST /api/sources/extraction-jobs/run-next",
                tool="pska_source_extract_job_run",
                view="sources",
                params={"run_id": job_id} if job_id else {},
            )
        )

    digest_jobs = _pending_digest_jobs(provider_jobs)
    if digest_jobs:
        job = digest_jobs[0]
        job_id = str(job.get("job_id") or "")
        actions.append(
            _action(
                "run_digest_job",
                "Run digest job",
                (
                    f"{len(digest_jobs)} digest job(s) are queued or waiting. "
                    "Digest creates a sourced artifact and may create an exception Review; it never writes memory directly."
                ),
                api=f"POST /api/digest-jobs/{job_id}/run" if job_id else "POST /api/digest-jobs/run-next",
                tool="pska_digest_job_run",
                view="activity",
                params={"run_id": job_id} if job_id else {},
            )
        )

    if memory_cards_error:
        actions.append(
            _action(
                "inspect_memory_cards_error",
                "Inspect memory cards",
                memory_cards_error["message"],
                api="GET /api/memory/cards",
                tool="pska_memory_card_list",
                view="memory",
            )
        )
    if memory_health_error:
        actions.append(
            _action(
                "inspect_memory_health_error",
                "Inspect memory health",
                memory_health_error["message"],
                api="GET /api/memory/health",
                tool="pska_memory_health_scan",
                view="memory",
            )
        )
    elif memory_health and int(memory_health.get("issue_count") or 0) > 0:
        first = dict((memory_health.get("issues") or [{}])[0])
        first_id = str((first.get("memory_ids") or [""])[0])
        actions.append(
            _action(
                "inspect_memory_health",
                "Inspect memory health",
                (
                    f"{memory_health.get('issue_count')} memory health issue(s) need review: "
                    f"{', '.join(key for key, value in (memory_health.get('summary') or {}).items() if key != 'severity' and value)}."
                ),
                api="GET /api/memory/health",
                tool="pska_memory_health_scan",
                view="memory",
                params={"memory_id": first_id, "issue_id": str(first.get("issue_id") or "")},
            )
        )
    elif memory_cards:
        card_actions = memory_cards.get("next_actions") or []
        if card_actions:
            first = dict(card_actions[0])
            actions.append(
                _action(
                    str(first.get("action") or "inspect_memory_card_quality"),
                    str(first.get("label") or "Inspect memory card quality"),
                    "Some durable memories are missing PSKA Memory Card envelope fields.",
                    api=str(first.get("api") or "GET /api/memory/cards"),
                    tool=str(first.get("tool") or "pska_memory_card_list"),
                    view=str(first.get("view") or "memory"),
                    params=dict(first.get("params") or {}),
                )
            )

    if not actions:
        actions.append(
            _action(
                "monitor_workspace",
                "Monitor workspace",
                "No blocking workflow action is currently pending.",
                api="GET /api/workspace/status",
                tool="pska_workspace_status",
                view="home",
            )
        )
    return actions


def _pending_digest_jobs(provider_jobs: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not provider_jobs:
        return []
    jobs = provider_jobs.get("jobs") or []
    return [
        dict(job)
        for job in jobs
        if job.get("kind") == "pska_digest_job" and str(job.get("status") or "") in {"queued", "waiting"}
    ]


def _pending_source_audit_jobs(provider_jobs: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not provider_jobs:
        return []
    jobs = provider_jobs.get("jobs") or []
    return [
        dict(job)
        for job in jobs
        if job.get("kind") == "pska_source_audit_job" and str(job.get("status") or "") == "queued"
    ]


def _pending_source_extraction_jobs(provider_jobs: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not provider_jobs:
        return []
    jobs = provider_jobs.get("jobs") or []
    return [
        dict(job)
        for job in jobs
        if job.get("kind") == "pska_source_extraction_job" and str(job.get("status") or "") == "queued"
    ]


def _due_source_audit_jobs(provider_jobs: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not provider_jobs:
        return []
    jobs = provider_jobs.get("jobs") or []
    return [
        dict(job)
        for job in jobs
        if job.get("kind") == "pska_source_audit_job"
        and str(job.get("status") or "") == "waiting"
        and bool(job.get("due"))
    ]


def _review_memory_operation(review: dict[str, Any]) -> str:
    proposal = review.get("proposal") or {}
    return memory_operation_for_proposal_kind(str(proposal.get("kind") or ""))


def _review_memory_operation_supported(review: dict[str, Any], memory_caps: dict[str, Any]) -> bool:
    operation = _review_memory_operation(review)
    if not operation:
        return False
    capability = (memory_caps.get("operations") or {}).get(operation) or {}
    return capability.get("supported") is not False


def _memory_capability_reason(memory_caps: dict[str, Any], operation: str) -> str:
    capability = (memory_caps.get("operations") or {}).get(operation) or {}
    return str(capability.get("reason") or "")


def _workspace_status(
    next_actions: list[dict[str, Any]],
    readiness: dict[str, Any] | None,
    kb_error: dict[str, str] | None,
    resumable_error: dict[str, str] | None,
) -> str:
    if kb_error or resumable_error:
        return "error"
    action_names = {action["action"] for action in next_actions}
    if {
        "apply_accepted_memory",
        "inspect_unsupported_memory_operation",
        "review_memory_candidate_quality",
        "review_pending_durable_knowledge",
        "resume_blocked_ask",
    } & action_names:
        return "action_required"
    if "run_agentic_question" in action_names:
        return "ready"
    if {
        "check_dataset_access",
        "check_provider_status",
        "configure_embedding_provider",
        "inspect_failure",
        "inspect_cancellation",
        "parse_documents",
        "inspect_resumable_ask_error",
    } & action_names:
        return "action_required"
    if {"wait_for_ingestion", "wait_for_resumable_ask"} & action_names:
        return "processing"
    if {"run_file_to_work_product_loop", "create_or_upload_knowledge_base", "upload_documents"} & action_names:
        return "empty"
    return "ok"


def _readiness_actions(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    job = readiness.get("ingestion_status") or {}
    reason = str(job.get("message") or readiness.get("message") or "Selected knowledge is not ready.")
    actions = [
        _product_readiness_action(str(action))
        for action in job.get("next_actions") or ["wait_for_ingestion"]
    ]
    return [_readiness_action(action, reason, readiness) for action in _unique_actions(actions)]


def _readiness_action(action: str, reason: str, readiness: dict[str, Any]) -> dict[str, Any]:
    if action == "parse_documents":
        return _action(
            action,
            _action_label(action),
            reason,
            api="POST /api/kb/datasets/{dataset_id}/parse",
            tool="pska_kb_parse_documents",
            view="kb",
            params=_scope_params(readiness),
        )
    if action == "upload_documents":
        return _action(
            action,
            _action_label(action),
            reason,
            api="POST /api/kb/ingest",
            tool="pska_kb_ingest_files",
            view="kb",
            params=_scope_params(readiness),
            requires_input=["files"],
        )
    if action == "check_dataset_access":
        return _action(
            action,
            _action_label(action),
            reason,
            api="GET /api/kb/datasets",
            tool="pska_kb_list",
            view="settings",
            params=_scope_params(readiness),
        )
    if action == "check_provider_status":
        return _action(
            action,
            _action_label(action),
            reason,
            api="GET /api/kb/datasets/{dataset_id}/documents",
            tool="pska_kb_document_status",
            view="kb",
            params=_scope_params(readiness),
        )
    if action == "configure_embedding_provider":
        return _action(
            action,
            _action_label(action),
            reason,
            api="GET /api/runtime/diagnostics",
            tool="pska_workspace_status",
            view="settings",
            params=_scope_params(readiness),
        )
    if action == "run_agentic_question":
        return _action(
            action,
            _action_label(action),
            reason,
            api="POST /api/ask",
            tool="pska_agentic_question_start",
            view="ask",
            params=_scope_params(readiness),
            requires_input=["question"],
        )
    if action in {"inspect_failure", "inspect_cancellation"}:
        return _action(
            action,
            _action_label(action),
            reason,
            api="GET /api/kb/datasets/{dataset_id}/documents",
            tool="pska_kb_document_status",
            view="kb",
            params=_scope_params(readiness),
        )
    return _action(
        action,
        _action_label(action),
        reason,
        api="GET /api/kb/datasets/{dataset_id}/ingestion-status",
        tool="pska_kb_ingestion_status",
        view="kb",
        params=_scope_params(readiness),
    )


def _action(
    action: str,
    label: str,
    reason: str,
    *,
    api: str = "",
    tool: str = "",
    view: str = "",
    params: dict[str, Any] | None = None,
    requires_input: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": action,
        "label": label,
        "reason": reason,
    }
    if api:
        payload["api"] = api
    if tool:
        payload["tool"] = tool
    if view:
        payload["view"] = view
    if params:
        payload["params"] = params
    if requires_input:
        payload["requires_input"] = requires_input
    return payload


def _scope_params(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_ids": [str(item) for item in readiness.get("dataset_ids") or []],
        "document_ids": [str(item) for item in readiness.get("document_ids") or []],
    }


def _dataset_ids_for_scopes(scopes: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        for item in scope.get("dataset_ids") or []:
            dataset_id = str(item or "").strip()
            if dataset_id and dataset_id not in seen:
                seen.add(dataset_id)
                result.append(dataset_id)
    return result


def _product_readiness_action(action: str) -> str:
    mapping = {
        "configure_embedding_provider": "configure_embedding_provider",
        "inspect_cancelled_documents": "inspect_cancellation",
        "inspect_failed_documents": "inspect_failure",
        "run_ask": "run_agentic_question",
        "start_parse": "parse_documents",
    }
    return mapping.get(action, action)


def _unique_actions(actions: list[str]) -> list[str]:
    result: list[str] = []
    for action in actions:
        if action and action not in result:
            result.append(action)
    return result


def _action_label(action: str) -> str:
    labels = {
        "check_dataset_access": "Check dataset access",
        "check_provider_status": "Check provider status",
        "configure_embedding_provider": "Configure embedding provider",
        "inspect_cancellation": "Inspect cancellation",
        "inspect_failure": "Inspect failure",
        "parse_documents": "Parse documents",
        "run_agentic_question": "Ask over ready knowledge",
        "upload_documents": "Upload documents",
        "wait_for_ingestion": "Wait for ingestion",
    }
    return labels.get(action, action.replace("_", " ").title())


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
