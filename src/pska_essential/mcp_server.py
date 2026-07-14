from __future__ import annotations

import json
import sys
from typing import Any, Callable

from pska_essential.agentic_loop import (
    list_resumable_agentic_questions,
    resume_agentic_question,
    run_agentic_question_with_readiness,
)
from pska_essential.config import build_service_from_env
from pska_essential.contracts import SourceRef, to_jsonable
from pska_essential.diagnostics import add_retrieval_probe_audit, run_retrieval_probe
from pska_essential.kb_audit import (
    add_kb_dataset_create_audit,
    add_kb_graph_read_audit,
    add_kb_ingest_audit,
    add_kb_parse_audit,
)
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.readiness import evaluate_kb_readiness


def tool_registry(service=None) -> dict[str, Callable[..., Any]]:
    service = service or build_service_from_env()

    def pska_workflow_start(intent: str, scope: dict[str, Any] | None = None):
        return to_jsonable(service.start(intent, scope or {}))

    def pska_workflow_list(limit: int = 50):
        return to_jsonable(service.store.list_workflows(limit=limit))

    def pska_workflow_state(run_id: str):
        return to_jsonable(service.state(run_id))

    def pska_workflow_artifact(run_id: str):
        return service.workflow_artifact(run_id)

    def pska_workflow_brief(run_id: str, format: str = "markdown"):
        return service.render_brief(run_id, format)

    def pska_context_retrieve(
        query: str,
        scope: dict[str, Any] | None = None,
        limit: int = 5,
        run_id: str | None = None,
    ):
        if not run_id:
            run_id = service.start(query, scope or {}).run_id
        if scope:
            run = service.state(run_id)
            run.scope.update(scope)
            service.store.save_workflow(run)
        return to_jsonable(service.context_retrieve(run_id, query, limit))

    def pska_source_read(source_ref: dict[str, Any]):
        return to_jsonable(service.source_read(SourceRef.from_dict(source_ref)))

    def pska_propose(run_id: str, kind: str, intent: str = ""):
        return to_jsonable(service.propose(run_id, kind, intent))

    def pska_review_create(proposal_id: str):
        return to_jsonable(service.review_create(proposal_id))

    def pska_review_list(status: str | None = None, limit: int = 50):
        return service.store.list_reviews(status=status or None, limit=limit)

    def pska_review_get(review_id: str):
        return service.store.get_review_record(review_id)

    def pska_review_decide(review_id: str, decision: str, reason: str = ""):
        return to_jsonable(service.review_decide(review_id, decision, reason))

    def pska_review_revise(review_id: str, intent: str = ""):
        return service.review_revise(review_id, intent)

    def pska_memory_search(query: str, scope: dict[str, Any] | None = None, limit: int = 10):
        return to_jsonable(service.memory_search(query, scope or {}, limit))

    def pska_memory_apply(review_id: str):
        return to_jsonable(service.memory_apply(review_id))

    def pska_memory_review_from_workflow(run_id: str, intent: str = ""):
        return service.memory_review_from_workflow(run_id, intent)

    def pska_memory_delete_review(memory_fact: dict[str, Any], reason: str = ""):
        return service.memory_delete_review(memory_fact, reason)

    def pska_memory_update_review(memory_fact: dict[str, Any], text: str, reason: str = ""):
        return service.memory_update_review(memory_fact, text, reason)

    def pska_memory_lifecycle(memory_target_id: str, limit: int = 50):
        return service.memory_lifecycle(memory_target_id, limit)

    def pska_export_brief(run_id: str, format: str = "markdown"):
        return service.export_brief(run_id, format)

    def pska_audit_list(action: str | None = None, limit: int = 50, descending: bool = True):
        return to_jsonable(
            service.store.list_audit_events(
                action=action or None,
                limit=limit,
                descending=descending,
            )
        )

    def pska_retrieval_probe(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 1,
        use_kg: bool = False,
    ):
        probe = run_retrieval_probe(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=dataset_ids,
            document_ids=document_ids or [],
            limit=limit,
            use_kg=use_kg,
        )
        add_retrieval_probe_audit(service.store, probe)
        return probe

    def pska_eval_run(suite: str = "smoke"):
        return service.eval_run(suite)

    def pska_kb_list(name: str | None = None, page_size: int = 30):
        return build_kb_gateway_from_env().list_datasets(name=name, page_size=page_size)

    def pska_kb_create(name: str, description: str = "", chunk_method: str = "naive"):
        dataset = build_kb_gateway_from_env().create_dataset(
            name=name,
            description=description,
            chunk_method=chunk_method,
        )
        add_kb_dataset_create_audit(service.store, dataset)
        return dataset

    def pska_kb_ingest_files(
        file_paths: list[str],
        dataset_name: str | None = None,
        dataset_id: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        parse: bool = True,
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        result = build_kb_gateway_from_env().ingest_files(
            file_paths=file_paths,
            dataset_name=dataset_name,
            dataset_id=dataset_id,
            description=description,
            chunk_method=chunk_method,
            parse=parse,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_ingest_audit(service.store, result)
        return result

    def pska_kb_document_status(
        dataset_id: str,
        document_id: str | None = None,
        name: str | None = None,
        page_size: int = 30,
    ):
        return build_kb_gateway_from_env().list_documents(
            dataset_id=dataset_id,
            document_id=document_id,
            name=name,
            page_size=page_size,
        )

    def pska_kb_readiness(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
    ):
        return evaluate_kb_readiness(
            build_kb_gateway_from_env(),
            dataset_ids=dataset_ids,
            document_ids=document_ids or [],
        )

    def pska_kb_parse_documents(
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        result = build_kb_gateway_from_env().parse_documents(
            dataset_id=dataset_id,
            document_ids=document_ids,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_parse_audit(service.store, result)
        return result

    def pska_kb_graph_read(dataset_id: str, document_id: str):
        graph = build_kb_gateway_from_env().document_graph(dataset_id=dataset_id, document_id=document_id)
        add_kb_graph_read_audit(service.store, graph, dataset_id=dataset_id, document_id=document_id)
        return graph

    def pska_agentic_question_start(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 5,
        proposal_kind: str = "writing_brief",
        create_review: bool | None = None,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
    ):
        result = run_agentic_question_with_readiness(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=dataset_ids,
            document_ids=document_ids or [],
            limit=limit,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
        )
        if result["status"] == "not_ready":
            result["note"] = (
                "Selected knowledge scope is not ready for retrieval. "
                "Check pska_kb_readiness or pska_kb_document_status before asking again."
            )
            return result
        result["note"] = (
            "Agent should answer from returned context and brief. "
            "Transient work products do not require review by default. "
            "Memory changes still require an accepted review before pska_memory_apply."
        )
        return result

    def pska_agentic_question_resume(run_id: str):
        result = resume_agentic_question(
            service,
            build_kb_gateway_from_env(),
            run_id=run_id,
        )
        if result["status"] == "not_ready":
            result["note"] = (
                "Selected knowledge scope is still not ready for retrieval. "
                "Check pska_kb_readiness or pska_kb_document_status before resuming again."
            )
            return result
        result["note"] = (
            "Resumed Ask created a new workflow run. "
            "Use returned context/brief and keep durable memory changes behind review."
        )
        return result

    def pska_agentic_question_resumable(limit: int = 50):
        return list_resumable_agentic_questions(
            service,
            build_kb_gateway_from_env(),
            limit=limit,
        )

    return {
        "pska_workflow_start": pska_workflow_start,
        "pska_workflow_list": pska_workflow_list,
        "pska_workflow_state": pska_workflow_state,
        "pska_workflow_artifact": pska_workflow_artifact,
        "pska_workflow_brief": pska_workflow_brief,
        "pska_context_retrieve": pska_context_retrieve,
        "pska_source_read": pska_source_read,
        "pska_propose": pska_propose,
        "pska_review_create": pska_review_create,
        "pska_review_list": pska_review_list,
        "pska_review_get": pska_review_get,
        "pska_review_decide": pska_review_decide,
        "pska_review_revise": pska_review_revise,
        "pska_memory_search": pska_memory_search,
        "pska_memory_apply": pska_memory_apply,
        "pska_memory_review_from_workflow": pska_memory_review_from_workflow,
        "pska_memory_delete_review": pska_memory_delete_review,
        "pska_memory_update_review": pska_memory_update_review,
        "pska_memory_lifecycle": pska_memory_lifecycle,
        "pska_export_brief": pska_export_brief,
        "pska_audit_list": pska_audit_list,
        "pska_retrieval_probe": pska_retrieval_probe,
        "pska_eval_run": pska_eval_run,
        "pska_kb_list": pska_kb_list,
        "pska_kb_create": pska_kb_create,
        "pska_kb_ingest_files": pska_kb_ingest_files,
        "pska_kb_document_status": pska_kb_document_status,
        "pska_kb_readiness": pska_kb_readiness,
        "pska_kb_parse_documents": pska_kb_parse_documents,
        "pska_kb_graph_read": pska_kb_graph_read,
        "pska_agentic_question_start": pska_agentic_question_start,
        "pska_agentic_question_resumable": pska_agentic_question_resumable,
        "pska_agentic_question_resume": pska_agentic_question_resume,
    }


def build_fastmcp(service=None):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install optional dependency with `uv sync --extra mcp` to run MCP") from exc

    mcp = FastMCP(
        "pska-essential",
        instructions=(
            "PSKA-Essential is an agent knowledge workflow gate. Use its tools "
            "to retrieve context, propose candidate knowledge, review it, and "
            "apply reviewed memory. Do not call backend RAGFlow or Graphiti MCP "
            "servers directly. Do not use case-specific shortcuts or fallback "
            "answers when retrieval/backend calls fail."
        ),
    )
    for name, func in tool_registry(service).items():
        mcp.add_tool(func, name=name)
    return mcp


def main() -> int:
    if "--list-tools" in sys.argv:
        print(json.dumps(sorted(tool_registry().keys()), ensure_ascii=False, indent=2))
        return 0
    server = build_fastmcp()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
