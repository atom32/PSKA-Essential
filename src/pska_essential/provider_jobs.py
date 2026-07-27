from __future__ import annotations

import os
from typing import Any

from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.digest_jobs import list_digest_jobs
from pska_essential.readiness import evaluate_kb_readiness


def build_provider_job_status(
    service: Any,
    gateway: Any,
    *,
    dataset_page_size: int = 50,
    digest_limit: int = 50,
    audit_limit: int = 50,
    include_ready: bool = True,
) -> dict[str, Any]:
    """Return a normalized job/status inventory without owning provider jobs."""

    if dataset_page_size < 1:
        raise ValueError("dataset_page_size must be greater than 0")
    if digest_limit < 1:
        raise ValueError("digest_limit must be greater than 0")
    if audit_limit < 1:
        raise ValueError("audit_limit must be greater than 0")
    kb_jobs, kb_error = _kb_jobs(gateway, page_size=dataset_page_size, include_ready=include_ready)
    digest_jobs = _digest_jobs(service, limit=digest_limit)
    recent_provider_events = _recent_provider_events(service, limit=audit_limit)
    jobs = [*kb_jobs, *digest_jobs]
    if not include_ready:
        jobs = [job for job in jobs if job.get("status") != "ready"]
    summary = _job_summary(jobs, kb_error)
    return {
        "kind": "provider_job_status",
        "schema": "pska.provider_jobs.v1",
        "generated_at": utc_now_iso(),
        "status": summary["status"],
        "providers": {
            "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower()
            or str(getattr(gateway, "backend_name", "custom")),
            "memory": os.getenv("PSKA_MEMORY_PROVIDER", "").strip().lower()
            or str(getattr(service.memory, "backend_name", "custom")),
            "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", "").strip().lower()
            or str(getattr(service.retrieval, "backend_name", "custom")),
        },
        "summary": summary,
        "jobs": jobs,
        "recent_provider_events": recent_provider_events,
        "error": kb_error,
        "note": (
            "PSKA reports normalized job state from provider readiness, audit, and explicit digest metadata. "
            "It does not own or replace provider-native queues."
        ),
    }


def _kb_jobs(gateway: Any, *, page_size: int, include_ready: bool) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    try:
        datasets = gateway.list_datasets(page_size=page_size)
        dataset_ids = [str(dataset.get("dataset_id") or "") for dataset in datasets if dataset.get("dataset_id")]
        jobs: list[dict[str, Any]] = []
        for dataset_id in dataset_ids:
            readiness = evaluate_kb_readiness(gateway, dataset_ids=[dataset_id])
            dataset_report = (readiness.get("datasets") or [{}])[0]
            ingestion = dataset_report.get("ingestion") or readiness.get("ingestion_status") or {}
            if include_ready or ingestion.get("status") != "ready":
                jobs.append(_dataset_job(dataset_report, readiness, ingestion))
            for document in dataset_report.get("documents") or []:
                if include_ready or document.get("status") != "ready":
                    jobs.append(_document_job(dataset_report, document))
        return jobs, None
    except Exception as exc:  # noqa: BLE001 - job status should surface explicit provider errors.
        return [], {"type": exc.__class__.__name__, "message": str(exc)}


def _dataset_job(dataset_report: dict[str, Any], readiness: dict[str, Any], ingestion: dict[str, Any]) -> dict[str, Any]:
    dataset_id = str(dataset_report.get("dataset_id") or ingestion.get("dataset_id") or "")
    return {
        "kind": "kb_dataset_ingestion",
        "job_id": f"kb_dataset:{dataset_id}",
        "provider": str((dataset_report.get("dataset") or {}).get("backend") or ""),
        "dataset_id": dataset_id,
        "dataset_name": str(dataset_report.get("name") or (dataset_report.get("dataset") or {}).get("name") or ""),
        "status": str(ingestion.get("status") or readiness.get("status") or "unknown"),
        "phase": str(ingestion.get("phase") or "unknown"),
        "progress": float(ingestion.get("progress") or 0.0),
        "document_count": int(ingestion.get("document_count") or 0),
        "ready_count": int(ingestion.get("ready_count") or 0),
        "processing_count": int(ingestion.get("processing_count") or 0),
        "failed_count": int(ingestion.get("failed_count") or 0),
        "cancelled_count": int(ingestion.get("cancelled_count") or 0),
        "pending_count": int(ingestion.get("pending_count") or 0),
        "next_actions": _job_next_actions(ingestion.get("next_action") or "", readiness.get("ingestion_status") or {}),
        "message": str(ingestion.get("message") or readiness.get("message") or ""),
        "readiness": {
            "ready": bool(readiness.get("ready")),
            "status": str(readiness.get("status") or "unknown"),
            "blocking": to_jsonable(readiness.get("blocking") or []),
        },
    }


