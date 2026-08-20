from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pska_essential.contracts import utc_now_iso
from pska_essential.provider_jobs import build_provider_job_status


JOB_HEALTH_SCHEMA = "pska.job_health.v1"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "digest",
        "label": "Digest Jobs",
        "kinds": ("pska_digest_job",),
        "run_action": "run_digest_job",
        "run_api": "POST /api/digest-jobs/{job_id}/run",
        "run_tool": "pska_digest_job_run",
    },
    {
        "id": "source_audit",
        "label": "Source Audit Jobs",
        "kinds": ("pska_source_audit_job",),
        "run_action": "run_source_audit_job",
        "run_api": "POST /api/sources/audit-jobs/{job_id}/run",
        "run_tool": "pska_source_audit_job_run",
        "tick_action": "activate_due_source_audit_jobs",
        "tick_api": "POST /api/sources/audit-jobs/tick",
        "tick_tool": "pska_source_audit_job_tick",
    },
    {
        "id": "source_extraction",
        "label": "Source Extraction Jobs",
        "kinds": ("pska_source_extraction_job",),
        "run_action": "run_source_extraction_job",
        "run_api": "POST /api/sources/extraction-jobs/{job_id}/run",
        "run_tool": "pska_source_extract_job_run",
    },
    {
        "id": "kb_ingestion",
        "label": "KB Ingestion",
        "kinds": ("kb_dataset_ingestion", "kb_document_ingestion"),
    },
)


def build_job_health(
    service: Any,
    gateway: Any,
    *,
    now: str = "",
    limit: int = DEFAULT_LIMIT,
    include_kb: bool = True,
) -> dict[str, Any]:
    selected_limit = min(MAX_LIMIT, max(1, int(limit)))
    now_iso = _normalize_now(now)
    provider_jobs = build_provider_job_status(
        service,
        gateway,
        dataset_page_size=selected_limit,
        digest_limit=selected_limit,
        source_audit_limit=selected_limit,
        source_extraction_limit=selected_limit,
        audit_limit=selected_limit,
        include_ready=bool(include_kb),
    )
    all_jobs = list(provider_jobs.get("jobs") or [])
    if not include_kb:
        all_jobs = [
            job
            for job in all_jobs
            if str(job.get("kind") or "") not in {"kb_dataset_ingestion", "kb_document_ingestion"}
        ]
    groups = [_group_health(group, all_jobs, now_iso=now_iso, limit=selected_limit) for group in GROUPS]
    if not include_kb:
        groups = [group for group in groups if group["id"] != "kb_ingestion"]
    summary = _summary(groups)
    return {
        "kind": "job_health",
        "schema": JOB_HEALTH_SCHEMA,
        "generated_at": utc_now_iso(),
        "status": summary["status"],
        "summary": summary,
        "groups": groups,
        "provider_jobs": {
            "schema": provider_jobs.get("schema") or "",
            "status": provider_jobs.get("status") or "",
            "summary": provider_jobs.get("summary") or {},
            "error": provider_jobs.get("error"),
        },
        "scheduler": {
            "source_audit_tick": {
                "api": "POST /api/sources/audit-jobs/tick",
                "tool": "pska_source_audit_job_tick",
                "cron_hint": "curl -fsS -X POST http://127.0.0.1:8765/api/sources/audit-jobs/tick -H 'content-type: application/json' -d '{\"limit\":20}'",
                "launchd_or_cron_required_for_automatic_due_activation": True,
            },
            "read_only_status": True,
            "runs_jobs": False,
            "activates_due_jobs": False,
        },
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "runs_jobs": False,
            "activates_due_jobs": False,
            "embedding_required": False,
        },
        "next_actions": _top_next_actions(groups),
    }


