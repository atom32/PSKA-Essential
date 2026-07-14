from __future__ import annotations

from typing import Any, Protocol

from pska_essential.contracts import (
    ContextPacket,
    MemoryApplyResult,
    MemoryFact,
    MemoryPatch,
    Proposal,
    ReviewBatch,
    ReviewDecision,
    SourceContext,
    SourceRef,
    WorkflowRun,
)


class RetrievalPort(Protocol):
    def retrieve(
        self,
        query: str,
        scope: dict[str, Any],
        limit: int,
        options: dict[str, Any] | None = None,
    ) -> list[ContextPacket]: ...

    def read_source(self, source_ref: SourceRef) -> SourceContext: ...


class WorkflowPort(Protocol):
    def start(self, intent: str, scope: dict[str, Any]) -> WorkflowRun: ...

    def state(self, run_id: str) -> WorkflowRun: ...


class ProposalPort(Protocol):
    def propose_digest(self, run_id: str, intent: str) -> Proposal: ...

    def propose_memory_patch(self, run_id: str, intent: str) -> Proposal: ...

    def propose_writing_brief(self, run_id: str, intent: str) -> Proposal: ...


class ReviewPort(Protocol):
    def create(self, proposal_id: str) -> ReviewBatch: ...

    def decide(self, review_id: str, decision: str, reason: str) -> ReviewDecision: ...


class MemoryPort(Protocol):
    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]: ...

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult: ...
