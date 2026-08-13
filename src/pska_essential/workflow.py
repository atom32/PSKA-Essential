from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.audit import audit_event
from pska_essential.capabilities import (
    APPEND_CORRECTION_EPISODE,
    MEMORY_DISPLAY_TEXT_KEYS,
    MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS,
    MEMORY_SUPERSESSION_TARGET_KEYS,
    memory_capabilities,
    memory_conversation_update_strategy_supported,
    memory_operation_capability,
)
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
from pska_essential.governance import (
    AUTO_ACCEPT,
    AUTO_APPLY,
    CONVERSATION_ORIGIN,
    DIGEST_ORIGIN,
    DURABLE_ORIGIN,
    DURABLE_PROPOSAL_KINDS,
    MANUAL_REVIEW,
    build_workspace_policy_from_env,
)
from pska_essential.memory_attribution import build_attribution_from_artifact, build_suggestions_from_artifact
from pska_essential.memory_use_trace import memory_search_trace_metadata
from pska_essential.ports import MemoryPort, RetrievalPort
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.runtime_context import build_runtime_memory_scope
from pska_essential.source_registry import SQLiteSourceRegistry, is_personal_source_ref


SOURCE_PROMOTION_ORIGIN = "source_promotion"
MEMORY_CARD_TYPES = {
    "identity",
    "preference",
    "project_state",
    "working_habit",
    "source_route",
    "correction",
    "exclusion",
}
MEMORY_CARD_SCOPES = {"global", "workspace", "project", "folder"}


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
        source_registry: SQLiteSourceRegistry | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.memory = memory
        self.store = store
        self.source_registry = source_registry

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
        if is_personal_source_ref(ref):
            source = self._source_registry().read_source(ref)
        else:
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

    def source_root_list(self) -> list[dict[str, Any]]:
        return self._source_registry().list_roots()

    def source_root_register(
        self,
        path: str,
        *,
        kind: str = "local_folder",
        permission_mode: str = "read_only",
        label: str | None = None,
    ) -> dict[str, Any]:
        root = self._source_registry().register_root(
            path,
            kind=kind,
            permission_mode=permission_mode,
            label=label,
        )
        self.store.add_audit_event(
            audit_event(
                "source.root.register",
                "source_root",
                root["root_id"],
                kind=root["kind"],
                permission_mode=root["permission_mode"],
                label=root["label"],
                path=root["absolute_path"],
                writes_source_files=False,
            )
        )
        return root

    def source_scan(
        self,
        root_id: str,
        *,
        max_files: int = 1000,
        max_bytes: int = 1_000_000,
        extractor: str = "auto",
    ) -> dict[str, Any]:
        result = self._source_registry().scan(
            root_id,
            max_files=max_files,
            max_bytes=max_bytes,
            extractor=extractor,
        )
        self.store.add_audit_event(
            audit_event(
                "source.scan",
                "source_root",
                root_id,
                counts=result.get("counts") or {},
                active_object_count=result.get("active_object_count") or 0,
                extractor=extractor,
                writes_source_files=False,
                embedding_required=False,
            )
        )
        return result

    def source_search(
        self,
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[ContextPacket]:
        packets = self._source_registry().search(query, scope or {}, limit=limit, filters=filters or {})
        self.store.add_audit_event(
            audit_event(
                "source.search",
                "source",
                "personal_source",
                query=query,
                count=len(packets),
                scope=scope or {},
                filters=filters or {},
                embedding_required=False,
            )
        )
        return packets

    def source_neighbors(
        self,
        source_ref: SourceRef | dict[str, Any],
        *,
        strategy: str = "auto",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        ref = source_ref if isinstance(source_ref, SourceRef) else SourceRef.from_dict(source_ref)
        neighbors = self._source_registry().neighbors(ref, strategy=strategy, limit=limit)
        self.store.add_audit_event(
            audit_event(
                "source.neighbors",
                "source",
                ref.document_id or ref.source_id or "personal_source",
                strategy=strategy,
                count=len(neighbors),
                source_ref=to_jsonable(ref),
                writes_source_files=False,
                embedding_required=False,
            )
        )
        return neighbors

    def duplicate_report(
        self,
        scope: dict[str, Any] | None = None,
        *,
        mode: str = "exact_hash",
        limit: int = 50,
    ) -> dict[str, Any]:
        report = self._source_registry().duplicate_report(scope or {}, mode=mode, limit=limit)
        self.store.add_audit_event(
            audit_event(
                "source.duplicate_report",
                "source",
                report.get("report_id") or "duplicate_report",
                mode=mode,
                scope=scope or {},
                group_count=report.get("group_count") or 0,
                duplicate_file_count=report.get("duplicate_file_count") or 0,
                writes_source_files=False,
                delete_move_merge_supported=False,
            )
        )
        return report

    def source_audit_run(self, scope: dict[str, Any] | None = None, *, limit: int = 20) -> dict[str, Any]:
        audit = self._source_registry().audit(scope or {}, limit=limit)
        self.store.add_audit_event(
            audit_event(
                "source.audit.run",
                "source",
                audit.get("audit_id") or "source_audit",
                scope=scope or {},
                root_count=audit.get("root_count") or 0,
                duplicate_group_count=(audit.get("duplicate_preview") or {}).get("group_count") or 0,
                unresolved_link_count=(audit.get("unresolved_links") or {}).get("count") or 0,
                unlinked_markdown_count=(audit.get("unlinked_markdown") or {}).get("count") or 0,
                route_candidate_count=len(audit.get("route_candidates") or []),
                next_action_count=len(audit.get("next_actions") or []),
                writes_source_files=False,
                writes_memory_directly=False,
                embedding_required=False,
            )
        )
        return audit

    def saved_search_create(
        self,
        label: str,
        query: str,
        scope: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        *,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        saved = self._source_registry().saved_search_create(
            label,
            query,
            scope or {},
            filters or {},
            sort=sort,
        )
        self.store.add_audit_event(
            audit_event(
                "source.saved_search.create",
                "source_search",
                saved["search_id"],
                label=saved["label"],
                query=saved["query"],
                scope=saved["scope"],
                filters=saved["filters"],
                sort=saved["sort"],
                writes_source_files=False,
            )
        )
        return saved

    def source_tag_propose(
        self,
        target_ref: SourceRef | dict[str, Any],
        tag: str,
        *,
        reason: str = "",
        write_target: str = "sidecar",
    ) -> dict[str, Any]:
        ref = target_ref if isinstance(target_ref, SourceRef) else SourceRef.from_dict(target_ref)
        proposal = self._source_registry().propose_tag(
            ref,
            tag,
            reason=reason,
            write_target=write_target,
        )
        self.store.add_audit_event(
            audit_event(
                "source.tag.propose",
                "source_action",
                proposal["proposal_id"],
                target=proposal["target"],
                tag=proposal["payload"].get("tag"),
                reason=reason,
                write_target=write_target,
                writes_source_files=False,
            )
        )
        return proposal

    def source_tag_apply(self, proposal_id: str) -> dict[str, Any]:
        result = self._source_registry().apply_tag(proposal_id)
        self.store.add_audit_event(
            audit_event(
                "source.tag.apply",
                "source_action",
                proposal_id,
                target=result["proposal"]["target"],
                tag=result["record"].get("name"),
                already_applied=result.get("already_applied", False),
                writes_source_files=False,
                writes_sidecar=True,
            )
        )
        return result

    def source_comment_propose(
        self,
        target_ref: SourceRef | dict[str, Any],
        body: str,
        *,
        reason: str = "",
        write_target: str = "sidecar",
    ) -> dict[str, Any]:
        ref = target_ref if isinstance(target_ref, SourceRef) else SourceRef.from_dict(target_ref)
        proposal = self._source_registry().propose_comment(
            ref,
            body,
            reason=reason,
            write_target=write_target,
        )
        self.store.add_audit_event(
            audit_event(
                "source.comment.propose",
                "source_action",
                proposal["proposal_id"],
                target=proposal["target"],
                reason=reason,
                write_target=write_target,
                writes_source_files=False,
            )
        )
        return proposal

    def source_comment_apply(self, proposal_id: str) -> dict[str, Any]:
        result = self._source_registry().apply_comment(proposal_id)
        self.store.add_audit_event(
            audit_event(
                "source.comment.apply",
                "source_action",
                proposal_id,
                target=result["proposal"]["target"],
                already_applied=result.get("already_applied", False),
                writes_source_files=False,
                writes_sidecar=True,
            )
        )
        return result

    def source_obsidian_moc_propose(
        self,
        root_id: str,
        source_refs: list[SourceRef | dict[str, Any]],
        *,
        moc_path: str = "PSKA MOC.md",
        title: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        refs = [ref if isinstance(ref, SourceRef) else SourceRef.from_dict(ref) for ref in source_refs]
        proposal = self._source_registry().propose_obsidian_moc(
            root_id,
            refs,
            moc_path=moc_path,
            title=title,
            reason=reason,
        )
        self.store.add_audit_event(
            audit_event(
                "source.obsidian_moc.propose",
                "source_action",
                proposal["proposal_id"],
                target=proposal["target"],
                link_count=proposal["payload"].get("link_count") or 0,
                moc_path=proposal["payload"].get("moc_path") or "",
                reason=reason,
                writes_source_files=False,
            )
        )
        return proposal

    def source_obsidian_moc_apply(self, proposal_id: str) -> dict[str, Any]:
        result = self._source_registry().apply_obsidian_moc(proposal_id)
        self.store.add_audit_event(
            audit_event(
                "source.obsidian_moc.apply",
                "source_action",
                proposal_id,
                target=result["proposal"]["target"],
                moc_path=result["record"].get("path") or "",
                link_count=result["record"].get("link_count") or 0,
                changed=result["record"].get("changed", False),
                already_applied=result.get("already_applied", False),
                writes_source_files=result["data_flow"].get("writes_source_files", False),
                writes_sidecar=False,
            )
        )
        return result

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
        body = _compose_body(normalized, run, intent)
        if normalized == "memory_patch":
            return self._create_memory_patch_proposal(
                run,
                intent=intent or run.intent,
                memory_patch=MemoryPatch(
                    text=body,
                    source_refs=source_refs,
                    confidence=0.8,
                    metadata={"run_id": run.run_id, "intent": intent or run.intent},
                ),
            )
        proposal_id = f"prop_{uuid4().hex}"
        proposal = Proposal(
            proposal_id=proposal_id,
            run_id=run.run_id,
            kind=normalized,
            intent=intent or run.intent,
            title=_proposal_title(normalized, intent or run.intent),
            body=body,
            source_refs=source_refs,
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
        origin = self._workflow_memory_origin(run)
        requested_governance_action = policy.action_for("memory_patch", origin=origin)
        governance_action = requested_governance_action
        proposal = self.propose(run_id, "memory_patch", intent or run.intent)
        if origin == DIGEST_ORIGIN:
            proposal.metadata["origin"] = DIGEST_ORIGIN
            if proposal.memory_patch is not None:
                proposal.memory_patch.metadata["origin"] = DIGEST_ORIGIN
            self.store.save_proposal(proposal)
        if _proposal_triage_review_recommended(proposal):
            governance_action = MANUAL_REVIEW
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
                "origin": origin,
                "action": governance_action,
                "requested_action": requested_governance_action,
                "triage_override": governance_action != requested_governance_action,
                "durable_proposal": True,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run_id),
        }

    def source_memory_review_create(
        self,
        source_refs: list[SourceRef | dict[str, Any]],
        *,
        text: str,
        memory_type: str = "source_route",
        behavior_delta: str,
        memory_scope: str = "workspace",
        reason: str = "",
        confidence: float = 0.82,
        scope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a governed Memory Card candidate from explicit source evidence."""

        self._ensure_memory_operation_supported("apply")
        normalized_text = text.strip()
        normalized_behavior = behavior_delta.strip()
        normalized_type = _normalize_memory_card_type(memory_type)
        normalized_scope = _normalize_memory_card_scope(memory_scope)
        if not normalized_text:
            raise WorkflowError("source memory review requires text")
        if not normalized_behavior:
            raise WorkflowError("source memory review requires behavior_delta")
        refs = _source_refs_from_input(source_refs)
        if not refs:
            raise WorkflowError("source memory review requires source_refs")
        policy = build_workspace_policy_from_env()
        requested_governance_action = policy.action_for("memory_patch", origin=SOURCE_PROMOTION_ORIGIN)
        governance_action = requested_governance_action
        run = self.start(
            f"source memory candidate: {normalized_type}",
            {
                **dict(scope or {}),
                "operation": "memory_patch",
                "origin": SOURCE_PROMOTION_ORIGIN,
                "memory_type": normalized_type,
                "memory_scope": normalized_scope,
            },
        )
        run.context_packets.extend(self._context_packets_for_source_refs(run.run_id, refs))
        run.metadata["source_memory_candidate"] = {
            "schema": "pska.memory_card_candidate.v1",
            "memory_type": normalized_type,
            "behavior_delta": normalized_behavior,
            "memory_scope": normalized_scope,
            "reason": reason,
            "source_count": len(refs),
        }
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)

        memory_patch = MemoryPatch(
            text=normalized_text,
            source_refs=refs,
            confidence=float(confidence),
            metadata={
                "origin": SOURCE_PROMOTION_ORIGIN,
                "memory_type": normalized_type,
                "behavior_delta": normalized_behavior,
                "memory_scope": normalized_scope,
                "display_text": normalized_text,
                "reason": reason,
                "source_promotion": {
                    "schema": "pska.source_memory_promotion.v1",
                    "source_count": len(refs),
                    "source_refs": to_jsonable(refs),
                },
            },
        )
        proposal = self._create_memory_patch_proposal(
            run,
            intent=reason or f"Promote {normalized_type} from source evidence",
            memory_patch=memory_patch,
        )
        if _proposal_triage_review_recommended(proposal):
            governance_action = MANUAL_REVIEW
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
        self.store.add_audit_event(
            audit_event(
                "source.memory_review.create",
                "review",
                review.review_id,
                run_id=run.run_id,
                proposal_id=proposal.proposal_id,
                memory_type=normalized_type,
                memory_scope=normalized_scope,
                source_count=len(refs),
                governance_action=governance_action,
                writes_memory_directly=False,
            )
        )
        return {
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(review.review_id),
            "review_decision": to_jsonable(review_decision),
            "memory_apply": to_jsonable(memory_apply),
            "memory_card": {
                "schema": "pska.memory_card_candidate.v1",
                "text": normalized_text,
                "type": normalized_type,
                "behavior_delta": normalized_behavior,
                "scope": normalized_scope,
                "source_refs": to_jsonable(refs),
                "confidence": float(confidence),
                "status": "pending_review" if memory_apply is None else "applied",
            },
            "governance": {
                "origin": SOURCE_PROMOTION_ORIGIN,
                "action": governance_action,
                "requested_action": requested_governance_action,
                "triage_override": governance_action != requested_governance_action,
                "durable_proposal": True,
                "writes_memory_directly": False,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run.run_id),
        }

    def source_memory_candidates_from_audit(
        self,
        scope: dict[str, Any] | None = None,
        *,
        audit_limit: int = 20,
        candidate_limit: int = 5,
        memory_scope: str = "project",
        dedupe_existing: bool = True,
    ) -> dict[str, Any]:
        """Promote source-audit route candidates into governed review items."""

        normalized_scope = dict(scope or {})
        normalized_memory_scope = _normalize_memory_card_scope(memory_scope)
        limit = max(1, min(int(candidate_limit or 5), 25))
        audit = self.source_audit_run(normalized_scope, limit=max(int(audit_limit or 20), limit))
        existing_keys = _existing_source_memory_review_keys(self.store.list_reviews(limit=200)) if dedupe_existing else set()
        seen_keys: set[str] = set()
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for candidate in audit.get("route_candidates") or []:
            if len(created) >= limit:
                break
            source_ref = candidate.get("source_ref")
            if source_ref is None:
                skipped.append(
                    {
                        "path": str(candidate.get("path") or ""),
                        "reason": "missing_source_ref",
                    }
                )
                continue
            ref = source_ref if isinstance(source_ref, SourceRef) else SourceRef.from_dict(source_ref)
            text = _source_route_memory_text(candidate)
            behavior_delta = _source_route_behavior_delta(candidate)
            key = _source_memory_candidate_key(
                [ref],
                memory_type="source_route",
                memory_scope=normalized_memory_scope,
                behavior_delta=behavior_delta,
            )
            if key in seen_keys:
                skipped.append(_skipped_source_memory_candidate(candidate, "duplicate_in_audit"))
                continue
            seen_keys.add(key)
            if key in existing_keys:
                skipped.append(_skipped_source_memory_candidate(candidate, "existing_review"))
                continue
            result = self.source_memory_review_create(
                [ref],
                text=text,
                memory_type="source_route",
                behavior_delta=behavior_delta,
                memory_scope=normalized_memory_scope,
                reason="source audit route candidate",
                confidence=0.82,
                scope=normalized_scope,
            )
            created.append(
                {
                    "schema": "pska.source_memory_candidate.v1",
                    "path": str(candidate.get("path") or ref.path or ""),
                    "title": str(candidate.get("title") or ref.title or ""),
                    "memory_type": "source_route",
                    "memory_scope": normalized_memory_scope,
                    "text": text,
                    "behavior_delta": behavior_delta,
                    "source_refs": to_jsonable([ref]),
                    "review_id": result["review"]["review_id"],
                    "proposal_id": result["proposal"]["proposal_id"],
                    "status": result["review"]["status"],
                }
            )
            existing_keys.add(key)
        result = {
            "schema": "pska.source_memory_candidates_from_audit.v1",
            "status": "created" if created else "empty",
            "scope": normalized_scope,
            "audit": audit,
            "audit_id": audit.get("audit_id") or "",
            "route_candidate_count": len(audit.get("route_candidates") or []),
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created": created,
            "skipped": skipped,
            "data_flow": {
                "writes_source_files": False,
                "writes_memory_directly": False,
                "creates_review": bool(created),
                "embedding_required": False,
            },
        }
        self.store.add_audit_event(
            audit_event(
                "source.memory_candidates.from_audit",
                "source_audit",
                result["audit_id"] or "source_audit",
                scope=normalized_scope,
                audit_limit=audit_limit,
                candidate_limit=limit,
                route_candidate_count=result["route_candidate_count"],
                created_count=result["created_count"],
                skipped_count=result["skipped_count"],
                writes_source_files=False,
                writes_memory_directly=False,
                creates_review=bool(created),
                embedding_required=False,
            )
        )
        return result

    def eidolia_context_read(
        self,
        *,
        project_id: str,
        node_id: str,
        node_type: str = "thought",
        text: str = "",
        title: str = "",
        canvas_path: str = "",
        role: str = "",
        artifact_kind: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Represent an Eidolia thought/artifact as source-safe PSKA context."""

        ref = _eidolia_source_ref(
            project_id=project_id,
            node_id=node_id,
            node_type=node_type,
            title=title,
            canvas_path=canvas_path,
            role=role,
            artifact_kind=artifact_kind,
            metadata=metadata or {},
        )
        normalized_text = text.strip()
        result = {
            "schema": "pska.eidolia_context.v1",
            "source_ref": to_jsonable(ref),
            "text": normalized_text,
            "metadata": {
                "source_layer": "thought_artifact",
                "project_id": project_id.strip(),
                "node_id": node_id.strip(),
                "node_type": _normalize_eidolia_node_type(node_type),
                "role": role.strip(),
                "artifact_kind": artifact_kind.strip(),
                "canvas_path": canvas_path.strip(),
                "read_mode": "request_payload",
                "canonical_owner": "eidolia_project",
            },
            "data_flow": {
                "writes_memory_directly": False,
                "writes_source_files": False,
                "embedding_required": False,
            },
            "limitations": [
                "This v1 bridge reads the caller-provided Eidolia node payload and normalizes SourceRef metadata.",
                "It does not copy Eidolia project files into PSKA or mutate the canvas.",
            ],
        }
        self.store.add_audit_event(
            audit_event(
                "eidolia.context.read",
                "eidolia_node",
                ref.external_id or ref.source_id or "eidolia_node",
                project_id=ref.source_id or "",
                node_id=ref.external_id or "",
                node_type=ref.metadata.get("node_type") or "",
                role=ref.metadata.get("role") or "",
                artifact_kind=ref.metadata.get("artifact_kind") or "",
                writes_memory_directly=False,
                writes_source_files=False,
            )
        )
        return result

    def eidolia_memory_review_create(
        self,
        *,
        project_id: str,
        node_id: str,
        text: str,
        behavior_delta: str,
        node_type: str = "thought",
        title: str = "",
        canvas_path: str = "",
        role: str = "",
        artifact_kind: str = "",
        memory_type: str = "project_state",
        memory_scope: str = "project",
        reason: str = "",
        confidence: float = 0.82,
        scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Promote an Eidolia thought/artifact node into a governed Memory Card candidate."""

        ref = _eidolia_source_ref(
            project_id=project_id,
            node_id=node_id,
            node_type=node_type,
            title=title,
            canvas_path=canvas_path,
            role=role,
            artifact_kind=artifact_kind,
            metadata=metadata or {},
        )
        normalized_scope = {
            **dict(scope or {}),
            "eidolia_project_id": ref.source_id or "",
            "eidolia_node_id": ref.external_id or "",
        }
        created = self.source_memory_review_create(
            [ref],
            text=text,
            memory_type=memory_type,
            behavior_delta=behavior_delta,
            memory_scope=memory_scope,
            reason=reason or f"Promote Eidolia {ref.metadata.get('node_type')} to memory",
            confidence=confidence,
            scope=normalized_scope,
        )
        created["eidolia"] = {
            "schema": "pska.eidolia_memory_review.v1",
            "project_id": ref.source_id or "",
            "node_id": ref.external_id or "",
            "node_type": ref.metadata.get("node_type") or "",
            "role": ref.metadata.get("role") or "",
            "artifact_kind": ref.metadata.get("artifact_kind") or "",
            "canvas_path": ref.path or "",
            "source_ref": to_jsonable(ref),
        }
        created["memory_card"]["source_origin"] = "eidolia"
        self.store.add_audit_event(
            audit_event(
                "eidolia.memory_review.create",
                "review",
                created["review"]["review_id"],
                project_id=ref.source_id or "",
                node_id=ref.external_id or "",
                node_type=ref.metadata.get("node_type") or "",
                memory_type=created["memory_card"]["type"],
                memory_scope=created["memory_card"]["scope"],
                writes_memory_directly=False,
                writes_source_files=False,
            )
        )
        return created

    def memory_delete_review(self, memory_fact: MemoryFact | dict[str, Any], reason: str = "") -> dict[str, Any]:
        """Govern durable memory deletion from an explicit PSKA memory fact."""

        self._ensure_memory_operation_supported("delete")
        fact = _memory_fact_from_input(memory_fact, "delete")
        if not fact.fact_id:
            raise WorkflowError("memory delete review requires fact_id")
        if not fact.source_refs:
            raise WorkflowError("memory delete review requires source refs")
        policy = build_workspace_policy_from_env()
        requested_governance_action = policy.action_for("memory_delete")
        governance_action = requested_governance_action
        run = self.start(
            f"delete durable memory {fact.fact_id}",
            {
                **_memory_fact_scope_metadata(fact),
                "memory_fact_id": fact.fact_id,
                "operation": "memory_delete",
            },
        )
        run.metadata["memory_delete_candidate"] = to_jsonable(
            _annotated_memory_delete(
                target_id=fact.fact_id,
                reason=reason,
                text=fact.text,
                source_refs=fact.source_refs,
                metadata=_memory_fact_scope_metadata(fact),
                origin=DURABLE_ORIGIN,
            )
        )
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        proposal = self.propose(run.run_id, "memory_delete", reason)
        if _proposal_triage_review_recommended(proposal):
            governance_action = MANUAL_REVIEW
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
                "requested_action": requested_governance_action,
                "triage_override": governance_action != requested_governance_action,
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
        requested_governance_action = policy.action_for("memory_update")
        governance_action = requested_governance_action
        run = self.start(
            f"update durable memory {fact.fact_id}",
            {
                **_memory_fact_scope_metadata(fact),
                "memory_fact_id": fact.fact_id,
                "operation": "memory_update",
            },
        )
        run.metadata["memory_update_candidate"] = to_jsonable(
            _annotated_memory_update(
                target_id=fact.fact_id,
                text=updated_text,
                previous_text=fact.text,
                reason=reason,
                source_refs=fact.source_refs,
                metadata=_memory_fact_scope_metadata(fact),
                origin=DURABLE_ORIGIN,
            )
        )
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)
        proposal = self.propose(run.run_id, "memory_update", reason)
        if _proposal_triage_review_recommended(proposal):
            governance_action = MANUAL_REVIEW
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
                "requested_action": requested_governance_action,
                "triage_override": governance_action != requested_governance_action,
                "durable_proposal": True,
                "policy": policy.to_dict(),
            },
            "artifact": self.workflow_artifact(run.run_id),
        }

    def memory_change_from_conversation(
        self,
        *,
        user_message: str,
        operation: str = "auto",
        text: str = "",
        memory_fact: MemoryFact | dict[str, Any] | None = None,
        source_refs: list[SourceRef | dict[str, Any]] | None = None,
        session_id: str = "",
        message_id: str = "",
        reason: str = "",
        scope: dict[str, Any] | None = None,
        force_review: bool = False,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        """Govern normal memory changes expressed inside conversation."""

        message = user_message.strip()
        if not message:
            raise WorkflowError("conversation memory change requires user_message")
        fact = _optional_memory_fact_from_input(memory_fact)
        normalized_operation = _normalize_conversation_memory_operation(
            operation=operation,
            memory_fact=fact,
            text=text,
            user_message=message,
        )
        proposal_operation = normalized_operation
        backend_operation = {
            "memory_patch": "apply",
            "memory_update": "update",
            "memory_delete": "delete",
        }[normalized_operation]
        memory_update_strategy = ""
        if normalized_operation == "memory_update" and not memory_operation_capability(
            self.memory, "update"
        ).get("supported", False):
            if memory_conversation_update_strategy_supported(self.memory, APPEND_CORRECTION_EPISODE):
                proposal_operation = "memory_patch"
                backend_operation = "apply"
                memory_update_strategy = APPEND_CORRECTION_EPISODE
        self._ensure_memory_operation_supported(backend_operation)

        policy = build_workspace_policy_from_env()
        target_resolution: dict[str, Any] | None = None
        if fact is None and normalized_operation in {"memory_update", "memory_delete"}:
            fact, target_resolution = _resolve_conversation_memory_target(
                self.memory,
                user_message=message,
                text=text,
                reason=reason,
                operation=normalized_operation,
                scope=scope or {},
            )
            self.store.add_audit_event(
                audit_event(
                    "memory.conversation_target_resolution",
                    "memory_scope",
                    _conversation_scope_target_id(scope or {}),
                    operation=normalized_operation,
                    status=target_resolution["status"],
                    query=target_resolution["query"],
                    candidate_count=target_resolution["candidate_count"],
                    selected_fact_id=target_resolution.get("selected_fact_id", ""),
                    session_id=session_id,
                    message_id=message_id,
                )
            )
            if fact is None:
                return _conversation_memory_needs_target_response(
                    operation=normalized_operation,
                    requested_operation=operation,
                    user_message=message,
                    text=text,
                    reason=reason,
                    session_id=session_id,
                    message_id=message_id,
                    scope=scope or {},
                    force_review=force_review,
                    policy=policy.to_dict(),
                    target_resolution=target_resolution,
                )
        elif fact is not None and normalized_operation in {"memory_update", "memory_delete"}:
            target_resolution = _provided_conversation_memory_target_resolution(fact)
        governance_action = policy.action_for(
            normalized_operation,
            origin=CONVERSATION_ORIGIN,
            force_review=force_review,
        )
        run = self.start(
            f"conversation memory {normalized_operation}",
            {
                **dict(scope or {}),
                "operation": normalized_operation,
                "origin": CONVERSATION_ORIGIN,
                "session_id": session_id,
                "message_id": message_id,
            },
        )
        conversation_source_refs = _conversation_source_refs(
            run_id=run.run_id,
            user_message=message,
            source_refs=source_refs or [],
            session_id=session_id,
            message_id=message_id,
            scope=scope or {},
        )
        memory_scope_metadata = _memory_runtime_scope(scope or {})
        run.metadata["conversation_memory_request"] = {
            "operation": normalized_operation,
            "requested_operation": operation,
            "user_message": message,
            "text": text,
            "reason": reason,
            "session_id": session_id,
            "message_id": message_id,
            "force_review": force_review,
            "target_resolution": target_resolution,
            "proposal_operation": proposal_operation,
            "backend_operation": backend_operation,
            "memory_update_strategy": memory_update_strategy,
        }
        run.updated_at = utc_now_iso()
        self.store.save_workflow(run)

        intent = reason or _conversation_intent(normalized_operation, message)
        if proposal_operation == "memory_patch":
            patch_text = _conversation_memory_text(text=text, user_message=message)
            patch_source_refs = conversation_source_refs
            patch_metadata = {
                "origin": CONVERSATION_ORIGIN,
                "user_message": message,
                "session_id": session_id,
                "message_id": message_id,
                **memory_scope_metadata,
            }
            if memory_update_strategy == APPEND_CORRECTION_EPISODE:
                if fact is None:
                    raise WorkflowError("conversation memory update requires memory_fact")
                if not text.strip():
                    raise WorkflowError("conversation memory update requires text")
                patch_text = _conversation_correction_episode_text(
                    current_text=text.strip(),
                    previous_text=fact.text,
                    target_fact_id=fact.fact_id,
                )
                patch_source_refs = _unique_source_refs([*fact.source_refs, *conversation_source_refs])
                patch_metadata.update(
                    {
                        "semantic_operation": normalized_operation,
                        "memory_update_strategy": memory_update_strategy,
                        "target_fact_id": fact.fact_id,
                        "current_text": text.strip(),
                        "display_text": text.strip(),
                        "previous_text": fact.text,
                    }
                )
            proposal = self._create_memory_patch_proposal(
                run,
                intent=intent,
                memory_patch=_annotated_memory_patch(
                    text=patch_text,
                    source_refs=patch_source_refs,
                    confidence=float(confidence),
                    metadata=patch_metadata,
                    operation="memory_patch",
                    origin=CONVERSATION_ORIGIN,
                ),
            )
        elif proposal_operation == "memory_update":
            if fact is None:
                raise WorkflowError("conversation memory update requires memory_fact")
            updated_text = text.strip()
            if not updated_text:
                raise WorkflowError("conversation memory update requires text")
            run.metadata["memory_update_candidate"] = to_jsonable(
                _annotated_memory_update(
                    target_id=fact.fact_id,
                    text=updated_text,
                    previous_text=fact.text,
                    reason=reason or message,
                    source_refs=_unique_source_refs([*fact.source_refs, *conversation_source_refs]),
                    metadata={
                        "fact_id": fact.fact_id,
                        "origin": CONVERSATION_ORIGIN,
                        "user_message": message,
                        "session_id": session_id,
                        "message_id": message_id,
                        **memory_scope_metadata,
                    },
                    origin=CONVERSATION_ORIGIN,
                    confidence=float(confidence),
                )
            )
            run.updated_at = utc_now_iso()
            self.store.save_workflow(run)
            proposal = self.propose(run.run_id, "memory_update", intent)
        else:
            if fact is None:
                raise WorkflowError("conversation memory delete requires memory_fact")
            run.metadata["memory_delete_candidate"] = to_jsonable(
                _annotated_memory_delete(
                    target_id=fact.fact_id,
                    reason=reason or message,
                    text=fact.text,
                    source_refs=_unique_source_refs([*fact.source_refs, *conversation_source_refs]),
                    metadata={
                        "fact_id": fact.fact_id,
                        "origin": CONVERSATION_ORIGIN,
                        "user_message": message,
                        "session_id": session_id,
                        "message_id": message_id,
                        **memory_scope_metadata,
                    },
                    origin=CONVERSATION_ORIGIN,
                    confidence=float(confidence),
                )
            )
            run.updated_at = utc_now_iso()
            self.store.save_workflow(run)
            proposal = self.propose(run.run_id, "memory_delete", intent)

        review = self.review_create(proposal.proposal_id)
        review_decision = None
        memory_apply = None
        if governance_action in {AUTO_ACCEPT, AUTO_APPLY}:
            review_decision = self.review_decide(
                review.review_id,
                "accept",
                f"accepted by conversation memory policy: {governance_action}",
            )
            if governance_action == AUTO_APPLY:
                memory_apply = self.memory_apply(review.review_id)

        status = "review_required"
        if review_decision and not memory_apply:
            status = "accepted"
        if memory_apply:
            status = "applied"
        self.store.add_audit_event(
            audit_event(
                "memory.conversation_change",
                "review",
                review.review_id,
                operation=normalized_operation,
                proposal_operation=proposal.kind,
                status=status,
                governance_action=governance_action,
                run_id=run.run_id,
                proposal_id=proposal.proposal_id,
                memory_target_id=memory_apply.target_id if memory_apply else "",
                source_count=len(proposal.source_refs),
                session_id=session_id,
                message_id=message_id,
                target_resolution_status=(target_resolution or {}).get("status", ""),
            )
        )
        return {
            "status": status,
            "operation": normalized_operation,
            "proposal_operation": proposal.kind,
            "memory_update_strategy": memory_update_strategy,
            "proposal": to_jsonable(proposal),
            "review": self.store.get_review_record(review.review_id),
            "review_decision": to_jsonable(review_decision),
            "memory_apply": to_jsonable(memory_apply),
            "governance": {
                "origin": CONVERSATION_ORIGIN,
                "action": governance_action,
                "durable_proposal": True,
                "force_review": force_review,
                "policy": policy.to_dict(),
            },
            "conversation": {
                "user_message": message,
                "session_id": session_id,
                "message_id": message_id,
                "source_refs": to_jsonable(conversation_source_refs),
            },
            "target_resolution": target_resolution,
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

    def memory_search(
        self,
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 10,
        trace_context: dict[str, Any] | None = None,
    ) -> list[MemoryFact]:
        search_scope = _memory_runtime_scope(scope)
        requested_limit = max(0, int(limit))
        include_superseded = any(bool(search_scope.get(key)) for key in MEMORY_INCLUDE_SUPERSEDED_SCOPE_KEYS)
        facts, raw_facts, superseded = _memory_search_view(
            self.memory,
            query,
            search_scope,
            requested_limit,
            include_superseded=include_superseded,
        )
        self.store.add_audit_event(
            audit_event(
                "memory.search",
                "memory_scope",
                ",".join(str(item) for item in search_scope.get("dataset_ids", [])) or "workspace",
                query=query,
                count=len(facts),
                raw_count=len(raw_facts),
                superseded_count=len(superseded),
                include_superseded=include_superseded,
                scope=search_scope,
                **memory_search_trace_metadata(
                    facts=facts,
                    raw_facts=raw_facts,
                    superseded=superseded,
                    trace_context=trace_context,
                ),
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
            _attach_memory_runtime_metadata(proposal.memory_patch.metadata, proposal)
            proposal.memory_patch.metadata.setdefault("review_id", review_id)
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
                    semantic_operation=proposal.memory_patch.metadata.get("semantic_operation") or "",
                    memory_update_strategy=proposal.memory_patch.metadata.get("memory_update_strategy") or "",
                    semantic_target_ids=_memory_fact_superseded_target_ids_from_metadata(
                        proposal.memory_patch.metadata
                    ),
                )
            )
            return result
        if proposal.kind == "memory_update":
            self._ensure_memory_operation_supported("update")
            if proposal.memory_update is None:
                raise WorkflowError("memory_update proposal is missing memory update payload")
            if not proposal.memory_update.source_refs:
                raise WorkflowError("memory update requires source refs before apply")
            _attach_memory_runtime_metadata(proposal.memory_update.metadata, proposal)
            proposal.memory_update.metadata.setdefault("review_id", review_id)
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
            _attach_memory_runtime_metadata(proposal.memory_delete.metadata, proposal)
            proposal.memory_delete.metadata.setdefault("review_id", review_id)
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

    def _workflow_memory_origin(self, run: WorkflowRun) -> str:
        if isinstance(run.metadata.get("digest_scope"), dict):
            return DIGEST_ORIGIN
        for proposal_id in run.proposal_ids:
            try:
                proposal = self.store.get_proposal(proposal_id)
            except Exception:
                continue
            if proposal.kind == "digest":
                return DIGEST_ORIGIN
        return DURABLE_ORIGIN

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
            if event.action in lifecycle_actions and self._memory_lifecycle_event_matches(event, target_id)
        ]
        returned_events = events[-limit:]
        return {
            "memory_target_id": target_id,
            "change_count": len(events),
            "returned_count": len(returned_events),
            "latest_event": to_jsonable(events[-1]) if events else None,
            "events": to_jsonable(returned_events),
        }

    def _memory_lifecycle_event_matches(self, event: Any, target_id: str) -> bool:
        metadata = getattr(event, "metadata", {}) or {}
        if str(metadata.get("memory_target_id") or "") == target_id:
            return True
        if target_id in _memory_lifecycle_semantic_target_ids(metadata):
            return True
        proposal_id = str(metadata.get("proposal_id") or "")
        if not proposal_id:
            return False
        try:
            proposal = self.store.get_proposal(proposal_id)
        except Exception:
            return False
        return target_id in _proposal_semantic_target_ids(proposal)

    def _context_packets_for_source_refs(self, run_id: str, source_refs: list[SourceRef]) -> list[ContextPacket]:
        packets: list[ContextPacket] = []
        for index, ref in enumerate(source_refs, start=1):
            source = self.source_read(ref)
            snippet = str(source.text or "").strip()
            if len(snippet) > 1200:
                snippet = snippet[:1200].rstrip() + "\n..."
            packets.append(
                ContextPacket(
                    context_id=f"ctx_source_memory_{index}_{ref.chunk_id or ref.source_id or ref.document_id or index}",
                    text=snippet,
                    source_ref=source.source_ref,
                    score=1.0,
                    title=source.source_ref.title or ref.title or _source_display_id(ref),
                    metadata={
                        "origin": SOURCE_PROMOTION_ORIGIN,
                        "run_id": run_id,
                        "source_memory_candidate": True,
                        **dict(source.metadata or {}),
                    },
                )
            )
        return packets

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
        _ensure_exportable_work_product(artifact)
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
        memory_attribution = artifact.get("memory_attribution") or {}
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
            f"- Used memory count: `{len(memory_attribution.get('used_memory_ids') or [])}`",
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
                lines.extend(
                    [
                        f"### Memory [{index}] `{fact.get('fact_id') or ''}`",
                        "",
                        _memory_fact_display_text(fact),
                        "",
                    ]
                )
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
        proposals = [self.store.get_proposal(proposal_id) for proposal_id in run.proposal_ids]
        proposal_payload = [to_jsonable(proposal) for proposal in proposals]
        proposal_source_refs = _unique_source_refs(
            [
                source_ref
                for proposal in proposals
                for source_ref in proposal.source_refs
            ]
        )
        memory_facts = list(run.metadata.get("memory_context") or [])
        source_inspections = list(run.metadata.get("source_inspections") or [])
        source_manifest = _source_manifest(run.context_packets, proposal_source_refs)
        memory_source_manifest = _memory_source_manifest(memory_facts)
        artifact = {
            "run": to_jsonable(run),
            "scope": run.scope,
            "proposals": proposal_payload,
            "latest_proposal": proposal_payload[-1] if proposal_payload else None,
            "source_manifest": source_manifest,
            "context_packets": packet_payload,
            "source_inspections": source_inspections,
            "memory_facts": memory_facts,
            "memory_source_manifest": memory_source_manifest,
            "memory_attribution": run.metadata.get("memory_attribution") or {},
            "memory_suggestions": run.metadata.get("memory_suggestions") or {},
            "traceability": {
                "context_count": len(packet_payload),
                "source_inspection_count": len(source_inspections),
                "memory_count": len(memory_facts),
                "memory_source_count": len(memory_source_manifest),
                "proposal_count": len(proposal_payload),
                "source_count": len(source_manifest),
            },
        }
        if not artifact["memory_attribution"]:
            artifact["memory_attribution"] = build_attribution_from_artifact(artifact)
        if not artifact["memory_suggestions"]:
            artifact["memory_suggestions"] = build_suggestions_from_artifact(artifact)
        return artifact

    def _create_memory_patch_proposal(
        self,
        run: WorkflowRun,
        *,
        intent: str,
        memory_patch: MemoryPatch,
    ) -> Proposal:
        if not memory_patch.text.strip():
            raise WorkflowError("memory_patch proposal requires text")
        if not memory_patch.source_refs:
            raise WorkflowError("memory_patch proposal requires source refs")
        _attach_memory_scope_metadata(memory_patch.metadata, run.scope)
        _annotate_memory_candidate(
            memory_patch.metadata,
            operation="memory_patch",
            origin=str(memory_patch.metadata.get("origin") or self._workflow_memory_origin(run)),
            text=memory_patch.text,
            source_refs=memory_patch.source_refs,
            confidence=memory_patch.confidence,
        )
        origin = str(memory_patch.metadata.get("origin") or self._workflow_memory_origin(run))
        if origin != CONVERSATION_ORIGIN:
            probe = self._memory_conflict_probe(run, memory_patch.text, origin=origin)
            _attach_memory_conflict_probe(memory_patch.metadata, probe)
        proposal_id = f"prop_{uuid4().hex}"
        proposal = Proposal(
            proposal_id=proposal_id,
            run_id=run.run_id,
            kind="memory_patch",
            intent=intent or run.intent,
            title=_proposal_title("memory_patch", intent or run.intent),
            body=memory_patch.text,
            source_refs=memory_patch.source_refs,
            memory_patch=memory_patch,
            metadata=dict(memory_patch.metadata),
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
                origin=proposal.metadata.get("origin") or "",
            )
        )
        return proposal

    def _memory_conflict_probe(self, run: WorkflowRun, candidate_text: str, *, origin: str) -> dict[str, Any]:
        query = _memory_conflict_query(candidate_text)
        search_scope = _memory_runtime_scope(run.scope)
        facts, raw_facts, superseded = _memory_search_view(self.memory, query, search_scope, limit=5)
        candidates = _memory_conflict_candidates(candidate_text, facts)
        max_conflict_score = max([candidate["conflict_score"] for candidate in candidates], default=0.0)
        probe = {
            "schema": "pska.memory_conflict_probe.v1",
            "origin": origin,
            "query": query,
            "returned_count": len(facts),
            "raw_count": len(raw_facts),
            "superseded_count": len(superseded),
            "superseded_fact_ids": [item["fact_id"] for item in superseded],
            "related_count": len(candidates),
            "max_conflict_score": round(max_conflict_score, 3),
            "candidates": candidates,
        }
        self.store.add_audit_event(
            audit_event(
                "memory.conflict_probe",
                "workflow",
                run.run_id,
                origin=origin,
                query=query,
                returned_count=len(facts),
                raw_count=len(raw_facts),
                superseded_count=len(superseded),
                superseded_fact_ids=[item["fact_id"] for item in superseded],
                related_count=len(candidates),
                max_conflict_score=round(max_conflict_score, 3),
            )
        )
        return probe

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
        _annotate_memory_candidate(
            memory_update.metadata,
            operation="memory_update",
            origin=str(memory_update.metadata.get("origin") or self._workflow_memory_origin(run)),
            text=" ".join(part for part in [memory_update.previous_text, memory_update.text, memory_update.reason] if part),
            source_refs=memory_update.source_refs,
            confidence=float(memory_update.metadata.get("confidence") or 0.9),
            conflict=bool(memory_update.previous_text),
        )
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
            metadata=dict(memory_update.metadata),
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
                origin=proposal.metadata.get("origin") or "",
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
        _annotate_memory_candidate(
            memory_delete.metadata,
            operation="memory_delete",
            origin=str(memory_delete.metadata.get("origin") or self._workflow_memory_origin(run)),
            text=" ".join(part for part in [memory_delete.text, memory_delete.reason] if part),
            source_refs=memory_delete.source_refs,
            confidence=float(memory_delete.metadata.get("confidence") or 0.9),
            conflict=True,
        )
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
            metadata=dict(memory_delete.metadata),
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
                origin=proposal.metadata.get("origin") or "",
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

    def _source_registry(self) -> SQLiteSourceRegistry:
        if self.source_registry is None:
            raise WorkflowError("personal source registry is not configured")
        return self.source_registry


def build_fake_service(db_path: str = ":memory:") -> WorkflowService:
    return WorkflowService(
        retrieval=FakeRetrievalAdapter(),
        memory=FakeMemoryAdapter(),
        store=SQLiteReviewStore(db_path),
        source_registry=SQLiteSourceRegistry(":memory:"),
    )


def _normalize_memory_card_type(memory_type: str) -> str:
    normalized = (memory_type or "").strip().lower()
    if normalized not in MEMORY_CARD_TYPES:
        raise WorkflowError(
            "memory_type must be one of: " + ", ".join(sorted(MEMORY_CARD_TYPES))
        )
    return normalized


def _normalize_memory_card_scope(memory_scope: str) -> str:
    normalized = (memory_scope or "workspace").strip().lower()
    if normalized not in MEMORY_CARD_SCOPES:
        raise WorkflowError(
            "memory_scope must be one of: " + ", ".join(sorted(MEMORY_CARD_SCOPES))
        )
    return normalized


def _source_refs_from_input(source_refs: list[SourceRef | dict[str, Any]]) -> list[SourceRef]:
    refs = []
    for item in source_refs or []:
        refs.append(item if isinstance(item, SourceRef) else SourceRef.from_dict(item))
    return _unique_source_refs(refs)


def _source_route_memory_text(candidate: dict[str, Any]) -> str:
    title = str(candidate.get("title") or candidate.get("path") or "this source").strip()
    path = str(candidate.get("path") or title).strip()
    return f"When this workspace asks about {title}, inspect {path} first."


def _source_route_behavior_delta(candidate: dict[str, Any]) -> str:
    path = str(candidate.get("path") or candidate.get("title") or "this source").strip()
    return f"Route future related questions to {path} before broad search."


def _skipped_source_memory_candidate(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    ref = candidate.get("source_ref")
    source_refs = [ref] if ref is not None else []
    return {
        "path": str(candidate.get("path") or ""),
        "title": str(candidate.get("title") or ""),
        "reason": reason,
        "source_refs": to_jsonable(source_refs),
    }


def _existing_source_memory_review_keys(reviews: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for review in reviews:
        if str(review.get("status") or "") not in {"pending", "accepted", "needs_edit"}:
            continue
        proposal = review.get("proposal") or {}
        memory_patch = proposal.get("memory_patch") or {}
        metadata = memory_patch.get("metadata") or proposal.get("metadata") or {}
        memory_type = str(metadata.get("memory_type") or "")
        behavior_delta = str(metadata.get("behavior_delta") or "")
        memory_scope = str(metadata.get("memory_scope") or "workspace")
        source_refs = _source_refs_from_input(memory_patch.get("source_refs") or proposal.get("source_refs") or [])
        if memory_type and behavior_delta and source_refs:
            keys.add(
                _source_memory_candidate_key(
                    source_refs,
                    memory_type=memory_type,
                    memory_scope=memory_scope,
                    behavior_delta=behavior_delta,
                )
            )
    return keys


def _source_memory_candidate_key(
    source_refs: list[SourceRef],
    *,
    memory_type: str,
    memory_scope: str,
    behavior_delta: str,
) -> str:
    ref_keys = [
        "|".join(
            [
                ref.adapter,
                ref.dataset_id or "",
                ref.document_id or "",
                ref.chunk_id or "",
                ref.source_id or "",
                ref.external_id or "",
                ref.path or "",
            ]
        )
        for ref in source_refs
    ]
    return json.dumps(
        {
            "source_refs": sorted(ref_keys),
            "memory_type": _normalize_memory_card_type(memory_type),
            "memory_scope": _normalize_memory_card_scope(memory_scope),
            "behavior_delta": " ".join(behavior_delta.strip().lower().split()),
        },
        sort_keys=True,
    )


def _eidolia_source_ref(
    *,
    project_id: str,
    node_id: str,
    node_type: str,
    title: str = "",
    canvas_path: str = "",
    role: str = "",
    artifact_kind: str = "",
    metadata: dict[str, Any] | None = None,
) -> SourceRef:
    normalized_project = project_id.strip()
    normalized_node = node_id.strip()
    normalized_type = _normalize_eidolia_node_type(node_type)
    if not normalized_project:
        raise WorkflowError("Eidolia source ref requires project_id")
    if not normalized_node:
        raise WorkflowError("Eidolia source ref requires node_id")
    normalized_path = canvas_path.strip() or f"{normalized_project}/{normalized_node}"
    values = {
        "source_layer": "thought_artifact",
        "project_id": normalized_project,
        "node_id": normalized_node,
        "node_type": normalized_type,
        "role": role.strip(),
        "artifact_kind": artifact_kind.strip(),
        "canvas_path": normalized_path,
        "canonical_owner": "eidolia_project",
        "writes_source_files": False,
    }
    values.update({str(key): value for key, value in (metadata or {}).items()})
    return SourceRef(
        adapter="eidolia",
        source_id=normalized_project,
        external_id=normalized_node,
        title=title.strip() or normalized_node,
        path=normalized_path,
        metadata=values,
    )


def _normalize_eidolia_node_type(node_type: str) -> str:
    normalized = (node_type or "thought").strip().lower()
    if normalized not in {"thought", "artifact"}:
        raise WorkflowError("Eidolia node_type must be thought or artifact")
    return normalized


def _memory_runtime_scope(scope: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_runtime_memory_scope(scope)


def _attach_memory_scope_metadata(metadata: dict[str, Any], scope: dict[str, Any] | None = None) -> None:
    runtime_scope = _memory_runtime_scope(scope)
    for key in ("workspace_id", "tenant_id", "workspace_configured", "tenant_configured", "memory_namespace"):
        if key in runtime_scope:
            metadata.setdefault(key, runtime_scope[key])


def _attach_memory_runtime_metadata(metadata: dict[str, Any], proposal: Proposal) -> None:
    _attach_memory_scope_metadata(metadata, proposal.metadata)
    metadata.setdefault("proposal_id", proposal.proposal_id)
    metadata.setdefault("run_id", proposal.run_id)
    metadata.setdefault("applied_at", utc_now_iso())


def _memory_fact_scope_metadata(fact: MemoryFact) -> dict[str, Any]:
    fact_metadata = fact.metadata or {}
    scope = {
        key: fact_metadata[key]
        for key in (
            "workspace_id",
            "tenant_id",
            "workspace_configured",
            "tenant_configured",
            "memory_namespace",
        )
        if key in fact_metadata
    }
    metadata = _memory_runtime_scope(scope)
    metadata["fact_id"] = fact.fact_id
    return metadata


def _annotated_memory_patch(
    *,
    text: str,
    source_refs: list[SourceRef],
    confidence: float,
    metadata: dict[str, Any],
    operation: str,
    origin: str,
) -> MemoryPatch:
    patch = MemoryPatch(
        text=text,
        source_refs=source_refs,
        confidence=confidence,
        metadata=dict(metadata),
    )
    _annotate_memory_candidate(
        patch.metadata,
        operation=operation,
        origin=origin,
        text=text,
        source_refs=source_refs,
        confidence=confidence,
    )
    return patch


def _annotated_memory_update(
    *,
    target_id: str,
    text: str,
    source_refs: list[SourceRef],
    previous_text: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    origin: str,
    confidence: float = 0.9,
) -> MemoryUpdate:
    update = MemoryUpdate(
        target_id=target_id,
        text=text,
        previous_text=previous_text,
        reason=reason,
        source_refs=source_refs,
        metadata=dict(metadata or {}),
    )
    _annotate_memory_candidate(
        update.metadata,
        operation="memory_update",
        origin=origin,
        text=" ".join(part for part in [previous_text, text, reason] if part),
        source_refs=source_refs,
        confidence=confidence,
        conflict=bool(previous_text),
    )
    return update


def _annotated_memory_delete(
    *,
    target_id: str,
    source_refs: list[SourceRef],
    reason: str = "",
    text: str = "",
    metadata: dict[str, Any] | None = None,
    origin: str,
    confidence: float = 0.9,
) -> MemoryDelete:
    delete = MemoryDelete(
        target_id=target_id,
        reason=reason,
        text=text,
        source_refs=source_refs,
        metadata=dict(metadata or {}),
    )
    _annotate_memory_candidate(
        delete.metadata,
        operation="memory_delete",
        origin=origin,
        text=" ".join(part for part in [text, reason] if part),
        source_refs=source_refs,
        confidence=confidence,
        conflict=True,
    )
    return delete


def _annotate_memory_candidate(
    metadata: dict[str, Any],
    *,
    operation: str,
    origin: str,
    text: str,
    source_refs: list[SourceRef],
    confidence: float | None = None,
    conflict: bool = False,
) -> None:
    now = utc_now_iso()
    normalized_origin = (origin or DURABLE_ORIGIN).strip().lower()
    normalized_operation = operation.strip().lower()
    metadata.setdefault("origin", normalized_origin)
    metadata.setdefault("operation", normalized_operation)
    metadata.setdefault("created_at", now)
    metadata.setdefault("observed_at", _observed_at_from_sources(source_refs) or now)
    metadata.setdefault("source_count", len(source_refs))
    if confidence is not None:
        metadata.setdefault("confidence", float(confidence))
    generated = _memory_triage(
        operation=normalized_operation,
        origin=normalized_origin,
        text=text,
        confidence=float(metadata.get("confidence") or confidence or 0.0),
        source_count=len(source_refs),
        conflict=conflict,
    )
    existing = dict(metadata.get("triage") or {})
    for key, value in generated.items():
        existing.setdefault(key, value)
    metadata["triage"] = existing


def _memory_triage(
    *,
    operation: str,
    origin: str,
    text: str,
    confidence: float,
    source_count: int,
    conflict: bool,
) -> dict[str, Any]:
    uncertainty = max(0.0, min(1.0, 1.0 - confidence))
    uncertainty_markers = _uncertainty_markers(text)
    if uncertainty_markers:
        uncertainty = max(uncertainty, 0.35)
    risk = _memory_risk_score(text)
    conflict_score = 0.65 if conflict or operation in {"memory_update", "memory_delete"} else 0.0
    importance = 0.85 if operation in {"memory_update", "memory_delete"} else 0.75
    if source_count <= 0:
        uncertainty = max(uncertainty, 0.5)
    non_conversation = origin != CONVERSATION_ORIGIN
    review_recommended = non_conversation and (
        (importance >= 0.7 and uncertainty >= 0.35)
        or risk >= 0.7
        or conflict_score >= 0.6
    )
    if origin == CONVERSATION_ORIGIN:
        route = "conversation_policy"
        reason = "conversation memory is corrected through later chat unless policy or user explicitly asks for review"
    elif review_recommended:
        route = "manual_review"
        reason = "candidate is important and uncertain, risky, or conflicting"
    else:
        route = "workspace_policy"
        reason = "candidate can follow workspace governance policy"
    return {
        "schema": "pska.memory_triage.v1",
        "importance": round(importance, 3),
        "uncertainty": round(uncertainty, 3),
        "risk": round(risk, 3),
        "conflict": round(conflict_score, 3),
        "source_count": source_count,
        "uncertainty_markers": uncertainty_markers,
        "review_recommended": review_recommended,
        "route": route,
        "reason": reason,
    }


def _attach_memory_conflict_probe(metadata: dict[str, Any], probe: dict[str, Any]) -> None:
    metadata["memory_conflict_probe"] = probe
    related_count = int(probe.get("related_count") or 0)
    max_conflict_score = float(probe.get("max_conflict_score") or 0.0)
    triage = dict(metadata.get("triage") or {})
    triage["related_memory_count"] = related_count
    triage["conflict"] = max(float(triage.get("conflict") or 0.0), max_conflict_score)
    if max_conflict_score >= 0.6:
        triage["review_recommended"] = metadata.get("origin") != CONVERSATION_ORIGIN
        triage["route"] = "manual_review" if triage["review_recommended"] else "conversation_policy"
        triage["reason"] = "candidate may conflict with existing durable memory"
    elif related_count:
        triage.setdefault("related_memory_count", related_count)
    metadata["triage"] = triage


def _proposal_triage_review_recommended(proposal: Proposal) -> bool:
    origin = str(proposal.metadata.get("origin") or "").strip().lower()
    if origin == CONVERSATION_ORIGIN:
        return False
    triage = proposal.metadata.get("triage") or {}
    return bool(triage.get("review_recommended"))


def _memory_conflict_query(text: str) -> str:
    return " ".join(_significant_tokens(text)[:12])


def _memory_conflict_candidates(candidate_text: str, facts: list[MemoryFact]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for fact in facts:
        relatedness, overlap = _memory_relatedness(candidate_text, fact.text)
        if relatedness <= 0:
            continue
        conflict_score = _memory_conflict_score(candidate_text, fact.text, relatedness=relatedness)
        candidates.append(
            {
                "fact_id": fact.fact_id,
                "text_excerpt": _compact_text(fact.text, 220),
                "relatedness": round(relatedness, 3),
                "conflict_score": round(conflict_score, 3),
                "overlap_tokens": overlap[:10],
                "valid_at": fact.valid_at or "",
                "invalid_at": fact.invalid_at or "",
                "source_count": len(fact.source_refs),
                "timestamps": {
                    key: value
                    for key in ("created_at", "observed_at", "updated_at", "applied_at")
                    if isinstance((value := fact.metadata.get(key)), str) and value
                },
            }
        )
    return sorted(candidates, key=lambda item: (item["conflict_score"], item["relatedness"]), reverse=True)


def _memory_relatedness(candidate_text: str, fact_text: str) -> tuple[float, list[str]]:
    candidate_tokens = set(_significant_tokens(candidate_text))
    fact_tokens = set(_significant_tokens(fact_text))
    if not candidate_tokens or not fact_tokens:
        return 0.0, []
    overlap = sorted(candidate_tokens & fact_tokens)
    if len(overlap) < 2:
        return 0.0, overlap
    denominator = max(1, min(len(candidate_tokens), len(fact_tokens)))
    return min(1.0, len(overlap) / denominator), overlap


def _memory_conflict_score(candidate_text: str, fact_text: str, *, relatedness: float) -> float:
    score = 0.35 if relatedness > 0 else 0.0
    negation_differs = _has_negation(candidate_text) != _has_negation(fact_text)
    distinct_claim = _distinct_claim_terms(candidate_text, fact_text)
    if score and negation_differs:
        score = max(score, 0.75)
    if score and _has_correction_marker(candidate_text) and (negation_differs or distinct_claim):
        score = max(score, 0.65)
    if relatedness >= 0.5 and distinct_claim:
        score = max(score, 0.6)
    return min(1.0, score)


def _distinct_claim_terms(candidate_text: str, fact_text: str) -> bool:
    candidate_tokens = set(_significant_tokens(candidate_text))
    fact_tokens = set(_significant_tokens(fact_text))
    distinct_candidate = candidate_tokens - fact_tokens
    distinct_fact = fact_tokens - candidate_tokens
    return bool(distinct_candidate and distinct_fact)


def _significant_tokens(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_][A-Za-z0-9_-]{2,}", text.lower()):
        if token in _MEMORY_PROBE_STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _has_negation(text: str) -> bool:
    normalized = text.lower()
    markers = (" not ", " no ", " never ", " without ", "不是", "不再", "不要", "没有", "并非")
    padded = f" {normalized} "
    return any(marker in padded for marker in markers)


def _has_correction_marker(text: str) -> bool:
    normalized = text.lower()
    markers = (
        "now",
        "changed",
        "instead",
        "rather than",
        "replaced",
        "updated",
        "current",
        "现在",
        "改为",
        "变成",
        "替代",
        "而不是",
    )
    return any(marker in normalized for marker in markers)


_MEMORY_PROBE_STOPWORDS = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "not",
    "that",
    "the",
    "this",
    "with",
    "reviewed",
    "memory",
    "candidate",
    "evidence",
    "source",
    "count",
    "summary",
    "prior",
    "context",
    "remember",
    "forget",
    "delete",
    "remove",
    "correct",
    "correction",
    "wrong",
    "actually",
    "replace",
    "instead",
    "rather",
    "than",
    "durable",
    "workspace",
    "user",
    "users",
    "fact",
}


def _uncertainty_markers(text: str) -> list[str]:
    normalized = text.lower()
    markers = [
        "maybe",
        "possibly",
        "probably",
        "uncertain",
        "not sure",
        "might",
        "可能",
        "也许",
        "大概",
        "不确定",
        "似乎",
    ]
    return [marker for marker in markers if marker in normalized]


def _memory_risk_score(text: str) -> float:
    normalized = text.lower()
    high_risk_markers = (
        "password",
        "secret",
        "api key",
        "access token",
        "private key",
        "sk-",
        "密码",
        "密钥",
        "令牌",
        "私钥",
    )
    if any(marker in normalized for marker in high_risk_markers):
        return 0.9
    sensitive_markers = (
        "salary",
        "medical",
        "legal",
        "finance",
        "财务",
        "薪资",
        "医疗",
        "法律",
    )
    if any(marker in normalized for marker in sensitive_markers):
        return 0.6
    return 0.2


def _observed_at_from_sources(source_refs: list[SourceRef]) -> str:
    candidates: list[str] = []
    for ref in source_refs:
        metadata = ref.metadata or {}
        for key in ("observed_at", "source_published_at", "created_at", "ingested_at"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    return max(candidates) if candidates else ""


def _rank_memory_facts(facts: list[MemoryFact]) -> list[MemoryFact]:
    return sorted(facts, key=_memory_fact_sort_key, reverse=True)


def _memory_search_raw_limit(limit: int) -> int:
    if limit <= 0:
        return 0
    return min(100, max(limit, limit * 3, limit + 5))


def _memory_search_view(
    memory: MemoryPort,
    query: str,
    scope: dict[str, Any],
    limit: int,
    *,
    include_superseded: bool = False,
) -> tuple[list[MemoryFact], list[MemoryFact], list[dict[str, Any]]]:
    requested_limit = max(0, int(limit))
    normalized_query = str(query or "").strip()
    if not normalized_query or requested_limit <= 0:
        return [], [], []
    raw_limit = _memory_search_raw_limit(requested_limit)
    raw_facts = _rank_memory_facts(memory.search(normalized_query, scope, raw_limit))
    facts, superseded = _resolve_memory_search_supersession(
        raw_facts,
        include_superseded=include_superseded,
    )
    return facts[:requested_limit], raw_facts, superseded


def _resolve_memory_search_supersession(
    facts: list[MemoryFact],
    *,
    include_superseded: bool = False,
) -> tuple[list[MemoryFact], list[dict[str, Any]]]:
    superseded_by: dict[str, MemoryFact] = {}
    fact_ids = {fact.fact_id for fact in facts}
    for fact in facts:
        for target_id in _memory_fact_superseded_target_ids(fact):
            if target_id and target_id != fact.fact_id and target_id in fact_ids:
                superseded_by[target_id] = fact
    if not superseded_by:
        return facts, []
    superseded = [
        {
            "fact_id": fact_id,
            "superseded_by_fact_id": newer.fact_id,
            "strategy": str(newer.metadata.get("memory_update_strategy") or ""),
            "semantic_operation": str(newer.metadata.get("semantic_operation") or ""),
        }
        for fact_id, newer in sorted(superseded_by.items())
    ]
    if include_superseded:
        return facts, superseded
    return [fact for fact in facts if fact.fact_id not in superseded_by], superseded


def _memory_fact_superseded_target_ids(fact: MemoryFact) -> list[str]:
    metadata = fact.metadata or {}
    return _memory_fact_superseded_target_ids_from_metadata(metadata)


def _memory_fact_superseded_target_ids_from_metadata(metadata: dict[str, Any]) -> list[str]:
    semantic_operation = str(metadata.get("semantic_operation") or "").strip()
    strategy = str(metadata.get("memory_update_strategy") or "").strip()
    target_ids: list[str] = []
    if semantic_operation == "memory_update" or strategy == "append_correction_episode":
        for key in MEMORY_SUPERSESSION_TARGET_KEYS:
            target_ids.extend(_string_list(metadata.get(key)))
    return _unique_strings(target_ids)


def _memory_lifecycle_semantic_target_ids(metadata: dict[str, Any]) -> list[str]:
    target_ids: list[str] = []
    target_ids.extend(_string_list(metadata.get("semantic_target_id")))
    target_ids.extend(_string_list(metadata.get("semantic_target_ids")))
    target_ids.extend(_memory_fact_superseded_target_ids_from_metadata(metadata))
    return _unique_strings(target_ids)


def _proposal_semantic_target_ids(proposal: Proposal) -> list[str]:
    if proposal.memory_patch is not None:
        return _memory_fact_superseded_target_ids_from_metadata(proposal.memory_patch.metadata)
    if proposal.memory_update is not None:
        return _unique_strings([proposal.memory_update.target_id])
    if proposal.memory_delete is not None:
        return _unique_strings([proposal.memory_delete.target_id])
    return []


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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _memory_fact_from_input(memory_fact: MemoryFact | dict[str, Any], operation: str) -> MemoryFact:
    if isinstance(memory_fact, MemoryFact):
        return memory_fact
    try:
        return MemoryFact.from_dict(memory_fact)
    except TypeError as exc:
        raise WorkflowError(f"memory {operation} review requires a valid MemoryFact") from exc


def _optional_memory_fact_from_input(memory_fact: MemoryFact | dict[str, Any] | None) -> MemoryFact | None:
    if memory_fact is None:
        return None
    if isinstance(memory_fact, dict) and not memory_fact:
        return None
    return _memory_fact_from_input(memory_fact, "conversation change")


def _resolve_conversation_memory_target(
    memory: MemoryPort,
    *,
    user_message: str,
    text: str,
    reason: str,
    operation: str,
    scope: dict[str, Any],
) -> tuple[MemoryFact | None, dict[str, Any]]:
    query = _conversation_target_query(
        user_message=user_message,
        text=text,
        reason=reason,
        operation=operation,
    )
    search_scope = _memory_runtime_scope(scope)
    facts, raw_facts, superseded = _memory_search_view(memory, query, search_scope, limit=5)
    candidates = _conversation_target_candidates(query, facts)
    resolution = {
        "schema": "pska.conversation_memory_target_resolution.v1",
        "status": "not_found",
        "query": query,
        "candidate_count": len(facts),
        "raw_count": len(raw_facts),
        "superseded_count": len(superseded),
        "superseded_fact_ids": [item["fact_id"] for item in superseded],
        "selected_fact_id": "",
        "candidates": candidates,
    }
    if not candidates:
        return None, resolution
    top = candidates[0]
    if len(candidates) > 1 and top["score"] == candidates[1]["score"]:
        resolution["status"] = "ambiguous"
        return None, resolution
    resolution["status"] = "resolved"
    resolution["selected_fact_id"] = top["fact_id"]
    selected = next((fact for fact in facts if fact.fact_id == top["fact_id"]), None)
    return selected, resolution


def _conversation_target_query(*, user_message: str, text: str, reason: str, operation: str) -> str:
    raw = " ".join(part.strip() for part in (user_message, reason, text) if part.strip())
    tokens = _significant_tokens(raw)
    if tokens:
        return " ".join(tokens[:16])
    return _compact_text(raw, 240)


def _conversation_target_candidates(query: str, facts: list[MemoryFact]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for fact in facts:
        score, overlap = _conversation_target_score(query, fact.text)
        if score <= 0:
            continue
        candidates.append(
            {
                "fact_id": fact.fact_id,
                "text_excerpt": _compact_text(fact.text, 220),
                "score": round(score, 3),
                "overlap_tokens": overlap[:10],
                "valid_at": fact.valid_at or "",
                "invalid_at": fact.invalid_at or "",
            }
        )
    return sorted(candidates, key=lambda item: (item["score"], item["fact_id"]), reverse=True)


def _conversation_target_score(query: str, fact_text: str) -> tuple[float, list[str]]:
    query_tokens = set(_significant_tokens(query))
    fact_tokens = set(_significant_tokens(fact_text))
    if query_tokens and fact_tokens:
        overlap = sorted(query_tokens & fact_tokens)
        if overlap:
            denominator = max(1, min(len(query_tokens), len(fact_tokens)))
            return min(1.0, len(overlap) / denominator), overlap
    normalized_query = query.strip().lower()
    normalized_fact = fact_text.strip().lower()
    if normalized_query and normalized_query in normalized_fact:
        return 0.5, [normalized_query]
    return 0.0, []


def _provided_conversation_memory_target_resolution(fact: MemoryFact) -> dict[str, Any]:
    return {
        "schema": "pska.conversation_memory_target_resolution.v1",
        "status": "provided",
        "query": "",
        "candidate_count": 1,
        "selected_fact_id": fact.fact_id,
        "candidates": [
            {
                "fact_id": fact.fact_id,
                "text_excerpt": _compact_text(fact.text, 220),
                "score": 1.0,
                "overlap_tokens": [],
                "valid_at": fact.valid_at or "",
                "invalid_at": fact.invalid_at or "",
            }
        ],
    }


def _conversation_memory_needs_target_response(
    *,
    operation: str,
    requested_operation: str,
    user_message: str,
    text: str,
    reason: str,
    session_id: str,
    message_id: str,
    scope: dict[str, Any],
    force_review: bool,
    policy: dict[str, Any],
    target_resolution: dict[str, Any],
) -> dict[str, Any]:
    query = str(target_resolution.get("query") or "").strip()
    next_actions: list[dict[str, Any]] = []
    if query:
        next_actions.append(
            {
                "tool": "pska_memory_search",
                "params": {"query": query, "scope": scope, "limit": 5},
            }
        )
    next_actions.append(
        {
            "instruction": "Ask the user which existing memory should be changed, then retry with memory_fact.",
        }
    )
    return {
        "status": "needs_target",
        "operation": operation,
        "proposal": None,
        "review": None,
        "review_decision": None,
        "memory_apply": None,
        "governance": {
            "origin": CONVERSATION_ORIGIN,
            "action": "needs_target",
            "durable_proposal": False,
            "force_review": force_review,
            "policy": policy,
        },
        "conversation": {
            "user_message": user_message,
            "session_id": session_id,
            "message_id": message_id,
            "source_refs": [],
        },
        "target_resolution": target_resolution,
        "next_actions": next_actions,
        "artifact": None,
        "request": {
            "requested_operation": requested_operation,
            "text": text,
            "reason": reason,
        },
    }


def _conversation_scope_target_id(scope: dict[str, Any]) -> str:
    runtime_scope = _memory_runtime_scope(scope)
    dataset_ids = runtime_scope.get("dataset_ids") or []
    if dataset_ids:
        return ",".join(str(item) for item in dataset_ids)
    namespace = str(runtime_scope.get("memory_namespace") or "").strip()
    return namespace or "workspace"


def _normalize_conversation_memory_operation(
    *,
    operation: str,
    memory_fact: MemoryFact | None,
    text: str,
    user_message: str,
) -> str:
    normalized = operation.strip().lower() or "auto"
    mapping = {
        "add": "memory_patch",
        "append": "memory_patch",
        "clarify": "memory_patch",
        "create": "memory_patch",
        "memory_patch": "memory_patch",
        "patch": "memory_patch",
        "remember": "memory_patch",
        "correct": "memory_update",
        "memory_update": "memory_update",
        "replace": "memory_update",
        "update": "memory_update",
        "delete": "memory_delete",
        "forget": "memory_delete",
        "invalidate": "memory_delete",
        "memory_delete": "memory_delete",
        "remove": "memory_delete",
    }
    if normalized == "auto":
        if _conversation_delete_intent(user_message):
            return "memory_delete"
        if memory_fact is not None and text.strip():
            return "memory_update"
        if text.strip() and _conversation_update_intent(user_message):
            return "memory_update"
        return "memory_patch"
    if normalized not in mapping:
        raise WorkflowError(
            "conversation memory operation must be auto, remember, clarify, update, correct, delete, or forget"
        )
    return mapping[normalized]


def _conversation_delete_intent(user_message: str) -> bool:
    normalized = user_message.strip().lower()
    delete_markers = (
        "delete",
        "forget",
        "remove",
        "invalidate",
        "do not remember",
        "don't remember",
        "删",
        "删除",
        "忘",
        "别记",
        "不用记",
        "不要记",
    )
    return any(marker in normalized for marker in delete_markers)


def _conversation_update_intent(user_message: str) -> bool:
    normalized = user_message.strip().lower()
    update_markers = (
        "correct",
        "correction",
        "wrong",
        "actually",
        "replace",
        "instead",
        "rather than",
        "更正",
        "纠正",
        "错了",
        "改成",
        "改为",
    )
    return any(marker in normalized for marker in update_markers)


def _conversation_memory_text(*, text: str, user_message: str) -> str:
    return text.strip() or user_message.strip()


def _conversation_correction_episode_text(*, current_text: str, previous_text: str, target_fact_id: str) -> str:
    lines = [
        "Memory correction episode.",
        f"Current fact: {current_text.strip()}",
    ]
    if previous_text.strip():
        lines.append(f"Previous fact: {previous_text.strip()}")
    if target_fact_id.strip():
        lines.append(f"Supersedes memory fact: {target_fact_id.strip()}")
    return "\n".join(lines)


def _conversation_intent(operation: str, user_message: str) -> str:
    label = {
        "memory_patch": "remember from conversation",
        "memory_update": "correct from conversation",
        "memory_delete": "forget from conversation",
    }[operation]
    return f"{label}: {_compact_text(user_message, 120)}"


def _conversation_source_refs(
    *,
    run_id: str,
    user_message: str,
    source_refs: list[SourceRef | dict[str, Any]],
    session_id: str,
    message_id: str,
    scope: dict[str, Any],
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for source_ref in source_refs:
        if isinstance(source_ref, SourceRef):
            refs.append(source_ref)
        else:
            refs.append(SourceRef.from_dict(source_ref))
    adapter = "hermes" if session_id or message_id else "conversation"
    refs.append(
        SourceRef(
            adapter=adapter,
            source_id=message_id or run_id,
            external_id=session_id or run_id,
            title="Conversation memory instruction",
            metadata={
                "origin": CONVERSATION_ORIGIN,
                "run_id": run_id,
                "session_id": session_id,
                "message_id": message_id,
                "user_message_excerpt": _compact_text(user_message, 1000),
                "scope": to_jsonable(scope),
            },
        )
    )
    return _unique_source_refs(refs)


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


def _ensure_exportable_work_product(artifact: dict[str, Any]) -> None:
    traceability = artifact.get("traceability") or {}
    if int(traceability.get("proposal_count") or 0) <= 0:
        raise WorkflowError(
            "export requires a sourced work product; create a proposal before exporting"
        )
    if int(traceability.get("source_count") or 0) <= 0 and int(traceability.get("memory_source_count") or 0) <= 0:
        raise WorkflowError(
            "export requires a sourced work product; retrieve context or attach source refs before exporting"
        )


_MEMORY_PATCH_MAX_BODY_CHARS = 1600
_MEMORY_PATCH_MAX_EVIDENCE_SNIPPETS = 3
_MEMORY_PATCH_SNIPPET_CHARS = 220


def _compose_body(kind: str, run: WorkflowRun, intent: str) -> str:
    purpose = intent or run.intent
    if kind == "memory_patch":
        return _compose_memory_patch_body(run, purpose)
    snippets = "\n".join(f"- {packet.text[:500]}" for packet in run.context_packets)
    memory_snippets = "\n".join(
        f"- {_memory_fact_display_text(fact)[:500]}" for fact in run.metadata.get("memory_context", [])
    )
    memory_section = f"\n\nDurable workspace memory:\n{memory_snippets}" if memory_snippets else ""
    if kind == "digest":
        return f"Digest candidate for: {purpose}\n\nGrounded points:\n{snippets}{memory_section}"
    if kind == "writing_brief":
        return f"Writing brief for: {purpose}\n\nUse these grounded notes:\n{snippets}{memory_section}"
    return f"Reviewed memory candidate for: {purpose}\n\n{snippets}{memory_section}"


def _compose_memory_patch_body(run: WorkflowRun, purpose: str) -> str:
    source_refs = _unique_source_refs([packet.source_ref for packet in run.context_packets])
    source_refs = _unique_source_refs([*source_refs, *_memory_source_refs(run)])
    lines = [
        f"Reviewed memory candidate for: {purpose}",
        "",
        f"Evidence source count: {len(source_refs)}",
    ]
    if run.context_packets:
        lines.extend(["", "Evidence summary:"])
        for index, packet in enumerate(run.context_packets[:_MEMORY_PATCH_MAX_EVIDENCE_SNIPPETS], start=1):
            title = packet.title or packet.source_ref.title or _source_display_id(packet.source_ref) or f"source {index}"
            lines.append(f"- {title}: {_compact_text(packet.text, _MEMORY_PATCH_SNIPPET_CHARS)}")
    memory_facts = [
        _compact_text(_memory_fact_display_text(fact), _MEMORY_PATCH_SNIPPET_CHARS)
        for fact in run.metadata.get("memory_context", [])
    ]
    memory_facts = [fact for fact in memory_facts if fact]
    if memory_facts:
        lines.extend(["", "Prior memory context:"])
        for fact in memory_facts[:_MEMORY_PATCH_MAX_EVIDENCE_SNIPPETS]:
            lines.append(f"- {fact}")
    return _truncate_text("\n".join(lines).strip(), _MEMORY_PATCH_MAX_BODY_CHARS)


def _memory_fact_display_text(fact: Any) -> str:
    if isinstance(fact, dict):
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), dict) else {}
        for key in MEMORY_DISPLAY_TEXT_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return str(fact.get("text") or "").strip()
    metadata = getattr(fact, "metadata", {}) or {}
    if isinstance(metadata, dict):
        for key in MEMORY_DISPLAY_TEXT_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(getattr(fact, "text", "") or "").strip()


def _compact_text(value: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    if limit < 4 or len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _truncate_text(value: str, limit: int) -> str:
    if limit < 4 or len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."


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


def _source_manifest(
    packets: list[ContextPacket],
    proposal_source_refs: list[SourceRef] | None = None,
) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for packet in packets:
        ref = packet.source_ref
        seen.add(_source_ref_key(ref))
        manifest.append(
            {
                "index": len(manifest) + 1,
                "context_id": packet.context_id,
                "title": packet.title or ref.title or packet.context_id,
                "origin": "context",
                "adapter": ref.adapter,
                "dataset_id": ref.dataset_id or "",
                "document_id": ref.document_id or "",
                "source_id": _source_display_id(ref),
                "score": packet.score,
                "source_ref": to_jsonable(ref),
            }
        )
    for ref in proposal_source_refs or []:
        key = _source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        manifest.append(
            {
                "index": len(manifest) + 1,
                "context_id": "",
                "title": ref.title or _source_display_id(ref) or f"Source {len(manifest) + 1}",
                "origin": "proposal",
                "adapter": ref.adapter,
                "dataset_id": ref.dataset_id or "",
                "document_id": ref.document_id or "",
                "source_id": _source_display_id(ref),
                "score": 0.0,
                "source_ref": to_jsonable(ref),
            }
        )
    return manifest


def _source_ref_key(ref: SourceRef) -> str:
    return "|".join(
        [
            ref.adapter,
            ref.dataset_id or "",
            ref.document_id or "",
            ref.chunk_id or "",
            ref.source_id or "",
            ref.external_id or "",
        ]
    )


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
