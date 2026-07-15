from __future__ import annotations

import os
from typing import Any

from pska_essential.agentic_loop import list_resumable_agentic_questions
from pska_essential.capabilities import memory_capabilities, memory_operation_for_proposal_kind
from pska_essential.governance import DURABLE_PROPOSAL_KINDS, build_workspace_policy_from_env
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
    ]
    workflows = service.store.list_workflows(limit=workflow_limit)
    resumable, resumable_error = _resumable_state(service, gateway, limit=workflow_limit)
    memory_caps = memory_capabilities(service.memory)
    next_actions = _next_actions(
        datasets=datasets,
        readiness=readiness,
        dataset_readiness=dataset_readiness,
        kb_error=kb_error,
        pending_reviews=pending_reviews,
        accepted_unapplied=accepted_unapplied,
        memory_caps=memory_caps,
        resumable=resumable,
        resumable_error=resumable_error,
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
        "kb": {
            "status": "error" if kb_error else (readiness or {}).get("status", "empty"),
            "dataset_count": len(datasets),
            "datasets": datasets,
            "readiness": readiness,
            "dataset_readiness": dataset_readiness,
            "error": kb_error,
        },
        "reviews": {
            "pending_count": len(pending_reviews),
            "accepted_unapplied_count": len(accepted_unapplied),
            "pending": pending_reviews[:10],
            "accepted_unapplied": accepted_unapplied[:10],
        },
        "workflows": {
            "recent_count": len(workflows),
            "last_run": workflows[0].run_id if workflows else "",
            "resumable_ask_count": len(resumable),
            "resumable_asks": resumable[:10],
            "resumable_error": resumable_error,
        },
        "next_actions": next_actions,
    }


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


def _next_actions(
    *,
    datasets: list[dict[str, Any]],
    readiness: dict[str, Any] | None,
    dataset_readiness: list[dict[str, Any]],
    kb_error: dict[str, str] | None,
    pending_reviews: list[dict[str, Any]],
    accepted_unapplied: list[dict[str, Any]],
    memory_caps: dict[str, Any],
    resumable: list[dict[str, Any]],
    resumable_error: dict[str, str] | None,
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
                "create_or_upload_knowledge_base",
                "Create or upload knowledge",
                "No knowledge base datasets are available.",
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
    if {"create_or_upload_knowledge_base", "upload_documents"} & action_names:
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
