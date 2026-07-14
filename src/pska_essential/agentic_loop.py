from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import ContextPacket, SourceContext, SourceRef, to_jsonable, utc_now_iso
from pska_essential.governance import (
    AUTO_ACCEPT,
    AUTO_APPLY,
    DURABLE_PROPOSAL_KINDS,
    MANUAL_REVIEW,
    WorkspaceGovernancePolicy,
    build_workspace_policy_from_env,
)
from pska_essential.readiness import build_not_ready_ask_result, build_readiness_loop_step, evaluate_kb_readiness
from pska_essential.workflow import WorkflowService


def run_agentic_question(
    service: WorkflowService,
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    limit: int = 5,
    proposal_kind: str = "writing_brief",
    create_review: bool | None = None,
    use_kg: bool = False,
    max_iterations: int = 2,
    min_context_packets: int = 1,
    retrieval_queries: list[str] | None = None,
    source_inspection_limit: int = 3,
    workspace_policy: WorkspaceGovernancePolicy | None = None,
    preflight_steps: list[dict[str, Any]] | None = None,
    resumed_from_run_id: str | None = None,
) -> dict[str, Any]:
    """Run a PSKA-controlled Ask loop.

    This loop is deliberately provider-independent. It records explicit steps,
    keeps retrieval inside the selected scope, creates transient work products
    freely, and creates review only when durable persistence is requested by
    proposal kind or caller policy.
    """

    normalized_question = question.strip()
    normalized_kind = proposal_kind.strip().lower() or "writing_brief"
    if normalized_kind in {"memory_delete", "memory_update"}:
        raise ValueError(f"{normalized_kind} proposals require an explicit memory fact")
    scope = {
        "dataset_ids": [str(dataset_id) for dataset_id in dataset_ids if str(dataset_id)],
        "document_ids": [str(document_id) for document_id in (document_ids or []) if str(document_id)],
        "use_kg": bool(use_kg),
    }
    if not normalized_question:
        raise ValueError("question is required")
    if not scope["dataset_ids"]:
        raise ValueError("dataset_ids is required")
    if limit < 1:
        raise ValueError("limit must be greater than 0")
    if source_inspection_limit < 0:
        raise ValueError("source_inspection_limit must be greater than or equal to 0")

    query_plan = _retrieval_query_plan(normalized_question, retrieval_queries)
    policy = workspace_policy or build_workspace_policy_from_env()
    durable_proposal = normalized_kind in DURABLE_PROPOSAL_KINDS
    governance_action = policy.action_for(normalized_kind, force_review=bool(create_review))
    review_required = governance_action in {MANUAL_REVIEW, AUTO_ACCEPT, AUTO_APPLY}
    steps: list[dict[str, Any]] = []

    def add_step(name: str, status: str, message: str, **metadata: Any) -> None:
        steps.append({"name": name, "status": status, "message": message, "metadata": metadata})

    run = service.start(normalized_question, scope)
    ask_request = _ask_request(
        question=normalized_question,
        scope=scope,
        limit=limit,
        proposal_kind=normalized_kind,
        create_review=create_review,
        max_iterations=max_iterations,
        min_context_packets=min_context_packets,
        retrieval_queries=query_plan[1:],
        source_inspection_limit=source_inspection_limit,
    )
    _save_ask_request(service, run.run_id, ask_request, resumed_from_run_id=resumed_from_run_id)
    run = service.state(run.run_id)
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.start",
            "workflow",
            run.run_id,
            question=normalized_question,
            dataset_ids=scope["dataset_ids"],
            document_ids=scope["document_ids"],
            proposal_kind=normalized_kind,
            retrieval_queries=query_plan[1:],
            resumed_from_run_id=resumed_from_run_id or "",
        )
    )
    add_step("scope.check", "complete", "Selected scope accepted.", scope=scope)
    if resumed_from_run_id:
        add_step(
            "workflow.resume",
            "complete",
            "Resumed Ask from a previous workflow.",
            resumed_from_run_id=resumed_from_run_id,
        )
    if scope["use_kg"]:
        add_step(
            "graph.retrieval",
            "complete",
            "Graph-aware retrieval requested inside the selected scope.",
            use_kg=True,
            dataset_ids=scope["dataset_ids"],
            document_ids=scope["document_ids"],
        )
    add_step(
        "governance.policy",
        "complete",
        "Workspace governance policy selected.",
        action=governance_action,
        durable=durable_proposal,
        policy=policy.to_dict(),
    )
    steps.extend(preflight_steps or [])
    add_step(
        "retrieval.plan",
        "complete",
        "Prepared scoped retrieval query plan.",
        query_count=len(query_plan),
        queries=query_plan,
    )

    memory_facts = service.memory_search(normalized_question, scope, limit=max(1, limit))
    add_step(
        "memory.search",
        "complete",
        "Searched governed durable workspace memory.",
        returned_count=len(memory_facts),
    )
    _save_memory_context(service, run.run_id, memory_facts)

    retrieved: list[ContextPacket] = []
    target_context = max(1, min_context_packets)
    iteration_count = max(1, max_iterations)
    for iteration in range(1, iteration_count + 1):
        iteration_limit = limit if iteration == 1 else max(limit, target_context)
        query = query_plan[min(iteration - 1, len(query_plan) - 1)]
        packets = service.context_retrieve(run.run_id, query, iteration_limit)
        retrieved = _unique_context_packets([*retrieved, *packets])
        add_step(
            "context.retrieve",
            "complete",
            "Retrieved context from selected scope.",
            iteration=iteration,
            query=query,
            query_index=min(iteration, len(query_plan)),
            query_count=len(query_plan),
            requested_limit=iteration_limit,
            returned_count=len(packets),
            unique_count=len(retrieved),
            use_kg=scope["use_kg"],
        )
        if len(retrieved) >= target_context:
            break
        add_step(
            "context.inspect",
            "needs_more_context",
            "Retrieved context is below the requested minimum.",
            iteration=iteration,
            required_count=target_context,
            unique_count=len(retrieved),
        )

    if len(retrieved) < target_context:
        if retrieved:
            message = f"Only {len(retrieved)} supporting context packet(s) were retrieved; {target_context} required."
        else:
            message = "No context was retrieved from the selected scope."
        add_step(
            "context.inspect",
            "insufficient",
            message,
            required_count=target_context,
            unique_count=len(retrieved),
        )
        loop = _loop_summary(
            status="insufficient_context",
            steps=steps,
            review_required=False,
            durable_proposal=durable_proposal,
            governance_action="skip",
            policy=policy,
            requested_governance_action=governance_action,
            context_count=len(retrieved),
            memory_count=len(memory_facts),
            required_context_count=target_context,
            retrieval_query_plan=query_plan,
            retrieval_query_count=len(query_plan),
            message=message,
            resumed_from_run_id=resumed_from_run_id or "",
        )
        _save_loop_metadata(service, run.run_id, loop)
        service.store.add_audit_event(
            audit_event(
                "agentic_loop.insufficient_context",
                "workflow",
                run.run_id,
                question=normalized_question,
                required_count=target_context,
                unique_count=len(retrieved),
                resumed_from_run_id=resumed_from_run_id or "",
            )
        )
        return {
            "status": "insufficient_context",
            "run": to_jsonable(service.state(run.run_id)),
            "context_packets": to_jsonable(retrieved),
            "proposal": None,
            "review": None,
            "review_decision": None,
            "memory_apply": None,
            "memory_facts": to_jsonable(memory_facts),
            "brief": "",
            "loop": loop,
            "message": message,
        }

    add_step("context.inspect", "complete", "Supporting context is available.", unique_count=len(retrieved))
    source_inspections = _inspect_sources(service, run.run_id, retrieved, source_inspection_limit)
    add_step(
        "source.inspect",
        "complete",
        "Inspected retrieved source material.",
        requested_limit=source_inspection_limit,
        inspected_count=len(source_inspections),
        source_refs=[to_jsonable(item.source_ref) for item in source_inspections],
    )
    proposal = service.propose(run.run_id, normalized_kind, normalized_question)
    add_step(
        "proposal.create",
        "complete",
        "Created durable knowledge candidate." if normalized_kind in DURABLE_PROPOSAL_KINDS else "Created transient work product.",
        proposal_id=proposal.proposal_id,
        kind=proposal.kind,
        durable=normalized_kind in DURABLE_PROPOSAL_KINDS,
    )

    review = None
    review_decision = None
    memory_apply = None
    if governance_action == MANUAL_REVIEW:
        review = service.review_create(proposal.proposal_id)
        add_step("review.create", "complete", "Created review for governance.", review_id=review.review_id)
    elif governance_action in {AUTO_ACCEPT, AUTO_APPLY}:
        review = service.review_create(proposal.proposal_id)
        review_decision = service.review_decide(
            review.review_id,
            "accept",
            f"accepted by workspace policy: {governance_action}",
        )
        add_step(
            "review.auto_accept",
            "complete",
            "Workspace policy accepted durable knowledge candidate.",
            review_id=review.review_id,
            action=governance_action,
        )
        if governance_action == AUTO_APPLY:
            memory_apply = service.memory_apply(review.review_id)
            add_step(
                "memory.auto_apply",
                "complete",
                "Workspace policy applied durable memory.",
                review_id=review.review_id,
                target_id=memory_apply.target_id,
                backend=memory_apply.backend,
            )
    else:
        add_step("review.skip", "complete", "No review required for transient output.")

    add_step("brief.prepare", "complete", "Prepared transient sourced brief.", format="markdown")
    loop = _loop_summary(
        status="ready",
        steps=steps,
        review_required=bool(review_required),
        durable_proposal=durable_proposal,
        governance_action=governance_action,
        policy=policy,
        context_count=len(retrieved),
        memory_count=len(memory_facts),
        source_inspection_count=len(source_inspections),
        proposal_id=proposal.proposal_id,
        review_id=review.review_id if review else "",
        memory_apply_target_id=memory_apply.target_id if memory_apply else "",
        retrieval_query_plan=query_plan,
        retrieval_query_count=len(query_plan),
        resumed_from_run_id=resumed_from_run_id or "",
    )
    _save_loop_metadata(service, run.run_id, loop)
    brief = service.render_brief(run.run_id, "markdown")
    artifact = service.workflow_artifact(run.run_id)
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.complete",
            "workflow",
            run.run_id,
            status="ready",
            context_count=len(retrieved),
            proposal_id=proposal.proposal_id,
            review_id=review.review_id if review else "",
            governance_action=governance_action,
            resumed_from_run_id=resumed_from_run_id or "",
        )
    )

    review_payload = to_jsonable(review) if review else None
    if review_payload and review_decision:
        review_payload.update(
            {
                "decision": review_decision.decision,
                "reason": review_decision.reason,
                "status": review_decision.status,
                "decided_at": review_decision.decided_at,
            }
        )

    return {
        "status": "ready",
        "run": to_jsonable(service.state(run.run_id)),
        "context_packets": to_jsonable(retrieved),
        "proposal": to_jsonable(proposal),
        "review": review_payload,
        "review_decision": to_jsonable(review_decision) if review_decision else None,
        "memory_apply": to_jsonable(memory_apply) if memory_apply else None,
        "memory_facts": to_jsonable(memory_facts),
        "artifact": artifact,
        "brief": brief,
        "loop": loop,
    }


