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
    return {
        "dataset_id": str(document.get("dataset_id") or ""),
        "document_id": str(document.get("document_id") or ""),
        "name": document.get("name") or "",
        "requested": requested,
        "ready": status == READY,
        "status": status,
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
    if run in {"FAIL", "FAILED", "CANCEL", "CANCELED", "ERROR"} or status in {"fail", "failed", "cancel", "canceled", "error"}:
        return FAILED
    if any(token in progress_msg for token in ("fail", "error", "cancel")):
        return FAILED
    if chunk_count > 0 or progress >= 1.0 or run in {"DONE", "SUCCESS"} or status in {"ready", "done", "success"}:
        return READY
    if run in {"", "UNSTART", "START", "STARTED", "RUNNING", "PARSING", "QUEUED", "1"} or progress > 0:
        return PROCESSING
    return UNKNOWN


def _document_blocking_message(doc: dict[str, Any]) -> str:
    label = doc.get("name") or doc.get("document_id") or "unknown document"
    if doc["status"] == FAILED:
        reason = doc.get("progress_msg") or doc.get("run") or "failed"
        return f"Document '{label}' failed during ingestion: {reason}."
    if doc["status"] == PROCESSING:
        return f"Document '{label}' is still processing: progress {doc['progress']:.2f}, run {doc.get('run') or 'unknown'}."
    return f"Document '{label}' is not ready for retrieval."


def _overall_status(statuses: list[str]) -> str:
    if not statuses:
        return UNKNOWN
    for status in (MISSING, FAILED, EMPTY, PROCESSING, UNKNOWN):
        if status in statuses:
            return status
    return READY


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


def _dataset_label(report: dict[str, Any]) -> str:
    return str(report.get("name") or report.get("dataset_id") or "unknown dataset")


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
