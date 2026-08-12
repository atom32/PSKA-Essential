from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import WorkflowRun, to_jsonable, utc_now_iso
from pska_essential.workflow import WorkflowService


SOURCE_AUDIT_JOB_KIND = "source_audit_job"
SOURCE_AUDIT_JOB_STATUSES = {"queued", "waiting", "running", "completed", "failed"}
SOURCE_AUDIT_JOB_CADENCES = {"manual", "once", "hourly", "daily", "weekly", "monthly"}


def enqueue_source_audit_job(
    service: WorkflowService,
    *,
    scope: dict[str, Any] | None = None,
    label: str = "",
    priority: int = 0,
    limit: int = 20,
    cadence: str = "manual",
    due_at: str = "",
    schedule_mode: str = "ad_hoc",
    series_id: str = "",
    previous_run_id: str = "",
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be greater than 0")
    selected_cadence = _normalize_cadence(cadence)
    selected_schedule_mode = _normalize_schedule_mode(schedule_mode)
    selected_due_at = _normalize_due_at(due_at)
    status = "waiting" if selected_due_at else "queued"
    if selected_schedule_mode == "scheduled":
        status = "waiting"
    request = {
        "scope": dict(scope or {}),
        "label": label.strip() or "Personal source audit",
        "limit": int(limit),
        "cadence": selected_cadence,
        "due_at": selected_due_at,
    }
    run = service.start(
        f"source audit job: {request['label']}",
        {
            "operation": "source_audit",
            "source_scope": request["scope"],
        },
    )
    run.status = status
    run.metadata["source_audit_job"] = {
        "kind": SOURCE_AUDIT_JOB_KIND,
        "status": status,
        "priority": int(priority),
        "request": request,
        "schedule_mode": selected_schedule_mode,
        "cadence": selected_cadence,
        "due_at": selected_due_at,
        "series_id": series_id.strip() or (run.run_id if selected_schedule_mode == "scheduled" else ""),
        "previous_run_id": previous_run_id.strip(),
        "next_run_id": "",
        "attempt_count": 0,
        "created_at": run.created_at,
        "updated_at": utc_now_iso(),
        "result_audit_id": "",
        "last_status": "",
        "last_message": "",
    }
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    service.store.add_audit_event(
        audit_event(
            "source.audit_job.enqueue",
            "workflow",
            run.run_id,
            status=status,
            priority=int(priority),
            request=request,
            schedule_mode=selected_schedule_mode,
            due_at=selected_due_at,
            series_id=run.metadata["source_audit_job"].get("series_id") or "",
            previous_run_id=previous_run_id.strip(),
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    return {
        "status": status,
        "job": to_jsonable(run),
        "source_audit_job": to_jsonable(run.metadata["source_audit_job"]),
        "next_actions": _source_audit_job_actions(run.run_id, status=status, due_at=selected_due_at),
    }


def schedule_source_audit_job(
    service: WorkflowService,
    *,
    scope: dict[str, Any] | None = None,
    label: str = "",
    priority: int = 0,
    limit: int = 20,
    cadence: str = "daily",
    due_at: str = "",
    now: str = "",
) -> dict[str, Any]:
    selected_cadence = _normalize_cadence(cadence, default="daily")
    selected_due_at = _normalize_due_at(due_at)
    if not selected_due_at:
        now_dt = _now_datetime(now)
        selected_due_at = _iso_datetime(_advance_datetime(now_dt, selected_cadence))
    return enqueue_source_audit_job(
        service,
        scope=scope or {},
        label=label,
        priority=priority,
        limit=limit,
        cadence=selected_cadence,
        due_at=selected_due_at,
        schedule_mode="scheduled",
    )


def list_source_audit_jobs(
    service: WorkflowService,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    selected_status = _optional_status(status)
    rows: list[dict[str, Any]] = []
    scan_limit = max(int(limit) * 10, 100)
    for run in service.store.list_workflows(limit=scan_limit):
        source_audit_job = _source_audit_job_metadata(run)
        if not source_audit_job:
            continue
        if selected_status and source_audit_job["status"] != selected_status:
            continue
        rows.append({"job": to_jsonable(run), "source_audit_job": to_jsonable(source_audit_job)})
    rows.sort(key=lambda row: _source_audit_job_sort_key(row["job"], row["source_audit_job"]))
    return rows[: max(0, int(limit))]


def activate_due_source_audit_jobs(
    service: WorkflowService,
    *,
    now: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be greater than 0")
    now_dt = _now_datetime(now)
    activated: list[dict[str, Any]] = []
    checked_count = 0
    waiting = list_source_audit_jobs(service, status="waiting", limit=max(limit * 10, 100))
    for item in waiting:
        checked_count += 1
        if len(activated) >= limit:
            break
        source_audit_job = dict(item.get("source_audit_job") or {})
        due_at = str(source_audit_job.get("due_at") or (source_audit_job.get("request") or {}).get("due_at") or "")
        if not _is_due(due_at, now_dt):
            continue
        run = WorkflowRun.from_dict(item["job"])
        updated = _update_source_audit_job(
            service,
            run,
            status="queued",
            last_status="due",
            last_message=f"Source audit job is due at {due_at or _iso_datetime(now_dt)}.",
        )
        service.store.add_audit_event(
            audit_event(
                "source.audit_job.due",
                "workflow",
                updated.run_id,
                due_at=due_at,
                now=_iso_datetime(now_dt),
                schedule_mode=str(source_audit_job.get("schedule_mode") or ""),
                cadence=str(source_audit_job.get("cadence") or (source_audit_job.get("request") or {}).get("cadence") or ""),
                writes_source_files=False,
                writes_memory_directly=False,
                embedding_required=False,
            )
        )
        activated.append(
            {
                "job": to_jsonable(updated),
                "source_audit_job": to_jsonable(updated.metadata["source_audit_job"]),
                "next_actions": _source_audit_job_actions(updated.run_id, status="queued", due_at=due_at),
            }
        )
    return {
        "status": "activated" if activated else "idle",
        "now": _iso_datetime(now_dt),
        "checked_count": checked_count,
        "activated_count": len(activated),
        "activated_jobs": activated,
        "next_due_at": _next_due_at(waiting, now_dt=now_dt),
    }


def run_source_audit_job(
    service: WorkflowService,
    *,
    run_id: str = "",
) -> dict[str, Any]:
    job = _selected_job(service, run_id=run_id)
    if job is None:
        return {
            "status": "empty",
            "job": None,
            "source_audit_job": None,
            "source_audit": None,
            "message": "No queued source audit job is available.",
        }
    source_audit_job = _source_audit_job_metadata(job)
    if not source_audit_job:
        raise ValueError(f"workflow is not a source audit job: {job.run_id}")
    if source_audit_job["status"] == "running":
        raise ValueError(f"source audit job is already running: {job.run_id}")
    if source_audit_job["status"] == "completed":
        return {
            "status": "completed",
            "job": to_jsonable(job),
            "source_audit_job": to_jsonable(source_audit_job),
            "source_audit": None,
            "message": "Source audit job is already completed.",
        }

    request = dict(source_audit_job.get("request") or {})
    running = _update_source_audit_job(service, job, status="running")
    try:
        audit = service.source_audit_run(
            dict(request.get("scope") or {}),
            limit=int(request.get("limit") or 20),
        )
    except Exception as exc:
        failed = _update_source_audit_job(
            service,
            running,
            status="failed",
            last_status="error",
            last_message=str(exc),
            error_type=exc.__class__.__name__,
        )
        service.store.add_audit_event(
            audit_event(
                "source.audit_job.run",
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

    completed = _update_source_audit_job(
        service,
        running,
        status="completed",
        result_audit_id=str(audit.get("audit_id") or ""),
        last_status=str(audit.get("schema") or "pska.source_audit.v1"),
        last_message=_audit_summary_message(audit),
        summary=_audit_job_summary(audit),
    )
    service.store.add_audit_event(
        audit_event(
            "source.audit_job.run",
            "workflow",
            completed.run_id,
            status="completed",
            result_audit_id=str(audit.get("audit_id") or ""),
            summary=_audit_job_summary(audit),
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    next_job = _schedule_next_recurring_source_audit_job(service, completed)
    if next_job:
        completed = service.state(completed.run_id)
    return {
        "status": "completed",
        "job": to_jsonable(completed),
        "source_audit_job": to_jsonable(completed.metadata["source_audit_job"]),
        "source_audit": audit,
        "next_job": next_job,
        "message": "Source audit job completed.",
    }


def _update_source_audit_job(
    service: WorkflowService,
    run: WorkflowRun,
    *,
    status: str,
    result_audit_id: str = "",
    last_status: str = "",
    last_message: str = "",
    error_type: str = "",
    summary: dict[str, Any] | None = None,
) -> WorkflowRun:
    source_audit_job = dict(run.metadata.get("source_audit_job") or {})
    if not source_audit_job:
        raise ValueError(f"workflow is not a source audit job: {run.run_id}")
    if status not in SOURCE_AUDIT_JOB_STATUSES:
        raise ValueError(f"source audit job status must be one of: {', '.join(sorted(SOURCE_AUDIT_JOB_STATUSES))}")
    if status == "running":
        source_audit_job["attempt_count"] = int(source_audit_job.get("attempt_count") or 0) + 1
        source_audit_job["last_started_at"] = utc_now_iso()
    if status == "queued":
        source_audit_job["last_queued_at"] = utc_now_iso()
    source_audit_job["status"] = status
    source_audit_job["updated_at"] = utc_now_iso()
    if result_audit_id:
        source_audit_job["result_audit_id"] = result_audit_id
    if last_status:
        source_audit_job["last_status"] = last_status
    if last_message:
        source_audit_job["last_message"] = last_message
    if error_type:
        source_audit_job["error_type"] = error_type
    if summary is not None:
        source_audit_job["summary"] = to_jsonable(summary)
    run.status = status
    run.metadata["source_audit_job"] = source_audit_job
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    return run


def _selected_job(service: WorkflowService, *, run_id: str) -> WorkflowRun | None:
    selected_run_id = str(run_id or "").strip()
    if selected_run_id:
        return service.state(selected_run_id)
    queued = list_source_audit_jobs(service, status="queued", limit=1)
    if queued:
        return WorkflowRun.from_dict(queued[0]["job"])
    return None


def _source_audit_job_metadata(run: WorkflowRun) -> dict[str, Any]:
    source_audit_job = run.metadata.get("source_audit_job")
    if not isinstance(source_audit_job, dict):
        return {}
    if source_audit_job.get("kind") != SOURCE_AUDIT_JOB_KIND:
        return {}
    return dict(source_audit_job)


def _optional_status(status: str | None) -> str:
    selected = str(status or "").strip().lower()
    if not selected:
        return ""
    if selected not in SOURCE_AUDIT_JOB_STATUSES:
        raise ValueError(f"source audit job status must be one of: {', '.join(sorted(SOURCE_AUDIT_JOB_STATUSES))}")
    return selected


def _source_audit_job_sort_key(job: dict[str, Any], source_audit_job: dict[str, Any]) -> tuple[int, str]:
    due_at = str(source_audit_job.get("due_at") or (source_audit_job.get("request") or {}).get("due_at") or "")
    return (-int(source_audit_job.get("priority") or 0), due_at, str(job.get("updated_at") or ""))


def _source_audit_job_actions(run_id: str, *, status: str, due_at: str = "") -> list[dict[str, Any]]:
    if status == "queued":
        return [
            {
                "action": "run_source_audit_job",
                "label": "Run Source Audit",
                "api": f"POST /api/sources/audit-jobs/{run_id}/run",
                "tool": "pska_source_audit_job_run",
                "view": "sources",
                "params": {"run_id": run_id},
            }
        ]
    if status == "waiting":
        if _is_due(due_at, _now_datetime("")):
            return [
                {
                    "action": "activate_due_source_audit_jobs",
                    "label": "Activate Due Source Audits",
                    "api": "POST /api/sources/audit-jobs/tick",
                    "tool": "pska_source_audit_job_tick",
                    "view": "sources",
                    "params": {},
                }
            ]
        return [
            {
                "action": "wait_until_due",
                "label": "Wait Until Due",
                "api": "GET /api/sources/audit-jobs?status=waiting",
                "tool": "pska_source_audit_job_list",
                "view": "sources",
                "params": {"run_id": run_id, "due_at": due_at},
            }
        ]
    return []


def _schedule_next_recurring_source_audit_job(
    service: WorkflowService,
    completed: WorkflowRun,
) -> dict[str, Any] | None:
    source_audit_job = dict(completed.metadata.get("source_audit_job") or {})
    request = dict(source_audit_job.get("request") or {})
    if str(source_audit_job.get("schedule_mode") or "") != "scheduled":
        return None
    cadence = _normalize_cadence(str(source_audit_job.get("cadence") or request.get("cadence") or "manual"))
    if cadence in {"manual", "once"}:
        return None
    next_due_at = _iso_datetime(_advance_datetime(_now_datetime(""), cadence))
    next_job = enqueue_source_audit_job(
        service,
        scope=dict(request.get("scope") or {}),
        label=str(request.get("label") or ""),
        priority=int(source_audit_job.get("priority") or 0),
        limit=int(request.get("limit") or 20),
        cadence=cadence,
        due_at=next_due_at,
        schedule_mode="scheduled",
        series_id=str(source_audit_job.get("series_id") or completed.run_id),
        previous_run_id=completed.run_id,
    )
    linked = service.state(completed.run_id)
    linked_metadata = dict(linked.metadata.get("source_audit_job") or {})
    linked_metadata["next_run_id"] = str((next_job.get("job") or {}).get("run_id") or "")
    linked.metadata["source_audit_job"] = linked_metadata
    linked.updated_at = utc_now_iso()
    service.store.save_workflow(linked)
    return next_job


def _audit_job_summary(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_id": str(audit.get("audit_id") or ""),
        "root_count": int(audit.get("root_count") or 0),
        "duplicate_group_count": int((audit.get("duplicate_preview") or {}).get("group_count") or 0),
        "unresolved_link_count": int((audit.get("unresolved_links") or {}).get("count") or 0),
        "unlinked_markdown_count": int((audit.get("unlinked_markdown") or {}).get("count") or 0),
        "route_candidate_count": len(audit.get("route_candidates") or []),
        "next_action_count": len(audit.get("next_actions") or []),
    }


def _audit_summary_message(audit: dict[str, Any]) -> str:
    summary = _audit_job_summary(audit)
    return (
        f"{summary['root_count']} root(s), {summary['duplicate_group_count']} duplicate group(s), "
        f"{summary['unresolved_link_count']} unresolved link(s), "
        f"{summary['unlinked_markdown_count']} unlinked note(s)."
    )


def _normalize_cadence(cadence: str, *, default: str = "manual") -> str:
    selected = str(cadence or default).strip().lower()
    if not selected:
        selected = default
    if selected not in SOURCE_AUDIT_JOB_CADENCES:
        raise ValueError(f"source audit job cadence must be one of: {', '.join(sorted(SOURCE_AUDIT_JOB_CADENCES))}")
    return selected


def _normalize_schedule_mode(schedule_mode: str) -> str:
    selected = str(schedule_mode or "ad_hoc").strip().lower()
    if selected not in {"ad_hoc", "scheduled"}:
        raise ValueError("source audit job schedule_mode must be ad_hoc or scheduled")
    return selected


def _normalize_due_at(due_at: str) -> str:
    value = str(due_at or "").strip()
    if not value:
        return ""
    return _iso_datetime(_parse_datetime(value))


def _now_datetime(now: str) -> datetime:
    value = str(now or "").strip()
    if not value:
        return datetime.now(timezone.utc)
    return _parse_datetime(value)


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _is_due(due_at: str, now_dt: datetime) -> bool:
    if not str(due_at or "").strip():
        return True
    return _parse_datetime(due_at) <= now_dt


def _advance_datetime(value: datetime, cadence: str) -> datetime:
    selected = _normalize_cadence(cadence)
    if selected in {"manual", "once"}:
        return value
    if selected == "hourly":
        return value + timedelta(hours=1)
    if selected == "daily":
        return value + timedelta(days=1)
    if selected == "weekly":
        return value + timedelta(days=7)
    if selected == "monthly":
        return value + timedelta(days=30)
    return value


def _next_due_at(waiting: list[dict[str, Any]], *, now_dt: datetime) -> str:
    due_values: list[datetime] = []
    for item in waiting:
        source_audit_job = dict(item.get("source_audit_job") or {})
        due_at = str(source_audit_job.get("due_at") or (source_audit_job.get("request") or {}).get("due_at") or "")
        if not due_at:
            continue
        due = _parse_datetime(due_at)
        if due > now_dt:
            due_values.append(due)
    if not due_values:
        return ""
    return _iso_datetime(min(due_values))
