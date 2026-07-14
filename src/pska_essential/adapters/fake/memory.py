from __future__ import annotations

from typing import Any
from uuid import uuid4

from pska_essential.contracts import MemoryApplyResult, MemoryFact, MemoryPatch


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
            if not words or any(word in fact.text.lower() for word in words)
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
