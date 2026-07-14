from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event
from pska_essential.contracts import ContextPacket, to_jsonable
from pska_essential.governance import (
    AUTO_ACCEPT,
    AUTO_APPLY,
    DURABLE_PROPOSAL_KINDS,
    MANUAL_REVIEW,
    WorkspaceGovernancePolicy,
    build_workspace_policy_from_env,
)
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
    workspace_policy: WorkspaceGovernancePolicy | None = None,
    preflight_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a PSKA-controlled Ask loop.

    This loop is deliberately provider-independent. It records explicit steps,
    keeps retrieval inside the selected scope, creates transient work products
    freely, and creates review only when durable persistence is requested by
    proposal kind or caller policy.
    """

    normalized_question = question.strip()
    normalized_kind = proposal_kind.strip().lower() or "writing_brief"
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

    policy = workspace_policy or build_workspace_policy_from_env()
    durable_proposal = normalized_kind in DURABLE_PROPOSAL_KINDS
    governance_action = policy.action_for(normalized_kind, force_review=bool(create_review))
    review_required = governance_action in {MANUAL_REVIEW, AUTO_ACCEPT, AUTO_APPLY}
    steps: list[dict[str, Any]] = []

    def add_step(name: str, status: str, message: str, **metadata: Any) -> None:
        steps.append({"name": name, "status": status, "message": message, "metadata": metadata})

    run = service.start(normalized_question, scope)
    service.store.add_audit_event(
        audit_event(
            "agentic_loop.start",
            "workflow",
            run.run_id,
            question=normalized_question,
            dataset_ids=scope["dataset_ids"],
            document_ids=scope["document_ids"],
            proposal_kind=normalized_kind,
        )
    )
    add_step("scope.check", "complete", "Selected scope accepted.", scope=scope)
    add_step(
        "governance.policy",
        "complete",
        "Workspace governance policy selected.",
        action=governance_action,
        durable=durable_proposal,
        policy=policy.to_dict(),
    )
    steps.extend(preflight_steps or [])

    retrieved: list[ContextPacket] = []
    target_context = max(1, min_context_packets)
    iteration_count = max(1, max_iterations)
    for iteration in range(1, iteration_count + 1):
        iteration_limit = limit if iteration == 1 else max(limit, target_context)
        packets = service.context_retrieve(run.run_id, normalized_question, iteration_limit)
        retrieved = _unique_context_packets([*retrieved, *packets])
        add_step(
            "context.retrieve",
            "complete",
            "Retrieved context from selected scope.",
            iteration=iteration,
            requested_limit=iteration_limit,
            returned_count=len(packets),
            unique_count=len(retrieved),
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
            required_context_count=target_context,
            message=message,
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
            "brief": "",
            "loop": loop,
            "message": message,
        }

    add_step("context.inspect", "complete", "Supporting context is available.", unique_count=len(retrieved))
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
        proposal_id=proposal.proposal_id,
        review_id=review.review_id if review else "",
        memory_apply_target_id=memory_apply.target_id if memory_apply else "",
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
        "artifact": artifact,
        "brief": brief,
        "loop": loop,
    }


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


def _unique_context_packets(packets: list[ContextPacket]) -> list[ContextPacket]:
    seen: set[str] = set()
    result: list[ContextPacket] = []
    for packet in packets:
        ref = packet.source_ref
        key = "|".join(
            [
                packet.context_id,
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
        result.append(packet)
    return result
