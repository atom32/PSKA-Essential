from __future__ import annotations

from typing import Any

from pska_essential.capabilities import (
    MEMORY_DISPLAY_TEXT_KEYS,
    MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS,
    MEMORY_SUPERSESSION_TARGET_KEYS,
)
from pska_essential.contracts import MemoryFact, to_jsonable, utc_now_iso
from pska_essential.runtime_context import build_runtime_memory_scope


MEMORY_CARD_SCHEMA = "pska.memory_card.v1"
MEMORY_CARD_COLLECTION_SCHEMA = "pska.memory_card_collection.v1"


class MemoryCardError(ValueError):
    pass


def list_memory_cards(
    service: Any,
    *,
    scope: dict[str, Any] | None = None,
    limit: int = 50,
    query: str = "",
    status: str = "active",
    memory_type: str = "",
    audit: bool = True,
) -> dict[str, Any]:
    requested_limit = max(0, int(limit))
    runtime_scope = build_runtime_memory_scope(scope or {})
    normalized_query = str(query or "").strip()
    normalized_status = _normalize_status(status)
    normalized_type = str(memory_type or "").strip().lower()
    include_inactive = normalized_status in {"deleted", "all"}
    include_superseded = normalized_status in {"superseded", "all"} or any(
        bool(runtime_scope.get(key)) for key in MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS
    )
    facts = _provider_facts(
        service.memory,
        runtime_scope,
        requested_limit,
        query=normalized_query,
        include_inactive=include_inactive,
        include_superseded=include_superseded,
    )
    facts = [_enrich_fact_from_service_lineage(service, fact) for fact in facts]
    status_context = _status_context_facts(service.memory, runtime_scope, facts)
    status_context = [_enrich_fact_from_service_lineage(service, fact) for fact in status_context]
    superseded_by = _superseded_by_map(status_context)
    cards = [
        _memory_card_from_fact(service, fact, runtime_scope=runtime_scope, superseded_by=superseded_by)
        for fact in facts
    ]
    if normalized_type:
        cards = [card for card in cards if card["memory_type"] == normalized_type]
    if normalized_status != "all":
        cards = [card for card in cards if card["status"] == normalized_status]
    cards = _rank_cards(cards)[:requested_limit]
    if audit:
        _add_memory_card_list_audit(
            service,
            query=normalized_query,
            status=normalized_status,
            memory_type=normalized_type,
            count=len(cards),
            memory_ids=[str(card.get("memory_id") or "") for card in cards],
            scope=runtime_scope,
        )
    return {
        "schema": MEMORY_CARD_COLLECTION_SCHEMA,
        "status": "ok",
        "cards": to_jsonable(cards),
        "count": len(cards),
        "query": normalized_query,
        "filters": {
            "status": normalized_status,
            "memory_type": normalized_type,
            "include_superseded": include_superseded,
            "include_inactive": include_inactive,
        },
        "scope": runtime_scope,
        "capabilities": {
            "provider_list_supported": callable(getattr(service.memory, "list_facts", None)),
            "provider_get_supported": callable(getattr(service.memory, "get_fact", None)),
        },
        "next_actions": _collection_next_actions(cards),
    }


def get_memory_card(
    service: Any,
    memory_id: str,
    *,
    scope: dict[str, Any] | None = None,
    audit: bool = True,
) -> dict[str, Any]:
    selected_id = str(memory_id or "").strip()
    if not selected_id:
        raise MemoryCardError("memory_id is required")
    runtime_scope = build_runtime_memory_scope(scope or {})
    fact = _get_provider_fact(service.memory, selected_id, runtime_scope)
    if fact is None:
        raise MemoryCardError(f"memory card not found: {selected_id}")
    fact = _enrich_fact_from_service_lineage(service, fact)
    related = _provider_facts(
        service.memory,
        runtime_scope,
        100,
        query="",
        include_inactive=True,
        include_superseded=True,
    )
    related = [_enrich_fact_from_service_lineage(service, item) for item in related]
    card = _memory_card_from_fact(
        service,
        fact,
        runtime_scope=runtime_scope,
        superseded_by=_superseded_by_map(related),
    )
    if audit:
        _add_memory_card_get_audit(service, card, scope=runtime_scope)
    return {
        "schema": MEMORY_CARD_SCHEMA,
        "status": "ok",
        "card": to_jsonable(card),
        "lifecycle": card["lifecycle"],
        "next_actions": card["next_actions"],
    }


