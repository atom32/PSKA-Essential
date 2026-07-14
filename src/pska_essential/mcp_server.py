from __future__ import annotations

import json
import sys
from typing import Any, Callable

from pska_essential.config import build_service_from_env
from pska_essential.contracts import SourceRef, to_jsonable
from pska_essential.kb_gateway import build_kb_gateway_from_env


def tool_registry(service=None) -> dict[str, Callable[..., Any]]:
    service = service or build_service_from_env()

    def pska_workflow_start(intent: str, scope: dict[str, Any] | None = None):
        return to_jsonable(service.start(intent, scope or {}))

    def pska_workflow_state(run_id: str):
        return to_jsonable(service.state(run_id))

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

    def pska_review_decide(review_id: str, decision: str, reason: str = ""):
        return to_jsonable(service.review_decide(review_id, decision, reason))

    def pska_memory_search(query: str, scope: dict[str, Any] | None = None, limit: int = 10):
        return to_jsonable(service.memory_search(query, scope or {}, limit))

    def pska_memory_apply(review_id: str):
        return to_jsonable(service.memory_apply(review_id))

    def pska_export_brief(run_id: str, format: str = "markdown"):
        return service.export_brief(run_id, format)

    def pska_eval_run(suite: str = "smoke"):
        return service.eval_run(suite)

    def pska_kb_list(name: str | None = None, page_size: int = 30):
        return build_kb_gateway_from_env().list_datasets(name=name, page_size=page_size)

    def pska_kb_create(name: str, description: str = "", chunk_method: str = "naive"):
        return build_kb_gateway_from_env().create_dataset(
            name=name,
            description=description,
            chunk_method=chunk_method,
        )

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
        return build_kb_gateway_from_env().ingest_files(
            file_paths=file_paths,
            dataset_name=dataset_name,
            dataset_id=dataset_id,
            description=description,
            chunk_method=chunk_method,
            parse=parse,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )

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

    def pska_kb_parse_documents(
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        return build_kb_gateway_from_env().parse_documents(
            dataset_id=dataset_id,
            document_ids=document_ids,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )

    def pska_kb_graph_read(dataset_id: str, document_id: str):
        return build_kb_gateway_from_env().document_graph(dataset_id=dataset_id, document_id=document_id)

    def pska_agentic_question_start(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 5,
        proposal_kind: str = "writing_brief",
        create_review: bool = True,
        use_kg: bool = False,
    ):
        scope = {
            "dataset_ids": dataset_ids,
            "document_ids": document_ids or [],
            "use_kg": use_kg,
        }
        run = service.start(question, scope)
        packets = service.context_retrieve(run.run_id, question, limit)
        proposal = service.propose(run.run_id, proposal_kind, question)
        review = service.review_create(proposal.proposal_id) if create_review else None
        return {
            "run": to_jsonable(service.state(run.run_id)),
            "context_packets": to_jsonable(packets),
            "proposal": to_jsonable(proposal),
            "review": to_jsonable(review) if review else None,
            "brief": service.export_brief(run.run_id, "markdown"),
            "note": (
                "Agent should answer from returned context and brief. "
                "Memory writes still require an accepted review before pska_memory_apply."
            ),
        }

    return {
        "pska_workflow_start": pska_workflow_start,
        "pska_workflow_state": pska_workflow_state,
        "pska_context_retrieve": pska_context_retrieve,
        "pska_source_read": pska_source_read,
        "pska_propose": pska_propose,
        "pska_review_create": pska_review_create,
        "pska_review_decide": pska_review_decide,
        "pska_memory_search": pska_memory_search,
        "pska_memory_apply": pska_memory_apply,
        "pska_export_brief": pska_export_brief,
        "pska_eval_run": pska_eval_run,
        "pska_kb_list": pska_kb_list,
        "pska_kb_create": pska_kb_create,
        "pska_kb_ingest_files": pska_kb_ingest_files,
        "pska_kb_document_status": pska_kb_document_status,
        "pska_kb_parse_documents": pska_kb_parse_documents,
        "pska_kb_graph_read": pska_kb_graph_read,
        "pska_agentic_question_start": pska_agentic_question_start,
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