def _document_job(dataset_report: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    dataset_id = str(document.get("dataset_id") or dataset_report.get("dataset_id") or "")
    document_id = str(document.get("document_id") or "")
    return {
        "kind": "kb_document_ingestion",
        "job_id": f"kb_document:{dataset_id}:{document_id}",
        "provider": str((dataset_report.get("dataset") or {}).get("backend") or ""),
        "dataset_id": dataset_id,
        "document_id": document_id,
        "document_name": str(document.get("name") or ""),
        "status": str(document.get("status") or "unknown"),
        "phase": str(document.get("phase") or "unknown"),
        "progress": float(document.get("progress") or 0.0),
        "chunk_count": int(document.get("chunk_count") or 0),
        "token_count": int(document.get("token_count") or 0),
        "next_actions": [document["next_action"]] if document.get("next_action") else [],
        "failure_code": str(document.get("failure_code") or ""),
        "failure_reason": str(document.get("failure_reason") or ""),
        "progress_msg": str(document.get("progress_msg") or ""),
        "run": str(document.get("run") or ""),
    }


def _digest_jobs(service: Any, *, limit: int) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for item in list_digest_jobs(service, limit=limit):
        run = dict(item.get("job") or {})
        digest_job = dict(item.get("digest_job") or {})
        request = dict(digest_job.get("request") or {})
        scope = dict(run.get("scope") or {})
        status = str(digest_job.get("status") or run.get("status") or "unknown")
        jobs.append(
            {
                "kind": "pska_digest_job",
                "job_id": str(run.get("run_id") or ""),
                "provider": "pska",
                "status": status,
                "phase": status,
                "progress": _digest_progress(status),
                "dataset_ids": _string_list(request.get("dataset_ids") or scope.get("dataset_ids") or []),
                "document_ids": _string_list(request.get("document_ids") or scope.get("document_ids") or []),
                "priority": int(digest_job.get("priority") or 0),
                "attempt_count": int(digest_job.get("attempt_count") or 0),
                "create_memory_review": bool(request.get("create_memory_review", False)),
                "memory_intent": str(request.get("memory_intent") or ""),
                "result_run_id": str(digest_job.get("result_run_id") or ""),
                "last_status": str(digest_job.get("last_status") or ""),
                "last_message": str(digest_job.get("last_message") or ""),
                "readiness": to_jsonable(digest_job.get("readiness") or {}),
                "next_actions": _digest_next_actions(status),
                "message": str(digest_job.get("last_message") or ""),
                "created_at": str(digest_job.get("created_at") or run.get("created_at") or ""),
                "updated_at": str(digest_job.get("updated_at") or run.get("updated_at") or ""),
                "data_flow": {
                    "source": "kb_ready_scope",
                    "candidate_target": "exception_review" if request.get("create_memory_review") else "digest_artifact",
                    "writes_memory_directly": False,
                },
            }
        )
    return jobs


def _recent_provider_events(service: Any, *, limit: int) -> list[dict[str, Any]]:
    provider_actions = {"kb.ingest", "kb.parse", "kb.dataset.create", "kb.dataset.delete"}
    events = [
        event
        for event in service.store.list_audit_events(limit=limit, descending=True)
        if event.action in provider_actions
    ]
    return [
        {
            "action": event.action,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "created_at": event.created_at,
            "metadata": {
                key: value
                for key, value in (event.metadata or {}).items()
                if key
                in {
                    "backend",
                    "dataset_id",
                    "dataset_name",
                    "dataset_ids",
                    "document_ids",
                    "document_names",
                    "document_count",
                    "parse_started",
                    "dataset_created",
                    "deleted",
                }
            },
        }
        for event in events
    ]


def _job_summary(jobs: list[dict[str, Any]], error: dict[str, str] | None) -> dict[str, Any]:
    counts = {
        "total": len(jobs),
        "ready": len([job for job in jobs if job.get("status") == "ready"]),
        "processing": len([job for job in jobs if job.get("status") == "processing"]),
        "failed": len([job for job in jobs if job.get("status") == "failed"]),
        "cancelled": len([job for job in jobs if job.get("status") == "cancelled"]),
        "queued": len([job for job in jobs if job.get("status") == "queued"]),
        "waiting": len([job for job in jobs if job.get("status") == "waiting"]),
        "unknown": len([job for job in jobs if job.get("status") == "unknown"]),
    }
    if error:
        status = "error"
    elif counts["failed"]:
        status = "failed"
    elif counts["processing"] or counts["queued"] or counts["waiting"]:
        status = "processing"
    elif jobs and counts["ready"] == len(jobs):
        status = "ready"
    elif jobs:
        status = "mixed"
    else:
        status = "empty"
    return {"status": status, **counts}


def _job_next_actions(dataset_next_action: str, ingestion_status: dict[str, Any]) -> list[str]:
    values = [str(dataset_next_action or "")]
    values.extend(str(action or "") for action in ingestion_status.get("next_actions") or [])
    return _unique_strings(values)


def _digest_progress(status: str) -> float:
    if status == "completed":
        return 1.0
    if status in {"running", "processing"}:
        return 0.5
    if status in {"queued", "waiting"}:
        return 0.0
    if status == "failed":
        return 0.0
    return 0.0


def _digest_next_actions(status: str) -> list[str]:
    if status in {"queued", "waiting"}:
        return ["run_digest_job"]
    if status == "failed":
        return ["inspect_failure"]
    return []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _string_list(values: list[Any]) -> list[str]:
    return [str(value) for value in values or [] if str(value or "").strip()]
