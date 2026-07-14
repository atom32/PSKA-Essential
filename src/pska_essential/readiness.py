from __future__ import annotations

from typing import Any

from pska_essential.governance import (
    DURABLE_PROPOSAL_KINDS,
    WorkspaceGovernancePolicy,
    build_workspace_policy_from_env,
)

READY = "ready"
PROCESSING = "processing"
FAILED = "failed"
CANCELLED = "cancelled"
MISSING = "missing"
EMPTY = "empty"
UNKNOWN = "unknown"


def evaluate_kb_readiness(
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    page_size: int = 200,
) -> dict[str, Any]:
    """Evaluate whether a selected KB scope is ready for retrieval.

    This function intentionally consumes only normalized PSKA-facing gateway
    summaries. Provider-specific status payloads must be translated by adapters
    before they reach this layer.
    """

    selected_dataset_ids = _normalized_ids(dataset_ids)
    selected_document_ids = _normalized_ids(document_ids or [])
    if not selected_dataset_ids:
        raise ValueError("dataset_ids is required")

    datasets = gateway.list_datasets(page_size=max(page_size, len(selected_dataset_ids) * 10))
    dataset_by_id = {str(dataset.get("dataset_id") or ""): dict(dataset) for dataset in datasets}
    dataset_reports = [_dataset_report(dataset_by_id.get(dataset_id), dataset_id) for dataset_id in selected_dataset_ids]

    blocking: list[str] = []
    for report in dataset_reports:
        if report["status"] == MISSING:
            blocking.append(
                f"Dataset '{report['dataset_id']}' does not exist or is not visible to the configured KB provider."
            )

    if selected_document_ids:
        _evaluate_document_scope(gateway, dataset_reports, selected_document_ids, blocking)
    else:
        _evaluate_dataset_scope(gateway, dataset_reports, blocking)

    status = _overall_status([report["status"] for report in dataset_reports])
    for report in dataset_reports:
        _attach_dataset_ingestion(report, document_scope=bool(selected_document_ids))
    ready = status == READY
    return {
        "ready": ready,
        "status": status,
        "message": (
            "Selected knowledge scope is ready for retrieval."
            if ready
            else "Selected knowledge scope is not ready for retrieval."
        ),
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "datasets": dataset_reports,
        "blocking": blocking,
        "ingestion_status": _ingestion_status(dataset_reports, status, blocking),
    }


def build_not_ready_ask_result(
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None,
    readiness: dict[str, Any],
    proposal_kind: str,
    create_review: bool | None = None,
    use_kg: bool = False,
    workspace_policy: WorkspaceGovernancePolicy | None = None,
) -> dict[str, Any]:
    normalized_kind = proposal_kind.strip().lower() or "writing_brief"
    if normalized_kind in {"memory_delete", "memory_update"}:
        raise ValueError(f"{normalized_kind} proposals require an explicit memory fact")
    selected_dataset_ids = _normalized_ids(dataset_ids)
    selected_document_ids = _normalized_ids(document_ids or [])
    policy = workspace_policy or build_workspace_policy_from_env()
    governance_action = policy.action_for(normalized_kind, force_review=bool(create_review))
    durable_proposal = normalized_kind in DURABLE_PROPOSAL_KINDS
    scope = {
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "use_kg": bool(use_kg),
    }
    steps = [
        {
            "name": "scope.check",
            "status": "complete",
            "message": "Selected scope accepted.",
            "metadata": {"scope": scope, "question": question.strip()},
        },
        {
            "name": "governance.policy",
            "status": "complete",
            "message": "Workspace governance policy selected.",
            "metadata": {
                "action": governance_action,
                "durable": durable_proposal,
                "policy": policy.to_dict(),
            },
        },
        build_readiness_loop_step(readiness),
    ]
    return {
        "status": "not_ready",
        "run": None,
        "context_packets": [],
        "proposal": None,
        "review": None,
        "review_decision": None,
        "memory_apply": None,
        "memory_facts": [],
        "brief": "",
        "readiness": readiness,
        "loop": {
            "status": "not_ready",
            "steps": steps,
            "review_required": False,
            "durable_proposal": durable_proposal,
            "governance": {
                "action": governance_action,
                "policy": policy.to_dict(),
                "durable_proposal": durable_proposal,
            },
        },
        "message": _not_ready_message(readiness),
    }


