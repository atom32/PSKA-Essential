from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any

from pska_essential.capabilities import adapter_slots_contract


TRACE_COVERAGE_SCHEMA = "pska.trace_coverage.v1"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


CATEGORY_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "ask",
        "label": "Ask And Answer",
        "actions": (
            "agentic_loop.start",
            "agentic_loop.complete",
            "workflow.export",
            "hermes.answer_proof",
        ),
        "required_when_active": ("agentic_loop.start", "agentic_loop.complete"),
        "recommended_probe": "Run a scoped Ask through Hermes WebUI or pska_agentic_question_start.",
    },
    {
        "id": "source",
        "label": "Source Recall",
        "actions": (
            "context.retrieve",
            "source.root.register",
            "source.scan",
            "source.search",
            "source.read",
            "source.neighbors",
            "source.collection.resolve",
            "retrieval.probe",
            "kb.ingest",
            "kb.parse",
            "kb.graph_read",
        ),
        "required_when_active": (
            "context.retrieve",
            "source.search",
            "source.read",
            "retrieval.probe",
            "kb.ingest",
            "kb.parse",
            "kb.graph_read",
        ),
        "required_mode": "any",
        "recommended_probe": "Run pska_source_search and pska_source_read, or run the governed_context eval.",
    },
    {
        "id": "memory",
        "label": "Memory",
        "actions": (
            "memory.search",
            "memory.card.get",
            "memory.card.list",
            "memory.apply",
            "memory.update",
            "memory.delete",
            "memory.use_trace.list",
            "memory.why_used",
            "memory.timeline",
            "memory.health.scan",
            "memory.conversation_change",
            "memory.review_queue",
        ),
        "required_when_active": ("memory.search",),
        "recommended_probe": "Run pska_memory_search or pska_memory_probe.",
    },
    {
        "id": "writeback",
        "label": "Governed Writeback",
        "actions": (
            "source.tag.propose",
            "source.tag.apply",
            "source.comment.propose",
            "source.comment.apply",
            "source.obsidian_moc.propose",
            "source.obsidian_moc.apply",
            "proposal.create",
            "review.create",
            "review.decide",
            "review.revise",
            "review.merge_candidates",
            "memory.apply",
            "memory.update",
            "memory.delete",
        ),
        "required_when_active": (
            "source.tag.propose",
            "source.comment.propose",
            "source.obsidian_moc.propose",
            "proposal.create",
            "review.create",
            "memory.apply",
            "memory.update",
            "memory.delete",
        ),
        "required_mode": "any",
        "recommended_probe": "Create a source tag/comment proposal or a governed memory review.",
    },
    {
        "id": "eval",
        "label": "Evaluation",
        "actions": ("eval.run",),
        "required_when_active": ("eval.run",),
        "recommended_probe": "Run pska_eval_run('governed_context') or POST /api/runtime/eval.",
    },
    {
        "id": "job",
        "label": "Background Jobs",
        "actions": (
            "source.audit_job.enqueue",
            "source.audit_job.due",
            "source.audit_job.run",
            "source.extraction_job.enqueue",
            "source.extraction_job.run",
            "digest.job.enqueue",
            "digest.job.run",
            "source.watch.once",
        ),
        "required_when_active": (
            "source.audit_job.enqueue",
            "source.audit_job.run",
            "source.extraction_job.enqueue",
            "source.extraction_job.run",
            "digest.job.enqueue",
            "digest.job.run",
            "source.watch.once",
        ),
        "required_mode": "any",
        "recommended_probe": "Run an audit/extraction/digest job tick from Settings or MCP.",
    },
)


