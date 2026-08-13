from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso


MEMORY_CANDIDATE_DEDUP_SCHEMA = "pska.memory_candidate_dedup.v1"
MEMORY_CANDIDATE_DEDUP_GROUP_SCHEMA = "pska.memory_candidate_dedup_group.v1"
MEMORY_CANDIDATE_RELATED_GROUP_SCHEMA = "pska.memory_candidate_related_group.v1"
REVIEW_STATUSES = {"pending", "accepted", "needs_edit"}
STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "as",
    "before",
    "for",
    "from",
    "in",
    "inspect",
    "memory",
    "of",
    "on",
    "or",
    "route",
    "source",
    "the",
    "this",
    "to",
    "use",
    "when",
    "with",
}


def build_memory_candidate_dedup(
    service: Any,
    *,
    scope: dict[str, Any] | None = None,
    review_limit: int = 100,
    similarity_threshold: float = 0.82,
    related_threshold: float = 0.72,
    audit: bool = True,
) -> dict[str, Any]:
    normalized_scope = dict(scope or {})
    threshold = max(0.5, min(float(similarity_threshold or 0.82), 1.0))
    related = max(0.5, min(float(related_threshold or 0.72), 1.0))
    reviews = service.store.list_reviews(limit=max(0, int(review_limit)))
    candidates = [_candidate_from_review(review) for review in reviews]
    candidates = [candidate for candidate in candidates if candidate is not None]
    groups = _duplicate_groups(candidates, threshold=threshold)
    related_groups = _related_groups(candidates, duplicate_groups=groups, threshold=related)
    result = {
        "schema": MEMORY_CANDIDATE_DEDUP_SCHEMA,
        "created_at": utc_now_iso(),
        "status": "review" if groups or related_groups else "ready",
        "scope": normalized_scope,
        "summary": {
            "candidate_count": len(candidates),
            "group_count": len(groups),
            "related_group_count": len(related_groups),
            "scope_collision_group_count": sum(
                1 for group in related_groups if "scope_collision" in group.get("match_types", [])
            ),
            "duplicate_candidate_count": sum(group["count"] for group in groups),
            "related_candidate_count": sum(group["count"] for group in related_groups),
            "review_limit": max(0, int(review_limit)),
            "similarity_threshold": threshold,
            "related_threshold": related,
        },
        "groups": to_jsonable(groups),
        "related_groups": to_jsonable(related_groups),
        "next_actions": _next_actions(groups, related_groups),
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "embedding_required": False,
            "generates_answer_text": False,
            "approves_or_rejects_reviews": False,
        },
        "limitations": [
            "This is a lexical and SourceRef-based duplicate-candidate view; it does not use embeddings.",
            "It does not merge, reject, revise, approve, apply, or write durable memory.",
            "Near-text groups are review hints and can be false positives.",
            "Related groups can indicate scope collisions; they are not automatic duplicate decisions.",
        ],
    }
    if audit:
        service.store.add_audit_event(
            audit_event(
                "memory.candidate_dedup",
                "memory_scope",
                str(normalized_scope.get("memory_namespace") or "workspace"),
                status=result["status"],
                candidate_count=result["summary"]["candidate_count"],
                group_count=result["summary"]["group_count"],
                related_group_count=result["summary"]["related_group_count"],
                scope_collision_group_count=result["summary"]["scope_collision_group_count"],
                duplicate_candidate_count=result["summary"]["duplicate_candidate_count"],
                related_candidate_count=result["summary"]["related_candidate_count"],
                writes_memory_directly=False,
                writes_source_files=False,
                embedding_required=False,
            )
        )
    return to_jsonable(result)


@dataclass(slots=True)
class _Candidate:
    review_id: str
    proposal_id: str
    status: str
    proposal_kind: str
    text: str
    normalized_text: str
    tokens: set[str]
    memory_type: str
    memory_scope: str
    behavior_delta: str
    behavior_fingerprint: str
    source_fingerprints: list[str]
    source_paths: list[str]
    source_refs: list[dict[str, Any]]


