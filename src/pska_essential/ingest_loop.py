from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from pska_essential.agentic_loop import record_not_ready_agentic_question, run_agentic_question_with_readiness
from pska_essential.audit import audit_event
from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable
from pska_essential.kb_audit import add_kb_ingest_audit
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.readiness import evaluate_kb_readiness


def run_ingest_loop(
    service: Any,
    gateway: Any,
    *,
    file_paths: list[str],
    dataset_id: str = "",
    dataset_name: str = "",
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
) -> dict[str, Any]:
    selected_files = _normalized_ids(file_paths)
    if not selected_files:
        raise ValueError("file_paths is required")
    if not dataset_id.strip() and not dataset_name.strip():
        raise ValueError("dataset_id or dataset_name is required")

    ingest = gateway.ingest_files(
        file_paths=selected_files,
        dataset_id=dataset_id.strip() or None,
        dataset_name=dataset_name.strip() or None,
        description=description,
        chunk_method=chunk_method,
        embedding_model=embedding_model,
        parse=parse,
        wait=False,
    )
    add_kb_ingest_audit(service.store, ingest)

    dataset = dict(ingest.get("dataset") or {})
    resolved_dataset_id = str(dataset.get("dataset_id") or dataset_id).strip()
    document_ids = [
        str(document.get("document_id") or "").strip()
        for document in ingest.get("documents") or []
        if str(document.get("document_id") or "").strip()
    ]
    readiness = _wait_for_readiness(
        gateway,
        dataset_ids=[resolved_dataset_id],
        document_ids=document_ids,
        wait_ready=wait_ready,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    if not readiness.get("ready"):
        ask_result = None
        if _should_record_resumable_ask(readiness):
            ask_result = record_not_ready_agentic_question(
                service,
                question=question,
                dataset_ids=[resolved_dataset_id],
                document_ids=document_ids,
                readiness=readiness,
                proposal_kind=proposal_kind,
                create_review=create_review,
                use_kg=use_kg,
                limit=limit,
                max_iterations=max_iterations,
                min_context_packets=min_context_packets,
                retrieval_queries=retrieval_queries or [],
                source_inspection_limit=source_inspection_limit,
            )
            service.store.add_audit_event(
                audit_event(
                    "kb.readiness.blocked",
                    "workflow",
                    ask_result["run"]["run_id"],
                    question=question,
                    dataset_ids=[resolved_dataset_id],
                    document_ids=document_ids,
                    readiness=readiness,
                    retrieval_queries=retrieval_queries or [],
                    upload_loop=True,
                )
            )
            ask_result["readiness"] = readiness
        return _loop_result(
            status="not_ready",
            message="Documents were ingested, but the selected scope is not ready for Ask.",
            ingest=ingest,
            readiness=readiness,
            ask_result=ask_result,
            export=None,
            export_format=export_format,
        )

    ask_result = run_agentic_question_with_readiness(
        service,
        gateway,
        question=question,
        dataset_ids=[resolved_dataset_id],
        document_ids=document_ids,
        limit=limit,
        proposal_kind=proposal_kind,
        create_review=create_review,
        use_kg=use_kg,
        max_iterations=max_iterations,
        min_context_packets=min_context_packets,
        retrieval_queries=retrieval_queries or [],
        source_inspection_limit=source_inspection_limit,
    )
    if ask_result.get("status") != "ready":
        return _loop_result(
            status=str(ask_result.get("status") or "not_ready"),
            message=str(ask_result.get("message") or "Ask did not produce an exportable work product."),
            ingest=ingest,
            readiness=readiness,
            ask_result=ask_result,
            export=None,
            export_format=export_format,
        )

    run_id = str((ask_result.get("run") or {}).get("run_id") or "")
    export = service.export_brief(run_id, export_format)
    return _loop_result(
        status="ok",
        message="Uploaded documents reached a sourced Ask/export work product.",
        ingest=ingest,
        readiness=readiness,
        ask_result=ask_result,
        export=export,
        export_format=export_format,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run upload -> readiness -> Ask -> export through PSKA.")
    parser.add_argument("file_paths", nargs="*", help="Files to ingest through the configured KB provider.")
    parser.add_argument("--dataset-id", default=os.getenv("PSKA_LOOP_DATASET_ID", ""))
    parser.add_argument("--dataset-name", default=os.getenv("PSKA_LOOP_DATASET_NAME", ""))
    parser.add_argument("--description", default=os.getenv("PSKA_LOOP_DATASET_DESCRIPTION", ""))
    parser.add_argument("--chunk-method", default=os.getenv("PSKA_LOOP_CHUNK_METHOD", "naive"))
    parser.add_argument("--embedding-model", default=os.getenv("PSKA_LOOP_EMBEDDING_MODEL", ""))
    parser.add_argument(
        "--question",
        default=os.getenv("PSKA_LOOP_QUESTION", "Summarize the uploaded documents with sources."),
    )
    parser.add_argument("--limit", type=int, default=_int_env("PSKA_LOOP_LIMIT", 5))
    parser.add_argument("--proposal-kind", default=os.getenv("PSKA_LOOP_PROPOSAL_KIND", "writing_brief"))
    parser.add_argument("--max-iterations", type=int, default=_int_env("PSKA_LOOP_MAX_ITERATIONS", 2))
    parser.add_argument("--min-context-packets", type=int, default=_int_env("PSKA_LOOP_MIN_CONTEXT_PACKETS", 1))
    parser.add_argument(
        "--source-inspection-limit",
        type=int,
        default=_int_env("PSKA_LOOP_SOURCE_INSPECTION_LIMIT", 3),
    )
    parser.add_argument("--export-format", default=os.getenv("PSKA_LOOP_EXPORT_FORMAT", "markdown"))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("PSKA_LOOP_TIMEOUT_SECONDS", "600")))
    parser.add_argument("--poll-interval-seconds", type=float, default=float(os.getenv("PSKA_LOOP_POLL_INTERVAL_SECONDS", "2")))
    parser.add_argument("--retrieval-query", action="append", default=None)
    parser.add_argument("--no-parse", action="store_true", default=_env_enabled("PSKA_LOOP_NO_PARSE"))
    parser.add_argument("--no-wait", action="store_true", default=_env_enabled("PSKA_LOOP_NO_WAIT"))
    parser.add_argument("--use-kg", action="store_true", default=_env_enabled("PSKA_LOOP_USE_KG"))
    parser.add_argument("--create-review", action="store_true", default=_env_enabled("PSKA_LOOP_CREATE_REVIEW"))
    args = parser.parse_args(argv)

    file_paths = args.file_paths or _csv_env("PSKA_LOOP_FILE_PATHS")
    service = build_service_from_env()
    gateway = build_kb_gateway_from_env()
    result = run_ingest_loop(
        service,
        gateway,
        file_paths=file_paths,
        dataset_id=args.dataset_id,
        dataset_name=args.dataset_name,
        description=args.description,
        chunk_method=args.chunk_method,
        embedding_model=args.embedding_model,
        parse=not args.no_parse,
        wait_ready=not args.no_wait,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        question=args.question,
        limit=args.limit,
        proposal_kind=args.proposal_kind,
        create_review=True if args.create_review else None,
        use_kg=args.use_kg,
        max_iterations=args.max_iterations,
        min_context_packets=args.min_context_packets,
        retrieval_queries=args.retrieval_query or _lines_env("PSKA_LOOP_RETRIEVAL_QUERIES"),
        source_inspection_limit=args.source_inspection_limit,
        export_format=args.export_format,
    )
    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 2