def build_readiness_loop_step(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "kb.readiness",
        "status": "complete" if readiness.get("ready") else "blocked",
        "message": readiness.get("message") or "Selected knowledge scope is not ready for retrieval.",
        "metadata": {"readiness": readiness},
    }


def _evaluate_dataset_scope(gateway: Any, dataset_reports: list[dict[str, Any]], blocking: list[str]) -> None:
    for report in dataset_reports:
        if report["status"] == MISSING:
            continue
        dataset = report["dataset"]
        document_count = int(dataset.get("document_count") or 0)
        chunk_count = int(dataset.get("chunk_count") or 0)
        report["document_count"] = document_count
        report["chunk_count"] = chunk_count
        if document_count <= 0:
            report["ready"] = False
            report["status"] = EMPTY
            blocking.append(f"Dataset '{_dataset_label(report)}' has no documents.")
            continue
        if chunk_count > 0:
            report["ready"] = True
            report["status"] = READY
            continue

        docs = gateway.list_documents(dataset_id=report["dataset_id"], page_size=20)
        doc_reports = [_document_report(doc, requested=True) for doc in docs]
        report["documents"] = doc_reports
        doc_statuses = [doc["status"] for doc in doc_reports]
        report["ready"] = False
        report["status"] = _overall_status(doc_statuses) if doc_statuses else PROCESSING
        blocking.append(
            f"Dataset '{_dataset_label(report)}' is not ready for retrieval: "
            f"{document_count} documents, {chunk_count} chunks."
        )


def _evaluate_document_scope(
    gateway: Any,
    dataset_reports: list[dict[str, Any]],
    selected_document_ids: list[str],
    blocking: list[str],
) -> None:
    existing_reports = [report for report in dataset_reports if report["status"] != MISSING]
    for report in existing_reports:
        report["documents"] = []
        report["ready"] = True
        report["status"] = READY

    for document_id in selected_document_ids:
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for report in existing_reports:
            docs = gateway.list_documents(dataset_id=report["dataset_id"], document_id=document_id, page_size=1)
            if docs:
                matches.append((report, docs[0]))
        if not matches:
            for report in existing_reports:
                report["ready"] = False
                report["status"] = _overall_status([report["status"], MISSING])
            blocking.append(f"Document '{document_id}' was not found in the selected datasets.")
            continue

        for report, doc in matches:
            doc_report = _document_report(doc, requested=True)
            report["documents"].append(doc_report)
            if doc_report["status"] != READY:
                report["ready"] = False
                report["status"] = _overall_status([report["status"], doc_report["status"]])
                blocking.append(_document_blocking_message(doc_report))

    for report in existing_reports:
        if not report["ready"]:
            continue
        report["status"] = READY


def _dataset_report(dataset: dict[str, Any] | None, dataset_id: str) -> dict[str, Any]:
    if not dataset:
        return {
            "dataset_id": dataset_id,
            "exists": False,
            "ready": False,
            "status": MISSING,
            "dataset": {},
            "documents": [],
        }
    return {
        "dataset_id": str(dataset.get("dataset_id") or dataset_id),
        "name": dataset.get("name") or "",
        "exists": True,
        "ready": False,
        "status": UNKNOWN,
        "document_count": int(dataset.get("document_count") or 0),
        "chunk_count": int(dataset.get("chunk_count") or 0),
        "dataset": dataset,
        "documents": [],
    }


