from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.audit import audit_event
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
    to_jsonable,
    utc_now_iso,
)
from pska_essential.ports import MemoryPort, RetrievalPort
from pska_essential.review_store import SQLiteReviewStore


class WorkflowError(RuntimeError):
    """Raised when the workflow gate refuses an unsafe transition."""


class WorkflowService:
    """Application service behind MCP tools.

    The service owns the gate: external adapters can retrieve or write only
    through these transitions. Memory writes require an accepted review.
    """

    def __init__(
        self,
        retrieval: RetrievalPort,
        memory: MemoryPort,
        store: SQLiteReviewStore,
    ) -> None:
        self.retrieval = retrieval
        self.memory = memory
        self.store = store

    def start(self, intent: str, scope: dict[str, Any] | None = None) -> WorkflowRun:
        run = WorkflowRun(
            run_id=f"run_{uuid4().hex}",
            intent=intent,
            scope=dict(scope or {}),
        )
        self.store.save_workflow(run)
        self.store.add_audit_event(audit_event("workflow.start", "workflow", run.run_id, intent=intent))
        return run

    def state(self, run_id: str) -> WorkflowRun:
        return self.store.get_workflow(run_id)

    def context_retrieve(self, run_id: str, query: str, limit: int = 5) -> list[ContextPacket]:
        run = self.store.get_workflow(run_id)
        packets = self.retrieval.retrieve(query, run.scope, limit, options={"run_id": run_id})
        run.context_packets.extend(packets)
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        self.store.add_audit_event(
            audit_event(
                "context.retrieve",
                "workflow",
                run_id,
                query=query,
                count=len(packets),
            )
        )
        return packets

    def source_read(self, source_ref: SourceRef | dict[str, Any]) -> SourceContext:
        ref = source_ref if isinstance(source_ref, SourceRef) else SourceRef.from_dict(source_ref)
        return self.retrieval.read_source(ref)

    def propose(self, run_id: str, kind: str, intent: str = "") -> Proposal:
        normalized = kind.strip().lower()
        if normalized not in {"digest", "memory_patch", "writing_brief"}:
            raise WorkflowError("proposal kind must be digest, memory_patch, or writing_brief")
        run = self.store.get_workflow(run_id)
        if not run.context_packets:
            raise WorkflowError("cannot propose without retrieved context")
        source_refs = _unique_source_refs([packet.source_ref for packet in run.context_packets])
        if not source_refs:
            raise WorkflowError("cannot propose without source refs")
        proposal_id = f"prop_{uuid4().hex}"
        body = _compose_body(normalized, run, intent)
        memory_patch = None
        if normalized == "memory_patch":
            memory_patch = MemoryPatch(
                text=body,
                source_refs=source_refs,
                confidence=0.8,
                metadata={"run_id": run.run_id, "intent": intent or run.intent},
            )
        proposal = Proposal(
            proposal_id=proposal_id,
            run_id=run.run_id,
            kind=normalized,
            intent=intent or run.intent,
            title=_proposal_title(normalized, intent or run.intent),
            body=body,
            source_refs=source_refs,
            memory_patch=memory_patch,
        )
        self.store.save_proposal(proposal)
        run.proposal_ids.append(proposal.proposal_id)
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        self.store.add_audit_event(
            audit_event("proposal.create", "proposal", proposal.proposal_id, kind=normalized, run_id=run_id)
        )
        return proposal

    def review_create(self, proposal_id: str) -> ReviewBatch:
        review = self.store.create_review(proposal_id)
        self.store.add_audit_event(
            audit_event("review.create", "review", review.review_id, proposal_id=proposal_id)
        )
        return review

    def review_decide(self, review_id: str, decision: str, reason: str) -> ReviewDecision:
        decided = self.store.decide_review(review_id, decision, reason)
        self.store.add_audit_event(
            audit_event(
                "review.decide",
                "review",
                review_id,
                decision=decided.decision,
                status=decided.status,
                reason=reason,
            )
        )
        return decided

    def memory_search(self, query: str, scope: dict[str, Any] | None = None, limit: int = 10) -> list[MemoryFact]:
        return self.memory.search(query, dict(scope or {}), limit)

    def memory_apply(self, review_id: str) -> MemoryApplyResult:
        existing = self.store.get_memory_apply(review_id)
        if existing:
            return MemoryApplyResult(**existing)
        review = self.store.get_review(review_id)
        if review["status"] != "accepted":
            raise WorkflowError("memory apply requires an accepted review")
        proposal = self.store.get_proposal(str(review["proposal_id"]))
        if proposal.kind != "memory_patch" or proposal.memory_patch is None:
            raise WorkflowError("only memory_patch proposals can be applied to memory")
        if not proposal.memory_patch.source_refs:
            raise WorkflowError("memory patch requires source refs before apply")
        result = self.memory.apply(proposal.memory_patch)
        self.store.save_memory_apply(review_id, to_jsonable(result))
        self.store.add_audit_event(
            audit_event(
                "memory.apply",
                "review",
                review_id,
                applied=result.applied,
                memory_target_id=result.target_id,
                backend=result.backend,
            )
        )
        return result

    def export_brief(self, run_id: str, format: str = "markdown") -> str | dict[str, Any]:
        run = self.store.get_workflow(run_id)
        fmt = format.strip().lower()
        if fmt not in {"markdown", "json"}:
            raise WorkflowError("export format must be markdown or json")
        packet_payload = [to_jsonable(packet) for packet in run.context_packets]
        proposals = [self.store.get_proposal(proposal_id) for proposal_id in run.proposal_ids]
        proposal_payload = [to_jsonable(proposal) for proposal in proposals]
        source_manifest = _source_manifest(run.context_packets)
        self.store.add_audit_event(
            audit_event(
                "workflow.export",
                "workflow",
                run_id,
                format=fmt,
                context_count=len(packet_payload),
                proposal_count=len(proposal_payload),
                source_count=len(source_manifest),
                scope=run.scope,
            )
        )
        if fmt == "json":
            return {
                "run": to_jsonable(run),
                "scope": run.scope,
                "proposals": proposal_payload,
                "latest_proposal": proposal_payload[-1] if proposal_payload else None,
                "source_manifest": source_manifest,
                "context_packets": packet_payload,
                "traceability": {
                    "context_count": len(packet_payload),
                    "proposal_count": len(proposal_payload),
                    "source_count": len(source_manifest),
                },
            }
        lines = [
            f"# PSKA-Essential Brief: {run.intent}",
            "",
            f"- Run: `{run.run_id}`",
            f"- Status: `{run.status}`",
            f"- Scope: `{_json_inline(run.scope)}`",
            f"- Source count: `{len(source_manifest)}`",
            "",
            "## Work Product",
            "",
        ]
        if proposals:
            latest = proposals[-1]
            lines.extend([latest.body, ""])
        else:
            lines.extend(["No proposal has been created for this workflow.", ""])
        lines.extend(["## Source Manifest", ""])
        if source_manifest:
            lines.extend(
                [
                    "| # | Title | Adapter | Dataset | Document | Chunk/Source | Score |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for source in source_manifest:
                lines.append(
                    "| {index} | {title} | {adapter} | {dataset_id} | {document_id} | {source_id} | {score} |".format(
                        index=source["index"],
                        title=_markdown_cell(source["title"]),
                        adapter=_markdown_cell(source["adapter"]),
                        dataset_id=_markdown_cell(source["dataset_id"]),
                        document_id=_markdown_cell(source["document_id"]),
                        source_id=_markdown_cell(source["source_id"]),
                        score=f"{float(source['score']):.2f}",
                    )
                )
            lines.append("")
        else:
            lines.extend(["No source manifest is available for this workflow.", ""])
        lines.extend(["## Supporting Context", ""])
        for index, packet in enumerate(run.context_packets, start=1):
            title = packet.title or packet.source_ref.title or packet.context_id
            lines.extend(
                [
                    f"### [{index}] {title}",
                    "",
                    packet.text,
                    "",
                    f"Source [{index}]: `{packet.source_ref.adapter}` / `{_source_display_id(packet.source_ref)}`",
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def eval_run(self, suite: str = "smoke") -> dict[str, Any]:
        if suite != "smoke":
            raise WorkflowError("only smoke eval is bundled in v1")
        run = self.start("smoke eval", {"dataset_ids": ["demo"]})
        packets = self.context_retrieve(run.run_id, "What can PSKA-Essential do?", 2)
        proposal = self.propose(run.run_id, "memory_patch", "remember the workflow gate")
        review = self.review_create(proposal.proposal_id)
        blocked_before_review = False
        try:
            self.memory_apply(review.review_id)
        except WorkflowError:
            blocked_before_review = True
        self.review_decide(review.review_id, "accept", "smoke eval")
        apply_result = self.memory_apply(review.review_id)
        return {
            "suite": suite,
            "ok": bool(packets and blocked_before_review and apply_result.applied),
            "run_id": run.run_id,
            "blocked_before_review": blocked_before_review,
            "applied": to_jsonable(apply_result),
        }


def build_fake_service(db_path: str = ":memory:") -> WorkflowService:
    return WorkflowService(
        retrieval=FakeRetrievalAdapter(),
        memory=FakeMemoryAdapter(),
        store=SQLiteReviewStore(db_path),
    )


def _compose_body(kind: str, run: WorkflowRun, intent: str) -> str:
    snippets = "\n".join(f"- {packet.text[:500]}" for packet in run.context_packets)
    purpose = intent or run.intent
    if kind == "digest":
        return f"Digest candidate for: {purpose}\n\nGrounded points:\n{snippets}"
    if kind == "writing_brief":
        return f"Writing brief for: {purpose}\n\nUse these grounded notes:\n{snippets}"
    return f"Reviewed memory candidate for: {purpose}\n\n{snippets}"


def _proposal_title(kind: str, intent: str) -> str:
    label = {"digest": "Digest", "memory_patch": "Memory Patch", "writing_brief": "Writing Brief"}[kind]
    return f"{label}: {intent}".strip()


def _unique_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    result: list[SourceRef] = []
    for ref in source_refs:
        key = "|".join(
            [
                ref.adapter,
                ref.dataset_id or "",
                ref.document_id or "",
                ref.chunk_id or "",
                ref.source_id or "",
                ref.external_id or "",
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _source_manifest(packets: list[ContextPacket]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for index, packet in enumerate(packets, start=1):
        ref = packet.source_ref
        manifest.append(
            {
                "index": index,
                "context_id": packet.context_id,
                "title": packet.title or ref.title or packet.context_id,
                "adapter": ref.adapter,
                "dataset_id": ref.dataset_id or "",
                "document_id": ref.document_id or "",
                "source_id": _source_display_id(ref),
                "score": packet.score,
                "source_ref": to_jsonable(ref),
            }
        )
    return manifest


def _source_display_id(ref: SourceRef) -> str:
    parts = []
    if ref.document_id:
        parts.append(f"doc:{ref.document_id}")
    if ref.chunk_id:
        parts.append(f"chunk:{ref.chunk_id}")
    if ref.source_id:
        parts.append(f"source:{ref.source_id}")
    if ref.external_id and ref.external_id not in {ref.document_id, ref.chunk_id, ref.source_id}:
        parts.append(f"external:{ref.external_id}")
    return " / ".join(parts)


def _json_inline(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True)


def _markdown_cell(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ")
