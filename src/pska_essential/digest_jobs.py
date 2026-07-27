from __future__ import annotations

from typing import Any

from pska_essential.agentic_loop import run_digest_scope
from pska_essential.audit import audit_event
from pska_essential.contracts import WorkflowRun, to_jsonable, utc_now_iso
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.workflow import WorkflowService


DIGEST_JOB_KIND = "digest_job"
DIGEST_JOB_STATUSES = {"queued", "waiting", "running", "completed", "failed"}


def enqueue_digest_job(
    service: WorkflowService,
    *,
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
) -> dict[str, Any]:
    selected_dataset_ids = _normalized_ids(dataset_ids)
    selected_document_ids = _normalized_ids(document_ids or [])
    if not selected_dataset_ids:
        raise ValueError("dataset_ids is required")
    if not question.strip():
        raise ValueError("question is required")
    if limit < 1:
        raise ValueError("limit must be greater than 0")
    if source_inspection_limit < 0:
        raise ValueError("source_inspection_limit must be greater than or equal to 0")

    request = {
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "question": question.strip(),
        "limit": int(limit),
        "use_kg": bool(use_kg),
        "max_iterations": int(max_iterations),
        "min_context_packets": int(min_context_packets),
        "retrieval_queries": _normalized_ids(retrieval_queries or []),
        "source_inspection_limit": int(source_inspection_limit),
        "create_memory_review": bool(create_memory_review),
        "memory_intent": memory_intent.strip(),
    }
    run = service.start(
        f"digest job: {request['question']}",
        {
            "dataset_ids": selected_dataset_ids,
            "document_ids": selected_document_ids,
            "use_kg": bool(use_kg),
        },
    )
    run.status = "queued"
    run.metadata["digest_job"] = {
        "kind": DIGEST_JOB_KIND,
        "status": "queued",
        "priority": int(priority),
        "request": request,
        "attempt_count": 0,
        "created_at": run.created_at,
        "updated_at": utc_now_iso(),
        "result_run_id": "",
        "last_status": "",
        "last_message": "",
    }
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    service.store.add_audit_event(
        audit_event(
            "digest.job.enqueue",
            "workflow",
            run.run_id,
            priority=int(priority),
            request=request,
        )
    )
    return {
        "status": "queued",
        "job": to_jsonable(run),
        "digest_job": to_jsonable(run.metadata["digest_job"]),
        "next_actions": [_digest_job_run_action(run.run_id)],
    }


