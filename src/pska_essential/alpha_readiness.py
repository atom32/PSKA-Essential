from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.capabilities import product_capabilities
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.diagnostics import build_runtime_diagnostics
from pska_essential.runtime_context import build_runtime_workspace_context
from pska_essential.workspace_status import build_workspace_status


ALPHA_READINESS_SCHEMA = "pska.alpha_readiness.v1"
ALPHA_TRIAL_GUIDE_SCHEMA = "pska.alpha_trial_guide.v1"
ALPHA_RECOVERY_PLAN_SCHEMA = "pska.alpha_recovery_plan.v1"
ALPHA_FIRST_RUN_SESSION_SCHEMA = "pska.alpha_first_run_session.v1"


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


def build_alpha_recovery_plan(*, service: Any, gateway: Any) -> dict[str, Any]:
    """Return a read-only backup/recovery plan for alpha trials."""

    workspace = build_runtime_workspace_context().to_dict()
    providers = {
        "kb": str(getattr(gateway, "backend_name", "") or os.getenv("PSKA_KB_PROVIDER", "") or "unknown"),
        "retrieval": str(getattr(service.retrieval, "backend_name", "") or os.getenv("PSKA_RETRIEVAL_PROVIDER", "") or "unknown"),
        "memory": str(getattr(service.memory, "backend_name", "") or os.getenv("PSKA_MEMORY_PROVIDER", "") or "unknown"),
        "source_registry": str(getattr(getattr(service, "source_registry", None), "backend_name", "") or "unconfigured"),
        "review_store": type(service.store).__name__,
    }
    backup_items = _recovery_backup_items(service=service, providers=providers)
    restore_drills = _recovery_drills(backup_items=backup_items, providers=providers)
    warnings = _recovery_warnings(backup_items=backup_items, providers=providers, workspace=workspace)
    return {
        "schema": ALPHA_RECOVERY_PLAN_SCHEMA,
        "status": "needs_rehearsal" if warnings else "ready",
        "purpose": "backup_restore_rehearsal_before_writeback_or_broader_alpha",
        "workspace": workspace,
        "providers": providers,
        "backup_items": backup_items,
        "restore_drills": restore_drills,
        "writeback_preflight": _writeback_preflight(),
        "operator_checklist": _operator_checklist(warnings),
        "warnings": warnings,
        "next_actions": _recovery_next_actions(warnings),
        "data_flow": {
            "read_only": True,
            "creates_backup": False,
            "restores_data": False,
            "writes_source_files": False,
            "writes_memory_directly": False,
            "executes_provider_export": False,
        },
    }


def build_alpha_first_run_session(
    *,
    service: Any,
    gateway: Any,
    session_id: str = "default",
) -> dict[str, Any]:
    """Return a persisted alpha first-run checklist session."""

    selected = _normalize_session_id(session_id)
    stored = service.store.get_alpha_session(selected) if hasattr(service.store, "get_alpha_session") else None
    recovery_plan = build_alpha_recovery_plan(service=service, gateway=gateway)
    guide = build_alpha_trial_guide(service=service, gateway=gateway)
    checklist = _first_run_checklist(guide=guide, recovery_plan=recovery_plan, stored=stored or {})
    session = _session_payload(
        session_id=selected,
        guide=guide,
        recovery_plan=recovery_plan,
        checklist=checklist,
        stored=stored or {},
    )
    if not stored and hasattr(service.store, "save_alpha_session"):
        saved = service.store.save_alpha_session(session)
        service.store.add_audit_event(
            audit_event(
                "alpha.first_run_session.create",
                "alpha_session",
                selected,
                checklist_count=len(checklist),
                writes_source_files=False,
                writes_memory_directly=False,
            )
        )
        return saved
    return session


