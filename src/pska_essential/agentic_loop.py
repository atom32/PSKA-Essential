from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import ContextPacket, SourceContext, SourceRef, WorkflowRun, to_jsonable, utc_now_iso
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
    model_context_tokens: int | None = None,
    model_profile: str = "",
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
        "dataset_ids": _normalized_ids(dataset_ids),
        "document_ids": _normalized_ids(document_ids or []),
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
    context_budget = _context_budget(
        requested_limit=limit,
        requested_source_inspection_limit=source_inspection_limit,
        requested_min_context_packets=min_context_packets,
        max_iterations=max_iterations,
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
    )
    effective_limit = int(context_budget["effective_retrieval_limit"])
    effective_memory_limit = int(context_budget["effective_memory_limit"])
    effective_source_inspection_limit = int(context_budget["effective_source_inspection_limit"])
    effective_min_context_packets = int(context_budget["effective_min_context_packets"])

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
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
        context_budget=context_budget,
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
            context_budget=context_budget,
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
        "context.budget",
        "complete",
        "Computed model-aware context budget.",
        **context_budget,
    )
    add_step(
        "retrieval.plan",
        "complete",
        "Prepared scoped retrieval query plan.",
        query_count=len(query_plan),
        queries=query_plan,
    )

    memory_facts = service.memory_search(normalized_question, scope, limit=max(1, effective_memory_limit))
    add_step(
        "memory.search",
        "complete",
        "Searched governed durable workspace memory.",
        returned_count=len(memory_facts),
    )
    _save_memory_context(service, run.run_id, memory_facts)

    retrieved: list[ContextPacket] = []
    target_context = max(1, effective_min_context_packets)
    iteration_count = max(1, max_iterations)
    for iteration in range(1, iteration_count + 1):
        iteration_limit = effective_limit if iteration == 1 else max(effective_limit, target_context)
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

    federated_packets, federation = _federate_memory_source_context(
        service,
        run.run_id,
        memory_facts,
        retrieved,
        limit=max(1, effective_limit),
    )
    if federation["memory_fact_count"]:
        retrieved = _unique_context_packets([*retrieved, *federated_packets])
        _save_context_packets(service, run.run_id, retrieved)
        add_step(
            "memory.source_federation",
            _federation_status(federation),
            "Fetched KB evidence referenced by durable memory facts.",
            **federation,
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
            context_budget=context_budget,
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
    source_inspections = _inspect_sources(service, run.run_id, retrieved, effective_source_inspection_limit)
    add_step(
        "source.inspect",
        "complete",
        "Inspected retrieved source material.",
        requested_limit=source_inspection_limit,
        effective_limit=effective_source_inspection_limit,
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
        context_budget=context_budget,
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
    model_context_tokens: int | None = None,
    model_profile: str = "",
    workspace_policy: WorkspaceGovernancePolicy | None = None,
    resumed_from_run_id: str | None = None,
) -> dict[str, Any]:
    """Persist a KB-readiness-blocked Ask as a recoverable workflow state."""

    normalized_question = question.strip()
    normalized_kind = proposal_kind.strip().lower() or "writing_brief"
    if normalized_kind in {"memory_delete", "memory_update"}:
        raise ValueError(f"{normalized_kind} proposals require an explicit memory fact")
    scope = {
        "dataset_ids": _normalized_ids(dataset_ids),
        "document_ids": _normalized_ids(document_ids or []),
        "use_kg": bool(use_kg),
    }
    if not normalized_question:
        raise ValueError("question is required")
    if not scope["dataset_ids"]:
        raise ValueError("dataset_ids is required")
    if source_inspection_limit < 0:
        raise ValueError("source_inspection_limit must be greater than or equal to 0")
    context_budget = _context_budget(
        requested_limit=limit,
        requested_source_inspection_limit=source_inspection_limit,
        requested_min_context_packets=min_context_packets,
        max_iterations=max_iterations,
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
    )
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
    result["loop"]["context_budget"] = context_budget
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
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
        context_budget=context_budget,
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
    model_context_tokens: int | None = None,
    model_profile: str = "",
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
            model_context_tokens=model_context_tokens,
            model_profile=model_profile,
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
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
        preflight_steps=[build_readiness_loop_step(readiness)],
        resumed_from_run_id=resumed_from_run_id,
    )
    result["readiness"] = readiness
    return result