def _candidate_from_review(review: dict[str, Any]) -> _Candidate | None:
    status = str(review.get("status") or "")
    if status not in REVIEW_STATUSES:
        return None
    if _merged_into_review_id(review):
        return None
    proposal = review.get("proposal") or {}
    if str(proposal.get("kind") or "") not in {"memory_patch", "memory_update"}:
        return None
    payload = proposal.get("memory_patch") or proposal.get("memory_update") or {}
    metadata = payload.get("metadata") or proposal.get("metadata") or {}
    text = str(payload.get("text") or proposal.get("body") or "").strip()
    if not text:
        return None
    source_refs = payload.get("source_refs") or proposal.get("source_refs") or review.get("source_refs") or []
    return _Candidate(
        review_id=str(review.get("review_id") or ""),
        proposal_id=str(review.get("proposal_id") or proposal.get("proposal_id") or ""),
        status=status,
        proposal_kind=str(proposal.get("kind") or ""),
        text=text,
        normalized_text=_normalize_text(text),
        tokens=_tokens(" ".join([text, str(metadata.get("behavior_delta") or "")])),
        memory_type=str(metadata.get("memory_type") or "unknown"),
        memory_scope=str(metadata.get("memory_scope") or "workspace"),
        behavior_delta=str(metadata.get("behavior_delta") or ""),
        behavior_fingerprint=_fingerprint(str(metadata.get("behavior_delta") or text)),
        source_fingerprints=sorted(_source_fingerprints(source_refs)),
        source_paths=sorted(_source_paths(source_refs)),
        source_refs=[dict(item) for item in source_refs if isinstance(item, dict)],
    )


def _duplicate_groups(candidates: list[_Candidate], *, threshold: float) -> list[dict[str, Any]]:
    candidate_by_id = {candidate.review_id: candidate for candidate in candidates if candidate.review_id}
    parent = {review_id: review_id for review_id in candidate_by_id}
    reasons: dict[tuple[str, str], dict[str, Any]] = {}
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            match = _candidate_match(left, right, threshold=threshold)
            if match is None:
                continue
            _union(parent, left.review_id, right.review_id)
            reasons[tuple(sorted([left.review_id, right.review_id]))] = match

    grouped: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        root = _find(parent, candidate.review_id)
        grouped.setdefault(root, []).append(candidate)

    groups = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        groups.append(_group_payload(members, reasons))
    groups.sort(key=lambda group: (-group["score"], -group["count"], group["group_id"]))
    return groups


