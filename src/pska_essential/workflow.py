from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.audit import audit_event
from pska_essential.capabilities import memory_capabilities, memory_operation_capability
from pska_essential.contracts import (
    ContextPacket,
    MemoryApplyResult,
    MemoryDelete,
    MemoryFact,
    MemoryPatch,
    MemoryUpdate,
    Proposal,
    ReviewBatch,
    ReviewDecision,
    SourceContext,
    SourceRef,
    WorkflowRun,
    to_jsonable,
    utc_now_iso,
)
from pska_essential.governance import AUTO_ACCEPT, AUTO_APPLY, DURABLE_PROPOSAL_KINDS, build_workspace_policy_from_env
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
        use_kg = bool(run.scope.get("use_kg", False))
        packets = self.retrieval.retrieve(query, run.scope, limit, options={"run_id": run_id, "use_kg": use_kg})
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
                use_kg=use_kg,
            )
        )
        return packets

    def source_read(self, source_ref: SourceRef | dict[str, Any]) -> SourceContext:
        ref = source_ref if isinstance(source_ref, SourceRef) else SourceRef.from_dict(source_ref)
        source = self.retrieval.read_source(ref)
        self.store.add_audit_event(
            audit_event(
                "source.read",
                "source",
                _source_display_id(ref) or ref.external_id or ref.source_id or ref.document_id or ref.adapter or "source",
                adapter=ref.adapter,
                dataset_id=ref.dataset_id or "",
                document_id=ref.document_id or "",
                chunk_id=ref.chunk_id or "",
                source_id=ref.source_id or "",
                external_id=ref.external_id or "",
                title=ref.title or "",
                path=ref.path or "",
                url=ref.url or "",
                source_ref=to_jsonable(ref),
            )
        )
        return source

    def propose(self, run_id: str, kind: str, intent: str = "") -> Proposal:
        normalized = kind.strip().lower()
        if normalized not in {"digest", "memory_delete", "memory_patch", "memory_update", "writing_brief"}:
            raise WorkflowError("proposal kind must be digest, memory_delete, memory_patch, memory_update, or writing_brief")
        run = self.store.get_workflow(run_id)
        if normalized == "memory_delete":
            return self._propose_memory_delete(run, intent)
        if normalized == "memory_update":
            return self._propose_memory_update(run, intent)
        if not run.context_packets:
            raise WorkflowError("cannot propose without retrieved context")
        source_refs = _unique_source_refs([packet.source_ref for packet in run.context_packets])
        source_refs = _unique_source_refs([*source_refs, *_memory_source_refs(run)])
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
        proposal = self.store.get_proposal(proposal_id)
        _ensure_durable_proposal_source_trace(proposal, "review creation")
        review = self.store.create_review(proposal_id)
        self.store.add_audit_event(
            audit_event(
                "review.create",
                "review",
                review.review_id,
                proposal_id=proposal_id,
                run_id=proposal.run_id,
                proposal_kind=proposal.kind,
                source_count=len(proposal.source_refs),
            )
        )
        return review

    def memory_review_from_workflow(self, run_id: str, intent: str = "") -> dict[str, Any]:
        """Govern durable memory creation from an existing sourced workflow.

        Transient work products may be produced freely. This method is the
        explicit transition where selected workflow context becomes a governed
        durable memory candidate.
        """

        self._ensure_memory_operation_supported("apply")
        run = self.store.get_workflow(run_id)
        policy = build_workspace_policy_from_env()
        governance_action = policy.action_for("memory_patch")
        proposal = self.propose(run_id, "memory_patch", intent or run.intent)
        review = self.review_create(proposal.proposal_id)
        review_decision = None
        memory_apply = None
        if governance_action in {AUTO_ACCEPT, AUTO_APPLY}:
            review_decision = self.review_decide(
                review.review_id,
                "accept",
                f"accepted by workspace policy: {governance_action}",
            )
            if governance_action == AUTO_APPLY:
                memory_apply = self.memory_apply(review.review_id)
        return {
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(review.review_id),
            "review_decision": to_jsonable(review_decision),
            "memory_apply": to_jsonable(memory_apply),
            "governance": {
                "action": governance_action,
                "durable_proposal": True,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run_id),
        }

    def memory_delete_review(self, memory_fact: MemoryFact | dict[str, Any], reason: str = "") -> dict[str, Any]:
        """Govern durable memory deletion from an explicit PSKA memory fact."""

        self._ensure_memory_operation_supported("delete")
        fact = _memory_fact_from_input(memory_fact, "delete")
        if not fact.fact_id:
            raise WorkflowError("memory delete review requires fact_id")
        if not fact.source_refs:
            raise WorkflowError("memory delete review requires source refs")
        policy = build_workspace_policy_from_env()
        governance_action = policy.action_for("memory_delete")
        run = self.start(
            f"delete durable memory {fact.fact_id}",
            {"memory_fact_id": fact.fact_id, "operation": "memory_delete"},
        )
        run.metadata["memory_delete_candidate"] = to_jsonable(
            MemoryDelete(
                target_id=fact.fact_id,
                reason=reason,
                text=fact.text,
                source_refs=fact.source_refs,
                metadata={"fact_id": fact.fact_id},
            )
        )
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        proposal = self.propose(run.run_id, "memory_delete", reason)
        review = self.review_create(proposal.proposal_id)
        review_decision = None
        memory_apply = None
        if governance_action in {AUTO_ACCEPT, AUTO_APPLY}:
            review_decision = self.review_decide(
                review.review_id,
                "accept",
                f"accepted by workspace policy: {governance_action}",
            )
            if governance_action == AUTO_APPLY:
                memory_apply = self.memory_apply(review.review_id)
        return {
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(review.review_id),
            "review_decision": to_jsonable(review_decision),
            "memory_apply": to_jsonable(memory_apply),
            "governance": {
                "action": governance_action,
                "durable_proposal": True,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run.run_id),
        }

    def memory_update_review(
        self,
        memory_fact: MemoryFact | dict[str, Any],
        text: str,
        reason: str = "",
    ) -> dict[str, Any]:
        """Govern durable memory update from an explicit PSKA memory fact."""

        self._ensure_memory_operation_supported("update")
        fact = _memory_fact_from_input(memory_fact, "update")
        updated_text = text.strip()
        if not fact.fact_id:
            raise WorkflowError("memory update review requires fact_id")
        if not updated_text:
            raise WorkflowError("memory update review requires text")
        if not fact.source_refs:
            raise WorkflowError("memory update review requires source refs")
        policy = build_workspace_policy_from_env()
        governance_action = policy.action_for("memory_update")
        run = self.start(
            f"update durable memory {fact.fact_id}",
            {"memory_fact_id": fact.fact_id, "operation": "memory_update"},
        )
        run.metadata["memory_update_candidate"] = to_jsonable(
            MemoryUpdate(
                target_id=fact.fact_id,
                text=updated_text,
                previous_text=fact.text,
                reason=reason,
                source_refs=fact.source_refs,
                metadata={"fact_id": fact.fact_id},
            )
        )
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        proposal = self.propose(run.run_id, "memory_update", reason)
        review = self.review_create(proposal.proposal_id)
        review_decision = None
        memory_apply = None
        if governance_action in {AUTO_ACCEPT, AUTO_APPLY}:
            review_decision = self.review_decide(
                review.review_id,
                "accept",
                f"accepted by workspace policy: {governance_action}",
            )
            if governance_action == AUTO_APPLY:
                memory_apply = self.memory_apply(review.review_id)
        return {
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(review.review_id),
            "review_decision": to_jsonable(review_decision),
            "memory_apply": to_jsonable(memory_apply),
            "governance": {
                "action": governance_action,
                "durable_proposal": True,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run.run_id),
        }

    def review_decide(self, review_id: str, decision: str, reason: str) -> ReviewDecision:
        if self.store.get_memory_apply(review_id):
            raise WorkflowError("cannot change review decision after durable memory has been applied")
        review = self.store.get_review(review_id)
        proposal = self.store.get_proposal(str(review["proposal_id"]))
        if _is_accept_decision(decision):
            _ensure_durable_proposal_source_trace(proposal, "review acceptance")
        decided = self.store.decide_review(review_id, decision, reason)
        self.store.add_audit_event(
            audit_event(
                "review.decide",
                "review",
                review_id,
                proposal_id=decided.proposal_id,
                run_id=proposal.run_id,
                proposal_kind=proposal.kind,
                source_count=len(proposal.source_refs),
                decision=decided.decision,
                status=decided.status,
                reason=reason,
            )
        )
        return decided

    def review_revise(self, review_id: str, intent: str = "") -> dict[str, Any]:
        review = self.store.get_review(review_id)
        if str(review["status"]) != "needs_edit":
            raise WorkflowError("review revision requires needs_edit status")
        original = self.store.get_proposal(str(review["proposal_id"]))
        revision_intent = intent or str(review.get("reason") or "") or original.intent
        proposal = self.propose(original.run_id, original.kind, revision_intent)
        revised = self.review_create(proposal.proposal_id)
        self.store.add_audit_event(
            audit_event(
                "review.revise",
                "review",
                revised.review_id,
                previous_review_id=review_id,
                previous_proposal_id=original.proposal_id,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                proposal_kind=proposal.kind,
                source_count=len(proposal.source_refs),
            )
        )
        return {
            "previous_review": self.store.get_review_record(review_id),
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(revised.review_id),
            "artifact": self.workflow_artifact(proposal.run_id),
        }

    def memory_search(self, query: str, scope: dict[str, Any] | None = None, limit: int = 10) -> list[MemoryFact]:
        search_scope = dict(scope or {})
        facts = self.memory.search(query, search_scope, limit)
        self.store.add_audit_event(
            audit_event(
                "memory.search",
                "memory_scope",
                ",".join(str(item) for item in search_scope.get("dataset_ids", [])) or "workspace",
                query=query,
                count=len(facts),
                scope=search_scope,
            )
        )
        return facts

    def memory_apply(self, review_id: str) -> MemoryApplyResult:
        existing = self.store.get_memory_apply(review_id)
        if existing:
            return MemoryApplyResult(**existing)
        review = self.store.get_review(review_id)
        if review["status"] != "accepted":
            raise WorkflowError("memory apply requires an accepted review")
        proposal = self.store.get_proposal(str(review["proposal_id"]))
        _ensure_durable_proposal_source_trace(proposal, "memory apply")
        if proposal.kind == "memory_patch":
            self._ensure_memory_operation_supported("apply")
            if proposal.memory_patch is None:
                raise WorkflowError("memory_patch proposal is missing memory patch payload")
            if not proposal.memory_patch.source_refs:
                raise WorkflowError("memory patch requires source refs before apply")
            result = self.memory.apply(proposal.memory_patch)
            self.store.save_memory_apply(review_id, to_jsonable(result))
            self.store.add_audit_event(
                audit_event(
                    "memory.apply",
                    "review",
                    review_id,
                    proposal_id=proposal.proposal_id,
                    run_id=proposal.run_id,
                    proposal_kind=proposal.kind,
                    applied=result.applied,
                    memory_target_id=result.target_id,
                    backend=result.backend,
                    layer=proposal.memory_patch.layer,
                    confidence=proposal.memory_patch.confidence,
                    source_count=len(proposal.memory_patch.source_refs),
                    source_refs=to_jsonable(proposal.memory_patch.source_refs),
                )
            )
            return result
        if proposal.kind == "memory_update":
            self._ensure_memory_operation_supported("update")
            if proposal.memory_update is None:
                raise WorkflowError("memory_update proposal is missing memory update payload")
            if not proposal.memory_update.source_refs:
                raise WorkflowError("memory update requires source refs before apply")
            result = self.memory.update(proposal.memory_update)
            self.store.save_memory_apply(review_id, to_jsonable(result))
            self.store.add_audit_event(
                audit_event(
                    "memory.update",
                    "review",
                    review_id,
                    proposal_id=proposal.proposal_id,
                    run_id=proposal.run_id,
                    proposal_kind=proposal.kind,
                    applied=result.applied,
                    memory_target_id=result.target_id,
                    backend=result.backend,
                    reason=proposal.memory_update.reason,
                    version=result.metadata.get("version"),
                    source_count=len(proposal.memory_update.source_refs),
                    source_refs=to_jsonable(proposal.memory_update.source_refs),
                )
            )
            return result
        if proposal.kind == "memory_delete":
            self._ensure_memory_operation_supported("delete")
            if proposal.memory_delete is None:
                raise WorkflowError("memory_delete proposal is missing memory delete payload")
            if not proposal.memory_delete.source_refs:
                raise WorkflowError("memory delete requires source refs before apply")
            result = self.memory.delete(proposal.memory_delete)
            self.store.save_memory_apply(review_id, to_jsonable(result))
            self.store.add_audit_event(
                audit_event(
                    "memory.delete",
                    "review",
                    review_id,
                    proposal_id=proposal.proposal_id,
                    run_id=proposal.run_id,
                    proposal_kind=proposal.kind,
                    applied=result.applied,
                    memory_target_id=result.target_id,
                    backend=result.backend,
                    reason=proposal.memory_delete.reason,
                    source_count=len(proposal.memory_delete.source_refs),
                    source_refs=to_jsonable(proposal.memory_delete.source_refs),
                )
            )
            return result
        raise WorkflowError("only durable memory proposals can be applied to memory")

    def _ensure_memory_operation_supported(self, operation: str) -> None:
        capability = memory_operation_capability(self.memory, operation)
        if capability.get("supported") is not False:
            return
        backend = memory_capabilities(self.memory)["backend"]
        reason = str(capability.get("reason") or "operation is not supported")
        raise WorkflowError(f"memory {operation} is not supported by {backend}: {reason}")

    def memory_lifecycle(self, memory_target_id: str, limit: int = 50) -> dict[str, Any]:
        target_id = str(memory_target_id or "").strip()
        if not target_id:
            raise WorkflowError("memory lifecycle requires memory_target_id")
        if limit < 1:
            raise WorkflowError("memory lifecycle limit must be positive")

        lifecycle_actions = {"memory.apply", "memory.update", "memory.delete"}
        events = [
            event
            for event in self.store.list_audit_events(descending=False)
            if event.action in lifecycle_actions and str(event.metadata.get("memory_target_id") or "") == target_id
        ]
        returned_events = events[-limit:]
        return {
            "memory_target_id": target_id,
            "change_count": len(events),
            "returned_count": len(returned_events),
            "latest_event": to_jsonable(events[-1]) if events else None,
            "events": to_jsonable(returned_events),
        }

    def workflow_artifact(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_workflow(run_id)
        return self._build_workflow_artifact(run)

    def render_brief(self, run_id: str, format: str = "markdown") -> str | dict[str, Any]:
        run = self.store.get_workflow(run_id)
        artifact = self._build_workflow_artifact(run)
        fmt = format.strip().lower()
        if fmt not in {"markdown", "json"}:
            raise WorkflowError("export format must be markdown or json")
        return self._format_artifact(run, artifact, fmt)

    def export_brief(self, run_id: str, format: str = "markdown") -> str | dict[str, Any]:
        run = self.store.get_workflow(run_id)
        artifact = self._build_workflow_artifact(run)
        fmt = format.strip().lower()
        if fmt not in {"markdown", "json"}:
            raise WorkflowError("export format must be markdown or json")
        packet_payload = artifact["context_packets"]
        proposal_payload = artifact["proposals"]
        source_manifest = artifact["source_manifest"]
        source_inspections = artifact.get("source_inspections") or []
        memory_source_manifest = artifact["memory_source_manifest"]
        export_event = self.store.add_audit_event(
            audit_event(
                "workflow.export",
                "workflow",
                run_id,
                format=fmt,
                context_count=len(packet_payload),
                source_inspection_count=len(source_inspections),
                memory_count=len(artifact.get("memory_facts") or []),
                memory_source_count=len(memory_source_manifest),
                proposal_count=len(proposal_payload),
                source_count=len(source_manifest),
                scope=run.scope,
            )
        )
        artifact["traceability"]["export"] = {
            "audit_event_id": export_event.audit_event_id,
            "action": export_event.action,
            "target_type": export_event.target_type,
            "target_id": export_event.target_id,
            "format": fmt,
            "source_inspection_count": len(source_inspections),
            "exported_at": export_event.created_at,
        }
        return self._format_artifact(run, artifact, fmt)

    def _format_artifact(
        self,
        run: WorkflowRun,
        artifact: dict[str, Any],
        fmt: str,
    ) -> str | dict[str, Any]:
        source_manifest = artifact["source_manifest"]
        source_inspections = artifact.get("source_inspections") or []
        memory_facts = artifact.get("memory_facts") or []
        memory_source_manifest = artifact.get("memory_source_manifest") or []
        if fmt == "json":
            return artifact
        lines = [
            f"# PSKA-Essential Brief: {run.intent}",
            "",
            f"- Run: `{run.run_id}`",
            f"- Status: `{run.status}`",
            f"- Scope: `{_json_inline(run.scope)}`",
            f"- Source count: `{len(source_manifest)}`",
            f"- Inspected source count: `{len(source_inspections)}`",
        ]
        export_trace = artifact.get("traceability", {}).get("export")
        if export_trace:
            lines.extend(
                [
                    f"- Export audit event: `{export_trace['audit_event_id']}`",
                    f"- Exported at: `{export_trace['exported_at']}`",
                    f"- Export format: `{export_trace['format']}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Work Product",
                "",
            ]
        )
        proposal_payload = artifact["proposals"]
        if proposal_payload:
            latest = proposal_payload[-1]
            lines.extend([str(latest.get("body") or ""), ""])
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
        if source_inspections:
            lines.extend(["## Inspected Sources", ""])
            for index, source in enumerate(source_inspections, start=1):
                source_ref = SourceRef.from_dict(source.get("source_ref") or {})
                title = source_ref.title or source_ref.document_id or source_ref.source_id or f"Source {index}"
                lines.extend(
                    [
                        f"### [{index}] {title}",
                        "",
                        str(source.get("text") or ""),
                        "",
                        f"Source [{index}]: `{source_ref.adapter}` / `{_source_display_id(source_ref)}`",
                        "",
                    ]
                )
        if memory_facts:
            lines.extend(["## Durable Workspace Memory", ""])
            for index, fact in enumerate(memory_facts, start=1):
                lines.extend([f"### Memory [{index}] `{fact.get('fact_id') or ''}`", "", str(fact.get("text") or ""), ""])
                memory_sources = [source for source in memory_source_manifest if source["memory_index"] == index]
                if memory_sources:
                    lines.extend(
                        [
                            "| Source | Adapter | Dataset | Document | Chunk/Source |",
                            "| --- | --- | --- | --- | --- |",
                        ]
                    )
                    for source in memory_sources:
                        lines.append(
                            "| {source_index} | {adapter} | {dataset_id} | {document_id} | {source_id} |".format(
                                source_index=source["source_index"],
                                adapter=_markdown_cell(source["adapter"]),
                                dataset_id=_markdown_cell(source["dataset_id"]),
                                document_id=_markdown_cell(source["document_id"]),
                                source_id=_markdown_cell(source["source_id"]),
                            )
                        )
                    lines.append("")
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

    def _build_workflow_artifact(self, run: WorkflowRun) -> dict[str, Any]:
        packet_payload = [to_jsonable(packet) for packet in run.context_packets]
        proposal_payload = [
            to_jsonable(self.store.get_proposal(proposal_id)) for proposal_id in run.proposal_ids
        ]
        memory_facts = list(run.metadata.get("memory_context") or [])
        source_inspections = list(run.metadata.get("source_inspections") or [])
        source_manifest = _source_manifest(run.context_packets)
        memory_source_manifest = _memory_source_manifest(memory_facts)
        return {
            "run": to_jsonable(run),
            "scope": run.scope,
            "proposals": proposal_payload,
            "latest_proposal": proposal_payload[-1] if proposal_payload else None,
            "source_manifest": source_manifest,
            "context_packets": packet_payload,
            "source_inspections": source_inspections,
            "memory_facts": memory_facts,
            "memory_source_manifest": memory_source_manifest,
            "traceability": {
                "context_count": len(packet_payload),
                "source_inspection_count": len(source_inspections),
                "memory_count": len(memory_facts),
                "memory_source_count": len(memory_source_manifest),
                "proposal_count": len(proposal_payload),
                "source_count": len(source_manifest),
            },
        }

    def _propose_memory_update(self, run: WorkflowRun, intent: str = "") -> Proposal:
        candidate = run.metadata.get("memory_update_candidate") or {}
        if not candidate:
            raise WorkflowError("memory_update proposal requires an explicit memory update candidate")
        memory_update = MemoryUpdate.from_dict(candidate)
        if intent:
            memory_update.reason = intent
        if not memory_update.target_id:
            raise WorkflowError("memory_update proposal requires target_id")
        if not memory_update.text.strip():
            raise WorkflowError("memory_update proposal requires text")
        if not memory_update.source_refs:
            raise WorkflowError("memory_update proposal requires source refs")
        proposal_id = f"prop_{uuid4().hex}"
        body = _compose_memory_update_body(memory_update, intent or memory_update.reason)
        proposal = Proposal(
            proposal_id=proposal_id,
            run_id=run.run_id,
            kind="memory_update",
            intent=intent or memory_update.reason or run.intent,
            title=_proposal_title("memory_update", memory_update.target_id),
            body=body,
            source_refs=memory_update.source_refs,
            memory_update=memory_update,
        )
        self.store.save_proposal(proposal)
        run.proposal_ids.append(proposal.proposal_id)
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        self.store.add_audit_event(
            audit_event(
                "proposal.create",
                "proposal",
                proposal.proposal_id,
                kind=proposal.kind,
                run_id=run.run_id,
                memory_target_id=memory_update.target_id,
            )
        )
        return proposal

    def _propose_memory_delete(self, run: WorkflowRun, intent: str = "") -> Proposal:
        candidate = run.metadata.get("memory_delete_candidate") or {}
        if not candidate:
            raise WorkflowError("memory_delete proposal requires an explicit memory delete candidate")
        memory_delete = MemoryDelete.from_dict(candidate)
        if intent:
            memory_delete.reason = intent
        if not memory_delete.target_id:
            raise WorkflowError("memory_delete proposal requires target_id")
        if not memory_delete.source_refs:
            raise WorkflowError("memory_delete proposal requires source refs")
        proposal_id = f"prop_{uuid4().hex}"
        body = _compose_memory_delete_body(memory_delete, intent or memory_delete.reason)
        proposal = Proposal(
            proposal_id=proposal_id,
            run_id=run.run_id,
            kind="memory_delete",
            intent=intent or memory_delete.reason or run.intent,
            title=_proposal_title("memory_delete", memory_delete.target_id),
            body=body,
            source_refs=memory_delete.source_refs,
            memory_delete=memory_delete,
        )
        self.store.save_proposal(proposal)
        run.proposal_ids.append(proposal.proposal_id)
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        self.store.add_audit_event(
            audit_event(
                "proposal.create",
                "proposal",
                proposal.proposal_id,
                kind=proposal.kind,
                run_id=run.run_id,
                memory_target_id=memory_delete.target_id,
            )
        )
        return proposal

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


def _memory_fact_from_input(memory_fact: MemoryFact | dict[str, Any], operation: str) -> MemoryFact:
    if isinstance(memory_fact, MemoryFact):
        return memory_fact
    try:
        return MemoryFact.from_dict(memory_fact)
    except TypeError as exc:
        raise WorkflowError(f"memory {operation} review requires a valid MemoryFact") from exc


def _is_accept_decision(decision: str) -> bool:
    normalized = decision.strip().lower()
    return normalized in {"accept", "accepted", "approve", "approved", "yes"}


def _ensure_durable_proposal_source_trace(proposal: Proposal, transition: str) -> None:
    if proposal.kind not in DURABLE_PROPOSAL_KINDS:
        return
    if not proposal.source_refs:
        raise WorkflowError(f"durable {proposal.kind} {transition} requires source refs")
    if proposal.kind == "memory_patch":
        if proposal.memory_patch is None:
            raise WorkflowError("memory_patch proposal is missing memory patch payload")
        if not proposal.memory_patch.source_refs:
            raise WorkflowError(f"durable {proposal.kind} {transition} requires source refs")
        return
    if proposal.kind == "memory_update":
        if proposal.memory_update is None:
            raise WorkflowError("memory_update proposal is missing memory update payload")
        if not proposal.memory_update.source_refs:
            raise WorkflowError(f"durable {proposal.kind} {transition} requires source refs")
        return
    if proposal.kind == "memory_delete":
        if proposal.memory_delete is None:
            raise WorkflowError("memory_delete proposal is missing memory delete payload")
        if not proposal.memory_delete.source_refs:
            raise WorkflowError(f"durable {proposal.kind} {transition} requires source refs")
        return


def _compose_body(kind: str, run: WorkflowRun, intent: str) -> str:
    snippets = "\n".join(f"- {packet.text[:500]}" for packet in run.context_packets)
    memory_snippets = "\n".join(
        f"- {str(fact.get('text') or '')[:500]}" for fact in run.metadata.get("memory_context", [])
    )
    purpose = intent or run.intent
    memory_section = f"\n\nDurable workspace memory:\n{memory_snippets}" if memory_snippets else ""
    if kind == "digest":
        return f"Digest candidate for: {purpose}\n\nGrounded points:\n{snippets}{memory_section}"
    if kind == "writing_brief":
        return f"Writing brief for: {purpose}\n\nUse these grounded notes:\n{snippets}{memory_section}"
    return f"Reviewed memory candidate for: {purpose}\n\n{snippets}{memory_section}"


def _proposal_title(kind: str, intent: str) -> str:
    label = {
        "digest": "Digest",
        "memory_delete": "Memory Delete",
        "memory_patch": "Memory Patch",
        "memory_update": "Memory Update",
        "writing_brief": "Writing Brief",
    }[kind]
    return f"{label}: {intent}".strip()


def _compose_memory_update_body(memory_update: MemoryUpdate, reason: str) -> str:
    lines = [
        f"Update durable memory `{memory_update.target_id}`.",
        "",
        "Previous memory:",
        memory_update.previous_text or "",
        "",
        "Updated memory:",
        memory_update.text,
    ]
    if reason:
        lines.extend(["", f"Reason: {reason}"])
    return "\n".join(lines).strip()


def _compose_memory_delete_body(memory_delete: MemoryDelete, reason: str) -> str:
    lines = [
        f"Delete durable memory `{memory_delete.target_id}`.",
        "",
        "Current memory:",
        memory_delete.text or "",
    ]
    if reason:
        lines.extend(["", f"Reason: {reason}"])
    return "\n".join(lines).strip()


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


def _memory_source_refs(run: WorkflowRun) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for fact in run.metadata.get("memory_context", []):
        for source_ref in fact.get("source_refs") or []:
            refs.append(SourceRef.from_dict(source_ref))
    return refs


def _memory_source_manifest(memory_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for memory_index, fact in enumerate(memory_facts, start=1):
        for source_index, source_ref in enumerate(fact.get("source_refs") or [], start=1):
            ref = SourceRef.from_dict(source_ref)
            manifest.append(
                {
                    "memory_index": memory_index,
                    "memory_fact_id": fact.get("fact_id") or "",
                    "source_index": source_index,
                    "adapter": ref.adapter,
                    "dataset_id": ref.dataset_id or "",
                    "document_id": ref.document_id or "",
                    "source_id": _source_display_id(ref),
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
