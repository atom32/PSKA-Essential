from __future__ import annotations

import json
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import SourceRef, to_jsonable, utc_now_iso


TRACE_QUERY_SCHEMA = "pska.trace_query.v1"
TRACE_ENTRY_SCHEMA = "pska.trace_entry.v1"


def build_trace_query(
    service: Any,
    *,
    target_type: str = "",
    target_id: str = "",
    review_id: str = "",
    proposal_id: str = "",
    memory_id: str = "",
    source_ref: SourceRef | dict[str, Any] | None = None,
    action: str = "",
    limit: int = 50,
    audit: bool = True,
) -> dict[str, Any]:
    requested_limit = max(0, int(limit))
    normalized_ref = _source_ref_from_value(source_ref)
    query = {
        "target_type": str(target_type or "").strip(),
        "target_id": str(target_id or "").strip(),
        "review_id": str(review_id or "").strip(),
        "proposal_id": str(proposal_id or "").strip(),
        "memory_id": str(memory_id or "").strip(),
        "source_ref": to_jsonable(normalized_ref) if normalized_ref is not None else {},
        "action": str(action or "").strip(),
    }
    if not any(value for key, value in query.items() if key != "source_ref") and normalized_ref is None:
        raise TraceQueryError("trace query requires at least one selector")

    events = service.store.list_audit_events(
        action=query["action"] or None,
        descending=True,
        limit=_audit_scan_limit(requested_limit, query, normalized_ref) if requested_limit else None,
    )
    entries = [_entry_from_event(event) for event in events if _event_matches(event, query, normalized_ref)]
    review_entries = _review_entries(service, query, normalized_ref)
    entries.extend(review_entries)
    entries = _dedupe_entries(entries)
    entries.sort(key=lambda item: str(item.get("occurred_at") or ""), reverse=True)
    if requested_limit:
        entries = entries[:requested_limit]
    summary = _summary(entries)
    result = {
        "schema": TRACE_QUERY_SCHEMA,
        "created_at": utc_now_iso(),
        "status": "found" if entries else "empty",
        "query": query,
        "summary": summary,
        "entries": to_jsonable(entries),
        "entry_count": len(entries),
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "embedding_required": False,
            "generates_answer_text": False,
        },
        "limitations": [
            "Trace query is a derived view over PSKA audit and review records.",
            "It does not reconstruct hidden model causality or provider-native history.",
            "SourceRef matching is structural and may miss traces that did not record source refs.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "trace.query",
                "trace",
                _query_target_id(query, normalized_ref),
                status=result["status"],
                entry_count=result["entry_count"],
                query_target_type=query["target_type"],
                query_target_id=query["target_id"],
                review_id=query["review_id"],
                proposal_id=query["proposal_id"],
                memory_id=query["memory_id"],
                source_ref=to_jsonable(normalized_ref) if normalized_ref is not None else {},
                writes_memory_directly=False,
                writes_source_files=False,
            )
        )
    return to_jsonable(result)


class TraceQueryError(ValueError):
    pass


def _entry_from_event(event: Any) -> dict[str, Any]:
    metadata = dict(getattr(event, "metadata", {}) or {})
    return {
        "schema": TRACE_ENTRY_SCHEMA,
        "entry_type": "audit_event",
        "occurred_at": str(getattr(event, "created_at", "") or ""),
        "title": str(getattr(event, "action", "") or "audit_event"),
        "summary": _event_summary(event),
        "evidence": {
            "audit_event_id": str(getattr(event, "audit_event_id", "") or ""),
            "action": str(getattr(event, "action", "") or ""),
            "target_type": str(getattr(event, "target_type", "") or ""),
            "target_id": str(getattr(event, "target_id", "") or ""),
            "metadata": metadata,
        },
        "review_ids": _ids(metadata, "review_id"),
        "proposal_ids": _ids(metadata, "proposal_id"),
        "memory_ids": _ids(metadata, "memory_id", "memory_ids", "memory_target_id", "used_memory_ids"),
        "source_refs": _event_source_refs(event, metadata),
        "confidence": "audit_record",
    }