def record_not_ready_agentic_question(
    service: WorkflowService,
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None,
    readiness: dict[str, Any],
    proposal_kind: str = "writing_brief",
    create_review: bool | None = None,
    use_kg: bool = False,
    limit: int = 5,
    max_iterations: int = 2,
    min_context_packets: int = 1,
    retrieval_queries: list[str] | None = None,
    source_inspection_limit: int = 3,
    workspace_policy: WorkspaceGovernancePolicy | None = None,
    resumed_from_run_id: str | None = None,
) -> dict[str, Any]:
    """Persist a KB-readiness-blocked Ask as a recoverable workflow state."""

    normalized_question = question.strip()
    normalized_kind = proposal_kind.strip().lower() or "writing_brief"
    if normalized_kind in {"memory_delete", "memory_update"}:
        raise ValueError(f"{normalized_kind} proposals require an explicit memory fact")
    scope = {
        "dataset_ids": [str(dataset_id) for dataset_id in dataset_ids if str(dataset_id)],
        "document_ids": [str(document_id) for document_id in (document_ids or []) if str(document_id)],
        "use_kg": bool(use_kg),
    }
    if not normalized_question:
        raise ValueError("question is required")
    if not scope["dataset_ids"]:
        raise ValueError("dataset_ids is required")
    if source_inspection_limit < 0:
        raise ValueError("source_inspection_limit must be greater than or equal to 0")
    query_plan = _retrieval_query_plan(normalized_question, retrieval_queries)
    result = build_not_ready_ask_result(
        question=normalized_question,
        dataset_ids=scope["dataset_ids"],
        document_ids=scope["document_ids"],
        readiness=readiness,
        proposal_kind=normalized_kind,
        create_review=create_review,
        use_kg=use_kg,
        workspace_policy=workspace_policy,
    )
    result["loop"]["retrieval_query_plan"] = query_plan
    result["loop"]["retrieval_query_count"] = len(query_plan)
    run = service.start(normalized_question, scope)
    ask_request = _ask_request(
        question=normalized_question,
        scope=scope,
        limit=limit,
        proposal_kind=normalized_kind,
        create_review=create_review,
        max_iterations=max_iterations,
        min_context_packets=min_context_packets,
        retrieval_queries=query_plan[1:],
        source_inspection_limit=source_inspection_limit,
    )
    _save_ask_request(service, run.run_id, ask_request, resumed_from_run_id=resumed_from_run_id)
    run = service.state(run.run_id)
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.start",
            "workflow",
            run.run_id,
            question=normalized_question,
            dataset_ids=scope["dataset_ids"],
            document_ids=scope["document_ids"],
            proposal_kind=normalized_kind,
            resumed_from_run_id=resumed_from_run_id or "",
        )
    )
    run.status = "blocked"
    if resumed_from_run_id:
        result["loop"]["steps"].insert(
            1,
            {
                "name": "workflow.resume",
                "status": "complete",
                "message": "Resumed Ask from a previous workflow.",
                "metadata": {"resumed_from_run_id": resumed_from_run_id},
            },
        )
        result["loop"]["resumed_from_run_id"] = resumed_from_run_id
    run.metadata["agentic_loop"] = to_jsonable(result["loop"])
    run.metadata["readiness"] = to_jsonable(readiness)
    run.metadata["blocked_reason"] = "kb_not_ready"
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.not_ready",
            "workflow",
            run.run_id,
            question=normalized_question,
            dataset_ids=scope["dataset_ids"],
            document_ids=scope["document_ids"],
            proposal_kind=normalized_kind,
            retrieval_queries=query_plan[1:],
            readiness_status=readiness.get("status") or "",
            blocking=readiness.get("blocking") or [],
            resumed_from_run_id=resumed_from_run_id or "",
        )
    )
    result["run"] = to_jsonable(service.state(run.run_id))
    result["artifact"] = service.workflow_artifact(run.run_id)
    return result


