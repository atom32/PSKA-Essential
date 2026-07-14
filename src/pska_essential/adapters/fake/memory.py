from __future__ import annotations

from typing import Any
from uuid import uuid4

from pska_essential.contracts import MemoryApplyResult, MemoryDelete, MemoryFact, MemoryPatch, MemoryUpdate, utc_now_iso


class FakeMemoryAdapter:
    backend_name = "fake"

    def __init__(self) -> None:
        self.facts: list[MemoryFact] = []
        self.applied_patches: list[MemoryPatch] = []

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        words = {word.lower() for word in query.split() if word.strip()}
        matches = [
            fact
            for fact in self.facts
            if not fact.invalid_at and (not words or any(word in fact.text.lower() for word in words))
        ]
        return matches[:limit]

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
            if fact.fact_id == reviewed_update.target_id:
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
            if fact.fact_id == reviewed_delete.target_id:
                fact.invalid_at = utc_now_iso()
                fact.metadata["delete_reason"] = reviewed_delete.reason
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Fake memory fact deactivated",
                    metadata={"operation": "delete"},
                )
        raise ValueError(f"memory fact not found: {reviewed_delete.target_id}")