def _group_health(
    group: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    now_iso: str,
    limit: int,
) -> dict[str, Any]:
    kinds = set(group["kinds"])
    selected = [job for job in jobs if str(job.get("kind") or "") in kinds]
    condensed = [_condensed_job(job, now_iso=now_iso) for job in selected[:limit]]
    counts = _counts(condensed)
    status = _group_status(counts)
    return {
        "id": str(group["id"]),
        "label": str(group["label"]),
        "status": status,
        "message": _group_message(group, counts),
        "counts": counts,
        "jobs": condensed,
        "next_actions": _group_next_actions(group, condensed),
    }


def _condensed_job(job: dict[str, Any], *, now_iso: str) -> dict[str, Any]:
    status = str(job.get("status") or "unknown")
    updated_at = str(job.get("updated_at") or job.get("created_at") or "")
    stale = _is_stale(status, updated_at, now_iso)
    return {
        "kind": str(job.get("kind") or ""),
        "job_id": str(job.get("job_id") or ""),
        "status": status,
        "phase": str(job.get("phase") or status),
        "progress": float(job.get("progress") or 0.0),
        "label": str(job.get("label") or job.get("dataset_name") or job.get("document_name") or ""),
        "priority": int(job.get("priority") or 0),
        "attempt_count": int(job.get("attempt_count") or 0),
        "due": bool(job.get("due", False)),
        "due_at": str(job.get("due_at") or ""),
        "stale": stale,
        "updated_at": updated_at,
        "last_status": str(job.get("last_status") or ""),
        "last_message": str(job.get("last_message") or job.get("message") or ""),
        "next_actions": list(job.get("next_actions") or []),
        "dataset_ids": list(job.get("dataset_ids") or ([job.get("dataset_id")] if job.get("dataset_id") else [])),
        "document_ids": list(job.get("document_ids") or ([job.get("document_id")] if job.get("document_id") else [])),
        "root_ids": list(job.get("root_ids") or ([job.get("root_id")] if job.get("root_id") else [])),
        "data_flow": dict(job.get("data_flow") or {}),
    }