def _document_report(document: dict[str, Any], *, requested: bool) -> dict[str, Any]:
    status = _document_status(document)
    phase = _document_phase(document, status)
    failure_reason = _document_failure_reason(document, status)
    return {
        "dataset_id": str(document.get("dataset_id") or ""),
        "document_id": str(document.get("document_id") or ""),
        "name": document.get("name") or "",
        "requested": requested,
        "ready": status == READY,
        "status": status,
        "phase": phase,
        "next_action": _document_next_action(status, phase),
        "failure_reason": failure_reason,
        "chunk_count": int(document.get("chunk_count") or 0),
        "token_count": int(document.get("token_count") or 0),
        "progress": _float_value(document.get("progress")),
        "progress_msg": document.get("progress_msg") or "",
        "run": str(document.get("run") or ""),
    }


def _document_status(document: dict[str, Any]) -> str:
    run = str(document.get("run") or "").strip().upper()
    status = str(document.get("status") or "").strip().lower()
    progress_msg = str(document.get("progress_msg") or "").strip().lower()
    progress = _float_value(document.get("progress"))
    chunk_count = int(document.get("chunk_count") or 0)
    if run in {"CANCEL", "CANCELED", "CANCELLED"} or status in {"cancel", "canceled", "cancelled"}:
        return CANCELLED
    if "cancel" in progress_msg:
        return CANCELLED
    if run in {"FAIL", "FAILED", "ERROR"} or status in {"fail", "failed", "error"}:
        return FAILED
    if any(token in progress_msg for token in ("fail", "error")):
        return FAILED
    if chunk_count > 0 or progress >= 1.0 or run in {"DONE", "SUCCESS"} or status in {"ready", "done", "success"}:
        return READY
    processing_runs = {
        "",
        "UNSTART",
        "START",
        "STARTED",
        "RUNNING",
        "PARSING",
        "QUEUED",
        "EMBEDDING",
        "VECTORIZING",
        "INDEXING",
        "OCR",
        "CHUNKING",
        "TOKENIZING",
        "1",
    }
    processing_statuses = {"processing", "running", "parsing", "embedding", "indexing", "queued", "uploaded", "pending"}
    if run in processing_runs or status in processing_statuses or progress > 0:
        return PROCESSING
    return UNKNOWN


def _document_blocking_message(doc: dict[str, Any]) -> str:
    label = doc.get("name") or doc.get("document_id") or "unknown document"
    if doc["status"] == FAILED:
        reason = doc.get("progress_msg") or doc.get("run") or "failed"
        return f"Document '{label}' failed during ingestion: {reason}."
    if doc["status"] == CANCELLED:
        reason = doc.get("progress_msg") or doc.get("run") or "cancelled"
        return f"Document '{label}' was cancelled during ingestion: {reason}."
    if doc["status"] == PROCESSING:
        return f"Document '{label}' is still processing: progress {doc['progress']:.2f}, run {doc.get('run') or 'unknown'}."
    return f"Document '{label}' is not ready for retrieval."


def _attach_dataset_ingestion(report: dict[str, Any], *, document_scope: bool) -> None:
    status = str(report.get("status") or UNKNOWN)
    documents = report.get("documents") or []
    document_count = len(documents) if document_scope else int(report.get("document_count") or len(documents) or 0)
    ready_count = len([document for document in documents if document.get("status") == READY])
    failed_count = len([document for document in documents if document.get("status") == FAILED])
    cancelled_count = len([document for document in documents if document.get("status") == CANCELLED])
    processing_count = len([document for document in documents if document.get("status") == PROCESSING])
    if not documents and status == READY:
        ready_count = document_count
    pending_count = max(document_count - ready_count - failed_count - cancelled_count - processing_count, 0)
    ingestion = {
        "dataset_id": str(report.get("dataset_id") or ""),
        "status": status,
        "phase": _dataset_phase(status, documents),
        "progress": _dataset_progress(report, documents),
        "document_count": document_count,
        "ready_count": ready_count,
        "processing_count": processing_count,
        "failed_count": failed_count,
        "cancelled_count": cancelled_count,
        "pending_count": pending_count,
        "next_action": _dataset_next_action(status, documents),
        "message": _dataset_ingestion_message(report, status),
    }
    report["ingestion"] = ingestion


