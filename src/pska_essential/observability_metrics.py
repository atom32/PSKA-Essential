from __future__ import annotations

import hashlib
from typing import Any

from pska_essential.capabilities import adapter_slots_contract
from pska_essential.contracts import utc_now_iso


OBSERVABILITY_METRICS_SCHEMA = "pska.observability_metrics.v1"
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
SAMPLE_LIMIT = 5


GROUP_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "source_extraction",
        "label": "Source Extraction",
        "actions": ("source.extraction_job.enqueue", "source.extraction_job.run"),
        "zero_result_keys": (),
    },
    {
        "id": "source_recall",
        "label": "Source Recall",
        "actions": (
            "context.retrieve",
            "source.search",
            "source.read",
            "source.neighbors",
            "source.collection.resolve",
            "retrieval.probe",
            "closed_loop.probe",
        ),
        "zero_result_keys": ("count", "context_count", "source_count", "source_inspection_count"),
    },
    {
        "id": "duplicate_review",
        "label": "Duplicate Review",
        "actions": (
            "source.duplicate_report",
            "source.duplicate_review.list",
            "source.duplicate_group.mark",
            "source.duplicate_cleanup.propose",
        ),
        "zero_result_keys": ("group_count", "duplicate_file_count", "count", "candidate_count"),
    },
    {
        "id": "eval",
        "label": "Evaluation",
        "actions": ("eval.run", "source.recall_eval.run"),
        "zero_result_keys": (),
    },
    {
        "id": "answer_proof",
        "label": "Answer Proof",
        "actions": ("hermes.answer_proof", "hermes.answer_proof.list"),
        "zero_result_keys": (),
    },
    {
        "id": "memory_use",
        "label": "Memory Use",
        "actions": (
            "memory.search",
            "memory.card.get",
            "memory.card.list",
            "memory.use_trace.list",
            "memory.why_used",
            "memory.timeline",
            "memory.health.scan",
            "memory.review_queue",
            "memory.probe",
        ),
        "zero_result_keys": ("count", "raw_count", "memory_count"),
    },
    {
        "id": "memory_governance",
        "label": "Memory Governance",
        "actions": (
            "proposal.create",
            "review.create",
            "review.decide",
            "review.revise",
            "review.merge_candidates",
            "memory.refresh_review.create",
            "memory.conversation_candidates.create",
            "memory.conversation_change",
            "memory.apply",
            "memory.update",
            "memory.delete",
        ),
        "zero_result_keys": (),
    },
)


