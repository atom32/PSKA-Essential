from __future__ import annotations

import os
from typing import Any

from pska_essential.agentic_loop import list_resumable_agentic_questions
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

    datasets, readiness, kb_error = _kb_state(gateway, page_size=dataset_page_size)
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
    next_actions = _next_actions(
        datasets=datasets,
        readiness=readiness,
        kb_error=kb_error,
        pending_reviews=pending_reviews,
        accepted_unapplied=accepted_unapplied,
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
        "kb": {
            "status": "error" if kb_error else (readiness or {}).get("status", "empty"),
            "dataset_count": len(datasets),
            "datasets": datasets,
            "readiness": readiness,
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


def _kb_state(gateway: Any, *, page_size: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, str] | None]:
    try:
        datasets = gateway.list_datasets(page_size=page_size)
        dataset_ids = [str(dataset.get("dataset_id") or "") for dataset in datasets if dataset.get("dataset_id")]
        readiness = evaluate_kb_readiness(gateway, dataset_ids=dataset_ids) if dataset_ids else None
        return datasets, readiness, None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return [], None, {"type": exc.__class__.__name__, "message": str(exc)}


def _resumable_state(service: Any, gateway: Any, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    try:
        return list_resumable_agentic_questions(service, gateway, limit=limit), None
    except Exception as exc:  # noqa: BLE001 - status must surface explicit backend errors.
        return [], {"type": exc.__class__.__name__, "message": str(exc)}


def _next_actions(
    *,
    datasets: list[dict[str, Any]],
    readiness: dict[str, Any] | None,
    kb_error: dict[str, str] | None,
    pending_reviews: list[dict[str, Any]],
    accepted_unapplied: list[dict[str, Any]],
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
    elif readiness and not readiness.get("ready"):
        job = readiness.get("ingestion_status") or {}
        for action in job.get("next_actions") or ["wait_for_ingestion"]:
            actions.append(
                _readiness_action(
                    str(action),
                    str(job.get("message") or readiness.get("message") or "Selected knowledge is not ready."),
                    readiness,
                )
            )
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
        actions.append(
            _action(
                "resume_blocked_ask",
                "Resume blocked Ask",
                f"{len(ready_resumable)} blocked Ask workflow(s) can resume.",
                api=f"POST /api/workflows/{ready_resumable[0]['run']['run_id']}/resume-ask",
                tool="pska_agentic_question_resume",
                view="ask",
                params={"run_id": ready_resumable[0]["run"]["run_id"]},
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

    if accepted_unapplied:
        review_id = str(accepted_unapplied[0].get("review_id") or "")
        actions.append(
            _action(
                "apply_accepted_memory",
                "Apply accepted memory",
                f"{len(accepted_unapplied)} accepted durable review(s) have not been applied.",
                api=f"POST /api/reviews/{review_id}/apply-memory" if review_id else "POST /api/reviews/{review_id}/apply-memory",
                tool="pska_memory_apply",
                view="review",
                params={"review_id": review_id} if review_id else {},
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


def _workspace_status(
    next_actions: list[dict[str, Any]],
    readiness: dict[str, Any] | None,
    kb_error: dict[str, str] | None,
    resumable_error: dict[str, str] | None,
) -> str:
    if kb_error or resumable_error:
        return "error"
    action_names = {action["action"] for action in next_actions}
    if {"apply_accepted_memory", "review_pending_durable_knowledge", "resume_blocked_ask"} & action_names:
        return "action_required"
    if {"inspect_failure", "inspect_cancellation", "parse_documents", "inspect_resumable_ask_error"} & action_names:
        return "action_required"
    if {"wait_for_ingestion", "wait_for_resumable_ask"} & action_names:
        return "processing"
    if readiness and readiness.get("ready"):
        return "ready"
    if "create_or_upload_knowledge_base" in action_names:
        return "empty"
    return "ok"


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


def _action_label(action: str) -> str:
    labels = {
        "inspect_cancellation": "Inspect cancellation",
        "inspect_failure": "Inspect failure",
        "parse_documents": "Parse documents",
        "run_ask": "Ask over ready knowledge",
        "wait_for_ingestion": "Wait for ingestion",
    }
    return labels.get(action, action.replace("_", " ").title())


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