def _wait_for_readiness(
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str],
    wait_ready: bool,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.time() + max(0.0, timeout_seconds)
    while True:
        readiness = evaluate_kb_readiness(gateway, dataset_ids=dataset_ids, document_ids=document_ids)
        if readiness.get("ready") or not wait_ready or str(readiness.get("status") or "") in {"failed", "cancelled"}:
            return readiness
        if time.time() >= deadline:
            readiness["timed_out"] = True
            readiness["message"] = "Timed out waiting for the selected knowledge scope to become ready."
            return readiness
        time.sleep(max(0.05, poll_interval_seconds))


def _should_record_resumable_ask(readiness: dict[str, Any]) -> bool:
    if readiness.get("ready"):
        return False
    status = str(readiness.get("status") or "").strip().lower()
    if status in {"failed", "cancelled", "missing", "empty"}:
        return False
    return bool(readiness.get("dataset_ids"))


def _loop_result(
    *,
    status: str,
    message: str,
    ingest: dict[str, Any],
    readiness: dict[str, Any],
    ask_result: dict[str, Any] | None,
    export: str | dict[str, Any] | None,
    export_format: str,
) -> dict[str, Any]:
    run = (ask_result or {}).get("run") or {}
    return {
        "kind": "ingest_loop",
        "status": status,
        "message": message,
        "dataset": ingest.get("dataset") or {},
        "documents": ingest.get("documents") or [],
        "ingest": ingest,
        "readiness": readiness,
        "ask_status": (ask_result or {}).get("status"),
        "run": run or None,
        "run_id": run.get("run_id") or "",
        "context_packets": (ask_result or {}).get("context_packets") or [],
        "proposal": (ask_result or {}).get("proposal"),
        "review": (ask_result or {}).get("review"),
        "review_decision": (ask_result or {}).get("review_decision"),
        "memory_apply": (ask_result or {}).get("memory_apply"),
        "memory_facts": (ask_result or {}).get("memory_facts") or [],
        "brief": (ask_result or {}).get("brief") or "",
        "loop": (ask_result or {}).get("loop"),
        "artifact": (ask_result or {}).get("artifact"),
        "export_format": export_format,
        "export": export,
    }


def _normalized_ids(values: list[str] | list[Any]) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _csv_env(name: str) -> list[str]:
    return _normalized_ids(os.getenv(name, "").split(","))


def _lines_env(name: str) -> list[str]:
    return _normalized_ids(os.getenv(name, "").splitlines())


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else int(default)


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