def run_agentic_question_with_readiness(
    service: WorkflowService,
    gateway: Any,
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    limit: int = 5,
    proposal_kind: str = "writing_brief",
    create_review: bool | None = None,
    use_kg: bool = False,
    max_iterations: int = 2,
    min_context_packets: int = 1,
    retrieval_queries: list[str] | None = None,
    source_inspection_limit: int = 3,
    resumed_from_run_id: str | None = None,
) -> dict[str, Any]:
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=dataset_ids,
        document_ids=document_ids or [],
    )
    if not readiness["ready"]:
        result = record_not_ready_agentic_question(
            service,
            question=question,
            dataset_ids=dataset_ids,
            document_ids=document_ids or [],
            readiness=readiness,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            limit=limit,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries,
            source_inspection_limit=source_inspection_limit,
            resumed_from_run_id=resumed_from_run_id,
        )
        service.store.add_audit_event(
            audit_event(
                "kb.readiness.blocked",
                "workflow",
                result["run"]["run_id"],
                question=question,
                dataset_ids=dataset_ids,
                document_ids=document_ids or [],
                readiness=readiness,
                retrieval_queries=_retrieval_query_plan(question, retrieval_queries)[1:],
                resumed_from_run_id=resumed_from_run_id or "",
            )
        )
        result["readiness"] = readiness
        return result

    result = run_agentic_question(
        service,
        question=question,
        dataset_ids=dataset_ids,
        document_ids=document_ids or [],
        limit=limit,
        proposal_kind=proposal_kind,
        create_review=create_review,
        use_kg=use_kg,
        max_iterations=max_iterations,
        min_context_packets=min_context_packets,
        retrieval_queries=retrieval_queries,
        source_inspection_limit=source_inspection_limit,
        preflight_steps=[build_readiness_loop_step(readiness)],
        resumed_from_run_id=resumed_from_run_id,
    )
    result["readiness"] = readiness
    return result