def _review_entries(
    service: Any,
    query: dict[str, Any],
    source_ref: SourceRef | None,
) -> list[dict[str, Any]]:
    if query["action"]:
        return []
    entries = []
    for review in service.store.list_reviews(limit=200):
        if not _review_matches(review, query, source_ref):
            continue
        proposal = review.get("proposal") or {}
        entries.append(
            {
                "schema": TRACE_ENTRY_SCHEMA,
                "entry_type": "review_record",
                "occurred_at": str(review.get("updated_at") or ""),
                "title": str(proposal.get("title") or review.get("review_id") or "review"),
                "summary": str(proposal.get("body") or review.get("reason") or ""),
                "evidence": {
                    "review_id": str(review.get("review_id") or ""),
                    "proposal_id": str(review.get("proposal_id") or ""),
                    "status": str(review.get("status") or ""),
                    "decision": str(review.get("decision") or ""),
                    "proposal_kind": str(proposal.get("kind") or ""),
                    "metadata": proposal.get("metadata") or {},
                },
                "review_ids": [str(review.get("review_id") or "")],
                "proposal_ids": [str(review.get("proposal_id") or "")],
                "memory_ids": _review_memory_ids(review),
                "source_refs": review.get("source_refs") or proposal.get("source_refs") or [],
                "confidence": "review_record",
            }
        )
    return entries


def _event_matches(event: Any, query: dict[str, Any], source_ref: SourceRef | None) -> bool:
    metadata = dict(getattr(event, "metadata", {}) or {})
    if query["target_type"] and str(getattr(event, "target_type", "") or "") != query["target_type"]:
        return False
    if query["target_id"] and str(getattr(event, "target_id", "") or "") != query["target_id"]:
        return False
    if query["review_id"] and query["review_id"] not in _ids(metadata, "review_id"):
        if str(getattr(event, "target_id", "") or "") != query["review_id"]:
            return False
    if query["proposal_id"] and query["proposal_id"] not in _ids(metadata, "proposal_id"):
        if str(getattr(event, "target_id", "") or "") != query["proposal_id"]:
            return False
    if query["memory_id"] and query["memory_id"] not in _ids(metadata, "memory_id", "memory_ids", "memory_target_id", "used_memory_ids"):
        if str(getattr(event, "target_id", "") or "") != query["memory_id"]:
            return False
    if source_ref is not None and not _source_ref_matches_any(source_ref, _event_source_refs(event, metadata)):
        return False
    return True


def _review_matches(review: dict[str, Any], query: dict[str, Any], source_ref: SourceRef | None) -> bool:
    proposal = review.get("proposal") or {}
    if query["review_id"] and str(review.get("review_id") or "") != query["review_id"]:
        return False
    if query["proposal_id"] and str(review.get("proposal_id") or "") != query["proposal_id"]:
        return False
    if query["memory_id"] and query["memory_id"] not in _review_memory_ids(review):
        return False
    if query["target_type"] == "review" and query["target_id"] and str(review.get("review_id") or "") != query["target_id"]:
        return False
    if query["target_type"] == "proposal" and query["target_id"] and str(review.get("proposal_id") or "") != query["target_id"]:
        return False
    if query["target_type"] and query["target_type"] not in {"review", "proposal"} and source_ref is None:
        return False
    if source_ref is not None and not _source_ref_matches_any(source_ref, review.get("source_refs") or proposal.get("source_refs") or []):
        return False
    return True