def _counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
    statuses = {
        "total": len(jobs),
        "queued": 0,
        "waiting": 0,
        "running": 0,
        "processing": 0,
        "completed": 0,
        "ready": 0,
        "failed": 0,
        "cancelled": 0,
        "unknown": 0,
        "due": 0,
        "stale": 0,
        "actionable": 0,
    }
    for job in jobs:
        status = str(job.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        if job.get("due"):
            statuses["due"] += 1
        if job.get("stale"):
            statuses["stale"] += 1
        if job.get("next_actions"):
            statuses["actionable"] += 1
    return statuses


def _group_status(counts: dict[str, int]) -> str:
    if counts["total"] == 0:
        return "empty"
    if counts["failed"] or counts["cancelled"] or counts["stale"] or counts["unknown"]:
        return "needs_attention"
    if counts["due"] or counts["queued"] or counts["running"] or counts["processing"] or counts["actionable"]:
        return "action_required"
    return "ok"


def _summary(groups: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "group_count": len(groups),
        "job_count": 0,
        "failed_count": 0,
        "due_count": 0,
        "queued_count": 0,
        "waiting_count": 0,
        "running_count": 0,
        "processing_count": 0,
        "stale_count": 0,
        "actionable_count": 0,
    }
    for group in groups:
        counts = dict(group.get("counts") or {})
        totals["job_count"] += int(counts.get("total") or 0)
        totals["failed_count"] += int(counts.get("failed") or 0)
        totals["due_count"] += int(counts.get("due") or 0)
        totals["queued_count"] += int(counts.get("queued") or 0)
        totals["waiting_count"] += int(counts.get("waiting") or 0)
        totals["running_count"] += int(counts.get("running") or 0)
        totals["processing_count"] += int(counts.get("processing") or 0)
        totals["stale_count"] += int(counts.get("stale") or 0)
        totals["actionable_count"] += int(counts.get("actionable") or 0)
    statuses = {str(group.get("status") or "") for group in groups}
    if "needs_attention" in statuses:
        status = "needs_attention"
    elif "action_required" in statuses:
        status = "action_required"
    elif totals["job_count"] == 0:
        status = "empty"
    else:
        status = "ok"
    return {"status": status, **totals}


def _group_message(group: dict[str, Any], counts: dict[str, int]) -> str:
    if counts["total"] == 0:
        return f"No recent {group['label'].lower()} are tracked."
    if counts["failed"] or counts["stale"] or counts["unknown"]:
        return "Inspect failed, stale, or unknown jobs before assuming the loop is healthy."
    if counts["due"]:
        return "Scheduled jobs are due; run the explicit tick before running queued jobs."
    if counts["queued"] or counts["actionable"]:
        return "Jobs are queued and ready for the explicit runner."
    if counts["running"] or counts["processing"]:
        return "Jobs are currently running or provider ingestion is processing."
    return "Tracked jobs are healthy."


def _group_next_actions(group: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if group.get("tick_action") and any(job.get("due") for job in jobs):
        actions.append(
            {
                "action": group["tick_action"],
                "label": "Activate Due Source Audits",
                "api": group["tick_api"],
                "tool": group["tick_tool"],
                "params": {"limit": 20},
            }
        )
    for job in jobs:
        for action in job.get("next_actions") or []:
            normalized = _normalize_action(action)
            if normalized == "wait_until_due":
                continue
            if normalized == "inspect_failure":
                actions.append(
                    {
                        "action": "inspect_failure",
                        "label": "Inspect Failure",
                        "api": _inspect_api(group),
                        "tool": _inspect_tool(group),
                        "params": {"job_id": job["job_id"]},
                    }
                )
                continue
            if normalized == group.get("run_action"):
                actions.append(
                    {
                        "action": normalized,
                        "label": "Run Job",
                        "api": str(group["run_api"]).format(job_id=job["job_id"]),
                        "tool": group["run_tool"],
                        "params": {"run_id": job["job_id"]},
                    }
                )
    return _dedupe_actions(actions)[:5]


def _top_next_actions(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for preferred in ("source_audit", "source_extraction", "digest", "kb_ingestion"):
        group = next((item for item in groups if item["id"] == preferred), None)
        if not group:
            continue
        actions.extend(group.get("next_actions") or [])
    return _dedupe_actions(actions)[:8]


def _inspect_api(group: dict[str, Any]) -> str:
    group_id = str(group.get("id") or "")
    if group_id == "digest":
        return "GET /api/digest-jobs?status=failed"
    if group_id == "source_audit":
        return "GET /api/sources/audit-jobs?status=failed"
    if group_id == "source_extraction":
        return "GET /api/sources/extraction-jobs?status=failed"
    return "GET /api/provider/jobs"


def _inspect_tool(group: dict[str, Any]) -> str:
    group_id = str(group.get("id") or "")
    if group_id == "digest":
        return "pska_digest_job_list"
    if group_id == "source_audit":
        return "pska_source_audit_job_list"
    if group_id == "source_extraction":
        return "pska_source_extract_job_list"
    return "pska_provider_jobs"


def _normalize_action(action: Any) -> str:
    value = str(action or "").strip()
    if value == "activate_due_source_audit_job":
        return "activate_due_source_audit_jobs"
    return value


def _dedupe_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for action in actions:
        key = (str(action.get("action") or ""), str((action.get("params") or {}).get("run_id") or action.get("api") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _is_stale(status: str, updated_at: str, now_iso: str) -> bool:
    if status not in {"queued", "waiting", "running", "processing"}:
        return False
    updated = _parse_iso(updated_at)
    now = _parse_iso(now_iso)
    if updated is None or now is None:
        return False
    threshold = timedelta(hours=1) if status in {"running", "processing"} else timedelta(hours=24)
    return now - updated > threshold


def _normalize_now(value: str) -> str:
    selected = str(value or "").strip()
    if not selected:
        return utc_now_iso()
    parsed = _parse_iso(selected)
    if parsed is None:
        return utc_now_iso()
    return parsed.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime | None:
    selected = str(value or "").strip()
    if not selected:
        return None
    try:
        if selected.endswith("Z"):
            selected = f"{selected[:-1]}+00:00"
        parsed = datetime.fromisoformat(selected)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
