from __future__ import annotations

from typing import Any

from pska_essential.capabilities import product_capabilities
from pska_essential.contracts import to_jsonable
from pska_essential.diagnostics import build_runtime_diagnostics
from pska_essential.workspace_status import build_workspace_status


ALPHA_READINESS_SCHEMA = "pska.alpha_readiness.v1"
ALPHA_TRIAL_GUIDE_SCHEMA = "pska.alpha_trial_guide.v1"


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


def build_alpha_trial_guide(
    *,
    service: Any,
    gateway: Any,
    kb_gateway_factory: Any | None = None,
    dataset_page_size: int = 30,
    review_limit: int = 50,
    workflow_limit: int = 50,
) -> dict[str, Any]:
    """Return a guided first-run plan derived from alpha readiness.

    The guide is intentionally read-only. It translates readiness checks into
    a user-facing trial path without registering roots, scanning files, applying
    memory, or writing source annotations.
    """

    gateway_factory = kb_gateway_factory or (lambda: gateway)
    readiness = build_alpha_readiness(
        service=service,
        gateway=gateway,
        kb_gateway_factory=gateway_factory,
        dataset_page_size=dataset_page_size,
        review_limit=review_limit,
        workflow_limit=workflow_limit,
    )
    return build_alpha_trial_guide_from_readiness(readiness)