def run_digest_scope(
    service: WorkflowService,
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    question: str = "Digest the selected ready knowledge into concise candidate knowledge.",
    limit: int = 5,
    use_kg: bool = False,
    max_iterations: int = 2,
    min_context_packets: int = 1,
    retrieval_queries: list[str] | None = None,
    source_inspection_limit: int = 3,
    model_context_tokens: int | None = None,
    model_profile: str = "",
    create_memory_review: bool = False,
    memory_intent: str = "",
) -> dict[str, Any]:
    """Run an explicit scope digest without writing durable memory as a side effect."""

    result = run_agentic_question_with_readiness(
        service,
        gateway,
        question=question,
        dataset_ids=dataset_ids,
        document_ids=document_ids or [],
        limit=limit,
        proposal_kind="digest",
        create_review=False,
        use_kg=use_kg,
        max_iterations=max_iterations,
        min_context_packets=min_context_packets,
        retrieval_queries=retrieval_queries or [],
        source_inspection_limit=source_inspection_limit,
        model_context_tokens=model_context_tokens,
        model_profile=model_profile,
    )
    result["kind"] = "digest_scope"
    result["digest"] = result.get("proposal")
    result["memory_review"] = None
    run_id = str((result.get("run") or {}).get("run_id") or "")
    if run_id:
        _save_digest_scope_metadata(
            service,
            run_id,
            create_memory_review=create_memory_review,
            memory_intent=memory_intent,
        )
        result["run"] = to_jsonable(service.state(run_id))
        result["artifact"] = service.workflow_artifact(run_id)
    if result.get("status") == "ready" and create_memory_review and run_id:
        memory_review = service.memory_review_from_workflow(
            run_id,
            memory_intent or f"Memory candidate from digest: {question}",
        )
        result["memory_review"] = memory_review
        result["run"] = to_jsonable(service.state(run_id))
        result["artifact"] = service.workflow_artifact(run_id)
    service.store.add_audit_event(
        audit_event(
            "digest.scope",
            "workflow",
            run_id or "unavailable",
            status=str(result.get("status") or ""),
            dataset_ids=_normalized_ids(dataset_ids),
            document_ids=_normalized_ids(document_ids or []),
            create_memory_review=create_memory_review,
            memory_review_id=str(((result.get("memory_review") or {}).get("review") or {}).get("review_id") or ""),
        )
    )
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
        dataset_ids=_normalized_ids(ask_request.get("dataset_ids") or []),
        document_ids=_normalized_ids(ask_request.get("document_ids") or []),
        limit=int(ask_request.get("limit") or 5),
        proposal_kind=str(ask_request.get("proposal_kind") or "writing_brief"),
        create_review=ask_request.get("create_review") if "create_review" in ask_request else None,
        use_kg=bool(ask_request.get("use_kg", False)),
        max_iterations=int(ask_request.get("max_iterations") or 2),
        min_context_packets=int(ask_request.get("min_context_packets") or 1),
        retrieval_queries=[str(item) for item in ask_request.get("retrieval_queries") or []],
        source_inspection_limit=int(ask_request["source_inspection_limit"]) if "source_inspection_limit" in ask_request else 3,
        model_context_tokens=(
            int(ask_request["model_context_tokens"])
            if ask_request.get("model_context_tokens") is not None
            else None
        ),
        model_profile=str(ask_request.get("model_profile") or ""),
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
        can_resume = bool(readiness.get("ready"))
        resume = _resumable_resume_contract(run, can_resume)
        records.append(
            {
                "run": to_jsonable(run),
                "ask_request": to_jsonable(ask_request),
                "readiness": readiness,
                "can_resume": can_resume,
                "resume": resume,
                "next_actions": _resumable_next_actions(
                    readiness=readiness,
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                    resume=resume,
                ),
                "message": (
                    "Selected knowledge scope is ready; resume can create a new Ask workflow."
                    if can_resume
                    else "Selected knowledge scope is still not ready."
                ),
            }
        )
    return records


def _resumable_resume_contract(run: WorkflowRun, can_resume: bool) -> dict[str, Any]:
    run_id = run.run_id
    is_ingest_loop = isinstance(run.metadata.get("ingest_loop"), dict)
    tool = "pska_ingest_loop_resume" if is_ingest_loop else "pska_agentic_question_resume"
    path = "resume-ingest-loop" if is_ingest_loop else "resume-ask"
    action = "resume_ingest_loop" if is_ingest_loop else "resume_blocked_ask"
    params: dict[str, Any] = {"run_id": run_id}
    if is_ingest_loop:
        export_format = str((run.metadata.get("ingest_loop") or {}).get("export_format") or "").strip()
        if export_format:
            params["export_format"] = export_format
    return {
        "action": action,
        "run_id": run_id,
        "can_resume": can_resume,
        "api": f"POST /api/workflows/{run_id}/{path}",
        "tool": tool,
        "params": params,
    }