def _provider_facts(
    memory: Any,
    scope: dict[str, Any],
    limit: int,
    *,
    query: str,
    include_inactive: bool,
    include_superseded: bool,
) -> list[MemoryFact]:
    if limit <= 0:
        return []
    if query:
        search_scope = dict(scope)
        if include_superseded:
            search_scope["include_superseded_memory"] = True
        return [
            fact
            for fact in memory.search(query, search_scope, _raw_limit(limit))
            if include_inactive or not fact.invalid_at
        ]
    list_facts = getattr(memory, "list_facts", None)
    if not callable(list_facts):
        backend = str(getattr(memory, "backend_name", "custom"))
        raise MemoryCardError(f"memory card list is not supported by {backend}: adapter does not expose list_facts")
    return list_facts(scope, _raw_limit(limit), include_inactive=include_inactive)


def _get_provider_fact(memory: Any, memory_id: str, scope: dict[str, Any]) -> MemoryFact | None:
    get_fact = getattr(memory, "get_fact", None)
    if callable(get_fact):
        return get_fact(memory_id, scope)
    matches = [
        fact
        for fact in memory.search(memory_id, {**scope, "include_superseded_memory": True}, 10)
        if fact.fact_id == memory_id
    ]
    return matches[0] if matches else None


def _status_context_facts(memory: Any, scope: dict[str, Any], selected: list[MemoryFact]) -> list[MemoryFact]:
    list_facts = getattr(memory, "list_facts", None)
    if not callable(list_facts):
        return selected
    by_id = {fact.fact_id: fact for fact in selected}
    for fact in list_facts(scope, 200, include_inactive=False):
        by_id.setdefault(fact.fact_id, fact)
    return list(by_id.values())


def _memory_card_from_fact(
    service: Any,
    fact: MemoryFact,
    *,
    runtime_scope: dict[str, Any],
    superseded_by: dict[str, MemoryFact] | None = None,
) -> dict[str, Any]:
    fact = _enrich_fact_from_service_lineage(service, fact)
    metadata = dict(fact.metadata or {})
    display_text = _display_text(fact)
    supersedes = _superseded_target_ids(metadata)
    lifecycle = service.memory_lifecycle(fact.fact_id) if fact.fact_id else {}
    superseding_fact = (superseded_by or {}).get(fact.fact_id)
    status = _memory_card_status(fact, lifecycle, superseding_fact=superseding_fact)
    quality = _memory_card_quality(fact, metadata, display_text)
    return {
        "schema": MEMORY_CARD_SCHEMA,
        "memory_id": fact.fact_id,
        "fact_id": fact.fact_id,
        "status": status,
        "text": fact.text,
        "display_text": display_text,
        "memory_type": str(metadata.get("memory_type") or "unspecified"),
        "memory_scope": str(metadata.get("memory_scope") or _scope_label(metadata, runtime_scope)),
        "behavior_delta": str(metadata.get("behavior_delta") or ""),
        "refresh_rule": str(metadata.get("refresh_rule") or "persistent"),
        "confidence": _confidence(metadata),
        "source_refs": to_jsonable(fact.source_refs),
        "source_count": len(fact.source_refs),
        "valid_at": fact.valid_at or "",
        "invalid_at": fact.invalid_at or "",
        "created_at": _metadata_time(metadata, "created_at", "observed_at", "valid_at") or fact.valid_at or "",
        "updated_at": _metadata_time(metadata, "updated_at", "applied_at", "created_at", "observed_at") or fact.valid_at or "",
        "origin": str(metadata.get("origin") or ""),
        "operation": str(metadata.get("operation") or metadata.get("semantic_operation") or ""),
        "supersedes": supersedes,
        "superseded_by": superseding_fact.fact_id if superseding_fact else "",
        "version": int(metadata.get("version") or 1),
        "quality": quality,
        "lifecycle": {
            "change_count": int(lifecycle.get("change_count") or 0),
            "latest_event": to_jsonable(lifecycle.get("latest_event")),
            "events": to_jsonable(lifecycle.get("events") or []),
        },
        "agent_view": {
            "text": display_text,
            "behavior_delta": str(metadata.get("behavior_delta") or ""),
            "why_use": _agent_why_use(metadata, display_text),
            "should_cite_source": bool(fact.source_refs),
        },
        "metadata": to_jsonable(metadata),
        "next_actions": _card_next_actions(fact, status, quality),
    }