def update_alpha_first_run_session(
    *,
    service: Any,
    gateway: Any,
    session_id: str = "default",
    item_id: str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    """Persist one first-run checklist item decision.

    This records operator progress only. It does not execute the underlying
    trial step, write source files, create backups, or apply memory.
    """

    selected = _normalize_session_id(session_id)
    current = build_alpha_first_run_session(service=service, gateway=gateway, session_id=selected)
    checklist = list(current.get("checklist") or [])
    item = _checklist_item_by_id(checklist, item_id)
    normalized_status = _normalize_item_status(status)
    item["status"] = normalized_status
    item["note"] = str(note or "")
    item["updated_at"] = utc_now_iso()
    current["checklist"] = checklist
    current["progress"] = _session_progress(checklist)
    current["status"] = _session_status(current["progress"])
    current["data_flow"] = _first_run_session_data_flow()
    saved = service.store.save_alpha_session(current)
    service.store.add_audit_event(
        audit_event(
            "alpha.first_run_session.update",
            "alpha_session",
            selected,
            item_id=item["item_id"],
            item_status=normalized_status,
            writes_source_files=False,
            writes_memory_directly=False,
            executes_trial_step=False,
        )
    )
    return saved


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


def _first_run_checklist(
    *,
    guide: dict[str, Any],
    recovery_plan: dict[str, Any],
    stored: dict[str, Any],
) -> list[dict[str, Any]]:
    stored_items = {str(item.get("item_id") or ""): item for item in stored.get("checklist") or []}
    items = [
        _first_run_item(
            "confirm_runtime",
            "Confirm runtime and providers",
            "Inspect runtime diagnostics and provider configuration.",
            "pska_runtime_diagnostics",
            "GET /api/runtime/diagnostics",
            "settings",
            required=True,
        ),
        _first_run_item(
            "confirm_recovery_plan",
            "Confirm backup and recovery plan",
            "Review PSKA-local backups, provider-owned backup boundaries, and restore drills.",
            "pska_alpha_recovery_plan",
            "GET /api/alpha/recovery-plan",
            "settings",
            required=True,
        ),
        _first_run_item(
            "select_read_only_scope",
            "Select one read-only scope",
            "Choose a small local folder, Obsidian subset, or curated KB dataset.",
            "pska_workspace_status",
            "GET /api/workspace/status",
            "sources",
            required=True,
        ),
        _first_run_item(
            "run_sourced_ask",
            "Run one sourced Ask",
            "Ask one real question and inspect citations before creating memory.",
            "pska_agentic_question_start",
            "POST /api/ask",
            "ask",
            required=True,
        ),
        _first_run_item(
            "review_memory_queue",
            "Inspect Memory Review queue",
            "Verify durable memory remains review/apply governed.",
            "pska_memory_review_queue",
            "GET /api/memory/review-queue",
            "review",
            required=True,
        ),
        _first_run_item(
            "keep_writeback_locked",
            "Keep native writeback locked",
            "Do not apply native tag/comment/MOC writes until source backup is verified.",
            "pska_alpha_recovery_plan",
            "GET /api/alpha/recovery-plan",
            "settings",
            required=True,
        ),
        _first_run_item(
            "record_exit_notes",
            "Record exit notes",
            "Capture whether the first run is safe to repeat or should stay owner-only.",
            "pska_alpha_trial_guide",
            "GET /api/alpha/trial-guide",
            "home",
            required=False,
        ),
    ]
    phase_status = {str(phase.get("phase_id") or ""): str(phase.get("status") or "") for phase in guide.get("phases") or []}
    if phase_status.get("knowledge_scope") == "blocked":
        items[2]["status"] = "blocked"
    if phase_status.get("first_read_only_run") == "blocked":
        items[3]["status"] = "blocked"
    if recovery_plan.get("status") != "ready":
        items[1]["status"] = "needs_attention"
    for item in items:
        stored_item = stored_items.get(item["item_id"])
        if not stored_item:
            continue
        if str(stored_item.get("status") or "") in _FIRST_RUN_ITEM_STATUSES:
            item["status"] = str(stored_item.get("status"))
        item["note"] = str(stored_item.get("note") or "")
        if stored_item.get("updated_at"):
            item["updated_at"] = stored_item["updated_at"]
    return items


def _first_run_item(
    item_id: str,
    label: str,
    description: str,
    tool: str,
    api: str,
    view: str,
    *,
    required: bool,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "label": label,
        "description": description,
        "status": "pending",
        "required": required,
        "tool": tool,
        "api": api,
        "view": view,
        "note": "",
        "updated_at": "",
    }


def _session_payload(
    *,
    session_id: str,
    guide: dict[str, Any],
    recovery_plan: dict[str, Any],
    checklist: list[dict[str, Any]],
    stored: dict[str, Any],
) -> dict[str, Any]:
    progress = _session_progress(checklist)
    workspace = build_runtime_workspace_context().to_dict()
    now = utc_now_iso()
    return {
        "schema": ALPHA_FIRST_RUN_SESSION_SCHEMA,
        "session_id": session_id,
        "status": _session_status(progress),
        "trial_mode": guide.get("trial_mode") or "development_only",
        "readiness_status": guide.get("readiness_status") or "not_ready",
        "recovery_status": recovery_plan.get("status") or "needs_rehearsal",
        "workspace_id": workspace["workspace_id"],
        "tenant_id": workspace["tenant_id"],
        "created_at": stored.get("created_at") or now,
        "updated_at": stored.get("updated_at") or now,
        "progress": progress,
        "checklist": checklist,
        "next_actions": _first_run_next_actions(checklist),
        "data_flow": _first_run_session_data_flow(),
    }


def _session_progress(checklist: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(checklist)
    done = sum(1 for item in checklist if item.get("status") == "done")
    blocked = sum(1 for item in checklist if item.get("status") == "blocked")
    skipped_required = sum(1 for item in checklist if item.get("required") and item.get("status") == "skipped")
    required_items = [item for item in checklist if item.get("required")]
    required_done = sum(1 for item in required_items if item.get("status") == "done")
    return {
        "total_count": total,
        "done_count": done,
        "blocked_count": blocked,
        "required_count": len(required_items),
        "required_done_count": required_done,
        "skipped_required_count": skipped_required,
        "percent": round(done / total, 4) if total else 0,
    }


def _session_status(progress: dict[str, Any]) -> str:
    if int(progress.get("blocked_count") or 0) or int(progress.get("skipped_required_count") or 0):
        return "blocked"
    if int(progress.get("required_count") or 0) and progress.get("required_done_count") == progress.get("required_count"):
        return "ready_for_repetition"
    if int(progress.get("done_count") or 0):
        return "in_progress"
    return "not_started"


def _first_run_next_actions(checklist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in checklist:
        if item.get("status") in {"pending", "needs_attention", "blocked"}:
            return [
                {
                    "action": "open_first_run_item",
                    "label": item.get("label") or "Open checklist item",
                    "reason": item.get("description") or "",
                    "tool": item.get("tool") or "",
                    "api": item.get("api") or "",
                    "view": item.get("view") or "home",
                    "params": {"item_id": item.get("item_id")},
                }
            ]
    return [
        {
            "action": "rerun_alpha_readiness",
            "label": "Rerun alpha readiness",
            "reason": "First-run checklist is complete; verify readiness before repeating the trial.",
            "tool": "pska_alpha_readiness",
            "api": "GET /api/alpha/readiness",
            "view": "settings",
            "params": {},
        }
    ]


def _first_run_session_data_flow() -> dict[str, Any]:
    return {
        "writes_checklist_state": True,
        "writes_pska_ledger": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "executes_trial_step": False,
        "creates_backup": False,
        "restores_data": False,
    }


_FIRST_RUN_ITEM_STATUSES = {"pending", "needs_attention", "done", "skipped", "blocked"}


def _normalize_item_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    aliases = {"complete": "done", "completed": "done", "todo": "pending", "skip": "skipped"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in _FIRST_RUN_ITEM_STATUSES:
        raise ValueError("status must be one of: pending, needs_attention, done, skipped, blocked")
    return normalized


def _checklist_item_by_id(checklist: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    selected = str(item_id or "").strip()
    for item in checklist:
        if item.get("item_id") == selected:
            return item
    raise ValueError(f"unknown alpha first-run checklist item: {selected}")


def _normalize_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    return normalized or "default"


def _recovery_backup_items(*, service: Any, providers: dict[str, str]) -> list[dict[str, Any]]:
    items = [
        _sqlite_backup_item(
            item_id="review_store",
            label="Review, workflow, and audit ledger",
            path=getattr(service.store, "path", ""),
            owner="pska",
            reason="Contains workflows, proposals, Review decisions, memory apply records, and audit events.",
        ),
    ]
    source_registry = getattr(service, "source_registry", None)
    if source_registry is not None:
        items.append(
            _sqlite_backup_item(
                item_id="source_registry",
                label="Personal source registry and rebuildable FTS index",
                path=getattr(source_registry, "path", ""),
                owner="pska",
                reason="Contains registered roots, indexed metadata, source sections, saved searches, collections, duplicate review state, and sidecar proposal metadata.",
                rebuildable=True,
            )
        )
    memory_path = getattr(service.memory, "path", "")
    if providers["memory"] == "sqlite" or memory_path:
        items.append(
            _sqlite_backup_item(
                item_id="sqlite_memory",
                label="SQLite durable memory provider",
                path=memory_path or os.getenv("PSKA_MEMORY_DB", ""),
                owner="pska",
                reason="Contains governed durable Memory Cards when PSKA_MEMORY_PROVIDER=sqlite.",
            )
        )
    else:
        items.append(
            _external_backup_item(
                item_id="external_memory_provider",
                label=f"{providers['memory']} memory provider",
                owner="provider",
                reason="Durable memory lives outside PSKA local SQLite; use the provider's export, snapshot, or backup process.",
                required_before=["durable_memory_apply", "memory_update", "memory_delete"],
            )
        )
    items.append(
        _external_backup_item(
            item_id="kb_provider",
            label=f"{providers['kb']} knowledge base provider",
            owner="provider",
            reason="Datasets, chunks, embeddings, and provider document records are owned by the KB backend; PSKA can re-upload known source files but does not snapshot provider internals.",
            required_before=["dataset_delete", "broad_reingest", "broader_alpha_invite"],
        )
    )
    items.append(
        {
            "item_id": "user_source_roots",
            "label": "User-owned source folders and Obsidian vaults",
            "owner": "user",
            "kind": "filesystem_source",
            "path": "",
            "exists": None,
            "backup_method": "user_filesystem_backup_or_vcs",
            "restore_method": "restore original files or vault from user backup, then rerun PSKA source scan",
            "rebuildable_from_source": False,
            "required_before": ["native_source_writeback", "obsidian_frontmatter", "obsidian_comment", "obsidian_moc"],
            "reason": "These files are canonical user data. PSKA source indices are rebuildable, but native writeback modifies the user's files.",
        }
    )
    return items


def _sqlite_backup_item(
    *,
    item_id: str,
    label: str,
    path: str,
    owner: str,
    reason: str,
    rebuildable: bool = False,
) -> dict[str, Any]:
    normalized = str(path or "")
    return {
        "item_id": item_id,
        "label": label,
        "owner": owner,
        "kind": "sqlite",
        "path": normalized,
        "exists": _path_exists(normalized),
        "backup_method": "sqlite_online_backup_or_copy_when_service_stopped",
        "restore_method": "stop PSKA, restore the sqlite file, restart Product API, rerun diagnostics",
        "rebuildable_from_source": rebuildable,
        "required_before": ["guided_alpha", "writeback_pilot", "durable_memory_apply"],
        "reason": reason,
    }


def _external_backup_item(
    *,
    item_id: str,
    label: str,
    owner: str,
    reason: str,
    required_before: list[str],
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "label": label,
        "owner": owner,
        "kind": "external_provider",
        "path": "",
        "exists": None,
        "backup_method": "provider_export_snapshot_or_documented_restore",
        "restore_method": "restore through provider tooling, then rerun PSKA readiness and probes",
        "rebuildable_from_source": False,
        "required_before": required_before,
        "reason": reason,
    }


def _path_exists(path: str) -> bool | None:
    if not path:
        return False
    if path == ":memory:":
        return False
    return Path(path).exists()


def _recovery_drills(*, backup_items: list[dict[str, Any]], providers: dict[str, str]) -> list[dict[str, Any]]:
    drills = [
        {
            "drill_id": "copy_pska_local_state",
            "status": "manual",
            "goal": "Verify PSKA-owned ledgers can be backed up before alpha work.",
            "covers": [
                item["item_id"]
                for item in backup_items
                if item.get("owner") == "pska" and item.get("kind") == "sqlite"
            ],
            "steps": [
                "Stop Product API or use SQLite online backup.",
                "Copy review/source/memory SQLite files that exist.",
                "Restart Product API and rerun alpha readiness.",
            ],
        },
        {
            "drill_id": "restore_pska_local_state",
            "status": "manual",
            "goal": "Prove a copied PSKA ledger can be restored without touching source files.",
            "covers": ["review_store", "source_registry", "sqlite_memory"],
            "steps": [
                "Start from a copy in a throwaway workspace.",
                "Restore SQLite files to the configured paths.",
                "Run workspace status, memory health, and trace query spot checks.",
            ],
        },
        {
            "drill_id": "provider_restore_boundary",
            "status": "provider_owned",
            "goal": "Confirm external KB and memory providers have their own backup path.",
            "covers": ["kb_provider", "external_memory_provider"],
            "steps": [
                f"Use {providers['kb']} tooling for dataset/document/chunk backup when applicable.",
                f"Use {providers['memory']} tooling for durable memory backup when applicable.",
                "Rerun PSKA diagnostics after provider restore.",
            ],
        },
        {
            "drill_id": "native_writeback_rollback",
            "status": "manual",
            "goal": "Confirm a source-root backup can reverse native tag/comment/MOC writes.",
            "covers": ["user_source_roots"],
            "steps": [
                "Create a file-level backup or VCS checkpoint outside PSKA.",
                "Apply one explicit writeback proposal in a small test folder.",
                "Restore the file from backup and rerun source scan.",
            ],
        },
    ]
    return drills


def _recovery_warnings(
    *,
    backup_items: list[dict[str, Any]],
    providers: dict[str, str],
    workspace: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for item in backup_items:
        if item.get("owner") == "pska" and item.get("kind") == "sqlite" and item.get("exists") is False:
            warnings.append(
                {
                    "code": f"{item['item_id']}_not_materialized",
                    "severity": "warning",
                    "message": f"{item['label']} does not exist on disk yet; create state or configure a persistent path before relying on restore.",
                    "item_id": item["item_id"],
                }
            )
    if providers["memory"] not in {"sqlite", "fake"}:
        warnings.append(
            {
                "code": "external_memory_backup_provider_owned",
                "severity": "warning",
                "message": "Memory provider backup is outside PSKA; rehearse provider export/restore before durable memory changes.",
                "item_id": "external_memory_provider",
            }
        )
    if providers["kb"] not in {"fake", "unknown"}:
        warnings.append(
            {
                "code": "kb_backup_provider_owned",
                "severity": "warning",
                "message": "KB datasets/chunks/embeddings are provider-owned; PSKA can describe scope but cannot snapshot provider internals.",
                "item_id": "kb_provider",
            }
        )
    if not workspace.get("workspace_configured"):
        warnings.append(
            {
                "code": "workspace_identity_default",
                "severity": "warning",
                "message": "Workspace identity is still default; set PSKA_WORKSPACE_ID before multi-user or long-lived alpha trials.",
                "item_id": "workspace",
            }
        )
    return warnings


def _writeback_preflight() -> list[dict[str, Any]]:
    return [
        {
            "operation": "sidecar_annotation",
            "minimum_backup": "PSKA source registry backup",
            "human_confirmation": "confirm sidecar target and proposal diff",
            "allowed_first_trial": True,
        },
        {
            "operation": "obsidian_frontmatter_tags",
            "minimum_backup": "Obsidian vault file backup or VCS checkpoint",
            "human_confirmation": "confirm native write target and changed file list",
            "allowed_first_trial": False,
        },
        {
            "operation": "obsidian_markdown_comment",
            "minimum_backup": "Obsidian vault file backup or VCS checkpoint",
            "human_confirmation": "confirm inserted PSKA Comment block",
            "allowed_first_trial": False,
        },
        {
            "operation": "obsidian_moc",
            "minimum_backup": "Obsidian vault file backup or VCS checkpoint",
            "human_confirmation": "confirm generated MOC marker block",
            "allowed_first_trial": False,
        },
        {
            "operation": "duplicate_cleanup",
            "minimum_backup": "not supported by PSKA alpha",
            "human_confirmation": "cleanup remains proposal-only",
            "allowed_first_trial": False,
        },
    ]


def _operator_checklist(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item": "persistent_local_state",
            "status": "needs_attention" if any("not_materialized" in str(w.get("code")) for w in warnings) else "ready",
            "message": "Use persistent SQLite paths for review, source registry, and SQLite memory before relying on restore.",
        },
        {
            "item": "provider_backup_documented",
            "status": "needs_attention" if any("provider_owned" in str(w.get("code")) for w in warnings) else "ready",
            "message": "Document provider-side backup/export for KB and non-SQLite memory providers.",
        },
        {
            "item": "source_writeback_backup",
            "status": "needs_attention",
            "message": "Before native source writeback, create a user-visible folder/vault backup or VCS checkpoint.",
        },
        {
            "item": "restore_rehearsal",
            "status": "needs_attention",
            "message": "Rehearse one restore in a throwaway workspace before inviting broader alpha users.",
        },
    ]


def _recovery_next_actions(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "backup_pska_local_state",
            "label": "Back up PSKA local state",
            "reason": "Copy review/source/memory SQLite files or configure persistent paths before trial.",
            "tool": "pska_alpha_recovery_plan",
            "api": "GET /api/alpha/recovery-plan",
            "view": "settings",
            "params": {"drill_id": "copy_pska_local_state"},
        },
        {
            "action": "document_provider_backups",
            "label": "Document provider backups",
            "reason": "KB and external memory providers need their own export/snapshot process.",
            "tool": "pska_alpha_recovery_plan",
            "api": "GET /api/alpha/recovery-plan",
            "view": "settings",
            "params": {"drill_id": "provider_restore_boundary"},
        },
        {
            "action": "verify_source_writeback_backup",
            "label": "Verify source writeback backup",
            "reason": "Native source writes require a folder/vault backup or VCS checkpoint.",
            "tool": "pska_alpha_recovery_plan",
            "api": "GET /api/alpha/recovery-plan",
            "view": "sources",
            "params": {"drill_id": "native_writeback_rollback"},
        },
    ]
    if not warnings:
        actions.append(
            {
                "action": "rerun_alpha_trial_guide",
                "label": "Rerun alpha trial guide",
                "reason": "Recovery plan has no warnings; return to the guided trial path.",
                "tool": "pska_alpha_trial_guide",
                "api": "GET /api/alpha/trial-guide",
                "view": "home",
                "params": {},
            }
        )
    return actions


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
                _trial_step("native_write_after_backup", "Use native Obsidian writeback only after backup verification", "pska_alpha_recovery_plan", "GET /api/alpha/recovery-plan", "settings"),
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
                _trial_step("rehearse_recovery", "Rehearse backup, restore, and rollback steps", "pska_alpha_recovery_plan", "GET /api/alpha/recovery-plan", "settings"),
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
        "writeback_pilot": ("keep_writeback_locked", "Keep writeback locked until backup is verified", "pska_alpha_recovery_plan", "GET /api/alpha/recovery-plan", "settings"),
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