def build_trace_coverage(service: Any, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Summarize whether recent governed operations are recoverable from audit traces."""

    selected_limit = min(MAX_LIMIT, max(1, int(limit)))
    events = list(service.store.list_audit_events(limit=selected_limit, descending=True))
    categories = [_category_status(rule, events) for rule in CATEGORY_RULES]
    needs_attention = [item for item in categories if item["status"] == "needs_attention"]
    covered = [item for item in categories if item["status"] == "covered"]
    observed = [item for item in categories if item["status"] != "no_recent_sample"]
    return {
        "schema": TRACE_COVERAGE_SCHEMA,
        "status": "needs_attention" if needs_attention else "ok",
        "window": {
            "requested_limit": selected_limit,
            "event_count": len(events),
            "oldest_created_at": events[-1].created_at if events else "",
            "newest_created_at": events[0].created_at if events else "",
        },
        "summary": {
            "checked_category_count": len(categories),
            "covered_category_count": len(covered),
            "observed_category_count": len(observed),
            "missing_required_action_count": sum(len(item["missing_required_actions"]) for item in needs_attention),
            "recent_action_count": len({event.action for event in events}),
        },
        "categories": categories,
        "adapter_slots": _observability_adapter_slots(),
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "creates_review": False,
            "exports_external_trace": False,
            "embedding_required": False,
            "agent_can_override_internal_flow": False,
        },
        "next_actions": _next_actions(categories),
    }


def _category_status(rule: dict[str, Any], events: list[Any]) -> dict[str, Any]:
    action_set = set(rule["actions"])
    matching = [event for event in events if event.action in action_set]
    observed_actions = sorted({event.action for event in matching})
    required_actions = list(rule["required_when_active"])
    required_mode = str(rule.get("required_mode") or "all")
    if not matching:
        status = "no_recent_sample"
        missing_required_actions: list[str] = []
        message = "No recent audit sample for this category."
    else:
        missing_required_actions = _missing_required_actions(observed_actions, required_actions, required_mode)
        status = "covered" if not missing_required_actions else "needs_attention"
        message = (
            "Recent operations have recoverable PSKA trace ids."
            if status == "covered"
            else "Recent operations exist, but expected trace actions are missing."
        )
    return {
        "id": str(rule["id"]),
        "label": str(rule["label"]),
        "status": status,
        "message": message,
        "observed_actions": observed_actions,
        "required_when_active": required_actions,
        "required_mode": required_mode,
        "missing_required_actions": missing_required_actions,
        "sample_trace_ids": [event.audit_event_id for event in matching[:5]],
        "sample_events": [_sample_event(event) for event in matching[:5]],
        "recommended_probe": str(rule["recommended_probe"]),
    }


def _missing_required_actions(
    observed_actions: list[str],
    required_actions: list[str],
    required_mode: str,
) -> list[str]:
    observed = set(observed_actions)
    required = set(required_actions)
    if required_mode == "any":
        return [] if observed & required else required_actions
    return [action for action in required_actions if action not in observed]


def _sample_event(event: Any) -> dict[str, Any]:
    metadata = dict(getattr(event, "metadata", {}) or {})
    return {
        "trace_id": str(getattr(event, "audit_event_id", "") or ""),
        "action": str(getattr(event, "action", "") or ""),
        "target_type": str(getattr(event, "target_type", "") or ""),
        "target_id": str(getattr(event, "target_id", "") or ""),
        "created_at": str(getattr(event, "created_at", "") or ""),
        "status": str(metadata.get("status") or ""),
        "run_id": str(metadata.get("run_id") or ""),
        "review_id": str(metadata.get("review_id") or ""),
        "proposal_id": str(metadata.get("proposal_id") or ""),
        "memory_id": str(metadata.get("memory_target_id") or metadata.get("memory_id") or ""),
        "source_path": str(metadata.get("path") or ""),
        "source_id": str(metadata.get("source_id") or metadata.get("document_id") or ""),
    }


def _observability_adapter_slots() -> dict[str, Any]:
    providers = []
    for provider in adapter_slots_contract()["slots"]["observability"].get("providers", []):
        item = dict(provider)
        module = str(item.get("python_module") or item.get("module") or "")
        if module:
            item["runtime"] = _python_package_status(module, str(item.get("extra") or ""))
        elif item.get("name") == "sqlite_audit":
            item["runtime"] = {"status": "available", "installed": True, "version": "", "module": ""}
        providers.append(item)
    return {
        "contract": "ObservabilityPort",
        "default_provider": "sqlite_audit",
        "providers": providers,
    }


def _python_package_status(module: str, extra: str = "") -> dict[str, Any]:
    installed = importlib.util.find_spec(module) is not None
    version = ""
    if installed:
        try:
            version = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
    return {
        "module": module,
        "installed": installed,
        "version": version,
        "status": "available" if installed else "unavailable",
        "install_hint": f"pip install -e '.[{extra}]'" if extra else "",
    }


def _next_actions(categories: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for category in categories:
        if category["status"] == "needs_attention":
            actions.append(
                {
                    "category": category["id"],
                    "action": "inspect_trace_query",
                    "message": (
                        "Use pska_trace_query filtered by the missing action or run the recommended probe "
                        "to regenerate an auditable sample."
                    ),
                }
            )
    for category in categories:
        if category["status"] == "no_recent_sample":
            actions.append(
                {
                    "category": category["id"],
                    "action": "generate_sample",
                    "message": category["recommended_probe"],
                }
            )
    if not actions:
        actions.append(
            {
                "category": "observability",
                "action": "optional_external_trace",
                "message": "Keep sqlite_audit as the source of truth; add OpenTelemetry or Phoenix only for external trace export.",
            }
        )
    return actions[:8]