def _candidate_match(left: _Candidate, right: _Candidate, *, threshold: float) -> dict[str, Any] | None:
    if left.review_id == right.review_id:
        return None
    if left.memory_type != right.memory_type or left.memory_scope != right.memory_scope:
        return None
    text_similarity = _jaccard(left.tokens, right.tokens)
    shared_sources = sorted(set(left.source_fingerprints) & set(right.source_fingerprints))
    shared_paths = sorted(set(left.source_paths) & set(right.source_paths))
    same_behavior = bool(left.behavior_fingerprint and left.behavior_fingerprint == right.behavior_fingerprint)
    if left.normalized_text and left.normalized_text == right.normalized_text:
        return {"match_type": "exact_text", "score": 1.0, "shared_sources": shared_sources, "shared_paths": shared_paths}
    if same_behavior and (shared_sources or shared_paths):
        return {
            "match_type": "same_source_route",
            "score": 0.96,
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    if text_similarity >= threshold:
        return {
            "match_type": "near_text",
            "score": round(text_similarity, 3),
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    if text_similarity >= 0.68 and (shared_sources or shared_paths):
        return {
            "match_type": "near_text_same_source",
            "score": round(max(text_similarity, 0.84), 3),
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    return None


def _related_groups(
    candidates: list[_Candidate],
    *,
    duplicate_groups: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    duplicate_pairs = _duplicate_pairs(duplicate_groups)
    candidate_by_id = {candidate.review_id: candidate for candidate in candidates if candidate.review_id}
    parent = {review_id: review_id for review_id in candidate_by_id}
    reasons: dict[tuple[str, str], dict[str, Any]] = {}
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            key = tuple(sorted([left.review_id, right.review_id]))
            if key in duplicate_pairs:
                continue
            match = _candidate_related_match(left, right, threshold=threshold)
            if match is None:
                continue
            _union(parent, left.review_id, right.review_id)
            reasons[key] = match

    grouped: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        root = _find(parent, candidate.review_id)
        grouped.setdefault(root, []).append(candidate)

    groups = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        member_ids = sorted(member.review_id for member in members)
        pair_reasons = [
            reason
            for key, reason in reasons.items()
            if key[0] in member_ids and key[1] in member_ids
        ]
        if pair_reasons:
            groups.append(_related_group_payload(members, pair_reasons))
    groups.sort(key=lambda group: (-group["score"], -group["count"], group["group_id"]))
    return groups


def _candidate_related_match(left: _Candidate, right: _Candidate, *, threshold: float) -> dict[str, Any] | None:
    if left.review_id == right.review_id:
        return None
    if left.memory_type != right.memory_type:
        return None
    if left.memory_scope == right.memory_scope:
        return None
    text_similarity = _jaccard(left.tokens, right.tokens)
    behavior_similarity = _jaccard(_tokens(left.behavior_delta), _tokens(right.behavior_delta))
    shared_sources = sorted(set(left.source_fingerprints) & set(right.source_fingerprints))
    shared_paths = sorted(set(left.source_paths) & set(right.source_paths))
    same_behavior = bool(left.behavior_fingerprint and left.behavior_fingerprint == right.behavior_fingerprint)
    score = max(text_similarity, behavior_similarity)
    if same_behavior:
        return {
            "match_type": "scope_collision",
            "score": 0.95,
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    if score >= threshold:
        return {
            "match_type": "scope_collision",
            "score": round(score, 3),
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    if score >= 0.64 and (shared_sources or shared_paths):
        return {
            "match_type": "scope_collision_same_source",
            "score": round(max(score, 0.8), 3),
            "shared_sources": shared_sources,
            "shared_paths": shared_paths,
        }
    return None


def _duplicate_pairs(groups: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for group in groups:
        ids = sorted(
            str(item.get("review_id") or "")
            for item in group.get("items") or []
            if str(item.get("review_id") or "")
        )
        for index, left in enumerate(ids):
            for right in ids[index + 1 :]:
                pairs.add(tuple(sorted([left, right])))
    return pairs


def _group_payload(members: list[_Candidate], reasons: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    member_ids = sorted(member.review_id for member in members)
    pair_reasons = [
        reason
        for key, reason in reasons.items()
        if key[0] in member_ids and key[1] in member_ids
    ]
    score = max((float(reason.get("score") or 0.0) for reason in pair_reasons), default=0.0)
    match_types = sorted({str(reason.get("match_type") or "") for reason in pair_reasons if reason.get("match_type")})
    shared_sources = sorted({source for reason in pair_reasons for source in reason.get("shared_sources") or []})
    shared_paths = sorted({path for reason in pair_reasons for path in reason.get("shared_paths") or []})
    first = members[0]
    return {
        "schema": MEMORY_CANDIDATE_DEDUP_GROUP_SCHEMA,
        "group_id": _fingerprint("|".join(member_ids))[:16],
        "memory_type": first.memory_type,
        "memory_scope": first.memory_scope,
        "match_types": match_types,
        "score": round(score, 3),
        "count": len(members),
        "shared_sources": shared_sources,
        "shared_paths": shared_paths,
        "items": [_candidate_item_payload(member) for member in members],
        "next_actions": _candidate_group_actions(
            member_ids,
            inspect_action="inspect_duplicate_memory_candidates",
            inspect_label="Inspect duplicate memory candidates",
            memory_type=first.memory_type,
            memory_scope=first.memory_scope,
        ),
    }


def _related_group_payload(members: list[_Candidate], reasons: list[dict[str, Any]]) -> dict[str, Any]:
    member_ids = sorted(member.review_id for member in members)
    score = max((float(reason.get("score") or 0.0) for reason in reasons), default=0.0)
    match_types = sorted({str(reason.get("match_type") or "") for reason in reasons if reason.get("match_type")})
    shared_sources = sorted({source for reason in reasons for source in reason.get("shared_sources") or []})
    shared_paths = sorted({path for reason in reasons for path in reason.get("shared_paths") or []})
    scopes = sorted({member.memory_scope for member in members if member.memory_scope})
    first = members[0]
    return {
        "schema": MEMORY_CANDIDATE_RELATED_GROUP_SCHEMA,
        "group_id": _fingerprint("|".join(["related", *member_ids]))[:16],
        "memory_type": first.memory_type,
        "memory_scopes": scopes,
        "match_types": match_types,
        "score": round(score, 3),
        "count": len(members),
        "shared_sources": shared_sources,
        "shared_paths": shared_paths,
        "items": [_candidate_item_payload(member) for member in members],
        "next_actions": _candidate_group_actions(
            member_ids,
            inspect_action="inspect_related_memory_candidates",
            inspect_label="Inspect related memory candidates",
            memory_type=first.memory_type,
            memory_scope=scopes[0] if scopes else "workspace",
        ),
    }


def _candidate_item_payload(member: _Candidate) -> dict[str, Any]:
    return {
        "item_type": "candidate_review",
        "review_id": member.review_id,
        "proposal_id": member.proposal_id,
        "status": member.status,
        "proposal_kind": member.proposal_kind,
        "title": member.text[:120],
        "reason": member.behavior_delta or member.text,
        "memory_type": member.memory_type,
        "memory_scope": member.memory_scope,
        "source_paths": member.source_paths,
        "source_refs": member.source_refs,
        "next_actions": [
            {
                "action": "open_review",
                "tool": "pska_review_get",
                "api": f"GET /api/reviews/{member.review_id}",
                "view": "review",
                "params": {"review_id": member.review_id},
            }
        ],
    }


def _candidate_group_actions(
    review_ids: list[str],
    *,
    inspect_action: str,
    inspect_label: str,
    memory_type: str,
    memory_scope: str,
) -> list[dict[str, Any]]:
    review_id = next((item for item in review_ids if item), "")
    return [
        {
            "action": inspect_action,
            "label": inspect_label,
            "tool": "pska_memory_candidate_dedup",
            "api": "GET /api/memory/candidate-dedup",
            "view": "review",
            "params": {"review_id": review_id} if review_id else {},
        },
        {
            "action": "merge_candidate_group",
            "label": "Merge candidate group",
            "tool": "pska_review_merge_candidates",
            "api": "POST /api/reviews/merge-candidates",
            "view": "review",
            "params": {
                "review_ids": review_ids,
                "memory_type": memory_type,
                "memory_scope": memory_scope,
            },
        }
    ]


def _next_actions(groups: list[dict[str, Any]], related_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not groups and not related_groups:
        return []
    actions = []
    if groups:
        first_item = ((groups[0].get("items") or [{}])[0]) or {}
        review_id = str(first_item.get("review_id") or "")
        actions.append(
            {
                "action": "inspect_duplicate_memory_candidates",
                "label": "Inspect duplicate memory candidates",
                "tool": "pska_memory_candidate_dedup",
                "api": "GET /api/memory/candidate-dedup",
                "view": "review",
                "params": {"review_id": review_id} if review_id else {},
            }
        )
    if related_groups:
        actions.extend((related_groups[0].get("next_actions") or [])[:1])
    return actions


def _merged_into_review_id(review: dict[str, Any]) -> str:
    revision = review.get("revision") or {}
    return str(revision.get("merged_into_review_id") or "")


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[\w/.-]+", text.lower(), flags=re.UNICODE))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w/.-]+", text.lower(), flags=re.UNICODE)
        if len(token) > 2 and token not in STOPWORDS
    }


def _fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_text(text)).strip()


def _source_fingerprints(source_refs: list[Any]) -> set[str]:
    fingerprints: set[str] = set()
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        fingerprints.add(
            "|".join(
                [
                    str(ref.get("adapter") or ""),
                    str(ref.get("dataset_id") or ""),
                    str(ref.get("document_id") or ""),
                    str(ref.get("chunk_id") or ""),
                    str(ref.get("source_id") or ""),
                    str(ref.get("external_id") or ""),
                    str(ref.get("path") or ""),
                ]
            )
        )
    return {fingerprint for fingerprint in fingerprints if fingerprint.strip("|")}


def _source_paths(source_refs: list[Any]) -> set[str]:
    paths: set[str] = set()
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        path = str(ref.get("path") or (ref.get("metadata") or {}).get("path") or "").strip().lower()
        if path:
            paths.add(path)
    return paths


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _find(parent: dict[str, str], item: str) -> str:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[right_root] = left_root