def _ingestion_status(
    dataset_reports: list[dict[str, Any]],
    status: str,
    blocking: list[str],
) -> dict[str, Any]:
    dataset_jobs = [report.get("ingestion") or {} for report in dataset_reports]
    document_count = sum(int(job.get("document_count") or 0) for job in dataset_jobs)
    ready_count = sum(int(job.get("ready_count") or 0) for job in dataset_jobs)
    processing_count = sum(int(job.get("processing_count") or 0) for job in dataset_jobs)
    failed_count = sum(int(job.get("failed_count") or 0) for job in dataset_jobs)
    cancelled_count = sum(int(job.get("cancelled_count") or 0) for job in dataset_jobs)
    pending_count = sum(int(job.get("pending_count") or 0) for job in dataset_jobs)
    weights = [max(int(job.get("document_count") or 0), 1) for job in dataset_jobs]
    progress_values = [_float_value(job.get("progress")) for job in dataset_jobs]
    if progress_values:
        progress = sum(value * weight for value, weight in zip(progress_values, weights)) / sum(weights)
    else:
        progress = 0.0
    next_actions = _unique_strings(
        str(job.get("next_action") or "") for job in dataset_jobs if job.get("next_action")
    )
    return {
        "kind": "kb_ingestion_status",
        "ready": status == READY,
        "status": status,
        "phase": _aggregate_job_phase(dataset_jobs, status),
        "progress": round(max(0.0, min(1.0, progress)), 4),
        "dataset_count": len(dataset_reports),
        "document_count": document_count,
        "ready_count": ready_count,
        "processing_count": processing_count,
        "failed_count": failed_count,
        "cancelled_count": cancelled_count,
        "pending_count": pending_count,
        "next_actions": next_actions,
        "message": _ingestion_message(status, blocking, document_count, ready_count, failed_count, cancelled_count),
    }


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return UNKNOWN
    for status in (MISSING, FAILED, CANCELLED, EMPTY, PROCESSING, UNKNOWN):
        if status in statuses:
            return status
    return READY


def _document_phase(document: dict[str, Any], status: str) -> str:
    if status == READY:
        return "ready"
    if status == CANCELLED:
        return "cancelled"
    if status == FAILED:
        return "failed"
    run = str(document.get("run") or "").strip().upper()
    provider_status = str(document.get("status") or "").strip().lower()
    progress_msg = str(document.get("progress_msg") or "").strip().lower()
    phase_text = f"{run.lower()} {provider_status} {progress_msg}"
    progress = _float_value(document.get("progress"))
    if _has_any(phase_text, {"embed", "vector"}):
        return "embedding"
    if _has_any(phase_text, {"index"}):
        return "indexing"
    if _has_any(phase_text, {"parse", "ocr", "chunk", "token"}):
        return "parsing"
    if run in {"EMBEDDING", "VECTORIZING"}:
        return "embedding"
    if run in {"INDEXING"}:
        return "indexing"
    if run in {"PARSING", "OCR", "CHUNKING", "TOKENIZING"}:
        return "parsing"
    if run in {"", "UNSTART", "QUEUED"} or provider_status in {"uploaded", "unstart", "pending", "queued"}:
        return "uploaded"
    if progress > 0 or run in {"START", "STARTED", "RUNNING", "1"}:
        return "processing"
    return "unknown"


def _document_failure_reason(document: dict[str, Any], status: str) -> str:
    if status not in {FAILED, CANCELLED}:
        return ""
    default = "cancelled" if status == CANCELLED else "failed"
    return str(document.get("progress_msg") or document.get("run") or document.get("status") or default)


def _document_next_action(status: str, phase: str) -> str:
    if status == READY:
        return "available_for_retrieval"
    if status == FAILED:
        return "inspect_failure"
    if status == CANCELLED:
        return "inspect_cancellation"
    if phase == "uploaded":
        return "start_parse"
    if status == PROCESSING:
        return "wait_for_ingestion"
    return "check_provider_status"