def _enrich_fact_from_service_lineage(service: Any, fact: MemoryFact) -> MemoryFact:
    enrich = getattr(service, "enrich_memory_fact_with_lineage", None)
    if not callable(enrich):
        return fact
    try:
        enriched = enrich(fact)
    except Exception:
        return fact
    return enriched if isinstance(enriched, MemoryFact) else fact


def _memory_card_status(
    fact: MemoryFact,
    lifecycle: dict[str, Any],
    *,
    superseding_fact: MemoryFact | None = None,
) -> str:
    latest = dict(lifecycle.get("latest_event") or {})
    if fact.invalid_at or latest.get("action") == "memory.delete":
        return "deleted"
    if superseding_fact is not None:
        return "superseded"
    return "active"


def _memory_card_quality(fact: MemoryFact, metadata: dict[str, Any], display_text: str) -> dict[str, Any]:
    missing = []
    if not str(metadata.get("memory_type") or "").strip():
        missing.append("memory_type")
    if not str(metadata.get("memory_scope") or "").strip():
        missing.append("memory_scope")
    if not str(metadata.get("behavior_delta") or "").strip():
        missing.append("behavior_delta")
    if not fact.source_refs:
        missing.append("source_refs")
    if not display_text:
        missing.append("display_text")
    risk = str((metadata.get("triage") or {}).get("risk") or "")
    return {
        "missing_fields": missing,
        "needs_review": bool(missing),
        "risk": risk,
        "stale_candidate": _is_stale_candidate(metadata),
        "complete": not missing,
    }


def _card_next_actions(fact: MemoryFact, status: str, quality: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "inspect_memory_lifecycle",
            "label": "Inspect Memory Lifecycle",
            "api": f"GET /api/memory/{fact.fact_id}/lifecycle",
            "tool": "pska_memory_lifecycle",
            "view": "memory",
            "params": {"memory_id": fact.fact_id},
        }
    ]
    if status == "active" and fact.source_refs:
        actions.extend(
            [
                {
                    "action": "create_memory_refresh_review",
                    "label": "Create Memory Refresh Review",
                    "api": f"POST /api/memory/cards/{fact.fact_id}/refresh-review",
                    "tool": "pska_memory_refresh_review",
                    "view": "review",
                    "params": {"memory_id": fact.fact_id},
                },
                {
                    "action": "create_memory_update_review",
                    "label": "Create Memory Update Review",
                    "api": "POST /api/memory/update-review",
                    "tool": "pska_memory_update_review",
                    "view": "review",
                    "params": {"memory_id": fact.fact_id},
                },
                {
                    "action": "create_memory_delete_review",
                    "label": "Create Memory Delete Review",
                    "api": "POST /api/memory/delete-review",
                    "tool": "pska_memory_delete_review",
                    "view": "review",
                    "params": {"memory_id": fact.fact_id},
                },
            ]
        )
    if quality.get("needs_review"):
        actions.append(
            {
                "action": "inspect_memory_card_quality",
                "label": "Inspect Memory Card Quality",
                "api": f"GET /api/memory/cards/{fact.fact_id}",
                "tool": "pska_memory_card_get",
                "view": "memory",
                "params": {"memory_id": fact.fact_id},
            }
        )
    return actions


