from __future__ import annotations

from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.memory_briefing import build_memory_briefing
from pska_essential.memory_review_queue import build_memory_review_queue
from pska_essential.workspace_status import build_workspace_status


SOURCE_ACTION_APIS = {
    "pska_source_scan": "POST /api/sources/roots/{root_id}/scan",
    "pska_duplicate_report": "POST /api/sources/duplicates",
    "pska_source_audit_run": "POST /api/sources/audits/run",
    "pska_source_read": "POST /api/sources/read",
    "pska_source_memory_review_create": "POST /api/sources/memory-reviews",
    "pska_source_memory_candidates_from_audit": "POST /api/sources/memory-candidates/from-audit",
}


def build_jarvis_briefing(
    *,
    service: Any,
    gateway: Any,
    scope: dict[str, Any] | None = None,
    source_scope: dict[str, Any] | None = None,
    audit_limit: int = 20,
    dataset_page_size: int = 30,
    review_limit: int = 50,
    workflow_limit: int = 50,
) -> dict[str, Any]:
    """Compose PSKA status, source audit, and next actions for Hermes."""

    normalized_scope = dict(scope or {})
    normalized_source_scope = _source_scope(normalized_scope, source_scope)
    workspace_status = build_workspace_status(
        service=service,
        gateway=gateway,
        dataset_page_size=dataset_page_size,
        review_limit=review_limit,
        workflow_limit=workflow_limit,
    )
    roots, source_root_error = _source_roots(service)
    audit, source_audit_error = _source_audit(
        service,
        roots=roots,
        source_scope=normalized_source_scope,
        audit_limit=audit_limit,
    )
    memory_briefing, memory_briefing_error = _memory_briefing(service, normalized_scope)
    memory_review_queue, memory_review_queue_error = _memory_review_queue(service, normalized_scope)
    priorities = _briefing_priorities(
        workspace_status=workspace_status,
        roots=roots,
        source_root_error=source_root_error,
        source_audit=audit,
        source_audit_error=source_audit_error,
        memory_briefing=memory_briefing,
        memory_briefing_error=memory_briefing_error,
        memory_review_queue=memory_review_queue,
        memory_review_queue_error=memory_review_queue_error,
    )
    next_actions = _briefing_next_actions(workspace_status, audit, memory_briefing, memory_review_queue, priorities)
    briefing_id = f"jarvis_{uuid4().hex}"
    status = _briefing_status(priorities, workspace_status)
    briefing = {
        "schema": "pska.jarvis_briefing.v1",
        "briefing_id": briefing_id,
        "created_at": utc_now_iso(),
        "status": status,
        "agent": {
            "primary": "Hermes",
            "role": "orchestrates PSKA tools; does not own source files, memory, or generation policy",
        },
        "scope": normalized_scope,
        "summary": _briefing_summary(
            workspace_status,
            roots,
            audit,
            memory_briefing,
            memory_review_queue,
            priorities,
            next_actions,
        ),
        "priorities": priorities,
        "memory_layer": {
            "briefing": memory_briefing,
            "briefing_error": memory_briefing_error,
            "review_queue": memory_review_queue,
            "review_queue_error": memory_review_queue_error,
        },
        "source_layer": {
            "root_count": len(roots),
            "roots": roots[:10],
            "audit": audit,
            "root_error": source_root_error,
            "audit_error": source_audit_error,
        },
        "workspace_status": workspace_status,
        "next_actions": next_actions,
        "data_flow": {
            "writes_source_files": False,
            "writes_memory_directly": False,
            "embedding_required": False,
            "generates_answer_text": False,
        },
    }
    service.store.add_audit_event(
        audit_event(
            "jarvis.briefing.build",
            "assistant_briefing",
            briefing_id,
            status=status,
            priority_count=len(priorities),
            next_action_count=len(next_actions),
            source_root_count=len(roots),
            source_audit_available=audit is not None,
            memory_briefing_available=memory_briefing is not None,
            memory_focus_count=((memory_briefing or {}).get("summary") or {}).get("focus_count", 0),
            memory_review_queue_available=memory_review_queue is not None,
            memory_review_queue_item_count=((memory_review_queue or {}).get("summary") or {}).get("item_count", 0),
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    return to_jsonable(briefing)


def _source_scope(scope: dict[str, Any], source_scope: dict[str, Any] | None) -> dict[str, Any]:
    if source_scope is not None:
        return dict(source_scope)
    extracted: dict[str, Any] = {}
    for key in ("root_ids", "root_id", "source_kinds", "source_kind"):
        if key in scope:
            extracted[key] = scope[key]
    nested = scope.get("source_scope")
    if isinstance(nested, dict):
        extracted.update(nested)
    return extracted


def _source_roots(service: Any) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    try:
        return service.source_root_list(), None
    except Exception as exc:  # noqa: BLE001 - briefing must surface backend failures.
        return [], {"type": exc.__class__.__name__, "message": str(exc)}


def _source_audit(
    service: Any,
    *,
    roots: list[dict[str, Any]],
    source_scope: dict[str, Any],
    audit_limit: int,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not roots and not source_scope:
        return None, None
    try:
        return service.source_audit_run(source_scope, limit=audit_limit), None
    except Exception as exc:  # noqa: BLE001 - briefing must surface audit failures.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _memory_briefing(service: Any, scope: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        return build_memory_briefing(service, scope=scope, audit=False), None
    except Exception as exc:  # noqa: BLE001 - Jarvis should surface memory layer failures.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _memory_review_queue(service: Any, scope: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        return build_memory_review_queue(service, scope=scope, audit=False), None
    except Exception as exc:  # noqa: BLE001 - Jarvis should surface memory queue failures.
        return None, {"type": exc.__class__.__name__, "message": str(exc)}


def _briefing_priorities(
    *,
    workspace_status: dict[str, Any],
    roots: list[dict[str, Any]],
    source_root_error: dict[str, str] | None,
    source_audit: dict[str, Any] | None,
    source_audit_error: dict[str, str] | None,
    memory_briefing: dict[str, Any] | None,
    memory_briefing_error: dict[str, str] | None,
    memory_review_queue: dict[str, Any] | None,
    memory_review_queue_error: dict[str, str] | None,
) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    if source_root_error:
        priorities.append(
            _priority("critical", "source", "source_root_error", "Source roots could not be listed.", source_root_error["message"])
        )
    if source_audit_error:
        priorities.append(
            _priority("critical", "source", "source_audit_error", "Source audit could not run.", source_audit_error["message"])
        )
    if memory_briefing_error:
        priorities.append(
            _priority(
                "warning",
                "memory",
                "memory_briefing_error",
                "Memory briefing could not run.",
                memory_briefing_error["message"],
            )
        )
    if memory_review_queue_error:
        priorities.append(
            _priority(
                "warning",
                "memory",
                "memory_review_queue_error",
                "Memory review queue could not run.",
                memory_review_queue_error["message"],
            )
        )
    if not roots and not source_root_error:
        priorities.append(
            _priority(
                "setup",
                "source",
                "register_source_root",
                "No personal source root is registered.",
                "Register a local folder or Obsidian vault before Hermes can inspect personal files.",
                next_action={
                    "action": "register_source_root",
                    "tool": "pska_source_root_register",
                    "api": "POST /api/sources/roots",
                    "view": "sources",
                    "requires_input": ["path"],
                },
            )
        )
    if source_audit:
        for root in source_audit.get("roots") or []:
            if root.get("needs_scan"):
                priorities.append(
                    _priority(
                        "warning",
                        "source",
                        "scan_source_root",
                        f"Source root needs scan: {root.get('label') or root.get('absolute_path')}",
                        "The root exists but has no indexed file map yet.",
                    )
                )
        duplicates = source_audit.get("duplicate_preview") or {}
        if duplicates.get("group_count"):
            priorities.append(
                _priority(
                    "warning",
                    "source",
                    "review_duplicates",
                    "Exact duplicate files found.",
                    f"{duplicates.get('group_count')} duplicate group(s), {duplicates.get('duplicate_file_count')} extra file(s).",
                )
            )
        unresolved = source_audit.get("unresolved_links") or {}
        if unresolved.get("count"):
            priorities.append(
                _priority(
                    "warning",
                    "source",
                    "inspect_unresolved_links",
                    "Unresolved Markdown or Obsidian links found.",
                    f"{unresolved.get('count')} link(s) point to missing indexed targets.",
                )
            )
        unlinked = source_audit.get("unlinked_markdown") or {}
        if unlinked.get("count"):
            priorities.append(
                _priority(
                    "info",
                    "source",
                    "inspect_unlinked_notes",
                    "Unlinked Markdown notes found.",
                    f"{unlinked.get('count')} note(s) have no indexed outgoing links or backlinks.",
                )
            )
        routes = source_audit.get("route_candidates") or []
        if routes:
            priorities.append(
                _priority(
                    "info",
                    "memory",
                    "create_source_memory_candidates_from_audit",
                    "Route-like source entry points found.",
                    f"{len(routes)} file(s) look useful as stable source routes.",
                )
            )
    reviews = workspace_status.get("reviews") or {}
    if memory_review_queue:
        queue_summary = memory_review_queue.get("summary") or {}
        if queue_summary.get("accepted_unapplied_count"):
            priorities.append(
                _priority(
                    "warning",
                    "memory",
                    "apply_grouped_memory_reviews",
                    "Accepted memory reviews are grouped and ready to apply.",
                    f"{queue_summary.get('accepted_unapplied_count')} accepted durable review(s) are waiting.",
                    next_action=(memory_review_queue.get("next_actions") or [None])[0],
                )
            )
        elif queue_summary.get("conversation_candidate_count"):
            priorities.append(
                _priority(
                    "warning",
                    "memory",
                    "review_conversation_memory_candidates",
                    "Conversation memory candidates are waiting for review.",
                    f"{queue_summary.get('conversation_candidate_count')} conversation-derived candidate(s) need accept/edit/reject.",
                    next_action=_queue_next_action(
                        memory_review_queue,
                        "review_conversation_memory_candidate",
                        fallback={
                            "action": "inspect_memory_review_queue",
                            "tool": "pska_memory_review_queue",
                            "api": "GET /api/memory/review-queue",
                            "view": "review",
                        },
                    ),
                )
            )
        elif queue_summary.get("related_candidate_group_count"):
            priorities.append(
                _priority(
                    "info",
                    "memory",
                    "inspect_related_memory_candidates",
                    "Related memory candidates may need scope review.",
                    f"{queue_summary.get('related_candidate_group_count')} related candidate group(s) may overlap across scopes.",
                    next_action=_queue_next_action(
                        memory_review_queue,
                        "inspect_related_memory_candidates",
                        fallback={
                            "action": "inspect_memory_review_queue",
                            "tool": "pska_memory_review_queue",
                            "api": "GET /api/memory/review-queue",
                            "view": "review",
                        },
                    ),
                )
            )
        elif queue_summary.get("item_count"):
            priorities.append(
                _priority(
                    "info",
                    "memory",
                    "inspect_memory_review_queue",
                    "Memory review queue has grouped maintenance items.",
                    f"{queue_summary.get('item_count')} item(s) across {queue_summary.get('group_count')} group(s).",
                    next_action={
                        "action": "inspect_memory_review_queue",
                        "tool": "pska_memory_review_queue",
                        "api": "GET /api/memory/review-queue",
                        "view": "review",
                    },
                )
            )
    if memory_briefing:
        memory_summary = memory_briefing.get("summary") or {}
        if memory_summary.get("conflict_issue_count"):
            priorities.append(
                _priority(
                    "warning",
                    "memory",
                    "inspect_memory_conflicts",
                    "Memory conflicts need attention.",
                    f"{memory_summary.get('conflict_issue_count')} conflict issue(s) are in the memory briefing.",
                    next_action={
                        "action": "inspect_memory_briefing",
                        "tool": "pska_memory_briefing",
                        "api": "GET /api/memory/briefing",
                        "view": "memory",
                    },
                )
            )
        elif memory_summary.get("issue_count"):
            priorities.append(
                _priority(
                    "info",
                    "memory",
                    "inspect_memory_briefing",
                    "Memory briefing has review candidates.",
                    f"{memory_summary.get('issue_count')} memory issue(s) need inspection.",
                    next_action={
                        "action": "inspect_memory_briefing",
                        "tool": "pska_memory_briefing",
                        "api": "GET /api/memory/briefing",
                        "view": "memory",
                    },
                )
            )
        elif memory_summary.get("recent_use_count"):
            priorities.append(
                _priority(
                    "info",
                    "memory",
                    "inspect_recent_memory_use",
                    "Recent memory use is available for inspection.",
                    f"{memory_summary.get('recent_use_count')} recent memory trace(s) can be reviewed.",
                )
            )
    if reviews.get("accepted_unapplied_count"):
        priorities.append(
            _priority(
                "warning",
                "memory",
                "apply_accepted_memory",
                "Accepted memory is waiting to apply.",
                f"{reviews.get('accepted_unapplied_count')} accepted review(s) have not been applied.",
            )
        )
    if reviews.get("pending_count"):
        priorities.append(
            _priority(
                "warning",
                "review",
                "review_pending_durable_knowledge",
                "Durable knowledge reviews need attention.",
                f"{reviews.get('pending_count')} review item(s) are pending.",
            )
        )
    if workspace_status.get("status") in {"error", "action_required", "processing", "empty"}:
        first = (workspace_status.get("next_actions") or [{}])[0]
        priorities.append(
            _priority(
                "warning" if workspace_status.get("status") != "error" else "critical",
                "workspace",
                str(first.get("action") or "inspect_workspace_status"),
                "Workspace needs an operational action.",
                str(first.get("reason") or workspace_status.get("status")),
            )
        )
    return priorities


def _queue_next_action(queue: dict[str, Any], action_name: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
    for action in queue.get("next_actions") or []:
        if str(action.get("action") or "") == action_name:
            return dict(action)
    return fallback


def _priority(
    severity: str,
    area: str,
    code: str,
    title: str,
    reason: str,
    *,
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "severity": severity,
        "area": area,
        "code": code,
        "title": title,
        "reason": reason,
    }
    if next_action:
        payload["next_action"] = next_action
    return payload


def _briefing_next_actions(
    workspace_status: dict[str, Any],
    source_audit: dict[str, Any] | None,
    memory_briefing: dict[str, Any] | None,
    memory_review_queue: dict[str, Any] | None,
    priorities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for priority in priorities:
        if priority.get("next_action"):
            actions.append(dict(priority["next_action"]))
    for action in (source_audit or {}).get("next_actions") or []:
        actions.append(_normalize_source_action(action))
    for action in (memory_briefing or {}).get("next_actions") or []:
        actions.append(dict(action))
    for action in (memory_review_queue or {}).get("next_actions") or []:
        actions.append(dict(action))
    for action in workspace_status.get("next_actions") or []:
        actions.append(dict(action))
    return _unique_actions(actions)


def _normalize_source_action(action: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(action)
    tool = str(normalized.get("tool") or "")
    normalized.setdefault("view", "sources")
    if tool in SOURCE_ACTION_APIS:
        normalized.setdefault("api", SOURCE_ACTION_APIS[tool])
    return normalized


def _unique_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for action in actions:
        key = (str(action.get("action") or ""), str(action.get("tool") or action.get("api") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


def _briefing_status(priorities: list[dict[str, Any]], workspace_status: dict[str, Any]) -> str:
    severities = {priority.get("severity") for priority in priorities}
    if "critical" in severities or workspace_status.get("status") == "error":
        return "error"
    if {"warning", "setup"} & severities:
        return "action_required"
    if workspace_status.get("status") in {"ready", "ok"}:
        return "ready"
    return str(workspace_status.get("status") or "ok")


def _briefing_summary(
    workspace_status: dict[str, Any],
    roots: list[dict[str, Any]],
    source_audit: dict[str, Any] | None,
    memory_briefing: dict[str, Any] | None,
    memory_review_queue: dict[str, Any] | None,
    priorities: list[dict[str, Any]],
    next_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    audit = source_audit or {}
    duplicate_preview = audit.get("duplicate_preview") or {}
    unresolved = audit.get("unresolved_links") or {}
    unlinked = audit.get("unlinked_markdown") or {}
    memory_summary = (memory_briefing or {}).get("summary") or {}
    queue_summary = (memory_review_queue or {}).get("summary") or {}
    return {
        "workspace_status": workspace_status.get("status"),
        "source_root_count": len(roots),
        "source_audited": bool(source_audit),
        "duplicate_group_count": duplicate_preview.get("group_count", 0),
        "unresolved_link_count": unresolved.get("count", 0),
        "unlinked_markdown_count": unlinked.get("count", 0),
        "pending_review_count": (workspace_status.get("reviews") or {}).get("pending_count", 0),
        "accepted_unapplied_count": (workspace_status.get("reviews") or {}).get("accepted_unapplied_count", 0),
        "memory_focus_count": memory_summary.get("focus_count", 0),
        "memory_issue_count": memory_summary.get("issue_count", 0),
        "memory_recent_use_count": memory_summary.get("recent_use_count", 0),
        "memory_review_queue_group_count": queue_summary.get("group_count", 0),
        "memory_review_queue_item_count": queue_summary.get("item_count", 0),
        "conversation_memory_candidate_count": queue_summary.get("conversation_candidate_count", 0),
        "related_memory_candidate_group_count": queue_summary.get("related_candidate_group_count", 0),
        "priority_count": len(priorities),
        "next_action_count": len(next_actions),
    }
