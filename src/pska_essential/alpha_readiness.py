from __future__ import annotations

from typing import Any

from pska_essential.capabilities import product_capabilities
from pska_essential.contracts import to_jsonable
from pska_essential.diagnostics import build_runtime_diagnostics
from pska_essential.workspace_status import build_workspace_status


ALPHA_READINESS_SCHEMA = "pska.alpha_readiness.v1"


def build_alpha_readiness(
    *,
    service: Any,
    gateway: Any,
    kb_gateway_factory: Any | None = None,
    dataset_page_size: int = 30,
    review_limit: int = 50,
    workflow_limit: int = 50,
) -> dict[str, Any]:
    """Return a product-level alpha trial readiness report.

    This is a read-only gate for operators and agents. It says whether the
    current instance is ready for self-dogfooding, technical alpha trial, or
    ordinary user trial. It does not run provider writes or closed-loop probes.
    """

    gateway_factory = kb_gateway_factory or (lambda: gateway)
    diagnostics = build_runtime_diagnostics(service=service, kb_gateway_factory=gateway_factory)
    workspace_status = build_workspace_status(
        service=service,
        gateway=gateway,
        dataset_page_size=dataset_page_size,
        review_limit=review_limit,
        workflow_limit=workflow_limit,
    )
    capabilities = product_capabilities(memory_adapter=service.memory)
    checks = _checks(diagnostics=diagnostics, workspace_status=workspace_status, capabilities=capabilities)
    summary = _summary(checks)
    status = _status(summary)
    return {
        "schema": ALPHA_READINESS_SCHEMA,
        "status": status,
        "audience": _audience(status),
        "summary": summary,
        "checks": checks,
        "next_actions": _next_actions(checks),
        "inputs": {
            "diagnostics_status": diagnostics.get("status") or "unknown",
            "workspace_status": workspace_status.get("status") or "unknown",
        },
        "safety": {
            "writes_source_files_by_default": False,
            "writes_memory_directly_by_default": False,
            "requires_review_for_durable_memory": True,
            "intended_first_run_mode": "read_only",
        },
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_memory_directly": False,
            "runs_closed_loop_probe": False,
        },
    }


def _checks(*, diagnostics: dict[str, Any], workspace_status: dict[str, Any], capabilities: dict[str, Any]) -> list[dict[str, Any]]:
    providers = diagnostics.get("providers") or {}
    source_safety = ((capabilities.get("source_layer") or {}).get("safety") or {})
    memory_operations = (((capabilities.get("memory") or {}).get("operations")) or {})
    memory_review_queue = ((capabilities.get("memory") or {}).get("review_queue_view") or {})
    tool_policy = ((capabilities.get("tool_policy") or {}).get("tools") or {})
    diagnostics_checks = {str(item.get("name") or ""): item for item in diagnostics.get("checks") or []}
    kb = workspace_status.get("kb") or {}
    reviews = workspace_status.get("reviews") or {}
    memory = workspace_status.get("memory") or {}
    checks = [
        _check(
            "runtime_diagnostics",
            _map_runtime_status(str(diagnostics.get("status") or "unknown")),
            "Runtime diagnostics are available.",
            required=True,
            evidence={"status": diagnostics.get("status") or "unknown"},
        ),
        _check(
            "provider_configuration",
            _provider_configuration_status(providers),
            _provider_configuration_message(providers),
            required=True,
            evidence={"providers": providers},
        ),
        _check(
            "workspace_context",
            "pass" if (workspace_status.get("workspace") or {}).get("workspace_configured") else "warn",
            (
                "Workspace identity is configured."
                if (workspace_status.get("workspace") or {}).get("workspace_configured")
                else "Workspace identity is using defaults; suitable for local trial but not multi-user alpha."
            ),
            required=False,
            evidence={"workspace": workspace_status.get("workspace") or {}},
        ),
        _check(
            "kb_gateway",
            _diagnostic_check_status(diagnostics_checks.get("kb_gateway")),
            _diagnostic_check_message(diagnostics_checks.get("kb_gateway"), "Knowledge base gateway check is missing."),
            required=True,
            evidence={"kb": kb},
        ),
        _check(
            "kb_readiness",
            _kb_readiness_status(kb),
            _kb_readiness_message(kb),
            required=False,
            evidence={
                "dataset_count": kb.get("dataset_count", 0),
                "ready_dataset_count": kb.get("ready_dataset_count", 0),
                "blocked_dataset_count": kb.get("blocked_dataset_count", 0),
            },
        ),
        _check(
            "source_safety",
            "pass"
            if source_safety.get("scans_full_disk_by_default") is False
            and source_safety.get("writes_source_files_by_default") is False
            and source_safety.get("delete_move_merge_supported") is False
            else "fail",
            "Source layer defaults are read-only and non-destructive.",
            required=True,
            evidence=source_safety,
        ),
        _check(
            "memory_governance",
            _memory_governance_status(memory_operations, memory_review_queue, tool_policy),
            "Durable memory writes are review/apply governed.",
            required=True,
            evidence={
                "apply_supported": (memory_operations.get("apply") or {}).get("supported"),
                "review_queue_schema": memory_review_queue.get("schema") or "",
                "memory_apply_policy": tool_policy.get("pska_memory_apply") or {},
            },
        ),
        _check(
            "memory_health",
            _memory_health_status(memory),
            _memory_health_message(memory),
            required=False,
            evidence={
                "health_summary": (((memory.get("health") or {}).get("summary")) or {}),
                "cards_error": memory.get("cards_error"),
                "health_error": memory.get("health_error"),
            },
        ),
        _check(
            "review_queue_load",
            "pass" if int(reviews.get("candidate_quality_issue_count") or 0) == 0 else "warn",
            _review_queue_message(reviews),
            required=False,
            evidence={
                "pending_count": reviews.get("pending_count", 0),
                "accepted_unapplied_count": reviews.get("accepted_unapplied_count", 0),
                "candidate_quality_issue_count": reviews.get("candidate_quality_issue_count", 0),
            },
        ),
        _check(
            "user_trial_ux",
            "warn",
            "Alpha UX is usable as an operator console, but first-run onboarding, backups, and guided recovery are still incomplete.",
            required=False,
            evidence={
                "webui": "operator_console",
                "missing": ["first_run_wizard", "writeback_backup_restore", "guided_recovery"],
            },
        ),
    ]
    return checks