def _collection_next_actions(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    incomplete = [card for card in cards if (card.get("quality") or {}).get("needs_review")]
    if not incomplete:
        return []
    return [
        {
            "action": "inspect_memory_card_quality",
            "label": "Inspect memory cards missing PSKA envelope fields",
            "api": "/api/memory/cards?status=active",
            "tool": "pska_memory_card_list",
            "view": "memory",
            "params": {"count": len(incomplete)},
        }
    ]


def _display_text(fact: MemoryFact) -> str:
    metadata = fact.metadata or {}
    for key in MEMORY_DISPLAY_TEXT_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(fact.text or "").strip()


def _agent_why_use(metadata: dict[str, Any], display_text: str) -> str:
    behavior_delta = str(metadata.get("behavior_delta") or "").strip()
    if behavior_delta:
        return behavior_delta
    memory_type = str(metadata.get("memory_type") or "").strip()
    if memory_type:
        return f"Use this {memory_type} memory when the current task matches its scope."
    return f"Use this memory only when directly relevant: {display_text[:160]}"


def _normalize_status(status: str) -> str:
    normalized = str(status or "active").strip().lower()
    if normalized not in {"active", "deleted", "superseded", "all"}:
        raise MemoryCardError("memory card status must be active, deleted, superseded, or all")
    return normalized


def _rank_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(cards, key=lambda card: (str(card.get("updated_at") or ""), str(card.get("memory_id") or "")), reverse=True)


def _raw_limit(limit: int) -> int:
    if limit <= 0:
        return 0
    return min(200, max(limit, limit * 3, limit + 10))


def _confidence(metadata: dict[str, Any]) -> float:
    try:
        return float(metadata.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _scope_label(metadata: dict[str, Any], runtime_scope: dict[str, Any]) -> str:
    if metadata.get("memory_namespace") or runtime_scope.get("memory_namespace"):
        return "workspace"
    return "global"


def _metadata_time(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_stale_candidate(metadata: dict[str, Any]) -> bool:
    refresh_rule = str(metadata.get("refresh_rule") or "").strip()
    if refresh_rule in {"review_after_date", "until_project_done"}:
        return True
    review_after = str(metadata.get("review_after") or metadata.get("review_after_date") or "").strip()
    return bool(review_after and review_after < utc_now_iso())


def _superseded_target_ids(metadata: dict[str, Any]) -> list[str]:
    target_ids: list[str] = []
    for key in MEMORY_SUPERSESSION_TARGET_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            target_ids.append(value.strip())
        elif isinstance(value, list):
            target_ids.extend(str(item).strip() for item in value if str(item).strip())
    seen: set[str] = set()
    unique: list[str] = []
    for target_id in target_ids:
        if target_id in seen:
            continue
        seen.add(target_id)
        unique.append(target_id)
    return unique


def _superseded_by_map(facts: list[MemoryFact]) -> dict[str, MemoryFact]:
    by_id = {fact.fact_id: fact for fact in facts}
    superseded_by: dict[str, MemoryFact] = {}
    for fact in facts:
        for target_id in _superseded_target_ids(fact.metadata):
            if target_id in by_id and target_id != fact.fact_id:
                superseded_by[target_id] = fact
    return superseded_by


def _add_memory_card_list_audit(
    service: Any,
    *,
    query: str,
    status: str,
    memory_type: str,
    count: int,
    memory_ids: list[str],
    scope: dict[str, Any],
) -> None:
    service.store.add_audit_event(
        _audit_event(
            "memory.card.list",
            "memory_scope",
            str(scope.get("memory_namespace") or "workspace"),
            query=query,
            status=status,
            memory_type=memory_type,
            count=count,
            memory_ids=[memory_id for memory_id in memory_ids if memory_id],
            scope=scope,
        )
    )


def _add_memory_card_get_audit(service: Any, card: dict[str, Any], *, scope: dict[str, Any]) -> None:
    service.store.add_audit_event(
        _audit_event(
            "memory.card.get",
            "memory",
            str(card.get("memory_id") or ""),
            memory_type=str(card.get("memory_type") or ""),
            status=str(card.get("status") or ""),
            memory_id=str(card.get("memory_id") or ""),
            source_count=int(card.get("source_count") or 0),
            scope=scope,
        )
    )


def _audit_event(action: str, target_type: str, target_id: str, **metadata: Any) -> Any:
    from pska_essential.audit import audit_event

    return audit_event(action, target_type, target_id, **metadata)