def _dataset_phase(status: str, documents: list[dict[str, Any]] | None = None) -> str:
    documents = documents or []
    if status == READY:
        return "ready"
    if status == PROCESSING:
        return _aggregate_document_phase(documents) or "processing"
    if status == FAILED:
        return "failed"
    if status == CANCELLED:
        return "cancelled"
    if status == EMPTY:
        return "awaiting_upload"
    if status == MISSING:
        return "scope_missing"
    return "unknown"


def _dataset_next_action(status: str, documents: list[dict[str, Any]]) -> str:
    if status == READY:
        return "run_ask"
    if status == EMPTY:
        return "upload_documents"
    if status == MISSING:
        return "check_dataset_access"
    if status == FAILED:
        return "inspect_failed_documents"
    if status == CANCELLED:
        return "inspect_cancelled_documents"
    if any(document.get("next_action") == "start_parse" for document in documents):
        return "start_parse"
    if status == PROCESSING:
        return "wait_for_ingestion"
    return "check_provider_status"


def _dataset_progress(report: dict[str, Any], documents: list[dict[str, Any]]) -> float:
    if report.get("status") == READY:
        return 1.0
    if report.get("status") in {MISSING, EMPTY}:
        return 0.0
    if documents:
        values = [_float_value(document.get("progress")) for document in documents]
        return round(sum(values) / len(values), 4)
    return 0.0


def _dataset_ingestion_message(report: dict[str, Any], status: str) -> str:
    label = _dataset_label(report)
    if status == READY:
        return f"Dataset '{label}' is ready for retrieval."
    if status == EMPTY:
        return f"Dataset '{label}' has no uploaded source documents."
    if status == MISSING:
        return f"Dataset '{label}' is missing or not visible."
    if status == FAILED:
        return f"Dataset '{label}' has failed ingestion documents."
    if status == CANCELLED:
        return f"Dataset '{label}' has cancelled ingestion documents."
    if status == PROCESSING:
        return f"Dataset '{label}' is still being parsed, embedded, or indexed."
    return f"Dataset '{label}' readiness is unknown."


def _ingestion_message(
    status: str,
    blocking: list[str],
    document_count: int,
    ready_count: int,
    failed_count: int,
    cancelled_count: int,
) -> str:
    if blocking:
        return " ".join(str(item) for item in blocking[:3])
    if status == READY:
        return f"{ready_count}/{document_count} document(s) ready for retrieval."
    if status == FAILED:
        return f"{failed_count} document(s) failed during ingestion."
    if status == CANCELLED:
        return f"{cancelled_count} document(s) were cancelled during ingestion."
    if status == EMPTY:
        return "No source documents have been uploaded for the selected scope."
    if status == MISSING:
        return "One or more selected datasets or documents are missing."
    return f"{ready_count}/{document_count} document(s) ready; ingestion is still running or unknown."


def _aggregate_job_phase(dataset_jobs: list[dict[str, Any]], status: str) -> str:
    phases = [str(job.get("phase") or "") for job in dataset_jobs]
    if status == READY:
        return "ready"
    for phase in ("failed", "cancelled", "indexing", "embedding", "parsing", "uploaded", "processing"):
        if phase in phases:
            return phase
    return _dataset_phase(status)


def _aggregate_document_phase(documents: list[dict[str, Any]]) -> str:
    phases = [str(document.get("phase") or "") for document in documents]
    for phase in ("indexing", "embedding", "parsing", "uploaded", "processing"):
        if phase in phases:
            return phase
    return ""


def _not_ready_message(readiness: dict[str, Any]) -> str:
    blocking = readiness.get("blocking") or []
    if blocking:
        return " ".join(str(item) for item in blocking[:3])
    return readiness.get("message") or "Selected knowledge scope is not ready for retrieval."


def _normalized_ids(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _has_any(value: str, tokens: set[str]) -> bool:
    return any(token in value for token in tokens)


def _dataset_label(report: dict[str, Any]) -> str:
    return str(report.get("name") or report.get("dataset_id") or "unknown dataset")


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
