from __future__ import annotations

from typing import Any
from uuid import uuid4

from pska_essential.contracts import MemoryApplyResult, MemoryDelete, MemoryFact, MemoryPatch, MemoryUpdate, utc_now_iso


class FakeMemoryAdapter:
    backend_name = "fake"
    memory_capabilities = {
        "search": True,
        "list": True,
        "get": True,
        "apply": True,
        "update": True,
        "delete": True,
    }

    def __init__(self) -> None:
        self.facts: list[MemoryFact] = []
        self.applied_patches: list[MemoryPatch] = []

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        words = {word.lower() for word in query.split() if word.strip()}
        matches = [
            fact
            for fact in self.facts
            if _fact_in_scope(fact, scope)
            and not fact.invalid_at
            and (not words or any(word in fact.text.lower() for word in words))
        ]
        return _rank_memory_facts(matches)[:limit]

    def list_facts(self, scope: dict[str, Any], limit: int, *, include_inactive: bool = False) -> list[MemoryFact]:
        matches = [
            fact
            for fact in self.facts
            if _fact_in_scope(fact, scope) and (include_inactive or not fact.invalid_at)
        ]
        return _rank_memory_facts(matches)[: max(0, int(limit))]

    def get_fact(self, fact_id: str, scope: dict[str, Any]) -> MemoryFact | None:
        selected = str(fact_id or "")
        for fact in self.facts:
            if fact.fact_id == selected and _fact_in_scope(fact, scope):
                return fact
        return None

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        fact = MemoryFact(
            fact_id=f"mem_{uuid4().hex}",
            text=reviewed_patch.text,
            source_refs=reviewed_patch.source_refs,
            metadata={"layer": reviewed_patch.layer, **reviewed_patch.metadata},
        )
        self.facts.append(fact)
        self.applied_patches.append(reviewed_patch)
        return MemoryApplyResult(
            applied=True,
            target_id=fact.fact_id,
            backend=self.backend_name,
            message="Fake memory patch applied",
        )

    def update(self, reviewed_update: MemoryUpdate) -> MemoryApplyResult:
        for fact in self.facts:
            if fact.fact_id == reviewed_update.target_id and _metadata_in_scope(fact.metadata, reviewed_update.metadata):
                previous_text = fact.text
                version = int(fact.metadata.get("version", 1)) + 1
                fact.metadata.setdefault("versions", []).append(
                    {
                        "version": version - 1,
                        "text": previous_text,
                        "updated_at": utc_now_iso(),
                        "reason": reviewed_update.reason,
                    }
                )
                fact.text = reviewed_update.text
                fact.source_refs = reviewed_update.source_refs
                fact.metadata.update(reviewed_update.metadata)
                fact.metadata["update_reason"] = reviewed_update.reason
                fact.metadata["version"] = version
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Fake memory fact updated",
                    metadata={"operation": "update", "version": version, "previous_text": previous_text},
                )
        raise ValueError(f"memory fact not found: {reviewed_update.target_id}")

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        for fact in self.facts:
            if fact.fact_id == reviewed_delete.target_id and _metadata_in_scope(fact.metadata, reviewed_delete.metadata):
                fact.invalid_at = utc_now_iso()
                fact.metadata.update(reviewed_delete.metadata)
                fact.metadata["delete_reason"] = reviewed_delete.reason
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Fake memory fact deactivated",
                    metadata={"operation": "delete"},
                )
        raise ValueError(f"memory fact not found: {reviewed_delete.target_id}")


def _fact_in_scope(fact: MemoryFact, scope: dict[str, Any]) -> bool:
    return _metadata_in_scope(fact.metadata, scope)


def _metadata_in_scope(metadata: dict[str, Any], scope: dict[str, Any]) -> bool:
    expected = str(scope.get("memory_namespace") or "")
    actual = str(metadata.get("memory_namespace") or "")
    if expected:
        return actual == expected
    return actual == ""


def _rank_memory_facts(facts: list[MemoryFact]) -> list[MemoryFact]:
    return sorted(facts, key=_memory_fact_sort_key, reverse=True)


def _memory_fact_sort_key(fact: MemoryFact) -> tuple[str, str]:
    metadata = fact.metadata or {}
    timestamp = (
        fact.valid_at
        or _metadata_timestamp(metadata, "applied_at")
        or _metadata_timestamp(metadata, "updated_at")
        or _metadata_timestamp(metadata, "created_at")
        or _metadata_timestamp(metadata, "observed_at")
        or ""
    )
    return (timestamp, fact.fact_id)


def _metadata_timestamp(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""