def _summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = str(check.get("status") or "warn")
        if status in counts:
            counts[status] += 1
    required_failures = [check for check in checks if check.get("required") and check.get("status") == "fail"]
    return {
        "check_count": len(checks),
        "pass_count": counts["pass"],
        "warn_count": counts["warn"],
        "fail_count": counts["fail"],
        "required_failure_count": len(required_failures),
        "required_failures": [check["code"] for check in required_failures],
    }


def _status(summary: dict[str, Any]) -> str:
    if summary["required_failure_count"]:
        return "not_ready"
    if summary["fail_count"]:
        return "technical_alpha_only"
    if summary["warn_count"]:
        return "technical_alpha"
    return "alpha_ready"


def _audience(status: str) -> str:
    return {
        "alpha_ready": "technical alpha users",
        "technical_alpha": "owner dogfooding and technical alpha users with guidance",
        "technical_alpha_only": "owner dogfooding only until failed optional checks are fixed",
        "not_ready": "development/demo only",
    }.get(status, "development/demo only")


def _next_actions(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for check in checks:
        if check.get("status") == "pass":
            continue
        code = str(check.get("code") or "")
        actions.append(_action_for_check(code, check))
    return actions


def _action_for_check(code: str, check: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "runtime_diagnostics": ("inspect_runtime_diagnostics", "Open runtime diagnostics", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
        "provider_configuration": ("configure_live_providers", "Configure live providers", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
        "workspace_context": ("configure_workspace_identity", "Configure workspace identity", "pska_workspace_status", "GET /api/workspace/status", "settings"),
        "kb_gateway": ("fix_kb_gateway", "Fix KB gateway", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
        "kb_readiness": ("prepare_knowledge_scope", "Prepare a ready knowledge scope", "pska_workspace_status", "GET /api/workspace/status", "kb"),
        "source_safety": ("inspect_source_safety", "Inspect source safety policy", "pska_capabilities_get", "GET /api/capabilities", "sources"),
        "memory_governance": ("inspect_memory_governance", "Inspect memory governance", "pska_capabilities_get", "GET /api/capabilities", "memory"),
        "memory_health": ("inspect_memory_health", "Inspect memory health", "pska_memory_health_scan", "GET /api/memory/health", "memory"),
        "review_queue_load": ("inspect_memory_review_queue", "Inspect memory review queue", "pska_memory_review_queue", "GET /api/memory/review-queue", "review"),
        "user_trial_ux": ("run_guided_alpha_checklist", "Run guided alpha checklist", "pska_alpha_readiness", "GET /api/alpha/readiness", "settings"),
    }
    action, label, tool, api, view = mapping.get(code, ("inspect_alpha_readiness", "Inspect alpha readiness", "pska_alpha_readiness", "GET /api/alpha/readiness", "settings"))
    return {
        "action": action,
        "label": label,
        "reason": str(check.get("message") or ""),
        "tool": tool,
        "api": api,
        "view": view,
        "params": {"check": code},
    }


def _check(code: str, status: str, message: str, *, required: bool, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "severity": "critical" if required and status == "fail" else ("warning" if status == "warn" else "info"),
        "required": required,
        "message": message,
        "evidence": to_jsonable(evidence or {}),
    }


def _map_runtime_status(status: str) -> str:
    if status == "error":
        return "fail"
    if status == "warning":
        return "warn"
    if status == "ok":
        return "pass"
    return "warn"


def _provider_configuration_status(providers: dict[str, Any]) -> str:
    if providers.get("dev_fake"):
        return "warn"
    configured = [str(providers.get(name) or "").lower() for name in ("kb", "retrieval", "memory")]
    if any(provider == "fake" for provider in configured):
        return "warn"
    return "pass"


def _provider_configuration_message(providers: dict[str, Any]) -> str:
    if providers.get("dev_fake"):
        return "Fake providers are explicitly enabled; suitable for demo/dev, not unsupervised alpha users."
    if any(str(providers.get(name) or "").lower() == "fake" for name in ("kb", "retrieval", "memory")):
        return "A fake provider is configured; use only for demo/dev until live providers are configured."
    return "Configured providers are not fake."


def _diagnostic_check_status(check: dict[str, Any] | None) -> str:
    if not check:
        return "fail"
    return _map_runtime_status(str(check.get("status") or "unknown"))


def _diagnostic_check_message(check: dict[str, Any] | None, fallback: str) -> str:
    return str((check or {}).get("message") or fallback)


def _kb_readiness_status(kb: dict[str, Any]) -> str:
    if kb.get("error"):
        return "fail"
    if int(kb.get("ready_dataset_count") or 0) > 0:
        return "pass"
    if int(kb.get("dataset_count") or 0) > 0:
        return "warn"
    return "warn"


def _kb_readiness_message(kb: dict[str, Any]) -> str:
    if kb.get("error"):
        return f"Knowledge scope status has an error: {(kb.get('error') or {}).get('message') or 'unknown error'}"
    if int(kb.get("ready_dataset_count") or 0) > 0:
        return "At least one knowledge scope is ready for read-only Ask/retrieval trial."
    if int(kb.get("dataset_count") or 0) > 0:
        return "Knowledge datasets exist but none are ready yet."
    return "No knowledge dataset is registered yet; alpha users need a guided first-run ingest path."


def _memory_governance_status(
    memory_operations: dict[str, Any],
    memory_review_queue: dict[str, Any],
    tool_policy: dict[str, Any],
) -> str:
    apply_policy = tool_policy.get("pska_memory_apply") or {}
    if not (memory_operations.get("apply") or {}).get("supported"):
        return "fail"
    if memory_review_queue.get("schema") != "pska.memory_review_queue_view.v1":
        return "fail"
    if apply_policy.get("requires_accepted_review") is not True:
        return "fail"
    return "pass"


def _memory_health_status(memory: dict[str, Any]) -> str:
    if memory.get("cards_error") or memory.get("health_error"):
        return "warn"
    health = memory.get("health") or {}
    if int(health.get("issue_count") or 0) > 0:
        return "warn"
    return "pass"


def _memory_health_message(memory: dict[str, Any]) -> str:
    if memory.get("cards_error"):
        return f"Memory Card inventory has an error: {(memory.get('cards_error') or {}).get('message') or 'unknown error'}"
    if memory.get("health_error"):
        return f"Memory health scan has an error: {(memory.get('health_error') or {}).get('message') or 'unknown error'}"
    health = memory.get("health") or {}
    issue_count = int(health.get("issue_count") or 0)
    if issue_count:
        return f"{issue_count} memory health issue(s) should be reviewed before a broader alpha trial."
    return "Memory Card inventory and health scan are usable."


def _review_queue_message(reviews: dict[str, Any]) -> str:
    quality_count = int(reviews.get("candidate_quality_issue_count") or 0)
    pending_count = int(reviews.get("pending_count") or 0)
    accepted_count = int(reviews.get("accepted_unapplied_count") or 0)
    if quality_count:
        return f"{quality_count} low-quality memory candidate(s) should be repaired before alpha trial."
    if pending_count or accepted_count:
        return f"{pending_count} pending and {accepted_count} accepted-unapplied review(s) remain; this is acceptable for guided alpha."
    return "Review queue has no low-quality memory candidates."