def _resumable_next_actions(
    *,
    readiness: dict[str, Any],
    dataset_ids: list[str],
    document_ids: list[str],
    resume: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if dataset_ids:
        actions.append(
            {
                "action": "track_ingestion_status",
                "label": "Track Status",
                "reason": "Track parsing, chunking, embedding, and indexing before resuming.",
                "api": f"GET /api/kb/datasets/{dataset_ids[0]}/ingestion-status",
                "tool": "pska_kb_ingestion_status",
                "view": "kb",
                "params": {"dataset_id": dataset_ids[0], "document_ids": document_ids},
            }
        )
    action = str(resume.get("action") or "resume_blocked_ask")
    is_ingest_loop = action == "resume_ingest_loop"
    actions.append(
        {
            "action": action,
            "label": "Resume Loop" if is_ingest_loop else "Resume Ask",
            "reason": (
                "Selected knowledge scope is ready; resume the preserved upload -> Ask -> export intent."
                if is_ingest_loop and readiness.get("ready")
                else "Resume the preserved upload -> Ask -> export intent after the selected knowledge scope is ready."
                if is_ingest_loop
                else "Selected knowledge scope is ready; resume the preserved Ask request."
                if readiness.get("ready")
                else "Resume the preserved Ask request after the selected knowledge scope is ready."
            ),
            "api": resume["api"],
            "tool": resume["tool"],
            "view": "ask",
            "params": resume["params"],
            "can_resume": bool(resume.get("can_resume")),
            "requires_ready": True,
        }
    )
    return actions


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


def _context_budget(
    *,
    requested_limit: int,
    requested_source_inspection_limit: int,
    requested_min_context_packets: int,
    max_iterations: int,
    model_context_tokens: int | None,
    model_profile: str,
) -> dict[str, Any]:
    requested = max(1, int(requested_limit))
    requested_inspections = max(0, int(requested_source_inspection_limit))
    requested_min = max(1, int(requested_min_context_packets))
    iterations = max(1, int(max_iterations))
    profile = str(model_profile or "").strip()
    if model_context_tokens is None:
        return {
            "schema": "pska.context_budget.v1",
            "mode": "fixed_limit",
            "model_profile": profile,
            "model_context_tokens": None,
            "requested_limit": requested,
            "effective_retrieval_limit": requested,
            "effective_memory_limit": requested,
            "requested_source_inspection_limit": requested_inspections,
            "effective_source_inspection_limit": requested_inspections,
            "requested_min_context_packets": requested_min,
            "effective_min_context_packets": requested_min,
            "max_iterations": iterations,
        }
    tokens = int(model_context_tokens)
    if tokens < 1024:
        raise ValueError("model_context_tokens must be at least 1024")
    reserved_tokens = min(max(2048, int(tokens * 0.35)), max(512, tokens - 512))
    retrieval_budget_tokens = max(512, tokens - reserved_tokens)
    retrieval_cap = max(1, retrieval_budget_tokens // 900)
    memory_cap = max(1, int(retrieval_budget_tokens * 0.2) // 300)
    source_inspection_cap = max(0, int(retrieval_budget_tokens * 0.25) // 900)
    effective_retrieval_limit = max(1, min(requested, retrieval_cap))
    effective_memory_limit = max(1, min(requested, memory_cap))
    effective_source_inspection_limit = max(0, min(requested_inspections, source_inspection_cap))
    effective_min_context = max(1, min(requested_min, effective_retrieval_limit * iterations))
    return {
        "schema": "pska.context_budget.v1",
        "mode": "model_context",
        "model_profile": profile,
        "model_context_tokens": tokens,
        "reserved_tokens": reserved_tokens,
        "retrieval_budget_tokens": retrieval_budget_tokens,
        "estimated_tokens_per_context_packet": 900,
        "estimated_tokens_per_memory_fact": 300,
        "estimated_tokens_per_source_inspection": 900,
        "requested_limit": requested,
        "effective_retrieval_limit": effective_retrieval_limit,
        "effective_memory_limit": effective_memory_limit,
        "requested_source_inspection_limit": requested_inspections,
        "effective_source_inspection_limit": effective_source_inspection_limit,
        "requested_min_context_packets": requested_min,
        "effective_min_context_packets": effective_min_context,
        "max_iterations": iterations,
    }


def _save_loop_metadata(service: WorkflowService, run_id: str, loop: dict[str, Any]) -> None:
    run = service.state(run_id)
    run.metadata["agentic_loop"] = to_jsonable(loop)
    service.store.save_workflow(run)


def _save_memory_context(service: WorkflowService, run_id: str, memory_facts: list[Any]) -> None:
    run = service.state(run_id)
    run.metadata["memory_context"] = to_jsonable(memory_facts)
    service.store.save_workflow(run)


def _save_context_packets(service: WorkflowService, run_id: str, packets: list[ContextPacket]) -> None:
    run = service.state(run_id)
    run.context_packets = _unique_context_packets(packets)
    run.updated_at = utc_now_iso()
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


def _save_digest_scope_metadata(
    service: WorkflowService,
    run_id: str,
    *,
    create_memory_review: bool,
    memory_intent: str,
) -> None:
    run = service.state(run_id)
    run.metadata["digest_scope"] = {
        "kind": "digest_scope",
        "create_memory_review": bool(create_memory_review),
        "memory_intent": memory_intent,
    }
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
    model_context_tokens: int | None = None,
    model_profile: str = "",
    context_budget: dict[str, Any] | None = None,
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
        "model_context_tokens": model_context_tokens,
        "model_profile": model_profile,
        "context_budget": to_jsonable(context_budget or {}),
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


def _normalized_ids(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _unique_context_packets(packets: list[ContextPacket]) -> list[ContextPacket]:
    seen: set[str] = set()
    result: list[ContextPacket] = []
    for packet in packets:
        key = _context_packet_key(packet)
        if key in seen:
            continue
        seen.add(key)
        result.append(packet)
    return result


def _context_packet_key(packet: ContextPacket) -> str:
    hash_key = _content_hash_key(packet.source_ref, packet.metadata)
    if hash_key:
        return hash_key
    ref_key = _source_ref_key(packet.source_ref)
    if ref_key:
        return f"source|{ref_key}"
    return "|".join(["context", packet.context_id, packet.text])


def _federate_memory_source_context(
    service: WorkflowService,
    run_id: str,
    memory_facts: list[Any],
    existing_packets: list[ContextPacket],
    *,
    limit: int,
) -> tuple[list[ContextPacket], dict[str, Any]]:
    backend_name = str(getattr(service.retrieval, "backend_name", "") or "")
    existing_ref_keys = {_source_ref_key(packet.source_ref) for packet in existing_packets}
    existing_hash_keys = {
        key
        for key in (_content_hash_key(packet.source_ref, packet.metadata) for packet in existing_packets)
        if key
    }
    candidates = _memory_source_candidates(memory_facts, backend_name, existing_ref_keys, existing_hash_keys)
    selected = candidates[:limit]
    packets: list[ContextPacket] = []
    failures: list[dict[str, Any]] = []
    for index, candidate in enumerate(selected, start=1):
        ref = candidate["source_ref"]
        try:
            source = service.source_read(ref)
        except Exception as exc:
            failures.append(
                {
                    "source_ref": to_jsonable(ref),
                    "memory_fact_ids": candidate["memory_fact_ids"],
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            )
            continue
        text = str(source.text or "").strip()
        if not text:
            failures.append(
                {
                    "source_ref": to_jsonable(ref),
                    "memory_fact_ids": candidate["memory_fact_ids"],
                    "error": "empty source text",
                    "error_type": "EmptySource",
                }
            )
            continue
        packets.append(
            ContextPacket(
                context_id=f"ctx_memory_source_{index}_{_stable_source_suffix(ref)}",
                text=text,
                source_ref=source.source_ref,
                score=0.0,
                title=source.source_ref.title or str(source.metadata.get("title") or "Memory source evidence"),
                metadata={
                    "origin": "memory_source_federation",
                    "memory_fact_ids": candidate["memory_fact_ids"],
                    "source_context_metadata": to_jsonable(source.metadata),
                },
            )
        )
    stats = {
        "memory_fact_count": len(memory_facts),
        "candidate_source_count": len(candidates),
        "requested_limit": limit,
        "read_count": len(selected),
        "added_count": len(packets),
        "skipped_count": _memory_source_skipped_count(memory_facts, candidates),
        "failed_count": len(failures),
        "unresolved_fact_count": _unresolved_memory_fact_count(memory_facts),
        "source_refs": to_jsonable([packet.source_ref for packet in packets]),
        "failures": failures,
    }
    if memory_facts:
        service.store.add_audit_event(
            audit_event(
                "memory.source_federate",
                "workflow",
                run_id,
                **stats,
            )
        )
    return packets, stats


def _memory_source_candidates(
    memory_facts: list[Any],
    backend_name: str,
    existing_ref_keys: set[str],
    existing_hash_keys: set[str],
) -> list[dict[str, Any]]:
    candidates_by_key: dict[str, dict[str, Any]] = {}
    skipped_keys: set[str] = set()
    for fact in memory_facts:
        fact_id = _memory_fact_id(fact)
        for ref in _memory_fact_source_refs(fact):
            if not _source_ref_readable_by_retrieval(ref, backend_name):
                skipped_keys.add(_source_ref_key(ref))
                continue
            ref_key = _source_ref_key(ref)
            hash_key = _content_hash_key(ref, {})
            if ref_key in existing_ref_keys or (hash_key and hash_key in existing_hash_keys):
                skipped_keys.add(ref_key)
                continue
            candidate_key = hash_key or ref_key
            if not candidate_key:
                continue
            candidate = candidates_by_key.setdefault(
                candidate_key,
                {
                    "source_ref": ref,
                    "memory_fact_ids": [],
                    "skipped_keys": skipped_keys,
                },
            )
            if fact_id and fact_id not in candidate["memory_fact_ids"]:
                candidate["memory_fact_ids"].append(fact_id)
    return list(candidates_by_key.values())


def _memory_source_skipped_count(memory_facts: list[Any], candidates: list[dict[str, Any]]) -> int:
    total_refs = sum(len(_memory_fact_source_refs(fact)) for fact in memory_facts)
    return max(0, total_refs - len(candidates))


def _unresolved_memory_fact_count(memory_facts: list[Any]) -> int:
    count = 0
    for fact in memory_facts:
        metadata = _memory_fact_metadata(fact)
        if metadata.get("lineage_status") == "unresolved" or not _memory_fact_source_refs(fact):
            count += 1
    return count


def _memory_fact_source_refs(fact: Any) -> list[SourceRef]:
    raw_refs = getattr(fact, "source_refs", None)
    if raw_refs is None and isinstance(fact, dict):
        raw_refs = fact.get("source_refs")
    refs: list[SourceRef] = []
    for raw_ref in raw_refs or []:
        if isinstance(raw_ref, SourceRef):
            refs.append(raw_ref)
        elif isinstance(raw_ref, dict):
            refs.append(SourceRef.from_dict(raw_ref))
    return refs


def _memory_fact_id(fact: Any) -> str:
    if isinstance(fact, dict):
        return str(fact.get("fact_id") or "")
    return str(getattr(fact, "fact_id", "") or "")


def _memory_fact_metadata(fact: Any) -> dict[str, Any]:
    if isinstance(fact, dict):
        return dict(fact.get("metadata") or {})
    return dict(getattr(fact, "metadata", {}) or {})


def _source_ref_readable_by_retrieval(ref: SourceRef, backend_name: str) -> bool:
    if ref.adapter in {"conversation", "hermes"}:
        return False
    if backend_name and ref.adapter and ref.adapter != backend_name:
        return False
    return bool(ref.dataset_id or ref.document_id or ref.chunk_id or ref.source_id or ref.external_id)


def _federation_status(federation: dict[str, Any]) -> str:
    if federation["failed_count"] and federation["added_count"]:
        return "partial"
    if federation["failed_count"]:
        return "failed"
    if federation["added_count"]:
        return "complete"
    return "skipped"


def _stable_source_suffix(ref: SourceRef) -> str:
    raw = ref.chunk_id or ref.document_id or ref.source_id or ref.external_id or ref.adapter or "source"
    return "".join(char if char.isalnum() else "_" for char in str(raw)).strip("_")[:80] or "source"


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
        key = _content_hash_key(ref, {}) or _source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


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


def _content_hash_key(ref: SourceRef, metadata: dict[str, Any]) -> str:
    content_hash = (
        (metadata or {}).get("content_hash")
        or ref.metadata.get("content_hash")
        or ref.metadata.get("excerpt_hash")
        or ""
    )
    return f"hash|{content_hash}" if content_hash else ""
