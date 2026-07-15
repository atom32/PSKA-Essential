from __future__ import annotations

import json
import sys
from typing import Any, Callable

from pska_essential.agentic_loop import (
    list_resumable_agentic_questions,
    resume_agentic_question,
    run_agentic_question_with_readiness,
)
from pska_essential.capabilities import product_capabilities
from pska_essential.component_check import run_component_check
from pska_essential.config import build_service_from_env
from pska_essential.contracts import SourceRef, to_jsonable
from pska_essential.diagnostics import (
    add_live_closed_loop_probe_audit,
    add_memory_probe_audit,
    add_retrieval_probe_audit,
    build_runtime_diagnostics,
    run_live_closed_loop_probe,
    run_memory_probe,
    run_retrieval_probe,
)
from pska_essential.env_file import env_file_arg_parser, load_env_file
from pska_essential.governance import build_workspace_policy_from_env
from pska_essential.ingest_loop import resume_ingest_loop, run_ingest_loop
from pska_essential.kb_audit import (
    add_kb_dataset_create_audit,
    add_kb_dataset_delete_audit,
    add_kb_graph_read_audit,
    add_kb_ingest_audit,
    add_kb_parse_audit,
)
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.workspace_status import build_workspace_status


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

    def pska_policy_get():
        return build_workspace_policy_from_env().to_dict()

    def pska_capabilities_get():
        return product_capabilities(memory_adapter=service.memory)

    def pska_workspace_status(
        dataset_page_size: int = 30,
        review_limit: int = 50,
        workflow_limit: int = 50,
    ):
        return build_workspace_status(
            service=service,
            gateway=build_kb_gateway_from_env(),
            dataset_page_size=dataset_page_size,
            review_limit=review_limit,
            workflow_limit=workflow_limit,
        )

    def pska_runtime_diagnostics():
        return build_runtime_diagnostics(
            service=service,
            kb_gateway_factory=build_kb_gateway_from_env,
        )

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
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        probe = run_retrieval_probe(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=limit,
            use_kg=use_kg,
        )
        add_retrieval_probe_audit(service.store, probe)
        return probe

    def pska_memory_probe(
        query: str = "PSKA memory probe",
        scope: dict[str, Any] | None = None,
        limit: int = 1,
        require_live: bool = True,
    ):
        probe = run_memory_probe(
            service,
            query=query,
            scope=scope or {},
            limit=limit,
            require_live=require_live,
        )
        add_memory_probe_audit(service.store, probe)
        return probe

    def pska_component_check(
        question: str = "PSKA component check",
        dataset_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        memory_query: str = "PSKA component memory probe",
        limit: int = 3,
        retrieval_limit: int = 1,
        proposal_kind: str = "writing_brief",
        use_kg: bool = False,
        export_format: str = "json",
        source_inspection_limit: int = 1,
        require_memory: bool = True,
        run_closed_loop: bool = True,
    ):
        return run_component_check(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=_optional_strings(dataset_ids),
            document_ids=_optional_strings(document_ids),
            memory_query=memory_query,
            limit=limit,
            retrieval_limit=retrieval_limit,
            proposal_kind=proposal_kind,
            use_kg=use_kg,
            export_format=export_format,
            source_inspection_limit=source_inspection_limit,
            require_memory=require_memory,
            run_closed_loop=run_closed_loop,
        )

    def pska_live_closed_loop_probe(
        question: str,
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
        limit: int = 3,
        proposal_kind: str = "writing_brief",
        use_kg: bool = False,
        export_format: str = "json",
        source_inspection_limit: int = 1,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        probe = run_live_closed_loop_probe(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=limit,
            proposal_kind=proposal_kind,
            use_kg=use_kg,
            export_format=export_format,
            source_inspection_limit=source_inspection_limit,
        )
        add_live_closed_loop_probe_audit(service.store, probe)
        return probe

    def pska_ingest_loop(
        file_paths: list[str],
        dataset_name: str | None = None,
        dataset_id: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
        parse: bool = True,
        wait_ready: bool = True,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 2.0,
        question: str = "Summarize the uploaded documents with sources.",
        limit: int = 5,
        proposal_kind: str = "writing_brief",
        create_review: bool | None = None,
        use_kg: bool = False,
        max_iterations: int = 2,
        min_context_packets: int = 1,
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
        export_format: str = "markdown",
    ):
        selected_file_paths = _required_strings(file_paths, "file_paths", dedupe=False)
        return run_ingest_loop(
            service,
            build_kb_gateway_from_env(),
            file_paths=selected_file_paths,
            dataset_name=dataset_name or "",
            dataset_id=dataset_id or "",
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
            parse=parse,
            wait_ready=wait_ready,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            question=question,
            limit=limit,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
            export_format=export_format,
        )

    def pska_ingest_loop_resume(run_id: str, export_format: str = ""):
        selected_run_id = _required_string(run_id, "run_id")
        return resume_ingest_loop(
            service,
            build_kb_gateway_from_env(),
            run_id=selected_run_id,
            export_format=export_format,
        )

    def pska_eval_run(suite: str = "smoke"):
        return service.eval_run(suite)

    def pska_kb_list(name: str | None = None, page_size: int = 30):
        return build_kb_gateway_from_env().list_datasets(name=name, page_size=page_size)

    def pska_kb_create(
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
    ):
        dataset = build_kb_gateway_from_env().create_dataset(
            name=name,
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
        )
        add_kb_dataset_create_audit(service.store, dataset)
        return dataset

    def pska_kb_delete(dataset_ids: list[str] | None = None, delete_all: bool = False):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids") if not delete_all else []
        result = build_kb_gateway_from_env().delete_datasets(
            dataset_ids=selected_dataset_ids,
            delete_all=delete_all,
        )
        add_kb_dataset_delete_audit(service.store, result)
        return result

    def pska_kb_ingest_files(
        file_paths: list[str],
        dataset_name: str | None = None,
        dataset_id: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
        parse: bool = True,
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        selected_file_paths = _required_strings(file_paths, "file_paths", dedupe=False)
        gateway = build_kb_gateway_from_env()
        result = gateway.ingest_files(
            file_paths=selected_file_paths,
            dataset_name=dataset_name,
            dataset_id=dataset_id,
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
            parse=parse,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_ingest_audit(service.store, result)
        return {
            **result,
            **_kb_operation_status_payload(gateway, result),
            "note": (
                "Upload accepted. Use ingestion_status/readiness before asking; "
                "uploaded or processing scopes are not retrieval-ready yet."
            ),
        }

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
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        return evaluate_kb_readiness(
            build_kb_gateway_from_env(),
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )

    def pska_kb_ingestion_status(
        dataset_ids: list[str],
        document_ids: list[str] | None = None,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        payload = _kb_status_payload(
            build_kb_gateway_from_env(),
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )
        return {
            **payload,
            "note": (
                "Use readiness.ready before retrieval. If ingestion_status is not ready, "
                "wait, parse listed documents, or inspect failure reasons instead of asking."
            ),
        }

    def pska_kb_parse_documents(
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ):
        selected_dataset_id = _required_string(dataset_id, "dataset_id")
        selected_document_ids = _required_strings(document_ids, "document_ids")
        gateway = build_kb_gateway_from_env()
        result = gateway.parse_documents(
            dataset_id=selected_dataset_id,
            document_ids=selected_document_ids,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )
        add_kb_parse_audit(service.store, result)
        return {
            **result,
            **_kb_status_payload(gateway, dataset_ids=[selected_dataset_id], document_ids=selected_document_ids),
            "note": "Parse started. Use ingestion_status/readiness before asking over this scope.",
        }

    def pska_kb_graph_read(dataset_id: str, document_id: str):
        selected_dataset_id = _required_string(dataset_id, "dataset_id")
        selected_document_id = _required_string(document_id, "document_id")
        graph = build_kb_gateway_from_env().document_graph(dataset_id=selected_dataset_id, document_id=selected_document_id)
        add_kb_graph_read_audit(service.store, graph, dataset_id=selected_dataset_id, document_id=selected_document_id)
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
        retrieval_queries: list[str] | None = None,
        source_inspection_limit: int = 3,
    ):
        selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
        selected_document_ids = _optional_strings(document_ids)
        result = run_agentic_question_with_readiness(
            service,
            build_kb_gateway_from_env(),
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=limit,
            proposal_kind=proposal_kind,
            create_review=create_review,
            use_kg=use_kg,
            max_iterations=max_iterations,
            min_context_packets=min_context_packets,
            retrieval_queries=retrieval_queries or [],
            source_inspection_limit=source_inspection_limit,
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
        selected_run_id = _required_string(run_id, "run_id")
        result = resume_agentic_question(
            service,
            build_kb_gateway_from_env(),
            run_id=selected_run_id,
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
        "pska_policy_get": pska_policy_get,
        "pska_capabilities_get": pska_capabilities_get,
        "pska_workspace_status": pska_workspace_status,
        "pska_runtime_diagnostics": pska_runtime_diagnostics,
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
        "pska_memory_probe": pska_memory_probe,
        "pska_component_check": pska_component_check,
        "pska_live_closed_loop_probe": pska_live_closed_loop_probe,
        "pska_ingest_loop": pska_ingest_loop,
        "pska_ingest_loop_resume": pska_ingest_loop_resume,
        "pska_eval_run": pska_eval_run,
        "pska_kb_list": pska_kb_list,
        "pska_kb_create": pska_kb_create,
        "pska_kb_delete": pska_kb_delete,
        "pska_kb_ingest_files": pska_kb_ingest_files,
        "pska_kb_document_status": pska_kb_document_status,
        "pska_kb_readiness": pska_kb_readiness,
        "pska_kb_ingestion_status": pska_kb_ingestion_status,
        "pska_kb_parse_documents": pska_kb_parse_documents,
        "pska_kb_graph_read": pska_kb_graph_read,
        "pska_agentic_question_start": pska_agentic_question_start,
        "pska_agentic_question_resumable": pska_agentic_question_resumable,
        "pska_agentic_question_resume": pska_agentic_question_resume,
    }


def _kb_status_payload(
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    selected_dataset_ids = _required_strings(dataset_ids, "dataset_ids")
    selected_document_ids = _optional_strings(document_ids)
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=selected_dataset_ids,
        document_ids=selected_document_ids,
    )
    return {"readiness": readiness, "ingestion_status": readiness.get("ingestion_status") or {}}


def _kb_operation_status_payload(gateway: Any, result: dict[str, Any]) -> dict[str, Any]:
    dataset = result.get("dataset") or {}
    dataset_id = str(dataset.get("dataset_id") or "")
    if not dataset_id:
        return {"readiness": {}, "ingestion_status": {}}
    document_ids = [
        str(document.get("document_id") or "").strip()
        for document in result.get("documents") or []
        if document.get("document_id")
    ]
    return _kb_status_payload(gateway, dataset_ids=[dataset_id], document_ids=document_ids)


def _required_string(value: Any, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _required_strings(values: list[str] | None, name: str, *, dedupe: bool = True) -> list[str]:
    result = _optional_strings(values, dedupe=dedupe)
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _optional_strings(values: list[str] | None, *, dedupe: bool = True) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        if dedupe:
            if normalized in seen:
                continue
            seen.add(normalized)
        result.append(normalized)
    return result


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
            "apply reviewed memory. Use pska_workspace_status to choose the "
            "next workflow action. Do not call backend RAGFlow or Graphiti MCP "
            "servers directly. Do not use case-specific shortcuts or fallback "
            "answers when retrieval/backend calls fail."
        ),
    )
    for name, func in tool_registry(service).items():
        mcp.add_tool(func, name=name)
    return mcp


def main(argv: list[str] | None = None) -> int:
    cli_args = list(sys.argv[1:] if argv is None else argv)
    if any(arg in {"-h", "--help"} for arg in cli_args):
        print("usage: pska-essential-mcp [--env-file ENV_FILE] [--list-tools]")
        return 0
    env_parser = env_file_arg_parser()
    env_args, remaining = env_parser.parse_known_args(cli_args)
    if env_args.env_file:
        load_env_file(env_args.env_file)

    if "--list-tools" in remaining:
        print(json.dumps(sorted(tool_registry().keys()), ensure_ascii=False, indent=2))
        return 0
    original_argv = sys.argv
    sys.argv = [original_argv[0], *remaining]
    try:
        server = build_fastmcp()
        server.run()
    finally:
        sys.argv = original_argv
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