def resume_agentic_question(service: WorkflowService, gateway: Any, *, run_id: str) -> dict[str, Any]:
    previous_run = service.state(run_id)
    if previous_run.metadata.get("blocked_reason") != "kb_not_ready":
        raise ValueError("only readiness-blocked ask workflows can be resumed")
    ask_request = previous_run.metadata.get("ask_request")
    if not isinstance(ask_request, dict):
        raise ValueError("workflow does not contain a resumable ask_request")
    result = run_agentic_question_with_readiness(
        service,
        gateway,
        question=str(ask_request.get("question") or previous_run.intent),
        dataset_ids=[str(item) for item in ask_request.get("dataset_ids") or []],
        document_ids=[str(item) for item in ask_request.get("document_ids") or []],
        limit=int(ask_request.get("limit") or 5),
        proposal_kind=str(ask_request.get("proposal_kind") or "writing_brief"),
        create_review=ask_request.get("create_review") if "create_review" in ask_request else None,
        use_kg=bool(ask_request.get("use_kg", False)),
        max_iterations=int(ask_request.get("max_iterations") or 2),
        min_context_packets=int(ask_request.get("min_context_packets") or 1),
        retrieval_queries=[str(item) for item in ask_request.get("retrieval_queries") or []],
        source_inspection_limit=int(ask_request["source_inspection_limit"]) if "source_inspection_limit" in ask_request else 3,
        resumed_from_run_id=run_id,
    )
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.resume",
            "workflow",
            result["run"]["run_id"],
            resumed_from_run_id=run_id,
            previous_status=previous_run.status,
            status=result["status"],
        )
    )
    result["resumed_from_run_id"] = run_id
    return result