def build_alpha_trial_guide_from_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    checks = {str(check.get("code") or ""): check for check in readiness.get("checks") or []}
    status = str(readiness.get("status") or "not_ready")
    phases = _trial_phases(checks=checks, readiness_status=status)
    return {
        "schema": ALPHA_TRIAL_GUIDE_SCHEMA,
        "readiness_schema": readiness.get("schema") or ALPHA_READINESS_SCHEMA,
        "readiness_status": status,
        "trial_mode": _trial_mode(status),
        "can_start_owner_dogfooding": status in {"alpha_ready", "technical_alpha", "technical_alpha_only"},
        "can_start_guided_trial": status in {"alpha_ready", "technical_alpha"},
        "audience": readiness.get("audience") or _audience(status),
        "summary": readiness.get("summary") or {},
        "first_run_scope": {
            "permission_mode": "read_only",
            "recommended_sources": ["one small local folder", "one Obsidian vault subset", "one curated KB dataset"],
            "avoid_on_first_run": [
                "full_disk_scan",
                "native_source_writeback",
                "automatic_duplicate_cleanup",
                "direct_durable_memory_write",
            ],
        },
        "guardrails": _trial_guardrails(),
        "phases": phases,
        "next_actions": _trial_next_actions(readiness=readiness, phases=phases),
        "exit_criteria": _trial_exit_criteria(),
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_memory_directly": False,
            "executes_trial_steps": False,
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
        "user_trial_ux": ("run_guided_alpha_checklist", "Run guided alpha checklist", "pska_alpha_trial_guide", "GET /api/alpha/trial-guide", "settings"),
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


def _trial_mode(status: str) -> str:
    return {
        "alpha_ready": "guided_alpha",
        "technical_alpha": "guided_technical_alpha",
        "technical_alpha_only": "owner_dogfooding_only",
        "not_ready": "development_only",
    }.get(status, "development_only")


def _trial_phases(*, checks: dict[str, dict[str, Any]], readiness_status: str) -> list[dict[str, Any]]:
    return [
        _trial_phase(
            phase_id="environment",
            title="Configure runtime",
            goal="Confirm providers, workspace identity, and KB gateway before user data enters the system.",
            check_codes=["runtime_diagnostics", "provider_configuration", "workspace_context", "kb_gateway"],
            checks=checks,
            steps=[
                _trial_step("inspect_runtime", "Inspect runtime diagnostics", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
                _trial_step("configure_providers", "Configure non-fake providers for live trial", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
                _trial_step("configure_workspace", "Set workspace and tenant identity", "pska_workspace_status", "GET /api/workspace/status", "settings"),
            ],
        ),
        _trial_phase(
            phase_id="knowledge_scope",
            title="Prepare one knowledge scope",
            goal="Start with a small, named, read-only scope that can be searched and cited.",
            check_codes=["kb_readiness"],
            checks=checks,
            steps=[
                _trial_step("register_source_root", "Register one read-only source root", "pska_source_root_register", "POST /api/sources/roots", "sources"),
                _trial_step("scan_source_root", "Scan the root into rebuildable metadata", "pska_source_scan", "POST /api/sources/roots/{root_id}/scan", "sources"),
                _trial_step("verify_scope", "Verify KB readiness for the selected scope", "pska_workspace_status", "GET /api/workspace/status", "kb"),
            ],
        ),
        _trial_phase(
            phase_id="first_read_only_run",
            title="Run a sourced Ask",
            goal="Answer one real question from the prepared scope and inspect citations before creating memory.",
            check_codes=["runtime_diagnostics", "kb_gateway", "kb_readiness", "source_safety"],
            checks=checks,
            steps=[
                _trial_step("run_ask", "Run Ask against the ready scope", "pska_agentic_question_start", "POST /api/ask", "ask"),
                _trial_step("inspect_sources", "Open cited source snippets", "pska_source_read", "POST /api/sources/read", "writing"),
                _trial_step("export_brief", "Export a traceable brief only after sourced output exists", "pska_export_brief", "GET /api/workflows/{run_id}/export", "writing"),
            ],
        ),
        _trial_phase(
            phase_id="memory_review",
            title="Review memory before apply",
            goal="Convert only explicit, source-backed, or user-approved claims into durable memory.",
            check_codes=["memory_governance", "memory_health", "review_queue_load"],
            checks=checks,
            steps=[
                _trial_step("inspect_review_queue", "Inspect pending memory reviews", "pska_memory_review_queue", "GET /api/memory/review-queue", "review"),
                _trial_step("inspect_memory_cards", "Inspect existing Memory Cards and health", "pska_memory_health_scan", "GET /api/memory/health", "memory"),
                _trial_step("apply_accepted_only", "Apply only accepted reviews", "pska_memory_apply", "POST /api/reviews/{review_id}/apply", "review"),
            ],
        ),
        _trial_phase(
            phase_id="writeback_pilot",
            title="Pilot writeback only after backup",
            goal="Keep the first trial read-only; test tag/comment/MOC writeback only with explicit permission and backups.",
            check_codes=["source_safety", "memory_governance"],
            checks=checks,
            default_status="needs_attention",
            steps=[
                _trial_step("propose_tag", "Create a tag proposal before source writeback", "pska_source_tag_propose", "POST /api/sources/tags/proposals", "sources"),
                _trial_step("prefer_sidecar", "Apply sidecar annotations before native writes", "pska_source_tag_apply", "POST /api/sources/tags/{proposal_id}/apply", "sources"),
                _trial_step("native_write_after_backup", "Use native Obsidian writeback only after backup verification", "pska_obsidian_moc_apply", "POST /api/sources/obsidian/moc/{proposal_id}/apply", "sources"),
            ],
        ),
        _trial_phase(
            phase_id="broader_alpha",
            title="Expand beyond one user",
            goal="Move beyond owner dogfooding only after warnings are closed and recovery paths are rehearsed.",
            check_codes=[
                "provider_configuration",
                "workspace_context",
                "kb_readiness",
                "memory_health",
                "review_queue_load",
                "user_trial_ux",
            ],
            checks=checks,
            default_status=_broader_alpha_phase_status(readiness_status),
            steps=[
                _trial_step("run_component_check", "Run component acceptance check", "pska_component_check", "POST /api/runtime/component-check", "settings"),
                _trial_step("rehearse_recovery", "Rehearse backup, restore, and rollback steps", "pska_alpha_trial_guide", "GET /api/alpha/trial-guide", "settings"),
                _trial_step("rerun_readiness", "Rerun alpha readiness before inviting users", "pska_alpha_readiness", "GET /api/alpha/readiness", "settings"),
            ],
        ),
    ]


def _trial_phase(
    *,
    phase_id: str,
    title: str,
    goal: str,
    check_codes: list[str],
    checks: dict[str, dict[str, Any]],
    steps: list[dict[str, Any]],
    default_status: str = "ready",
) -> dict[str, Any]:
    selected = [checks[code] for code in check_codes if code in checks]
    status = _phase_status(selected, default_status=default_status)
    blockers = [
        str(check.get("code") or "")
        for check in selected
        if check.get("required") and check.get("status") == "fail"
    ]
    warnings = [
        str(check.get("code") or "")
        for check in selected
        if check.get("status") == "warn"
    ]
    return {
        "phase_id": phase_id,
        "title": title,
        "status": status,
        "goal": goal,
        "check_codes": check_codes,
        "blockers": blockers,
        "warnings": warnings,
        "steps": steps,
    }


def _phase_status(checks: list[dict[str, Any]], *, default_status: str) -> str:
    if any(check.get("required") and check.get("status") == "fail" for check in checks):
        return "blocked"
    if any(check.get("status") == "fail" for check in checks):
        return "blocked"
    if default_status != "ready":
        return default_status
    if any(check.get("status") == "warn" for check in checks):
        return "needs_attention"
    return "ready"


def _broader_alpha_phase_status(readiness_status: str) -> str:
    if readiness_status == "alpha_ready":
        return "ready"
    if readiness_status == "technical_alpha":
        return "needs_attention"
    return "blocked"


def _trial_step(step_id: str, label: str, tool: str, api: str, view: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "label": label,
        "tool": tool,
        "api": api,
        "view": view,
    }


def _trial_guardrails() -> list[dict[str, Any]]:
    return [
        {
            "guardrail": "read_only_first_run",
            "required": True,
            "message": "The first user trial should register and scan sources without editing source files.",
        },
        {
            "guardrail": "review_before_durable_memory",
            "required": True,
            "message": "Durable memory should come from accepted reviews, not hidden extraction.",
        },
        {
            "guardrail": "backup_before_native_writeback",
            "required": True,
            "message": "Native Obsidian/tag/comment/MOC writes need an operator-verified backup first.",
        },
        {
            "guardrail": "no_cleanup_apply",
            "required": True,
            "message": "Duplicate cleanup remains proposal-only; do not delete, move, merge, or archive files.",
        },
    ]


def _trial_next_actions(*, readiness: dict[str, Any], phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = list(readiness.get("next_actions") or [])
    phase_actions = {
        "environment": ("inspect_trial_environment", "Inspect trial environment", "pska_runtime_diagnostics", "GET /api/runtime/diagnostics", "settings"),
        "knowledge_scope": ("prepare_first_scope", "Prepare first knowledge scope", "pska_workspace_status", "GET /api/workspace/status", "kb"),
        "first_read_only_run": ("run_first_read_only_ask", "Run first read-only Ask", "pska_agentic_question_start", "POST /api/ask", "ask"),
        "memory_review": ("review_memory_before_apply", "Review memory queue", "pska_memory_review_queue", "GET /api/memory/review-queue", "review"),
        "writeback_pilot": ("keep_writeback_locked", "Keep writeback locked until backup is verified", "pska_alpha_trial_guide", "GET /api/alpha/trial-guide", "settings"),
        "broader_alpha": ("close_alpha_warnings", "Close readiness warnings before broader alpha", "pska_alpha_readiness", "GET /api/alpha/readiness", "settings"),
    }
    seen = {str(action.get("action") or "") for action in actions}
    for phase in phases:
        if phase.get("status") == "ready":
            continue
        action, label, tool, api, view = phase_actions[str(phase.get("phase_id") or "")]
        if action in seen:
            continue
        actions.append(
            {
                "action": action,
                "label": label,
                "reason": str(phase.get("goal") or ""),
                "tool": tool,
                "api": api,
                "view": view,
                "params": {"phase_id": phase.get("phase_id")},
            }
        )
        seen.add(action)
    return actions


def _trial_exit_criteria() -> list[dict[str, Any]]:
    return [
        {
            "criterion": "single_scope_read_only_run_completed",
            "evidence": ["sourced Ask artifact", "source citations inspected", "export generated only after source trace exists"],
        },
        {
            "criterion": "memory_review_rehearsed",
            "evidence": ["pending Review inspected", "accepted-only apply path verified", "memory health scan reviewed"],
        },
        {
            "criterion": "recovery_rehearsed",
            "evidence": ["workspace backup location known", "native writeback rollback path documented", "operator can rerun readiness"],
        },
    ]


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