def list_digest_jobs(
    service: WorkflowService,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    selected_status = _optional_status(status)
    rows: list[dict[str, Any]] = []
    scan_limit = max(int(limit) * 10, 100)
    for run in service.store.list_workflows(limit=scan_limit):
        digest_job = _digest_job_metadata(run)
        if not digest_job:
            continue
        if selected_status and digest_job["status"] != selected_status:
            continue
        rows.append({"job": to_jsonable(run), "digest_job": to_jsonable(digest_job)})
    rows.sort(key=lambda row: _digest_job_sort_key(row["job"], row["digest_job"]))
    return rows[: max(0, int(limit))]


def run_digest_job(
    service: WorkflowService,
    gateway: Any,
    *,
    run_id: str = "",
) -> dict[str, Any]:
    job = _selected_job(service, run_id=run_id)
    if job is None:
        return {
            "status": "empty",
            "job": None,
            "digest_job": None,
            "digest_result": None,
            "message": "No queued or waiting digest job is available.",
        }
    digest_job = _digest_job_metadata(job)
    if not digest_job:
        raise ValueError(f"workflow is not a digest job: {job.run_id}")
    if digest_job["status"] in {"running"}:
        raise ValueError(f"digest job is already running: {job.run_id}")
    if digest_job["status"] in {"completed"}:
        return {
            "status": "completed",
            "job": to_jsonable(job),
            "digest_job": to_jsonable(digest_job),
            "digest_result": None,
            "message": "Digest job is already completed.",
        }

    request = dict(digest_job.get("request") or {})
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=_normalized_ids(request.get("dataset_ids") or []),
        document_ids=_normalized_ids(request.get("document_ids") or []),
    )
    if not readiness.get("ready"):
        updated = _update_digest_job(
            service,
            job,
            status="waiting",
            readiness=readiness,
            last_status="not_ready",
            last_message=str(readiness.get("message") or "Selected knowledge scope is not ready for digest."),
        )
        service.store.add_audit_event(
            audit_event(
                "digest.job.waiting",
                "workflow",
                job.run_id,
                readiness=readiness,
            )
        )
        return {
            "status": "waiting",
            "job": to_jsonable(updated),
            "digest_job": to_jsonable(updated.metadata["digest_job"]),
            "digest_result": None,
            "readiness": readiness,
            "message": str(readiness.get("message") or "Selected knowledge scope is not ready for digest."),
        }

    running = _update_digest_job(service, job, status="running", readiness=readiness)
    try:
        result = run_digest_scope(
            service,
            gateway,
            dataset_ids=_normalized_ids(request.get("dataset_ids") or []),
            document_ids=_normalized_ids(request.get("document_ids") or []),
            question=str(request.get("question") or "Digest the selected ready knowledge."),
            limit=int(request.get("limit") or 5),
            use_kg=bool(request.get("use_kg", False)),
            max_iterations=int(request.get("max_iterations") or 2),
            min_context_packets=int(request.get("min_context_packets") or 1),
            retrieval_queries=_normalized_ids(request.get("retrieval_queries") or []),
            source_inspection_limit=int(request.get("source_inspection_limit") or 3),
            create_memory_review=bool(request.get("create_memory_review", False)),
            memory_intent=str(request.get("memory_intent") or ""),
        )
    except Exception as exc:
        failed = _update_digest_job(
            service,
            running,
            status="failed",
            readiness=readiness,
            last_status="error",
            last_message=str(exc),
            error_type=exc.__class__.__name__,
        )
        service.store.add_audit_event(
            audit_event(
                "digest.job.run",
                "workflow",
                failed.run_id,
                status="failed",
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
        )
        raise

    result_run_id = str((result.get("run") or {}).get("run_id") or "")
    status = "completed" if result.get("status") == "ready" else "failed"
    completed = _update_digest_job(
        service,
        running,
        status=status,
        readiness=readiness,
        result_run_id=result_run_id,
        last_status=str(result.get("status") or ""),
        last_message=str(result.get("message") or ""),
    )
    service.store.add_audit_event(
        audit_event(
            "digest.job.run",
            "workflow",
            completed.run_id,
            status=status,
            result_status=str(result.get("status") or ""),
            result_run_id=result_run_id,
            create_memory_review=bool(request.get("create_memory_review", False)),
        )
    )
    return {
        "status": status,
        "job": to_jsonable(completed),
        "digest_job": to_jsonable(completed.metadata["digest_job"]),
        "digest_result": result,
        "readiness": readiness,
        "message": "Digest job completed." if status == "completed" else "Digest job did not produce a ready digest.",
    }


def _update_digest_job(
    service: WorkflowService,
    run: WorkflowRun,
    *,
    status: str,
    readiness: dict[str, Any] | None = None,
    result_run_id: str = "",
    last_status: str = "",
    last_message: str = "",
    error_type: str = "",
) -> WorkflowRun:
    digest_job = dict(run.metadata.get("digest_job") or {})
    if not digest_job:
        raise ValueError(f"workflow is not a digest job: {run.run_id}")
    if status not in DIGEST_JOB_STATUSES:
        raise ValueError(f"digest job status must be one of: {', '.join(sorted(DIGEST_JOB_STATUSES))}")
    if status == "running":
        digest_job["attempt_count"] = int(digest_job.get("attempt_count") or 0) + 1
        digest_job["last_started_at"] = utc_now_iso()
    digest_job["status"] = status
    digest_job["updated_at"] = utc_now_iso()
    if readiness is not None:
        digest_job["readiness"] = to_jsonable(readiness)
    if result_run_id:
        digest_job["result_run_id"] = result_run_id
    if last_status:
        digest_job["last_status"] = last_status
    if last_message:
        digest_job["last_message"] = last_message
    if error_type:
        digest_job["error_type"] = error_type
    run.status = status
    run.metadata["digest_job"] = digest_job
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    return run


def _selected_job(service: WorkflowService, *, run_id: str) -> WorkflowRun | None:
    selected_run_id = str(run_id or "").strip()
    if selected_run_id:
        return service.state(selected_run_id)
    queued = list_digest_jobs(service, status="queued", limit=1)
    if queued:
        return WorkflowRun.from_dict(queued[0]["job"])
    waiting = list_digest_jobs(service, status="waiting", limit=1)
    if waiting:
        return WorkflowRun.from_dict(waiting[0]["job"])
    return None


def _digest_job_metadata(run: WorkflowRun) -> dict[str, Any]:
    digest_job = run.metadata.get("digest_job")
    if not isinstance(digest_job, dict):
        return {}
    if digest_job.get("kind") != DIGEST_JOB_KIND:
        return {}
    return dict(digest_job)


def _optional_status(status: str | None) -> str:
    selected = str(status or "").strip().lower()
    if not selected:
        return ""
    if selected not in DIGEST_JOB_STATUSES:
        raise ValueError(f"digest job status must be one of: {', '.join(sorted(DIGEST_JOB_STATUSES))}")
    return selected


def _digest_job_sort_key(job: dict[str, Any], digest_job: dict[str, Any]) -> tuple[int, str]:
    return (-int(digest_job.get("priority") or 0), str(job.get("updated_at") or ""))


def _digest_job_run_action(run_id: str) -> dict[str, Any]:
    return {
        "action": "run_digest_job",
        "label": "Run Digest",
        "api": f"POST /api/digest-jobs/{run_id}/run",
        "tool": "pska_digest_job_run",
        "params": {"run_id": run_id},
    }


def _normalized_ids(values: list[str] | list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