def _event_source_refs(event: Any, metadata: dict[str, Any]) -> list[Any]:
    refs = []
    refs.extend(metadata.get("source_refs") or [])
    if metadata.get("source_ref"):
        refs.append(metadata["source_ref"])
    if str(getattr(event, "target_type", "") or "") == "eidolia_node":
        refs.append(
            {
                "adapter": "eidolia",
                "source_id": metadata.get("project_id") or "",
                "external_id": metadata.get("node_id") or "",
            }
        )
    if str(getattr(event, "target_type", "") or "") == "eidolia_trace":
        refs.append(
            {
                "adapter": "eidolia",
                "source_id": metadata.get("project_id") or "",
                "external_id": metadata.get("trace_id") or getattr(event, "target_id", "") or "",
            }
        )
    return refs


def _review_memory_ids(review: dict[str, Any]) -> list[str]:
    memory_apply = review.get("memory_apply") or {}
    target_id = str(memory_apply.get("target_id") or "")
    return [target_id] if target_id else []


def _source_ref_from_value(value: SourceRef | dict[str, Any] | None) -> SourceRef | None:
    if value is None:
        return None
    if isinstance(value, SourceRef):
        return value
    if isinstance(value, dict) and value:
        return SourceRef.from_dict(value)
    return None


def _source_ref_matches_any(expected: SourceRef, values: list[Any]) -> bool:
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            candidate = SourceRef.from_dict(value)
        except TypeError:
            continue
        if _source_ref_matches(expected, candidate):
            return True
    return False


def _source_ref_matches(expected: SourceRef, candidate: SourceRef) -> bool:
    if (expected.adapter or "") != (candidate.adapter or ""):
        return False
    comparable_fields = ("dataset_id", "document_id", "chunk_id", "source_id", "external_id", "path")
    matched = False
    for field in comparable_fields:
        expected_value = str(getattr(expected, field) or "")
        candidate_value = str(getattr(candidate, field) or "")
        if expected_value and candidate_value and expected_value != candidate_value:
            return False
        if expected_value and candidate_value and expected_value == candidate_value:
            matched = True
    return matched


def _ids(metadata: dict[str, Any], *keys: str) -> list[str]:
    values = []
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if str(item))
        elif value:
            values.append(str(value))
    return values


def _event_summary(event: Any) -> str:
    metadata = dict(getattr(event, "metadata", {}) or {})
    for key in ("message", "reason", "query", "question_preview", "answer_preview", "status", "memory_type", "node_type"):
        value = metadata.get(key)
        if value:
            return str(value)
    return str(getattr(event, "target_id", "") or getattr(event, "action", "") or "")


def _summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for entry in entries:
        by_type[str(entry.get("entry_type") or "unknown")] = by_type.get(str(entry.get("entry_type") or "unknown"), 0) + 1
    return {
        "entry_count": len(entries),
        "entry_type_counts": by_type,
        "review_count": len({review_id for entry in entries for review_id in entry.get("review_ids") or [] if review_id}),
        "proposal_count": len({proposal_id for entry in entries for proposal_id in entry.get("proposal_ids") or [] if proposal_id}),
        "memory_count": len({memory_id for entry in entries for memory_id in entry.get("memory_ids") or [] if memory_id}),
    }


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for entry in entries:
        evidence = entry.get("evidence") or {}
        key = json.dumps(
            [
                entry.get("entry_type"),
                evidence.get("audit_event_id") or evidence.get("review_id") or "",
                evidence.get("action") or evidence.get("proposal_id") or "",
            ],
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _audit_scan_limit(requested_limit: int, query: dict[str, Any], source_ref: SourceRef | None) -> int:
    base_limit = max(requested_limit * 4, requested_limit, 50)
    if query.get("action"):
        return base_limit
    if source_ref is not None or query.get("target_id") or query.get("review_id") or query.get("proposal_id") or query.get("memory_id"):
        return max(base_limit, 1000)
    return base_limit


def _query_target_id(query: dict[str, Any], source_ref: SourceRef | None) -> str:
    for key in ("review_id", "proposal_id", "memory_id", "target_id", "action"):
        if query.get(key):
            return str(query[key])
    if source_ref is not None:
        return source_ref.external_id or source_ref.source_id or source_ref.path or source_ref.adapter
    return "trace"
