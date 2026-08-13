from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import WorkflowRun, to_jsonable, utc_now_iso
from pska_essential.workflow import WorkflowService


SOURCE_EXTRACTION_JOB_KIND = "source_extraction_job"
SOURCE_EXTRACTION_JOB_STATUSES = {"queued", "running", "completed", "failed"}


def enqueue_source_extraction_job(
    service: WorkflowService,
    *,
    root_id: str,
    label: str = "",
    priority: int = 0,
    max_files: int = 1000,
    max_bytes: int = 1_000_000,
    extractor: str = "auto",
) -> dict[str, Any]:
    selected_root_id = str(root_id or "").strip()
    if not selected_root_id:
        raise ValueError("root_id is required")
    if max_files < 1:
        raise ValueError("max_files must be greater than 0")
    if max_bytes < 1:
        raise ValueError("max_bytes must be greater than 0")
    root = service.source_root_list()
    root_label = _root_label(root, selected_root_id)
    request = {
        "root_id": selected_root_id,
        "label": label.strip() or f"Source extraction: {root_label or selected_root_id}",
        "max_files": int(max_files),
        "max_bytes": int(max_bytes),
        "extractor": str(extractor or "auto").strip() or "auto",
    }
    run = service.start(
        f"source extraction job: {request['label']}",
        {
            "operation": "source_extraction",
            "source_root_id": selected_root_id,
            "extractor": request["extractor"],
        },
    )
    run.status = "queued"
    run.metadata["source_extraction_job"] = {
        "kind": SOURCE_EXTRACTION_JOB_KIND,
        "status": "queued",
        "priority": int(priority),
        "request": request,
        "attempt_count": 0,
        "created_at": run.created_at,
        "updated_at": utc_now_iso(),
        "last_status": "",
        "last_message": "",
        "summary": {},
    }
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    service.store.add_audit_event(
        audit_event(
            "source.extraction_job.enqueue",
            "workflow",
            run.run_id,
            status="queued",
            priority=int(priority),
            request=request,
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    return {
        "status": "queued",
        "job": to_jsonable(run),
        "source_extraction_job": to_jsonable(run.metadata["source_extraction_job"]),
        "next_actions": _source_extraction_job_actions(run.run_id, status="queued"),
    }


def list_source_extraction_jobs(
    service: WorkflowService,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    selected_status = _optional_status(status)
    rows: list[dict[str, Any]] = []
    scan_limit = max(int(limit) * 10, 100)
    for run in service.store.list_workflows(limit=scan_limit):
        source_extraction_job = _source_extraction_job_metadata(run)
        if not source_extraction_job:
            continue
        if selected_status and source_extraction_job["status"] != selected_status:
            continue
        rows.append({"job": to_jsonable(run), "source_extraction_job": to_jsonable(source_extraction_job)})
    rows.sort(key=lambda row: _source_extraction_job_sort_key(row["job"], row["source_extraction_job"]))
    return rows[: max(0, int(limit))]


def run_source_extraction_job(
    service: WorkflowService,
    *,
    run_id: str = "",
) -> dict[str, Any]:
    job = _selected_job(service, run_id=run_id)
    if job is None:
        return {
            "status": "empty",
            "job": None,
            "source_extraction_job": None,
            "scan": None,
            "message": "No queued source extraction job is available.",
        }
    source_extraction_job = _source_extraction_job_metadata(job)
    if not source_extraction_job:
        raise ValueError(f"workflow is not a source extraction job: {job.run_id}")
    if source_extraction_job["status"] == "running":
        raise ValueError(f"source extraction job is already running: {job.run_id}")
    if source_extraction_job["status"] == "completed":
        return {
            "status": "completed",
            "job": to_jsonable(job),
            "source_extraction_job": to_jsonable(source_extraction_job),
            "scan": None,
            "message": "Source extraction job is already completed.",
        }

    request = dict(source_extraction_job.get("request") or {})
    running = _update_source_extraction_job(service, job, status="running")
    try:
        scan = service.source_scan(
            str(request.get("root_id") or ""),
            max_files=int(request.get("max_files") or 1000),
            max_bytes=int(request.get("max_bytes") or 1_000_000),
            extractor=str(request.get("extractor") or "auto"),
        )
    except Exception as exc:
        failed = _update_source_extraction_job(
            service,
            running,
            status="failed",
            last_status="error",
            last_message=str(exc),
            error_type=exc.__class__.__name__,
        )
        service.store.add_audit_event(
            audit_event(
                "source.extraction_job.run",
                "workflow",
                failed.run_id,
                status="failed",
                error=str(exc),
                error_type=exc.__class__.__name__,
                writes_source_files=False,
                writes_memory_directly=False,
                embedding_required=False,
            )
        )
        raise

    summary = _scan_job_summary(scan)
    completed = _update_source_extraction_job(
        service,
        running,
        status="completed",
        last_status="pska.source_scan.v1",
        last_message=_scan_summary_message(summary),
        summary=summary,
    )
    service.store.add_audit_event(
        audit_event(
            "source.extraction_job.run",
            "workflow",
            completed.run_id,
            status="completed",
            summary=summary,
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    return {
        "status": "completed",
        "job": to_jsonable(completed),
        "source_extraction_job": to_jsonable(completed.metadata["source_extraction_job"]),
        "scan": scan,
        "message": "Source extraction job completed.",
    }


def _update_source_extraction_job(
    service: WorkflowService,
    run: WorkflowRun,
    *,
    status: str,
    last_status: str = "",
    last_message: str = "",
    error_type: str = "",
    summary: dict[str, Any] | None = None,
) -> WorkflowRun:
    source_extraction_job = dict(run.metadata.get("source_extraction_job") or {})
    if not source_extraction_job:
        raise ValueError(f"workflow is not a source extraction job: {run.run_id}")
    if status not in SOURCE_EXTRACTION_JOB_STATUSES:
        raise ValueError(
            f"source extraction job status must be one of: {', '.join(sorted(SOURCE_EXTRACTION_JOB_STATUSES))}"
        )
    if status == "running":
        source_extraction_job["attempt_count"] = int(source_extraction_job.get("attempt_count") or 0) + 1
        source_extraction_job["last_started_at"] = utc_now_iso()
    source_extraction_job["status"] = status
    source_extraction_job["updated_at"] = utc_now_iso()
    if last_status:
        source_extraction_job["last_status"] = last_status
    if last_message:
        source_extraction_job["last_message"] = last_message
    if error_type:
        source_extraction_job["error_type"] = error_type
    if summary is not None:
        source_extraction_job["summary"] = to_jsonable(summary)
    run.status = status
    run.metadata["source_extraction_job"] = source_extraction_job
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    return run


def _selected_job(service: WorkflowService, *, run_id: str) -> WorkflowRun | None:
    selected_run_id = str(run_id or "").strip()
    if selected_run_id:
        return service.state(selected_run_id)
    queued = list_source_extraction_jobs(service, status="queued", limit=1)
    if queued:
        return WorkflowRun.from_dict(queued[0]["job"])
    return None


def _source_extraction_job_metadata(run: WorkflowRun) -> dict[str, Any]:
    source_extraction_job = run.metadata.get("source_extraction_job")
    if not isinstance(source_extraction_job, dict):
        return {}
    if source_extraction_job.get("kind") != SOURCE_EXTRACTION_JOB_KIND:
        return {}
    return dict(source_extraction_job)


def _optional_status(status: str | None) -> str:
    selected = str(status or "").strip().lower()
    if not selected:
        return ""
    if selected not in SOURCE_EXTRACTION_JOB_STATUSES:
        raise ValueError(
            f"source extraction job status must be one of: {', '.join(sorted(SOURCE_EXTRACTION_JOB_STATUSES))}"
        )
    return selected


def _source_extraction_job_sort_key(job: dict[str, Any], source_extraction_job: dict[str, Any]) -> tuple[int, str]:
    return (-int(source_extraction_job.get("priority") or 0), str(job.get("updated_at") or ""))


def _source_extraction_job_actions(run_id: str, *, status: str) -> list[dict[str, Any]]:
    if status == "queued":
        return [
            {
                "action": "run_source_extraction_job",
                "label": "Run Source Extraction",
                "api": f"POST /api/sources/extraction-jobs/{run_id}/run",
                "tool": "pska_source_extract_job_run",
                "view": "sources",
                "params": {"run_id": run_id},
            }
        ]
    if status == "failed":
        return [
            {
                "action": "inspect_failure",
                "label": "Inspect Source Extraction Failure",
                "api": f"GET /api/sources/extraction-jobs?status=failed",
                "tool": "pska_source_extract_job_list",
                "view": "sources",
                "params": {"run_id": run_id},
            }
        ]
    return []


def _scan_job_summary(scan: dict[str, Any]) -> dict[str, Any]:
    counts = dict(scan.get("counts") or {})
    extraction = dict(scan.get("extraction") or {})
    return {
        "root_id": str((scan.get("root") or {}).get("root_id") or ""),
        "active_object_count": int(scan.get("active_object_count") or 0),
        "extractor": str(extraction.get("extractor") or ""),
        "indexed": int(counts.get("indexed") or 0),
        "metadata_only": int(counts.get("metadata_only") or 0),
        "unsupported": int(counts.get("unsupported") or 0),
        "too_large": int(counts.get("too_large") or 0),
        "errors": int(counts.get("errors") or 0),
    }


def _scan_summary_message(summary: dict[str, Any]) -> str:
    return (
        f"{summary['indexed']} indexed, {summary['metadata_only']} metadata-only, "
        f"{summary['unsupported']} unsupported, {summary['errors']} error(s)."
    )


def _root_label(roots: list[dict[str, Any]], root_id: str) -> str:
    for root in roots:
        if str(root.get("root_id") or "") == root_id:
            return str(root.get("label") or root.get("absolute_path") or "")
    return ""