def build_observability_metrics(service: Any, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Aggregate PSKA audit events into a read-only operational metrics view."""

    selected_limit = min(MAX_LIMIT, max(1, int(limit)))
    events = list(service.store.list_audit_events(limit=selected_limit, descending=True))
    groups = [_build_group(rule, events) for rule in GROUP_RULES]
    summary = _summary(groups, events)
    return {
        "schema": OBSERVABILITY_METRICS_SCHEMA,
        "status": _overall_status(summary, events),
        "generated_at": utc_now_iso(),
        "window": {
            "requested_limit": selected_limit,
            "event_count": len(events),
            "oldest_created_at": events[-1].created_at if events else "",
            "newest_created_at": events[0].created_at if events else "",
        },
        "summary": summary,
        "groups": groups,
        "adapter_slots": _observability_adapter_slots(),
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "runs_jobs": False,
            "activates_due_jobs": False,
            "creates_review": False,
            "exports_external_trace": False,
            "embedding_required": False,
            "agent_can_override_internal_flow": False,
        },
        "next_actions": _next_actions(groups),
    }


def _build_group(rule: dict[str, Any], events: list[Any]) -> dict[str, Any]:
    actions = tuple(str(action) for action in rule["actions"])
    matching = [event for event in events if event.action in actions]
    failed = [event for event in matching if _event_failed(event)]
    zero_result = [
        event
        for event in matching
        if _event_zero_result(event, tuple(str(key) for key in rule.get("zero_result_keys", ())))
    ]
    status = _group_status(rule["id"], matching, failed, zero_result)
    metrics = _group_metrics(str(rule["id"]), matching, failed, zero_result)
    return {
        "id": str(rule["id"]),
        "label": str(rule["label"]),
        "status": status,
        "message": _group_message(str(rule["id"]), status, metrics),
        "actions": list(actions),
        "action_counts": _action_counts(matching),
        "metrics": metrics,
        "samples": [_event_sample(event) for event in matching[:SAMPLE_LIMIT]],
        "failure_samples": [_event_sample(event) for event in failed[:SAMPLE_LIMIT]],
        "zero_result_samples": [_event_sample(event) for event in zero_result[:SAMPLE_LIMIT]],
    }


def _group_metrics(
    group_id: str,
    events: list[Any],
    failed: list[Any],
    zero_result: list[Any],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "event_count": len(events),
        "failed_event_count": len(failed),
        "zero_result_event_count": len(zero_result),
    }
    if group_id == "source_extraction":
        run_events = [event for event in events if event.action == "source.extraction_job.run"]
        metrics.update(
            {
                "enqueue_count": _action_counts(events).get("source.extraction_job.enqueue", 0),
                "run_count": len(run_events),
                "completed_count": sum(1 for event in run_events if _metadata_status(event) in {"completed", "ok"}),
                "failed_count": len(failed),
                "failure_rate": _ratio(len(failed), len(run_events)),
            }
        )
    elif group_id == "source_recall":
        metrics.update(
            {
                "search_count": _action_counts(events).get("source.search", 0),
                "read_count": _action_counts(events).get("source.read", 0),
                "context_retrieve_count": _action_counts(events).get("context.retrieve", 0),
                "retrieval_probe_count": _action_counts(events).get("retrieval.probe", 0),
                "returned_context_count": sum(_first_int(event, ("count", "context_count")) for event in events),
            }
        )
    elif group_id == "duplicate_review":
        status_counts = _metadata_value_counts(events, "status")
        metrics.update(
            {
                "report_count": _action_counts(events).get("source.duplicate_report", 0),
                "review_list_count": _action_counts(events).get("source.duplicate_review.list", 0),
                "group_mark_count": _action_counts(events).get("source.duplicate_group.mark", 0),
                "cleanup_proposal_count": _action_counts(events).get("source.duplicate_cleanup.propose", 0),
                "reported_group_count": sum(_first_int(event, ("group_count",)) for event in events),
                "reported_duplicate_file_count": sum(_first_int(event, ("duplicate_file_count",)) for event in events),
                "cleanup_candidate_count": sum(_first_int(event, ("candidate_count",)) for event in events),
                "review_status_counts": status_counts,
            }
        )
    elif group_id == "eval":
        metrics.update(
            {
                "ok_count": sum(1 for event in events if _metadata_bool(event, "ok") is True),
                "failed_count": len(failed),
                "source_recall_eval_count": _action_counts(events).get("source.recall_eval.run", 0),
                "suite_counts": _metadata_value_counts(events, "suite"),
                "failed_step_count": sum(len(_metadata_list(event, "failed_steps")) for event in events),
            }
        )
    elif group_id == "answer_proof":
        metrics.update(
            {
                "proof_count": _action_counts(events).get("hermes.answer_proof", 0),
                "list_count": _action_counts(events).get("hermes.answer_proof.list", 0),
                "failed_check_count": sum(_first_int(event, ("failed_check_count",)) for event in events),
                "passed_check_count": sum(_first_int(event, ("passed_check_count",)) for event in events),
                "write_like_tool_event_count": sum(_first_int(event, ("write_like_tool_count",)) for event in events),
            }
        )
    elif group_id == "memory_use":
        metrics.update(
            {
                "search_count": _action_counts(events).get("memory.search", 0),
                "card_inspection_count": _action_counts(events).get("memory.card.get", 0)
                + _action_counts(events).get("memory.card.list", 0),
                "why_used_count": _action_counts(events).get("memory.why_used", 0),
                "returned_memory_count": sum(_first_int(event, ("count", "memory_count")) for event in events),
            }
        )
    elif group_id == "memory_governance":
        status_counts = _metadata_value_counts(events, "status")
        decision_counts = _metadata_value_counts(events, "decision")
        metrics.update(
            {
                "review_create_count": _action_counts(events).get("review.create", 0),
                "review_decide_count": _action_counts(events).get("review.decide", 0),
                "merge_candidate_count": _action_counts(events).get("review.merge_candidates", 0),
                "memory_apply_count": _action_counts(events).get("memory.apply", 0),
                "memory_update_count": _action_counts(events).get("memory.update", 0),
                "memory_delete_count": _action_counts(events).get("memory.delete", 0),
                "status_counts": status_counts,
                "decision_counts": decision_counts,
            }
        )
    return metrics


def _summary(groups: list[dict[str, Any]], events: list[Any]) -> dict[str, Any]:
    group_statuses = _value_counts([str(group["status"]) for group in groups])
    action_counts = _action_counts(events)
    return {
        "group_count": len(groups),
        "observed_group_count": sum(1 for group in groups if group["status"] != "no_recent_signal"),
        "event_count": len(events),
        "recent_action_count": len(action_counts),
        "attention_group_count": group_statuses.get("needs_attention", 0),
        "action_required_group_count": group_statuses.get("action_required", 0),
        "no_recent_signal_group_count": group_statuses.get("no_recent_signal", 0),
        "failed_event_count": sum(int(group["metrics"].get("failed_event_count") or 0) for group in groups),
        "zero_result_event_count": sum(int(group["metrics"].get("zero_result_event_count") or 0) for group in groups),
        "source_extraction_failure_count": _metric(groups, "source_extraction", "failed_count"),
        "source_recall_zero_result_count": _metric(groups, "source_recall", "zero_result_event_count"),
        "duplicate_cleanup_proposal_count": _metric(groups, "duplicate_review", "cleanup_proposal_count"),
        "eval_failed_count": _metric(groups, "eval", "failed_count"),
        "answer_failed_check_count": _metric(groups, "answer_proof", "failed_check_count"),
        "memory_search_count": _metric(groups, "memory_use", "search_count"),
    }


def _overall_status(summary: dict[str, Any], events: list[Any]) -> str:
    if not events:
        return "no_recent_signal"
    if summary["attention_group_count"] or summary["failed_event_count"] or summary["answer_failed_check_count"]:
        return "needs_attention"
    if summary["action_required_group_count"] or summary["zero_result_event_count"]:
        return "action_required"
    return "ok"


def _group_status(group_id: str, events: list[Any], failed: list[Any], zero_result: list[Any]) -> str:
    if not events:
        return "no_recent_signal"
    if failed:
        return "needs_attention"
    if group_id == "answer_proof" and sum(_first_int(event, ("failed_check_count",)) for event in events) > 0:
        return "needs_attention"
    if group_id == "eval" and any(_metadata_list(event, "failed_steps") for event in events):
        return "needs_attention"
    if group_id == "duplicate_review":
        reported = sum(_first_int(event, ("group_count",)) for event in events)
        proposed = sum(1 for event in events if event.action == "source.duplicate_cleanup.propose")
        if reported or proposed:
            return "action_required"
    if zero_result:
        return "action_required"
    return "ok"


def _group_message(group_id: str, status: str, metrics: dict[str, Any]) -> str:
    if status == "no_recent_signal":
        return "No recent audit signal in this window."
    if status == "needs_attention":
        if group_id == "source_extraction":
            return "Recent source extraction had failed runs."
        if group_id == "eval":
            return "Recent evaluation reported failed checks or steps."
        if group_id == "answer_proof":
            return "Recent Hermes answer proof reported failed evidence checks."
        return "Recent events include failures."
    if status == "action_required":
        if group_id == "source_recall":
            return "Recent retrieval/search returned zero results in at least one call."
        if group_id == "duplicate_review":
            return "Recent duplicate findings or cleanup proposals need human review."
        if group_id == "memory_use":
            return "Recent memory search returned zero results in at least one call."
        return "Recent events have follow-up work."
    return "Recent events look healthy."


def _next_actions(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    by_id = {str(group["id"]): group for group in groups}
    extraction = by_id.get("source_extraction") or {}
    if extraction.get("status") == "needs_attention":
        actions.append(
            {
                "action": "inspect_source_extraction_failures",
                "label": "Inspect failed extraction jobs",
                "api": "GET /api/sources/extraction-jobs",
                "mcp": "pska_source_extract_job_list",
            }
        )
    recall = by_id.get("source_recall") or {}
    if recall.get("status") == "action_required":
        actions.append(
            {
                "action": "evaluate_source_search",
                "label": "Run source recall evaluation",
                "api": "GET /api/sources/search-index-evaluation",
                "mcp": "pska_search_index_evaluation",
            }
        )
    duplicate = by_id.get("duplicate_review") or {}
    if duplicate.get("status") == "action_required":
        actions.append(
            {
                "action": "review_duplicate_groups",
                "label": "Review duplicate groups",
                "api": "GET /api/sources/duplicates/review",
                "mcp": "pska_duplicate_review_list",
            }
        )
    eval_group = by_id.get("eval") or {}
    if eval_group.get("status") in {"needs_attention", "no_recent_signal"}:
        actions.append(
            {
                "action": "run_governed_context_eval",
                "label": "Run governed-context eval",
                "api": "POST /api/runtime/eval",
                "mcp": "pska_eval_run",
            }
        )
    answer = by_id.get("answer_proof") or {}
    if answer.get("status") == "needs_attention":
        actions.append(
            {
                "action": "inspect_answer_proofs",
                "label": "Inspect Hermes answer proof failures",
                "api": "GET /api/hermes/answer-proofs",
                "mcp": "pska_hermes_answer_proofs",
            }
        )
    return actions[:6]


def _event_failed(event: Any) -> bool:
    status = _metadata_status(event)
    metadata = dict(getattr(event, "metadata", {}) or {})
    if status in {"failed", "failure", "error", "exception", "cancelled", "blocked", "needs_attention"}:
        return True
    if _metadata_bool(event, "ok") is False:
        return True
    if metadata.get("error_type") or metadata.get("error"):
        return True
    return False


def _event_zero_result(event: Any, keys: tuple[str, ...]) -> bool:
    if not keys:
        return False
    metadata = dict(getattr(event, "metadata", {}) or {})
    for key in keys:
        if key in metadata and _to_int(metadata.get(key)) == 0:
            return True
    return False


def _metadata_status(event: Any) -> str:
    metadata = dict(getattr(event, "metadata", {}) or {})
    return str(metadata.get("status") or metadata.get("last_status") or "").strip().lower()


def _metadata_bool(event: Any, key: str) -> bool | None:
    metadata = dict(getattr(event, "metadata", {}) or {})
    if key not in metadata:
        return None
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "ok"}:
            return True
        if lowered in {"0", "false", "no", "error", "failed"}:
            return False
    return None


def _metadata_list(event: Any, key: str) -> list[Any]:
    metadata = dict(getattr(event, "metadata", {}) or {})
    value = metadata.get(key)
    return value if isinstance(value, list) else []


def _metadata_value_counts(events: list[Any], key: str) -> dict[str, int]:
    values: list[str] = []
    for event in events:
        metadata = dict(getattr(event, "metadata", {}) or {})
        value = str(metadata.get(key) or "").strip()
        if value:
            values.append(value)
    return _value_counts(values)


def _value_counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _action_counts(events: list[Any]) -> dict[str, int]:
    return _value_counts([str(getattr(event, "action", "") or "") for event in events])


def _metric(groups: list[dict[str, Any]], group_id: str, key: str) -> int:
    for group in groups:
        if group["id"] == group_id:
            return int(group["metrics"].get(key) or 0)
    return 0


def _first_int(event: Any, keys: tuple[str, ...]) -> int:
    metadata = dict(getattr(event, "metadata", {}) or {})
    for key in keys:
        if key in metadata:
            return _to_int(metadata.get(key))
    return 0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _event_sample(event: Any) -> dict[str, Any]:
    metadata = dict(getattr(event, "metadata", {}) or {})
    query = str(metadata.get("query") or metadata.get("question") or "")
    error_message = str(metadata.get("error_message") or metadata.get("error") or metadata.get("message") or "")
    return {
        "trace_id": str(getattr(event, "audit_event_id", "") or ""),
        "action": str(getattr(event, "action", "") or ""),
        "target_type": str(getattr(event, "target_type", "") or ""),
        "target_id": str(getattr(event, "target_id", "") or ""),
        "created_at": str(getattr(event, "created_at", "") or ""),
        "status": _metadata_status(event),
        "query_preview": _preview(query),
        "query_sha256": _sha256(query),
        "count": _first_int(event, ("count", "context_count", "source_count", "memory_count")),
        "group_count": _first_int(event, ("group_count",)),
        "duplicate_file_count": _first_int(event, ("duplicate_file_count",)),
        "failed_check_count": _first_int(event, ("failed_check_count",)),
        "error_type": str(metadata.get("error_type") or ""),
        "error_message": _preview(error_message),
        "source_id": str(metadata.get("source_id") or metadata.get("document_id") or ""),
        "source_path": str(metadata.get("path") or ""),
        "review_id": str(metadata.get("review_id") or ""),
        "proposal_id": str(metadata.get("proposal_id") or ""),
        "run_id": str(metadata.get("run_id") or ""),
    }


def _preview(text: str, limit: int = 160) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _sha256(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _observability_adapter_slots() -> dict[str, Any]:
    slots = adapter_slots_contract()["slots"].get("observability", {})
    return {
        "contract": slots.get("contract") or "ObservabilityPort",
        "default_provider": slots.get("default_provider") or "sqlite_audit",
        "providers": list(slots.get("providers") or []),
        "current_provider": "sqlite_audit",
        "current_storage": "PSKA audit ledger",
    }