def list_resumable_agentic_questions(
    service: WorkflowService,
    gateway: Any,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List readiness-blocked Ask workflows with fresh readiness checks."""

    records: list[dict[str, Any]] = []
    for run in service.store.list_workflows(limit=limit):
        if run.metadata.get("blocked_reason") != "kb_not_ready":
            continue
        ask_request = run.metadata.get("ask_request")
        if not isinstance(ask_request, dict):
            continue
        dataset_ids = [str(item) for item in ask_request.get("dataset_ids") or []]
        document_ids = [str(item) for item in ask_request.get("document_ids") or []]
        readiness = evaluate_kb_readiness(gateway, dataset_ids=dataset_ids, document_ids=document_ids)
        records.append(
            {
                "run": to_jsonable(run),
                "ask_request": to_jsonable(ask_request),
                "readiness": readiness,
                "can_resume": bool(readiness.get("ready")),
                "message": (
                    "Selected knowledge scope is ready; resume can create a new Ask workflow."
                    if readiness.get("ready")
                    else "Selected knowledge scope is still not ready."
                ),
            }
        )
    return records


def _loop_summary(
    *,
    status: str,
    steps: list[dict[str, Any]],
    review_required: bool,
    durable_proposal: bool,
    governance_action: str,
    policy: WorkspaceGovernancePolicy,
    **metadata: Any,
) -> dict[str, Any]:
    loop = {
        "status": status,
        "steps": steps,
        "review_required": review_required,
        "durable_proposal": durable_proposal,
        "governance": {
            "action": governance_action,
            "policy": policy.to_dict(),
            "durable_proposal": durable_proposal,
        },
    }
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        loop[key] = value
    return loop


def _save_loop_metadata(service: WorkflowService, run_id: str, loop: dict[str, Any]) -> None:
    run = service.state(run_id)
    run.metadata["agentic_loop"] = to_jsonable(loop)
    service.store.save_workflow(run)


def _save_memory_context(service: WorkflowService, run_id: str, memory_facts: list[Any]) -> None:
    run = service.state(run_id)
    run.metadata["memory_context"] = to_jsonable(memory_facts)
    service.store.save_workflow(run)


def _save_source_inspections(service: WorkflowService, run_id: str, source_inspections: list[SourceContext]) -> None:
    run = service.state(run_id)
    run.metadata["source_inspections"] = to_jsonable(source_inspections)
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)


def _save_ask_request(
    service: WorkflowService,
    run_id: str,
    ask_request: dict[str, Any],
    *,
    resumed_from_run_id: str | None,
) -> None:
    run = service.state(run_id)
    run.metadata["ask_request"] = to_jsonable(ask_request)
    if resumed_from_run_id:
        run.metadata["resumed_from_run_id"] = resumed_from_run_id
    run.updated_at = utc_now_iso()
    service.store.save_workflow(run)


def _ask_request(
    *,
    question: str,
    scope: dict[str, Any],
    limit: int,
    proposal_kind: str,
    create_review: bool | None,
    max_iterations: int,
    min_context_packets: int,
    retrieval_queries: list[str],
    source_inspection_limit: int,
) -> dict[str, Any]:
    return {
        "question": question,
        "dataset_ids": list(scope.get("dataset_ids") or []),
        "document_ids": list(scope.get("document_ids") or []),
        "use_kg": bool(scope.get("use_kg", False)),
        "limit": limit,
        "proposal_kind": proposal_kind,
        "create_review": create_review,
        "max_iterations": max_iterations,
        "min_context_packets": min_context_packets,
        "retrieval_queries": list(retrieval_queries),
        "source_inspection_limit": source_inspection_limit,
    }


def _retrieval_query_plan(question: str, retrieval_queries: list[str] | None) -> list[str]:
    queries = [question, *(retrieval_queries or [])]
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = str(query or "").strip()
        if not normalized:
            continue
        dedupe_key = normalized.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(normalized)
    return result or [question]


def _unique_context_packets(packets: list[ContextPacket]) -> list[ContextPacket]:
    seen: set[str] = set()
    result: list[ContextPacket] = []
    for packet in packets:
        ref = packet.source_ref
        source_parts = [
            ref.adapter,
            ref.dataset_id or "",
            ref.document_id or "",
            ref.chunk_id or "",
            ref.source_id or "",
            ref.external_id or "",
        ]
        if any(source_parts):
            key = "source|" + "|".join(source_parts)
        else:
            key = "|".join(["context", packet.context_id, packet.text])
        if key in seen:
            continue
        seen.add(key)
        result.append(packet)
    return result


def _inspect_sources(
    service: WorkflowService,
    run_id: str,
    packets: list[ContextPacket],
    limit: int,
) -> list[SourceContext]:
    if limit <= 0:
        _save_source_inspections(service, run_id, [])
        return []
    refs = _unique_source_refs([packet.source_ref for packet in packets])
    source_inspections = [service.source_read(ref) for ref in refs[:limit]]
    _save_source_inspections(service, run_id, source_inspections)
    return source_inspections


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
