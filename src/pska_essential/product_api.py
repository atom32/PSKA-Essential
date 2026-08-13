from __future__ import annotations

import argparse
import json
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from pska_essential.agentic_loop import (
    list_resumable_agentic_questions,
    resume_agentic_question,
    run_digest_scope,
    run_agentic_question_with_readiness,
)
from pska_essential.capabilities import product_capabilities
from pska_essential.component_check import run_component_check
from pska_essential.config import build_service_from_env
from pska_essential.contracts import ContextPacket, MemoryFact, SourceRef, to_jsonable
from pska_essential.diagnostics import (
    add_live_closed_loop_probe_audit,
    add_memory_probe_audit,
    add_retrieval_probe_audit,
    build_runtime_diagnostics,
    run_live_closed_loop_probe,
    run_memory_probe,
    run_retrieval_probe,
)
from pska_essential.digest_jobs import enqueue_digest_job, list_digest_jobs, run_digest_job
from pska_essential.eidolia_import import import_eidolia_project_traces
from pska_essential.env_file import preload_env_file
from pska_essential.eval import run_eval
from pska_essential.governance import build_workspace_policy_from_env
from pska_essential.ingest_loop import resume_ingest_loop, run_ingest_loop
from pska_essential.jarvis import build_jarvis_briefing
from pska_essential.kb_audit import (
    add_kb_dataset_create_audit,
    add_kb_dataset_delete_audit,
    add_kb_graph_read_audit,
    add_kb_ingest_audit,
    add_kb_parse_audit,
)
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.memory_cards import get_memory_card, list_memory_cards
from pska_essential.memory_briefing import build_memory_briefing
from pska_essential.memory_candidate_dedup import build_memory_candidate_dedup
from pska_essential.memory_health import scan_memory_health
from pska_essential.memory_review_queue import build_memory_review_queue
from pska_essential.memory_timeline import build_memory_timeline
from pska_essential.memory_use_trace import explain_memory_why_used, list_memory_use_traces
from pska_essential.migration_manifest import build_migration_manifest
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.runtime_context import build_runtime_workspace_context
from pska_essential.source_audit_jobs import (
    activate_due_source_audit_jobs,
    enqueue_source_audit_job,
    list_source_audit_jobs,
    run_source_audit_job,
    schedule_source_audit_job,
)
from pska_essential.source_extraction_jobs import (
    enqueue_source_extraction_job,
    list_source_extraction_jobs,
    run_source_extraction_job,
)
from pska_essential.source_watch import watch_source_once
from pska_essential.trace_query import build_trace_query
from pska_essential.workflow import WorkflowError, WorkflowService
from pska_essential.workspace_status import build_workspace_status


KbGatewayFactory = Callable[[], Any]


PRODUCT_API_REQUIRED_ROUTES: tuple[dict[str, str], ...] = (
    {"method": "GET", "path": "/api/health"},
    {"method": "GET", "path": "/api/capabilities"},
    {"method": "GET", "path": "/api/workspace/status"},
    {"method": "POST", "path": "/api/jarvis/briefing"},
    {"method": "GET", "path": "/api/provider/jobs"},
    {"method": "POST", "path": "/api/turn-context"},
    {"method": "POST", "path": "/api/ask"},
    {"method": "POST", "path": "/api/digest"},
    {"method": "POST", "path": "/api/digest-jobs"},
    {"method": "GET", "path": "/api/digest-jobs"},
    {"method": "POST", "path": "/api/digest-jobs/run-next"},
    {"method": "POST", "path": "/api/digest-jobs/{run_id}/run"},
    {"method": "POST", "path": "/api/workflows/{run_id}/memory-review"},
    {"method": "POST", "path": "/api/sources/audit-jobs"},
    {"method": "GET", "path": "/api/sources/audit-jobs"},
    {"method": "POST", "path": "/api/sources/audit-schedules"},
    {"method": "POST", "path": "/api/sources/audit-jobs/tick"},
    {"method": "POST", "path": "/api/sources/audit-jobs/run-next"},
    {"method": "POST", "path": "/api/sources/audit-jobs/{run_id}/run"},
    {"method": "POST", "path": "/api/sources/extraction-jobs"},
    {"method": "GET", "path": "/api/sources/extraction-jobs"},
    {"method": "POST", "path": "/api/sources/extraction-jobs/run-next"},
    {"method": "POST", "path": "/api/sources/extraction-jobs/{run_id}/run"},
    {"method": "POST", "path": "/api/sources/watch-once"},
    {"method": "GET", "path": "/api/sources/roots"},
    {"method": "POST", "path": "/api/sources/roots"},
    {"method": "POST", "path": "/api/sources/roots/{root_id}/scan"},
    {"method": "POST", "path": "/api/sources/search"},
    {"method": "POST", "path": "/api/sources/neighbors"},
    {"method": "POST", "path": "/api/sources/duplicates"},
    {"method": "POST", "path": "/api/sources/duplicate-review"},
    {"method": "POST", "path": "/api/sources/duplicate-groups/{group_id}/mark"},
    {"method": "POST", "path": "/api/sources/audits/run"},
    {"method": "POST", "path": "/api/sources/saved-searches"},
    {"method": "GET", "path": "/api/sources/collections"},
    {"method": "POST", "path": "/api/sources/collections"},
    {"method": "POST", "path": "/api/sources/collections/{collection_id}/resolve"},
    {"method": "POST", "path": "/api/sources/tags/proposals"},
    {"method": "POST", "path": "/api/sources/tags/{proposal_id}/apply"},
    {"method": "POST", "path": "/api/sources/comments/proposals"},
    {"method": "POST", "path": "/api/sources/comments/{proposal_id}/apply"},
    {"method": "POST", "path": "/api/sources/obsidian/moc/proposals"},
    {"method": "POST", "path": "/api/sources/obsidian/moc/{proposal_id}/apply"},
    {"method": "POST", "path": "/api/sources/memory-reviews"},
    {"method": "POST", "path": "/api/sources/memory-candidates/from-audit"},
    {"method": "POST", "path": "/api/sources/read"},
    {"method": "POST", "path": "/api/eidolia/context/read"},
    {"method": "POST", "path": "/api/eidolia/memory-reviews"},
    {"method": "POST", "path": "/api/eidolia/project-traces/import"},
    {"method": "GET", "path": "/api/memory/cards"},
    {"method": "GET", "path": "/api/memory/cards/{memory_id}"},
    {"method": "GET", "path": "/api/memory/briefing"},
    {"method": "GET", "path": "/api/memory/review-queue"},
    {"method": "GET", "path": "/api/memory/candidate-dedup"},
    {"method": "GET", "path": "/api/memory/health"},
    {"method": "GET", "path": "/api/memory/use-traces"},
    {"method": "GET", "path": "/api/memory/{memory_id}/use-trace"},
    {"method": "GET", "path": "/api/memory/{memory_id}/why-used"},
    {"method": "GET", "path": "/api/memory/{memory_id}/timeline"},
    {"method": "GET", "path": "/api/trace/query"},
    {"method": "POST", "path": "/api/memory/search"},
    {"method": "POST", "path": "/api/memory/conversation-change"},
    {"method": "POST", "path": "/api/memory/conversation-candidates"},
    {"method": "GET", "path": "/api/workflows/{run_id}/memory-attribution"},
    {"method": "GET", "path": "/api/workflows/{run_id}/memory-suggestions"},
    {"method": "POST", "path": "/api/reviews/batch-decision"},
    {"method": "POST", "path": "/api/reviews/merge-candidates"},
    {"method": "POST", "path": "/api/kb/ingest"},
)


@dataclass(slots=True)
class ProductApiState:
    service: WorkflowService
    kb_gateway_factory: KbGatewayFactory
    static_dir: Path


def build_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    service: WorkflowService | None = None,
    kb_gateway_factory: KbGatewayFactory = build_kb_gateway_from_env,
    static_dir: str | Path | None = None,
) -> ThreadingHTTPServer:
    resolved_service = service or build_service_from_env()
    # Build once at startup so missing KB provider configuration fails before serving.
    kb_gateway_factory()
    state = ProductApiState(
        service=resolved_service,
        kb_gateway_factory=kb_gateway_factory,
        static_dir=Path(static_dir) if static_dir else Path(__file__).with_name("web"),
    )
    server = ThreadingHTTPServer((host, port), _handler_class(state))
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    env_parser = preload_env_file(argv)
    parser = argparse.ArgumentParser(
        description="Run the PSKA-Essential Product API and frontend.",
        parents=[env_parser],
    )
    parser.add_argument("--host", default=os.getenv("PSKA_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PSKA_API_PORT", "8765")))
    args = parser.parse_args(argv)

    server = build_server(host=args.host, port=args.port)
    print(f"PSKA Product API listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _handler_class(state: ProductApiState):
    class ProductApiHandler(BaseHTTPRequestHandler):
        server_version = "PSKAProductAPI/0.1"

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            if os.getenv("PSKA_API_LOG_REQUESTS"):
                super().log_message(format, *args)

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            try:
                if path.startswith("/api/"):
                    self._route_api(method, path, query)
                else:
                    self._serve_static(path)
            except ApiError as exc:
                self._send_json({"ok": False, "error": {"message": exc.message}}, exc.status)
            except (KeyError, ValueError, WorkflowError) as exc:
                self._send_json({"ok": False, "error": {"message": str(exc)}}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001 - product API must turn backend failures into explicit errors.
                self._send_json(
                    {"ok": False, "error": {"message": str(exc), "type": exc.__class__.__name__}},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def _route_api(self, method: str, path: str, query: dict[str, str]) -> None:
            if method == "GET" and path == "/api/health":
                self._send_json(
                    {
                        "ok": True,
                        "service": "pska-essential",
                        "product_api": "0.1",
                        "providers": {
                            "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", ""),
                            "kb": os.getenv("PSKA_KB_PROVIDER", ""),
                            "memory": os.getenv("PSKA_MEMORY_PROVIDER", ""),
                            "dev_fake": _env_enabled("PSKA_DEV_FAKE"),
                        },
                        "workspace": build_runtime_workspace_context().to_dict(),
                        "governance": build_workspace_policy_from_env().to_dict(),
                        "capabilities": product_capabilities(memory_adapter=state.service.memory),
                        "product_api_contract": _product_api_contract(),
                    }
                )
                return

            if method == "GET" and path == "/api/capabilities":
                self._send_json(
                    {
                        "ok": True,
                        "capabilities": product_capabilities(memory_adapter=state.service.memory),
                        "product_api_contract": _product_api_contract(),
                    }
                )
                return

            if method == "GET" and path == "/api/migration/manifest":
                self._send_json(
                    {
                        "ok": True,
                        "migration_manifest": build_migration_manifest(
                            state.service,
                            limit=_int_param(query.get("limit"), 200),
                        ),
                    }
                )
                return

            if method == "GET" and path == "/api/provider/jobs":
                self._send_json(
                    {
                        "ok": True,
                        "provider_jobs": build_provider_job_status(
                            state.service,
                            state.kb_gateway_factory(),
                            dataset_page_size=_int_param(query.get("dataset_page_size"), 50),
                            digest_limit=_int_param(query.get("digest_limit"), 50),
                            audit_limit=_int_param(query.get("audit_limit"), 50),
                            include_ready=_bool_value(query.get("include_ready"), True),
                        ),
                    }
                )
                return

            if method == "GET" and path == "/api/policy":
                self._send_json({"ok": True, "governance": build_workspace_policy_from_env().to_dict()})
                return

            if method == "GET" and path == "/api/runtime/diagnostics":
                diagnostics = build_runtime_diagnostics(
                    service=state.service,
                    kb_gateway_factory=state.kb_gateway_factory,
                )
                self._send_json({"ok": True, "diagnostics": diagnostics})
                return

            if method == "GET" and path == "/api/workspace/status":
                status = build_workspace_status(
                    service=state.service,
                    gateway=state.kb_gateway_factory(),
                    dataset_page_size=_int_param(query.get("dataset_page_size"), 30),
                    review_limit=_int_param(query.get("review_limit"), 50),
                    workflow_limit=_int_param(query.get("workflow_limit"), 50),
                )
                self._send_json({"ok": True, "workspace_status": status})
                return

            if method == "POST" and path == "/api/runtime/retrieval-probe":
                payload = self._read_json()
                probe = run_retrieval_probe(
                    state.service,
                    state.kb_gateway_factory(),
                    question=str(payload.get("question") or "PSKA retrieval probe"),
                    dataset_ids=[str(item) for item in payload.get("dataset_ids") or []],
                    dataset_names=[str(item) for item in payload.get("dataset_names") or []],
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                    limit=int(payload.get("limit") or 1),
                    use_kg=bool(payload.get("use_kg", False)),
                )
                add_retrieval_probe_audit(state.service.store, probe)
                self._send_json({"ok": True, "probe": probe})
                return

            if method == "POST" and path == "/api/runtime/component-check":
                payload = self._read_json()
                result = run_component_check(
                    state.service,
                    state.kb_gateway_factory(),
                    dataset_ids=[str(item) for item in payload.get("dataset_ids") or []],
                    dataset_names=[str(item) for item in payload.get("dataset_names") or []],
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                    question=str(payload.get("question") or "PSKA component check"),
                    memory_query=str(payload.get("memory_query") or "PSKA component memory probe"),
                    limit=int(payload.get("limit") or 3),
                    retrieval_limit=int(payload.get("retrieval_limit") or 1),
                    proposal_kind=str(payload.get("proposal_kind") or "writing_brief"),
                    use_kg=bool(payload.get("use_kg", False)),
                    export_format=str(payload.get("export_format") or "json"),
                    source_inspection_limit=int(payload.get("source_inspection_limit") or 1),
                    require_memory=bool(payload.get("require_memory", True)),
                    run_closed_loop=bool(payload.get("run_closed_loop", True)),
                )
                self._send_json({"ok": True, "component_check": result})
                return

            if method == "POST" and path == "/api/runtime/eval":
                payload = self._read_json()
                result = run_eval(
                    str(payload.get("suite") or "product_acceptance"),
                    state.service,
                    gateway_factory=state.kb_gateway_factory,
                )
                self._send_json({"ok": True, "eval": result})
                return

            if method == "POST" and path == "/api/runtime/memory-probe":
                payload = self._read_json()
                probe = run_memory_probe(
                    state.service,
                    query=str(payload.get("query") or "PSKA memory probe"),
                    scope=dict(payload.get("scope") or {}),
                    limit=int(payload.get("limit") or 1),
                    require_live=bool(payload.get("require_live", True)),
                )
                add_memory_probe_audit(state.service.store, probe)
                self._send_json({"ok": True, "probe": probe})
                return

            if method == "POST" and path == "/api/runtime/closed-loop-probe":
                payload = self._read_json()
                probe = run_live_closed_loop_probe(
                    state.service,
                    state.kb_gateway_factory(),
                    question=str(payload.get("question") or "PSKA live closed-loop probe"),
                    dataset_ids=[str(item) for item in payload.get("dataset_ids") or []],
                    dataset_names=[str(item) for item in payload.get("dataset_names") or []],
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                    limit=int(payload.get("limit") or 3),
                    proposal_kind=str(payload.get("proposal_kind") or "writing_brief"),
                    use_kg=bool(payload.get("use_kg", False)),
                    export_format=str(payload.get("export_format") or "json"),
                    source_inspection_limit=int(payload.get("source_inspection_limit") or 1),
                )
                add_live_closed_loop_probe_audit(state.service.store, probe)
                self._send_json({"ok": True, "probe": probe})
                return

            if method == "GET" and path == "/api/kb/datasets":
                gateway = state.kb_gateway_factory()
                self._send_json(
                    {
                        "ok": True,
                        "datasets": gateway.list_datasets(
                            name=query.get("name") or None,
                            page_size=_int_param(query.get("page_size"), 30),
                        ),
                    }
                )
                return

            if method == "POST" and path == "/api/kb/datasets":
                payload = self._read_json()
                gateway = state.kb_gateway_factory()
                dataset = gateway.create_dataset(
                    name=_required_str(payload, "name"),
                    description=str(payload.get("description") or ""),
                    chunk_method=str(payload.get("chunk_method") or "naive"),
                    embedding_model=str(payload.get("embedding_model") or ""),
                )
                add_kb_dataset_create_audit(state.service.store, dataset)
                self._send_json(
                    {"ok": True, "dataset": dataset},
                    HTTPStatus.CREATED,
                )
                return

            if method == "DELETE" and path == "/api/kb/datasets":
                payload = self._read_json()
                gateway = state.kb_gateway_factory()
                result = gateway.delete_datasets(
                    dataset_ids=[str(item) for item in payload.get("dataset_ids") or []],
                    dataset_names=_optional_str_list(payload, "dataset_names"),
                    delete_all=bool(payload.get("delete_all", False)),
                )
                add_kb_dataset_delete_audit(state.service.store, result)
                self._send_json({"ok": True, "delete": result})
                return

            if method == "POST" and path == "/api/kb/ingest":
                self._handle_ingest()
                return

            if method == "POST" and path == "/api/ingest-loop":
                self._handle_ingest_loop()
                return

            if method == "POST" and path == "/api/kb/readiness":
                payload = self._read_json()
                status_payload = _kb_status_payload(
                    state.kb_gateway_factory(),
                    dataset_ids=_required_list(payload, "dataset_ids"),
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                )
                self._send_json({"ok": True, **status_payload})
                return

            if method == "POST" and path == "/api/kb/ingestion-status":
                payload = self._read_json()
                status_payload = _kb_status_payload(
                    state.kb_gateway_factory(),
                    dataset_ids=_required_list(payload, "dataset_ids"),
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                )
                self._send_json({"ok": True, **status_payload})
                return

            dataset_ingestion_status = _match(path, "/api/kb/datasets/", "/ingestion-status")
            if method == "GET" and dataset_ingestion_status:
                document_ids = _csv_values(query.get("document_ids") or query.get("document_id") or "")
                status_payload = _kb_status_payload(
                    state.kb_gateway_factory(),
                    dataset_ids=[dataset_ingestion_status],
                    document_ids=document_ids,
                )
                self._send_json({"ok": True, **status_payload})
                return

            dataset_readiness = _match(path, "/api/kb/datasets/", "/readiness")
            if method == "GET" and dataset_readiness:
                document_ids = _csv_values(query.get("document_ids") or query.get("document_id") or "")
                status_payload = _kb_status_payload(
                    state.kb_gateway_factory(),
                    dataset_ids=[dataset_readiness],
                    document_ids=document_ids,
                )
                self._send_json({"ok": True, **status_payload})
                return

            dataset_delete = _match(path, "/api/kb/datasets/", "")
            if method == "DELETE" and dataset_delete and "/" not in dataset_delete:
                gateway = state.kb_gateway_factory()
                result = gateway.delete_datasets(dataset_ids=[dataset_delete])
                add_kb_dataset_delete_audit(state.service.store, result)
                self._send_json({"ok": True, "delete": result})
                return

            dataset_documents = _match(path, "/api/kb/datasets/", "/documents")
            if method == "GET" and dataset_documents:
                dataset_id = dataset_documents
                gateway = state.kb_gateway_factory()
                self._send_json(
                    {
                        "ok": True,
                        "documents": gateway.list_documents(
                            dataset_id=dataset_id,
                            document_id=query.get("document_id") or None,
                            name=query.get("name") or None,
                            page_size=_int_param(query.get("page_size"), 30),
                        ),
                    }
                )
                return

            dataset_parse = _match(path, "/api/kb/datasets/", "/parse")
            if method == "POST" and dataset_parse:
                payload = self._read_json()
                gateway = state.kb_gateway_factory()
                document_ids = _required_list(payload, "document_ids")
                parse_result = gateway.parse_documents(
                    dataset_id=dataset_parse,
                    document_ids=document_ids,
                    wait=bool(payload.get("wait", False)),
                    timeout_seconds=float(payload.get("timeout_seconds") or 300.0),
                )
                add_kb_parse_audit(state.service.store, parse_result)
                self._send_json(
                    {
                        "ok": True,
                        "parse": parse_result,
                        **_kb_status_payload(gateway, dataset_ids=[dataset_parse], document_ids=document_ids),
                    }
                )
                return

            document_graph = _match_document_graph(path)
            if method == "GET" and document_graph:
                dataset_id, document_id = document_graph
                graph = state.kb_gateway_factory().document_graph(dataset_id=dataset_id, document_id=document_id)
                add_kb_graph_read_audit(state.service.store, graph, dataset_id=dataset_id, document_id=document_id)
                self._send_json({"ok": True, "graph": graph})
                return

            if method == "POST" and path == "/api/ask":
                payload = self._read_json()
                question = _required_str(payload, "question")
                dataset_ids = _required_list(payload, "dataset_ids")
                document_ids = [str(item) for item in payload.get("document_ids") or []]
                proposal_kind = str(payload.get("proposal_kind") or "writing_brief")
                create_review = payload.get("create_review") if "create_review" in payload else None
                use_kg = bool(payload.get("use_kg", False))
                retrieval_queries = _optional_str_list(payload, "retrieval_queries")
                result = run_agentic_question_with_readiness(
                    state.service,
                    state.kb_gateway_factory(),
                    question=question,
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                    limit=int(payload.get("limit") or 5),
                    proposal_kind=proposal_kind,
                    create_review=create_review,
                    use_kg=use_kg,
                    max_iterations=int(payload.get("max_iterations") or 2),
                    min_context_packets=int(payload.get("min_context_packets") or 1),
                    retrieval_queries=retrieval_queries,
                    source_inspection_limit=(
                        int(payload["source_inspection_limit"]) if "source_inspection_limit" in payload else 3
                    ),
                    model_context_tokens=_optional_int(payload, "model_context_tokens"),
                    model_profile=str(payload.get("model_profile") or ""),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/turn-context":
                payload = self._read_json()
                result = _assemble_turn_context(state.service, payload)
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/digest":
                payload = self._read_json()
                dataset_ids = _required_list(payload, "dataset_ids")
                document_ids = [str(item) for item in payload.get("document_ids") or []]
                retrieval_queries = _optional_str_list(payload, "retrieval_queries")
                result = run_digest_scope(
                    state.service,
                    state.kb_gateway_factory(),
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                    question=str(
                        payload.get("question")
                        or "Digest the selected ready knowledge into concise candidate knowledge."
                    ),
                    limit=int(payload.get("limit") or 5),
                    use_kg=bool(payload.get("use_kg", False)),
                    max_iterations=int(payload.get("max_iterations") or 2),
                    min_context_packets=int(payload.get("min_context_packets") or 1),
                    retrieval_queries=retrieval_queries,
                    source_inspection_limit=(
                        int(payload["source_inspection_limit"]) if "source_inspection_limit" in payload else 3
                    ),
                    model_context_tokens=_optional_int(payload, "model_context_tokens"),
                    model_profile=str(payload.get("model_profile") or ""),
                    create_memory_review=_bool_value(payload.get("create_memory_review"), False),
                    memory_intent=str(payload.get("memory_intent") or ""),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/digest-jobs":
                payload = self._read_json()
                dataset_ids = _required_list(payload, "dataset_ids")
                document_ids = [str(item) for item in payload.get("document_ids") or []]
                retrieval_queries = _optional_str_list(payload, "retrieval_queries")
                result = enqueue_digest_job(
                    state.service,
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                    question=str(
                        payload.get("question")
                        or "Digest the selected ready knowledge into concise candidate knowledge."
                    ),
                    priority=int(payload.get("priority") or 0),
                    limit=int(payload.get("limit") or 5),
                    use_kg=bool(payload.get("use_kg", False)),
                    max_iterations=int(payload.get("max_iterations") or 2),
                    min_context_packets=int(payload.get("min_context_packets") or 1),
                    retrieval_queries=retrieval_queries,
                    source_inspection_limit=(
                        int(payload["source_inspection_limit"]) if "source_inspection_limit" in payload else 3
                    ),
                    create_memory_review=_bool_value(payload.get("create_memory_review"), False),
                    memory_intent=str(payload.get("memory_intent") or ""),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/digest-jobs":
                status = str(query.get("status") or "")
                limit = _int_param(query.get("limit"), 50)
                self._send_json(
                    {
                        "ok": True,
                        "digest_jobs": list_digest_jobs(state.service, status=status or None, limit=limit),
                    }
                )
                return

            if method == "POST" and path == "/api/digest-jobs/run-next":
                result = run_digest_job(state.service, state.kb_gateway_factory())
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/sources/audit-jobs":
                payload = self._read_json()
                result = enqueue_source_audit_job(
                    state.service,
                    scope=_optional_dict(payload, "scope"),
                    label=str(payload.get("label") or ""),
                    priority=int(payload.get("priority") or 0),
                    limit=int(payload.get("limit") or 20),
                    cadence=str(payload.get("cadence") or "manual"),
                    due_at=str(payload.get("due_at") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/sources/audit-schedules":
                payload = self._read_json()
                result = schedule_source_audit_job(
                    state.service,
                    scope=_optional_dict(payload, "scope"),
                    label=str(payload.get("label") or ""),
                    priority=int(payload.get("priority") or 0),
                    limit=int(payload.get("limit") or 20),
                    cadence=str(payload.get("cadence") or "daily"),
                    due_at=str(payload.get("due_at") or ""),
                    now=str(payload.get("now") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "GET" and path == "/api/sources/audit-jobs":
                status = str(query.get("status") or "")
                limit = _int_param(query.get("limit"), 50)
                self._send_json(
                    {
                        "ok": True,
                        "source_audit_jobs": list_source_audit_jobs(
                            state.service,
                            status=status or None,
                            limit=limit,
                        ),
                    }
                )
                return

            if method == "POST" and path == "/api/sources/audit-jobs/tick":
                payload = self._read_json()
                result = activate_due_source_audit_jobs(
                    state.service,
                    now=str(payload.get("now") or ""),
                    limit=int(payload.get("limit") or 20),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/sources/audit-jobs/run-next":
                result = run_source_audit_job(state.service)
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/sources/extraction-jobs":
                payload = self._read_json()
                result = enqueue_source_extraction_job(
                    state.service,
                    root_id=str(payload.get("root_id") or ""),
                    label=str(payload.get("label") or ""),
                    priority=int(payload.get("priority") or 0),
                    max_files=int(payload.get("max_files") or 1000),
                    max_bytes=int(payload.get("max_bytes") or 1_000_000),
                    extractor=str(payload.get("extractor") or "auto"),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "GET" and path == "/api/sources/extraction-jobs":
                status = str(query.get("status") or "")
                limit = _int_param(query.get("limit"), 50)
                self._send_json(
                    {
                        "ok": True,
                        "source_extraction_jobs": list_source_extraction_jobs(
                            state.service,
                            status=status or None,
                            limit=limit,
                        ),
                    }
                )
                return

            if method == "POST" and path == "/api/sources/extraction-jobs/run-next":
                result = run_source_extraction_job(state.service)
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/sources/watch-once":
                payload = self._read_json()
                result = watch_source_once(
                    state.service,
                    root_id=_required_str(payload, "root_id"),
                    duration_seconds=_optional_float(payload, "duration_seconds", 5.0),
                    quiet_seconds=_optional_float(payload, "quiet_seconds", 0.25),
                    max_events=int(payload.get("max_events") or 100),
                    recursive=_bool_value(payload.get("recursive"), True),
                    enqueue_extraction=_bool_value(payload.get("enqueue_extraction"), True),
                    enqueue_audit=_bool_value(payload.get("enqueue_audit"), False),
                    label=str(payload.get("label") or ""),
                    priority=int(payload.get("priority") or 0),
                    extractor=str(payload.get("extractor") or "auto"),
                    max_files=int(payload.get("max_files") or 1000),
                    max_bytes=int(payload.get("max_bytes") or 1_000_000),
                    audit_limit=int(payload.get("audit_limit") or 20),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/jarvis/briefing":
                payload = self._read_json()
                briefing = build_jarvis_briefing(
                    service=state.service,
                    gateway=state.kb_gateway_factory(),
                    scope=_optional_dict(payload, "scope"),
                    source_scope=_optional_dict(payload, "source_scope"),
                    audit_limit=int(payload.get("audit_limit") or 20),
                    dataset_page_size=int(payload.get("dataset_page_size") or 30),
                    review_limit=int(payload.get("review_limit") or 50),
                    workflow_limit=int(payload.get("workflow_limit") or 50),
                )
                self._send_json({"ok": True, "briefing": briefing})
                return

            digest_job_run = _match(path, "/api/digest-jobs/", "/run")
            if method == "POST" and digest_job_run:
                result = run_digest_job(
                    state.service,
                    state.kb_gateway_factory(),
                    run_id=digest_job_run,
                )
                self._send_json({"ok": True, **result})
                return

            source_audit_job_run = _match(path, "/api/sources/audit-jobs/", "/run")
            if method == "POST" and source_audit_job_run:
                result = run_source_audit_job(state.service, run_id=source_audit_job_run)
                self._send_json({"ok": True, **result})
                return

            source_extraction_job_run = _match(path, "/api/sources/extraction-jobs/", "/run")
            if method == "POST" and source_extraction_job_run:
                result = run_source_extraction_job(state.service, run_id=source_extraction_job_run)
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/turn-context":
                payload = self._read_json()
                result = _assemble_turn_context(state.service, payload)
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/workflows":
                limit = _int_param(query.get("limit"), 50)
                workflows = state.service.store.list_workflows(limit=limit)
                self._send_json({"ok": True, "workflows": to_jsonable(workflows)})
                return

            if method == "GET" and path == "/api/workflows/resumable-asks":
                limit = _int_param(query.get("limit"), 50)
                resumable = list_resumable_agentic_questions(
                    state.service,
                    state.kb_gateway_factory(),
                    limit=limit,
                )
                self._send_json({"ok": True, "resumable_asks": resumable})
                return

            workflow_id = _match(path, "/api/workflows/", "")
            if method == "GET" and workflow_id and "/" not in workflow_id:
                workflow = state.service.state(workflow_id)
                self._send_json(
                    {
                        "ok": True,
                        "workflow": to_jsonable(workflow),
                        "artifact": state.service.workflow_artifact(workflow_id),
                    }
                )
                return

            workflow_resume = _match(path, "/api/workflows/", "/resume-ask")
            if method == "POST" and workflow_resume:
                result = resume_agentic_question(
                    state.service,
                    state.kb_gateway_factory(),
                    run_id=workflow_resume,
                )
                self._send_json({"ok": True, **result})
                return

            workflow_ingest_resume = _match(path, "/api/workflows/", "/resume-ingest-loop")
            if method == "POST" and workflow_ingest_resume:
                payload = self._read_json()
                result = resume_ingest_loop(
                    state.service,
                    state.kb_gateway_factory(),
                    run_id=workflow_ingest_resume,
                    export_format=str(payload.get("export_format") or ""),
                )
                self._send_json({"ok": True, "ingest_loop": result})
                return

            workflow_memory_review = _match(path, "/api/workflows/", "/memory-review")
            if method == "POST" and workflow_memory_review:
                payload = self._read_json()
                result = state.service.memory_review_from_workflow(
                    workflow_memory_review,
                    intent=str(payload.get("intent") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            workflow_memory_attribution = _match(path, "/api/workflows/", "/memory-attribution")
            if method == "GET" and workflow_memory_attribution:
                artifact = state.service.workflow_artifact(workflow_memory_attribution)
                self._send_json({"ok": True, "memory_attribution": artifact["memory_attribution"]})
                return

            workflow_memory_suggestions = _match(path, "/api/workflows/", "/memory-suggestions")
            if method == "GET" and workflow_memory_suggestions:
                artifact = state.service.workflow_artifact(workflow_memory_suggestions)
                self._send_json({"ok": True, "memory_suggestions": artifact["memory_suggestions"]})
                return

            export_id = _match(path, "/api/workflows/", "/export")
            if method == "GET" and export_id:
                exported = state.service.export_brief(export_id, query.get("format") or "markdown")
                self._send_json({"ok": True, "export": exported})
                return

            if method == "POST" and path == "/api/sources/read":
                payload = self._read_json()
                source = state.service.source_read(SourceRef.from_dict(payload.get("source_ref") or payload))
                self._send_json({"ok": True, "source": to_jsonable(source)})
                return

            if method == "GET" and path == "/api/sources/roots":
                self._send_json({"ok": True, "roots": state.service.source_root_list()})
                return

            if method == "POST" and path == "/api/sources/roots":
                payload = self._read_json()
                root = state.service.source_root_register(
                    _required_str(payload, "path"),
                    kind=str(payload.get("kind") or "local_folder"),
                    permission_mode=str(payload.get("permission_mode") or "read_only"),
                    label=str(payload.get("label") or "") or None,
                )
                self._send_json({"ok": True, "root": root}, HTTPStatus.CREATED)
                return

            source_scan_root = _match(path, "/api/sources/roots/", "/scan")
            if method == "POST" and source_scan_root:
                payload = self._read_json()
                result = state.service.source_scan(
                    source_scan_root,
                    max_files=int(payload.get("max_files") or 1000),
                    max_bytes=int(payload.get("max_bytes") or 1_000_000),
                    extractor=str(payload.get("extractor") or "auto"),
                )
                self._send_json({"ok": True, "scan": result})
                return

            if method == "POST" and path == "/api/sources/search":
                payload = self._read_json()
                packets = state.service.source_search(
                    _required_str(payload, "query"),
                    scope=_optional_dict(payload, "scope"),
                    limit=int(payload.get("limit") or 10),
                    filters=_optional_dict(payload, "filters"),
                )
                self._send_json(
                    {
                        "ok": True,
                        "context_packets": to_jsonable(packets),
                        "count": len(packets),
                    }
                )
                return

            if method == "POST" and path == "/api/sources/neighbors":
                payload = self._read_json()
                neighbors = state.service.source_neighbors(
                    SourceRef.from_dict(payload.get("source_ref") or payload.get("target_ref") or {}),
                    strategy=str(payload.get("strategy") or "auto"),
                    limit=int(payload.get("limit") or 10),
                )
                self._send_json(
                    {
                        "ok": True,
                        "neighbors": to_jsonable(neighbors),
                        "count": len(neighbors),
                    }
                )
                return

            if method == "POST" and path == "/api/sources/duplicates":
                payload = self._read_json()
                report = state.service.duplicate_report(
                    _optional_dict(payload, "scope"),
                    mode=str(payload.get("mode") or "exact_hash"),
                    limit=int(payload.get("limit") or 50),
                )
                self._send_json({"ok": True, "duplicate_report": to_jsonable(report)})
                return

            if method == "POST" and path == "/api/sources/duplicate-review":
                payload = self._read_json()
                review = state.service.duplicate_review_list(
                    _optional_dict(payload, "scope"),
                    status=str(payload.get("status") or ""),
                    limit=int(payload.get("limit") or 50),
                )
                self._send_json({"ok": True, "duplicate_review": to_jsonable(review)})
                return

            duplicate_group_mark_id = _match(path, "/api/sources/duplicate-groups/", "/mark")
            if method == "POST" and duplicate_group_mark_id:
                payload = self._read_json()
                result = state.service.duplicate_group_mark(
                    duplicate_group_mark_id,
                    status=_required_str(payload, "status"),
                    note=str(payload.get("note") or payload.get("review_note") or ""),
                )
                self._send_json({"ok": True, "duplicate_group_review": to_jsonable(result)})
                return

            if method == "POST" and path == "/api/sources/audits/run":
                payload = self._read_json()
                audit = state.service.source_audit_run(
                    scope=_optional_dict(payload, "scope"),
                    limit=int(payload.get("limit") or 20),
                )
                self._send_json({"ok": True, "audit": to_jsonable(audit)})
                return

            if method == "POST" and path == "/api/sources/saved-searches":
                payload = self._read_json()
                saved = state.service.saved_search_create(
                    _required_str(payload, "label"),
                    _required_str(payload, "query"),
                    scope=_optional_dict(payload, "scope"),
                    filters=_optional_dict(payload, "filters"),
                    sort=str(payload.get("sort") or "relevance"),
                )
                self._send_json({"ok": True, "saved_search": saved}, HTTPStatus.CREATED)
                return

            if method == "GET" and path == "/api/sources/collections":
                collections = state.service.source_collection_list()
                self._send_json({"ok": True, "collections": to_jsonable(collections), "count": len(collections)})
                return

            if method == "POST" and path == "/api/sources/collections":
                payload = self._read_json()
                source_refs = payload.get("source_refs") or []
                if not isinstance(source_refs, list):
                    raise ApiError("source_refs must be a list", HTTPStatus.BAD_REQUEST)
                collection = state.service.source_collection_create(
                    _required_str(payload, "label"),
                    description=str(payload.get("description") or ""),
                    selector=_optional_dict(payload, "selector"),
                    source_refs=source_refs,
                )
                self._send_json({"ok": True, "collection": to_jsonable(collection)}, HTTPStatus.CREATED)
                return

            collection_resolve_id = _match(path, "/api/sources/collections/", "/resolve")
            if method == "POST" and collection_resolve_id:
                payload = self._read_json()
                resolved = state.service.source_collection_resolve(
                    collection_resolve_id,
                    limit=int(payload.get("limit") or 10),
                )
                self._send_json({"ok": True, "resolved": to_jsonable(resolved)})
                return

            if method == "POST" and path == "/api/sources/tags/proposals":
                payload = self._read_json()
                proposal = state.service.source_tag_propose(
                    SourceRef.from_dict(payload.get("target_ref") or payload.get("source_ref") or {}),
                    _required_str(payload, "tag"),
                    reason=str(payload.get("reason") or ""),
                    write_target=str(payload.get("write_target") or "sidecar"),
                )
                self._send_json({"ok": True, "proposal": proposal}, HTTPStatus.CREATED)
                return

            tag_apply_id = _match(path, "/api/sources/tags/", "/apply")
            if method == "POST" and tag_apply_id:
                applied = state.service.source_tag_apply(tag_apply_id)
                self._send_json({"ok": True, "applied": applied})
                return

            if method == "POST" and path == "/api/sources/comments/proposals":
                payload = self._read_json()
                proposal = state.service.source_comment_propose(
                    SourceRef.from_dict(payload.get("target_ref") or payload.get("source_ref") or {}),
                    _required_str(payload, "body"),
                    reason=str(payload.get("reason") or ""),
                    write_target=str(payload.get("write_target") or "sidecar"),
                )
                self._send_json({"ok": True, "proposal": proposal}, HTTPStatus.CREATED)
                return

            comment_apply_id = _match(path, "/api/sources/comments/", "/apply")
            if method == "POST" and comment_apply_id:
                applied = state.service.source_comment_apply(comment_apply_id)
                self._send_json({"ok": True, "applied": applied})
                return

            if method == "POST" and path == "/api/sources/obsidian/moc/proposals":
                payload = self._read_json()
                source_refs = payload.get("source_refs") or []
                if not isinstance(source_refs, list):
                    raise ApiError("source_refs must be a list", HTTPStatus.BAD_REQUEST)
                proposal = state.service.source_obsidian_moc_propose(
                    _required_str(payload, "root_id"),
                    source_refs,
                    moc_path=str(payload.get("moc_path") or "PSKA MOC.md"),
                    title=str(payload.get("title") or ""),
                    reason=str(payload.get("reason") or ""),
                    group_by=str(payload.get("group_by") or "none"),
                )
                self._send_json({"ok": True, "proposal": proposal}, HTTPStatus.CREATED)
                return

            moc_apply_id = _match(path, "/api/sources/obsidian/moc/", "/apply")
            if method == "POST" and moc_apply_id:
                applied = state.service.source_obsidian_moc_apply(moc_apply_id)
                self._send_json({"ok": True, "applied": applied})
                return

            if method == "POST" and path == "/api/sources/memory-reviews":
                payload = self._read_json()
                source_refs = payload.get("source_refs") or []
                if not isinstance(source_refs, list):
                    raise ApiError("source_refs must be a list", HTTPStatus.BAD_REQUEST)
                created = state.service.source_memory_review_create(
                    source_refs,
                    text=_required_str(payload, "text"),
                    memory_type=str(payload.get("memory_type") or "source_route"),
                    behavior_delta=_required_str(payload, "behavior_delta"),
                    memory_scope=str(payload.get("memory_scope") or "workspace"),
                    reason=str(payload.get("reason") or ""),
                    confidence=float(payload.get("confidence") or 0.82),
                    scope=_optional_dict(payload, "scope"),
                )
                self._send_json({"ok": True, **created}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/sources/memory-candidates/from-audit":
                payload = self._read_json()
                result = state.service.source_memory_candidates_from_audit(
                    _optional_dict(payload, "scope"),
                    audit_limit=int(payload.get("audit_limit") or 20),
                    candidate_limit=int(payload.get("candidate_limit") or 5),
                    memory_scope=str(payload.get("memory_scope") or "project"),
                    dedupe_existing=_bool_value(payload.get("dedupe_existing"), True),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/eidolia/context/read":
                payload = self._read_json()
                result = state.service.eidolia_context_read(
                    project_id=_required_str(payload, "project_id"),
                    node_id=_required_str(payload, "node_id"),
                    node_type=str(payload.get("node_type") or "thought"),
                    text=str(payload.get("text") or ""),
                    title=str(payload.get("title") or ""),
                    canvas_path=str(payload.get("canvas_path") or ""),
                    role=str(payload.get("role") or ""),
                    artifact_kind=str(payload.get("artifact_kind") or ""),
                    metadata=_optional_dict(payload, "metadata"),
                )
                self._send_json({"ok": True, "context": result})
                return

            if method == "POST" and path == "/api/eidolia/memory-reviews":
                payload = self._read_json()
                created = state.service.eidolia_memory_review_create(
                    project_id=_required_str(payload, "project_id"),
                    node_id=_required_str(payload, "node_id"),
                    text=_required_str(payload, "text"),
                    behavior_delta=_required_str(payload, "behavior_delta"),
                    node_type=str(payload.get("node_type") or "thought"),
                    title=str(payload.get("title") or ""),
                    canvas_path=str(payload.get("canvas_path") or ""),
                    role=str(payload.get("role") or ""),
                    artifact_kind=str(payload.get("artifact_kind") or ""),
                    memory_type=str(payload.get("memory_type") or "project_state"),
                    memory_scope=str(payload.get("memory_scope") or "project"),
                    reason=str(payload.get("reason") or ""),
                    confidence=float(payload.get("confidence") or 0.82),
                    scope=_optional_dict(payload, "scope"),
                    metadata=_optional_dict(payload, "metadata"),
                )
                self._send_json({"ok": True, **created}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/eidolia/project-traces/import":
                payload = self._read_json()
                result = import_eidolia_project_traces(
                    state.service,
                    project_path=str(payload.get("project_path") or ""),
                    workspace_path=str(payload.get("workspace_path") or ""),
                    trace_paths=_optional_str_list(payload, "trace_paths"),
                    node_limit=int(payload.get("node_limit") or 100),
                    trace_limit=int(payload.get("trace_limit") or 50),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/memory/search":
                payload = self._read_json()
                facts = state.service.memory_search(
                    _required_str(payload, "query"),
                    _optional_dict(payload, "scope"),
                    limit=int(payload.get("limit") or 10),
                    trace_context={
                        "caller": str(payload.get("caller") or "product_api"),
                        "run_id": str(payload.get("run_id") or ""),
                        "message_id": str(payload.get("message_id") or ""),
                        "purpose": str(payload.get("purpose") or "memory_search_api"),
                        "used_as": str(payload.get("used_as") or "candidate_memory"),
                        "usage_stage": str(payload.get("usage_stage") or "retrieval"),
                    },
                )
                capabilities = product_capabilities(memory_adapter=state.service.memory)
                self._send_json(
                    {
                        "ok": True,
                        "memory_facts": to_jsonable(facts),
                        "count": len(facts),
                        "search_view": capabilities["memory"]["search_view"],
                    }
                )
                return

            if method == "GET" and path == "/api/memory/use-traces":
                result = list_memory_use_traces(
                    state.service,
                    memory_id=str(query.get("memory_id") or ""),
                    query=str(query.get("query") or ""),
                    action=str(query.get("action") or ""),
                    limit=_int_param(query.get("limit"), 50),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/memory/cards":
                result = list_memory_cards(
                    state.service,
                    scope=_query_scope(query),
                    limit=_int_param(query.get("limit"), 50),
                    query=str(query.get("query") or ""),
                    status=str(query.get("status") or "active"),
                    memory_type=str(query.get("memory_type") or ""),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/memory/health":
                result = scan_memory_health(
                    state.service,
                    scope=_query_scope(query),
                    issue_type=str(query.get("issue_type") or ""),
                    limit=_int_param(query.get("limit"), 100),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/memory/briefing":
                result = build_memory_briefing(
                    state.service,
                    scope=_query_scope(query),
                    card_limit=_int_param(query.get("card_limit"), 30),
                    health_limit=_int_param(query.get("health_limit"), 20),
                    trace_limit=_int_param(query.get("trace_limit"), 30),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/memory/review-queue":
                result = build_memory_review_queue(
                    state.service,
                    scope=_query_scope(query),
                    review_limit=_int_param(query.get("review_limit"), 50),
                    health_limit=_int_param(query.get("health_limit"), 20),
                    focus_limit=_int_param(query.get("focus_limit"), 20),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/memory/candidate-dedup":
                result = build_memory_candidate_dedup(
                    state.service,
                    scope=_query_scope(query),
                    review_limit=_int_param(query.get("review_limit"), 100),
                    similarity_threshold=float(query.get("similarity_threshold") or 0.82),
                    related_threshold=float(query.get("related_threshold") or 0.72),
                )
                self._send_json({"ok": True, **result})
                return

            memory_use_trace_id = _match(path, "/api/memory/", "/use-trace")
            if method == "GET" and memory_use_trace_id:
                result = list_memory_use_traces(
                    state.service,
                    memory_id=unquote(memory_use_trace_id),
                    query=str(query.get("query") or ""),
                    action=str(query.get("action") or ""),
                    limit=_int_param(query.get("limit"), 50),
                )
                self._send_json({"ok": True, **result})
                return

            memory_why_used_id = _match(path, "/api/memory/", "/why-used")
            if method == "GET" and memory_why_used_id:
                result = explain_memory_why_used(
                    state.service,
                    unquote(memory_why_used_id),
                    scope=_query_scope(query),
                    limit=_int_param(query.get("limit"), 20),
                )
                self._send_json({"ok": True, **result})
                return

            memory_timeline_id = _match(path, "/api/memory/", "/timeline")
            if method == "GET" and memory_timeline_id:
                result = build_memory_timeline(
                    state.service,
                    unquote(memory_timeline_id),
                    scope=_query_scope(query),
                    limit=_int_param(query.get("limit"), 50),
                    include_usage=_bool_param(query.get("include_usage"), True),
                    include_sources=_bool_param(query.get("include_sources"), True),
                )
                self._send_json({"ok": True, **result})
                return

            memory_card_id = _match(path, "/api/memory/cards/", "")
            if method == "GET" and memory_card_id and "/" not in memory_card_id:
                result = get_memory_card(
                    state.service,
                    unquote(memory_card_id),
                    scope=_query_scope(query),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/memory/conversation-change":
                payload = self._read_json()
                source_refs = payload.get("source_refs") or []
                if not isinstance(source_refs, list):
                    raise ApiError("source_refs must be a list", HTTPStatus.BAD_REQUEST)
                result = state.service.memory_change_from_conversation(
                    user_message=_required_str(payload, "user_message"),
                    operation=str(payload.get("operation") or "auto"),
                    text=str(payload.get("text") or ""),
                    memory_fact=payload.get("memory_fact") or payload.get("fact"),
                    source_refs=source_refs,
                    session_id=str(payload.get("session_id") or ""),
                    message_id=str(payload.get("message_id") or ""),
                    reason=str(payload.get("reason") or ""),
                    scope=dict(payload.get("scope") or {}),
                    force_review=_bool_value(payload.get("force_review"), False),
                    confidence=float(payload.get("confidence") or 0.95),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/memory/conversation-candidates":
                payload = self._read_json()
                messages = payload.get("messages") or []
                candidates = payload.get("candidates") or []
                if not isinstance(messages, list):
                    raise ApiError("messages must be a list", HTTPStatus.BAD_REQUEST)
                if not isinstance(candidates, list):
                    raise ApiError("candidates must be a list", HTTPStatus.BAD_REQUEST)
                result = state.service.conversation_memory_candidates_create(
                    messages=messages,
                    candidates=candidates,
                    session_id=str(payload.get("session_id") or ""),
                    scope=_optional_dict(payload, "scope"),
                    dedupe_existing=_bool_value(payload.get("dedupe_existing"), True),
                    candidate_limit=int(payload.get("candidate_limit") or 5),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/memory/delete-review":
                payload = self._read_json()
                result = state.service.memory_delete_review(
                    payload.get("memory_fact") or payload.get("fact") or payload,
                    reason=str(payload.get("reason") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            if method == "POST" and path == "/api/memory/update-review":
                payload = self._read_json()
                result = state.service.memory_update_review(
                    payload.get("memory_fact") or payload.get("fact") or payload,
                    text=_required_str(payload, "text"),
                    reason=str(payload.get("reason") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            memory_lifecycle = _match(path, "/api/memory/", "/lifecycle")
            if method == "GET" and memory_lifecycle:
                lifecycle = state.service.memory_lifecycle(
                    memory_lifecycle,
                    limit=_int_param(query.get("limit"), 50),
                )
                self._send_json({"ok": True, "lifecycle": lifecycle})
                return

            if method == "GET" and path == "/api/reviews":
                status = query.get("status") or None
                limit = _int_param(query.get("limit"), 50)
                self._send_json({"ok": True, "reviews": state.service.store.list_reviews(status=status, limit=limit)})
                return

            if method == "POST" and path == "/api/reviews/batch-decision":
                payload = self._read_json()
                result = state.service.review_decide_batch(
                    _required_list(payload, "review_ids"),
                    _required_str(payload, "decision"),
                    str(payload.get("reason") or ""),
                )
                self._send_json({"ok": True, **result})
                return

            if method == "POST" and path == "/api/reviews/merge-candidates":
                payload = self._read_json()
                result = state.service.review_merge_candidates(
                    _required_list(payload, "review_ids"),
                    memory_candidate=_optional_dict(payload, "memory_candidate"),
                    intent=str(payload.get("intent") or ""),
                    reason=str(payload.get("reason") or ""),
                )
                self._send_json({"ok": True, **result}, HTTPStatus.CREATED)
                return

            review_get = _match(path, "/api/reviews/", "")
            if method == "GET" and review_get and "/" not in review_get:
                self._send_json({"ok": True, "review": state.service.store.get_review_record(review_get)})
                return

            review_decision = _match(path, "/api/reviews/", "/decision")
            if method == "POST" and review_decision:
                payload = self._read_json()
                decision = state.service.review_decide(
                    review_decision,
                    _required_str(payload, "decision"),
                    str(payload.get("reason") or ""),
                )
                self._send_json({"ok": True, "decision": to_jsonable(decision)})
                return

            review_revision = _match(path, "/api/reviews/", "/revision")
            if method == "POST" and review_revision:
                payload = self._read_json()
                revised = state.service.review_revise(
                    review_revision,
                    intent=str(payload.get("intent") or ""),
                    memory_candidate=_optional_dict(payload, "memory_candidate") or None,
                )
                self._send_json({"ok": True, **revised}, HTTPStatus.CREATED)
                return

            review_apply = _match(path, "/api/reviews/", "/apply-memory")
            if method == "POST" and review_apply:
                applied = state.service.memory_apply(review_apply)
                self._send_json({"ok": True, "applied": to_jsonable(applied)})
                return

            if method == "GET" and path == "/api/audit":
                events = state.service.store.list_audit_events(
                    action=query.get("action") or None,
                    limit=_int_param(query.get("limit"), 50),
                    descending=True,
                )
                self._send_json({"ok": True, "events": to_jsonable(events)})
                return

            if method == "GET" and path == "/api/trace/query":
                result = build_trace_query(
                    state.service,
                    target_type=query.get("target_type") or "",
                    target_id=query.get("target_id") or "",
                    review_id=query.get("review_id") or "",
                    proposal_id=query.get("proposal_id") or "",
                    memory_id=query.get("memory_id") or "",
                    source_ref=_query_json_object(query, "source_ref") or None,
                    action=query.get("action") or "",
                    limit=_int_param(query.get("limit"), 50),
                )
                self._send_json({"ok": True, **result})
                return

            raise ApiError(f"route not found: {method} {path}", HTTPStatus.NOT_FOUND)

        def _handle_ingest(self) -> None:
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("multipart/form-data"):
                fields, files = self._read_multipart()
                if not files:
                    raise ApiError("at least one file is required", HTTPStatus.BAD_REQUEST)
                with tempfile.TemporaryDirectory(prefix="pska-upload-") as temp_dir:
                    paths: list[str] = []
                    for file_item in files:
                        safe_name = _safe_filename(file_item["filename"])
                        path = Path(temp_dir) / safe_name
                        path.write_bytes(file_item["content"])
                        paths.append(str(path))
                    gateway = state.kb_gateway_factory()
                    result = gateway.ingest_files(
                        file_paths=paths,
                        dataset_name=fields.get("dataset_name") or None,
                        dataset_id=fields.get("dataset_id") or None,
                        description=fields.get("description") or "",
                        chunk_method=fields.get("chunk_method") or "naive",
                        embedding_model=fields.get("embedding_model") or "",
                        priority=int(fields.get("priority") or 0),
                        parse=_bool_value(fields.get("parse"), True),
                        wait=_bool_value(fields.get("wait"), False),
                        timeout_seconds=float(fields.get("timeout_seconds") or 300.0),
                    )
                add_kb_ingest_audit(state.service.store, result)
                self._send_json(
                    {"ok": True, "ingest": result, **_kb_operation_status_payload(gateway, result)},
                    HTTPStatus.CREATED,
                )
                return

            payload = self._read_json()
            gateway = state.kb_gateway_factory()
            result = gateway.ingest_files(
                file_paths=_required_list(payload, "file_paths"),
                dataset_name=payload.get("dataset_name") or None,
                dataset_id=payload.get("dataset_id") or None,
                description=str(payload.get("description") or ""),
                chunk_method=str(payload.get("chunk_method") or "naive"),
                embedding_model=str(payload.get("embedding_model") or ""),
                priority=int(payload.get("priority") or 0),
                parse=bool(payload.get("parse", True)),
                wait=bool(payload.get("wait", False)),
                timeout_seconds=float(payload.get("timeout_seconds") or 300.0),
            )
            add_kb_ingest_audit(state.service.store, result)
            self._send_json(
                {"ok": True, "ingest": result, **_kb_operation_status_payload(gateway, result)},
                HTTPStatus.CREATED,
            )

        def _handle_ingest_loop(self) -> None:
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("multipart/form-data"):
                fields, files = self._read_multipart()
                if not files:
                    raise ApiError("at least one file is required", HTTPStatus.BAD_REQUEST)
                with tempfile.TemporaryDirectory(prefix="pska-loop-upload-") as temp_dir:
                    paths: list[str] = []
                    for file_item in files:
                        safe_name = _safe_filename(file_item["filename"])
                        path = Path(temp_dir) / safe_name
                        path.write_bytes(file_item["content"])
                        paths.append(str(path))
                    result = run_ingest_loop(
                        state.service,
                        state.kb_gateway_factory(),
                        file_paths=paths,
                        dataset_name=fields.get("dataset_name") or "",
                        dataset_id=fields.get("dataset_id") or "",
                        description=fields.get("description") or "",
                        chunk_method=fields.get("chunk_method") or "naive",
                        embedding_model=fields.get("embedding_model") or "",
                        parse=_bool_value(fields.get("parse"), True),
                        wait_ready=_bool_value(fields.get("wait_ready"), True),
                        timeout_seconds=float(fields.get("timeout_seconds") or 600.0),
                        poll_interval_seconds=float(fields.get("poll_interval_seconds") or 2.0),
                        question=fields.get("question") or "Summarize the uploaded documents with sources.",
                        limit=int(fields.get("limit") or 5),
                        proposal_kind=fields.get("proposal_kind") or "writing_brief",
                        create_review=_optional_bool_field(fields, "create_review"),
                        use_kg=_bool_value(fields.get("use_kg"), False),
                        max_iterations=int(fields.get("max_iterations") or 2),
                        min_context_packets=int(fields.get("min_context_packets") or 1),
                        retrieval_queries=_lines_or_csv_values(fields.get("retrieval_queries") or ""),
                        source_inspection_limit=int(fields.get("source_inspection_limit") or 3),
                        model_context_tokens=_optional_int(fields, "model_context_tokens"),
                        model_profile=fields.get("model_profile") or "",
                        export_format=fields.get("export_format") or "markdown",
                    )
                self._send_json({"ok": True, "ingest_loop": result}, HTTPStatus.CREATED)
                return

            payload = self._read_json()
            result = run_ingest_loop(
                state.service,
                state.kb_gateway_factory(),
                file_paths=_required_list(payload, "file_paths"),
                dataset_name=str(payload.get("dataset_name") or ""),
                dataset_id=str(payload.get("dataset_id") or ""),
                description=str(payload.get("description") or ""),
                chunk_method=str(payload.get("chunk_method") or "naive"),
                embedding_model=str(payload.get("embedding_model") or ""),
                parse=bool(payload.get("parse", True)),
                wait_ready=bool(payload.get("wait_ready", True)),
                timeout_seconds=float(payload.get("timeout_seconds") or 600.0),
                poll_interval_seconds=float(payload.get("poll_interval_seconds") or 2.0),
                question=str(payload.get("question") or "Summarize the uploaded documents with sources."),
                limit=int(payload.get("limit") or 5),
                proposal_kind=str(payload.get("proposal_kind") or "writing_brief"),
                create_review=payload.get("create_review") if "create_review" in payload else None,
                use_kg=bool(payload.get("use_kg", False)),
                max_iterations=int(payload.get("max_iterations") or 2),
                min_context_packets=int(payload.get("min_context_packets") or 1),
                retrieval_queries=_optional_str_list(payload, "retrieval_queries"),
                source_inspection_limit=int(payload.get("source_inspection_limit") or 3),
                model_context_tokens=_optional_int(payload, "model_context_tokens"),
                model_profile=str(payload.get("model_profile") or ""),
                export_format=str(payload.get("export_format") or "markdown"),
            )
            self._send_json({"ok": True, "ingest_loop": result}, HTTPStatus.CREATED)

        def _read_json(self) -> dict[str, Any]:
            raw = self._read_body()
            if not raw:
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ApiError("request body must be valid JSON", HTTPStatus.BAD_REQUEST) from exc
            if not isinstance(payload, dict):
                raise ApiError("request body must be a JSON object", HTTPStatus.BAD_REQUEST)
            return payload

        def _read_multipart(self) -> tuple[dict[str, str], list[dict[str, Any]]]:
            content_type = self.headers.get("Content-Type", "")
            raw = self._read_body()
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
            )
            if not message.is_multipart():
                raise ApiError("request body must be multipart/form-data", HTTPStatus.BAD_REQUEST)
            fields: dict[str, str] = {}
            files: list[dict[str, Any]] = []
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                filename = part.get_filename()
                content = part.get_payload(decode=True) or b""
                if filename:
                    files.append({"field": name, "filename": filename, "content": content})
                else:
                    fields[name] = content.decode(part.get_content_charset() or "utf-8")
            return fields, files

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or "0")
            return self.rfile.read(length) if length else b""

        def _serve_static(self, path: str) -> None:
            if path in {"", "/"}:
                target = state.static_dir / "index.html"
            else:
                relative = Path(unquote(path.lstrip("/")))
                if relative.is_absolute() or ".." in relative.parts:
                    raise ApiError("invalid static path", HTTPStatus.BAD_REQUEST)
                target = state.static_dir / relative
            if not target.is_file():
                raise ApiError("asset not found", HTTPStatus.NOT_FOUND)
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(to_jsonable(payload), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ProductApiHandler


class ApiError(RuntimeError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _match(path: str, prefix: str, suffix: str) -> str | None:
    if not path.startswith(prefix):
        return None
    if suffix and not path.endswith(suffix):
        return None
    value = path[len(prefix) : len(path) - len(suffix) if suffix else len(path)]
    return unquote(value.strip("/")) or None


def _assemble_turn_context(service: WorkflowService, payload: dict[str, Any]) -> dict[str, Any]:
    user_message = (
        str(payload.get("user_message") or payload.get("query") or payload.get("task") or "")
        .strip()
    )
    if not user_message:
        raise ApiError("user_message is required", HTTPStatus.BAD_REQUEST)

    mode = str(payload.get("mode") or "auto").strip().lower() or "auto"
    scope = _turn_context_scope(payload)
    budget = _optional_dict(payload, "budget")
    requirements = _optional_dict(payload, "requirements")
    max_evidence_blocks = _bounded_int(
        budget.get("max_evidence_blocks", payload.get("limit", payload.get("max_evidence_blocks"))),
        default=5,
        minimum=0,
        maximum=20,
        field_name="budget.max_evidence_blocks",
    )
    max_memory_notes = _bounded_int(
        budget.get("max_memory_notes", payload.get("max_memory_notes")),
        default=5,
        minimum=0,
        maximum=20,
        field_name="budget.max_memory_notes",
    )

    warnings: list[dict[str, Any]] = []
    if mode != "memory-only" and max_evidence_blocks > 0:
        run = service.start(
            f"turn context: {user_message[:120]}",
            {
                **scope,
                "turn_context": True,
                "caller": str(payload.get("caller") or ""),
                "workspace": str(payload.get("workspace") or scope.get("workspace") or ""),
                "project_id": str(payload.get("project_id") or scope.get("project_id") or ""),
            },
        )
        packets = service.context_retrieve(run.run_id, user_message, max_evidence_blocks)
    else:
        run = service.start(
            f"turn context: {user_message[:120]}",
            {**scope, "turn_context": True, "evidence_disabled": True},
        )
        packets = []

    memory_facts = []
    if mode != "evidence-only" and max_memory_notes > 0:
        capabilities = product_capabilities(memory_adapter=service.memory)
        search_capability = capabilities["memory"]["operations"].get("search", {})
        if search_capability.get("supported") is False:
            warnings.append(
                {
                    "code": "memory_search_unsupported",
                    "message": "Configured PSKA memory backend does not support memory search.",
                }
            )
        else:
            memory_facts = service.memory_search(
                user_message,
                scope,
                max_memory_notes,
                trace_context={
                    "caller": str(payload.get("caller") or "turn_context"),
                    "run_id": run.run_id,
                    "message_id": str(payload.get("message_id") or ""),
                    "purpose": "turn_context_memory_notes",
                    "used_as": "memory_note",
                    "usage_stage": "turn_context",
                },
            )

    evidence_blocks = [_turn_context_evidence_block(packet) for packet in packets]
    memory_blocks = [_turn_context_memory_block(fact) for fact in memory_facts]
    return {
        "schema": "pska.turn_context_response.v1",
        "run_id": run.run_id,
        "mode": mode,
        "scope": scope,
        "budget": {
            "max_evidence_blocks": max_evidence_blocks,
            "max_memory_notes": max_memory_notes,
        },
        "requirements": requirements,
        "turn_context": {
            "summary": (
                f"Retrieved {len(evidence_blocks)} evidence block(s) and "
                f"{len(memory_blocks)} memory note(s)."
            ),
            "blocks": [*evidence_blocks, *memory_blocks],
            "evidence_blocks": evidence_blocks,
            "memory_notes": memory_blocks,
            "citations": _turn_context_citations(packets, memory_facts),
            "warnings": warnings,
        },
    }


def _turn_context_scope(payload: dict[str, Any]) -> dict[str, Any]:
    scope = _optional_dict(payload, "scope")
    for key in ("dataset_ids", "document_ids", "memory_namespaces"):
        values = _optional_str_list(payload, key)
        if values:
            scope[key] = values
    for key in ("workspace", "project_id", "memory_namespace"):
        value = str(payload.get(key) or "").strip()
        if value:
            scope[key] = value
    return scope


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
    field_name: str,
) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field_name} must be an integer", HTTPStatus.BAD_REQUEST) from None
    if parsed < minimum or parsed > maximum:
        raise ApiError(f"{field_name} must be between {minimum} and {maximum}", HTTPStatus.BAD_REQUEST)
    return parsed


def _turn_context_evidence_block(packet: Any) -> dict[str, Any]:
    return {
        "type": "evidence",
        "context_id": packet.context_id,
        "text": packet.text,
        "title": packet.title or "",
        "score": packet.score,
        "source_ref": to_jsonable(packet.source_ref),
        "metadata": to_jsonable(packet.metadata),
    }


def _turn_context_memory_block(fact: Any) -> dict[str, Any]:
    metadata = dict(getattr(fact, "metadata", {}) or {})
    return {
        "type": "memory",
        "fact_id": fact.fact_id,
        "text": fact.text,
        "confidence": metadata.get("confidence"),
        "valid_at": fact.valid_at or "",
        "source_refs": to_jsonable(fact.source_refs),
        "metadata": to_jsonable(metadata),
    }


def _turn_context_citations(packets: list[Any], memory_facts: list[Any]) -> list[dict[str, Any]]:
    citations = [
        {
            "type": "evidence",
            "source_ref": to_jsonable(packet.source_ref),
            "title": packet.title or packet.source_ref.title or "",
        }
        for packet in packets
    ]
    for fact in memory_facts:
        for source_ref in fact.source_refs:
            citations.append(
                {
                    "type": "memory",
                    "fact_id": fact.fact_id,
                    "source_ref": to_jsonable(source_ref),
                    "title": source_ref.title or "",
                }
            )
    return citations


def _product_api_contract() -> dict[str, Any]:
    return {
        "schema": "pska.product_api_contract.v1",
        "required_routes": [dict(route) for route in PRODUCT_API_REQUIRED_ROUTES],
        "frontend": "hermes_webui_proxy",
    }


def _match_document_graph(path: str) -> tuple[str, str] | None:
    value = _match(path, "/api/kb/datasets/", "/graph")
    if not value:
        return None
    parts = value.split("/")
    if len(parts) != 3 or parts[1] != "documents" or not parts[0] or not parts[2]:
        raise ApiError("document graph route must be /api/kb/datasets/{dataset_id}/documents/{document_id}/graph")
    return parts[0], parts[2]


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ApiError(f"{key} is required", HTTPStatus.BAD_REQUEST)
    return value


def _required_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ApiError(f"{key} must be a non-empty list", HTTPStatus.BAD_REQUEST)
    normalized = [str(item or "").strip() for item in value]
    result = [item for item in normalized if item]
    if not result:
        raise ApiError(f"{key} must be a non-empty list", HTTPStatus.BAD_REQUEST)
    return result


def _optional_str_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        candidates = value
    else:
        raise ApiError(f"{key} must be a list or comma-separated string", HTTPStatus.BAD_REQUEST)
    return [str(item).strip() for item in candidates if str(item).strip()]


def _optional_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ApiError(f"{key} must be an object", HTTPStatus.BAD_REQUEST)
    return dict(value)


def _query_scope(query: dict[str, str]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    for key in (
        "memory_namespace",
        "workspace_id",
        "tenant_id",
        "include_superseded_memory",
        "include_superseded",
    ):
        value = query.get(key)
        if value is None or value == "":
            continue
        if key in {"include_superseded_memory", "include_superseded"}:
            scope[key] = _bool_value(value, False)
        else:
            scope[key] = value
    return scope


def _query_json_object(query: dict[str, str], key: str) -> dict[str, Any]:
    value = query.get(key)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ApiError(f"{key} must be a JSON object", HTTPStatus.BAD_REQUEST) from exc
    if not isinstance(parsed, dict):
        raise ApiError(f"{key} must be a JSON object", HTTPStatus.BAD_REQUEST)
    return parsed


def _int_param(value: str | None, default: int) -> int:
    if not value:
        return default
    return int(value)


def _bool_param(value: str | None, default: bool) -> bool:
    return _bool_value(value, default)


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(payload: dict[str, Any], key: str, default: float) -> float:
    if key not in payload:
        return default
    value = payload.get(key)
    if value is None or value == "":
        return default
    return float(value)


def _bool_value(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_bool_field(fields: dict[str, str], key: str) -> bool | None:
    if key not in fields:
        return None
    return _bool_value(fields.get(key), False)


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _lines_or_csv_values(value: str) -> list[str]:
    if "\n" in value:
        return [item.strip() for item in value.splitlines() if item.strip()]
    return _csv_values(value)


def _kb_status_payload(
    gateway: Any,
    *,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=dataset_ids,
        document_ids=document_ids or [],
    )
    return {"readiness": readiness, "ingestion_status": readiness.get("ingestion_status") or {}}


def _kb_operation_status_payload(gateway: Any, result: dict[str, Any]) -> dict[str, Any]:
    dataset = result.get("dataset") or {}
    dataset_id = str(dataset.get("dataset_id") or "")
    if not dataset_id:
        return {"ingestion_status": {}, "readiness": {}}
    document_ids = [
        str(document.get("document_id") or "")
        for document in result.get("documents") or []
        if document.get("document_id")
    ]
    return _kb_status_payload(gateway, dataset_ids=[dataset_id], document_ids=document_ids)


def _assemble_turn_context(service: WorkflowService, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiError("request body must be a JSON object", HTTPStatus.BAD_REQUEST)
    user_message = _required_str(payload, "user_message")
    mode = str(payload.get("mode") or "auto").strip().lower() or "auto"
    if mode not in {"auto", "project", "evidence-only", "memory-only"}:
        raise ApiError("mode must be auto, project, evidence-only, or memory-only", HTTPStatus.BAD_REQUEST)
    raw_scope = payload.get("scope") or {}
    if not isinstance(raw_scope, dict):
        raise ApiError("scope must be an object", HTTPStatus.BAD_REQUEST)
    raw_budget = payload.get("budget") or {}
    if not isinstance(raw_budget, dict):
        raise ApiError("budget must be an object", HTTPStatus.BAD_REQUEST)

    scope = _turn_context_scope(payload, raw_scope)
    max_evidence_blocks = _bounded_int(
        raw_budget.get("max_evidence_blocks"),
        default=5,
        minimum=0,
        maximum=20,
    )
    max_memory_notes = _bounded_int(
        raw_budget.get("max_memory_notes"),
        default=5,
        minimum=0,
        maximum=20,
    )
    max_tokens = _bounded_int(raw_budget.get("max_tokens"), default=3000, minimum=500, maximum=12000)
    requirements = payload.get("requirements") or {}
    if not isinstance(requirements, dict):
        raise ApiError("requirements must be an object", HTTPStatus.BAD_REQUEST)

    run = service.start(f"turn-context: {user_message[:160]}", scope)
    evidence_blocks: list[dict[str, Any]] = []
    memory_notes: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    if mode != "memory-only" and max_evidence_blocks > 0:
        packets = service.context_retrieve(run.run_id, user_message, max_evidence_blocks)
        evidence_blocks = [_turn_context_evidence_block(packet, index) for index, packet in enumerate(packets, start=1)]

    if mode != "evidence-only" and max_memory_notes > 0:
        try:
            facts = service.memory_search(
                user_message,
                scope,
                max_memory_notes,
                trace_context={
                    "caller": str(payload.get("caller") or "turn_context"),
                    "run_id": run.run_id,
                    "message_id": str(payload.get("message_id") or ""),
                    "purpose": "turn_context_memory_notes",
                    "used_as": "memory_note",
                    "usage_stage": "turn_context",
                },
            )
            memory_notes = [_turn_context_memory_block(fact, index) for index, fact in enumerate(facts, start=1)]
        except Exception as exc:  # noqa: BLE001 - turn context should degrade when optional memory search is unavailable.
            warnings.append({"code": "memory_search_failed", "message": str(exc)})

    blocks = [*evidence_blocks, *memory_notes]
    return {
        "schema": "pska.turn_context_response.v1",
        "run_id": run.run_id,
        "caller": str(payload.get("caller") or ""),
        "mode": mode,
        "scope": scope,
        "budget": {
            "max_tokens": max_tokens,
            "max_evidence_blocks": max_evidence_blocks,
            "max_memory_notes": max_memory_notes,
        },
        "requirements": {
            "need_citations": bool(requirements.get("need_citations", True)),
            "allow_memory_write": False,
        },
        "turn_context": {
            "summary": _turn_context_summary(evidence_blocks, memory_notes, warnings),
            "blocks": blocks,
            "evidence_blocks": evidence_blocks,
            "memory_notes": memory_notes,
            "citations": _turn_context_citations(evidence_blocks, memory_notes),
            "warnings": warnings,
        },
    }


def _turn_context_scope(payload: dict[str, Any], raw_scope: dict[str, Any]) -> dict[str, Any]:
    scope = {
        "dataset_ids": _turn_context_string_list(raw_scope.get("dataset_ids") or payload.get("dataset_ids")),
        "document_ids": _turn_context_string_list(raw_scope.get("document_ids") or payload.get("document_ids")),
    }
    for key in ("workspace", "project_id", "memory_namespace"):
        value = str(raw_scope.get(key) or payload.get(key) or "").strip()
        if value:
            scope[key] = value
    if raw_scope.get("use_kg") is not None or payload.get("use_kg") is not None:
        scope["use_kg"] = bool(raw_scope.get("use_kg") if raw_scope.get("use_kg") is not None else payload.get("use_kg"))
    retrieval_queries = _turn_context_string_list(raw_scope.get("retrieval_queries") or payload.get("retrieval_queries"))
    if retrieval_queries:
        scope["retrieval_queries"] = retrieval_queries[:5]
    return scope


def _turn_context_string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raise ApiError("scope values must be lists or comma-separated strings", HTTPStatus.BAD_REQUEST)
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_items:
        item = str(raw or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"value must be an integer between {minimum} and {maximum}", HTTPStatus.BAD_REQUEST) from None
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _turn_context_evidence_block(packet: ContextPacket, index: int) -> dict[str, Any]:
    source_ref = packet.source_ref
    return {
        "type": "evidence",
        "index": index,
        "title": packet.title or source_ref.title or packet.context_id,
        "text": packet.text,
        "score": packet.score,
        "source_ref": to_jsonable(source_ref),
        "metadata": to_jsonable(packet.metadata),
    }


def _turn_context_memory_block(fact: MemoryFact, index: int) -> dict[str, Any]:
    return {
        "type": "memory",
        "index": index,
        "fact_id": fact.fact_id,
        "text": fact.text,
        "source_refs": to_jsonable(fact.source_refs),
        "metadata": to_jsonable(fact.metadata),
    }


def _turn_context_citations(evidence_blocks: list[dict[str, Any]], memory_notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(source_ref: dict[str, Any], *, block_type: str, block_index: int) -> None:
        key = json.dumps(source_ref, sort_keys=True, ensure_ascii=False)
        if key in seen:
            return
        seen.add(key)
        citations.append({"block_type": block_type, "block_index": block_index, "source_ref": source_ref})

    for block in evidence_blocks:
        source_ref = block.get("source_ref")
        if isinstance(source_ref, dict):
            add(source_ref, block_type="evidence", block_index=int(block.get("index") or 0))
    for block in memory_notes:
        for source_ref in block.get("source_refs") or []:
            if isinstance(source_ref, dict):
                add(source_ref, block_type="memory", block_index=int(block.get("index") or 0))
    return citations


def _turn_context_summary(
    evidence_blocks: list[dict[str, Any]],
    memory_notes: list[dict[str, Any]],
    warnings: list[dict[str, str]],
) -> str:
    parts = [
        f"{len(evidence_blocks)} evidence block{'s' if len(evidence_blocks) != 1 else ''}",
        f"{len(memory_notes)} memory note{'s' if len(memory_notes) != 1 else ''}",
    ]
    if warnings:
        parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
    return "Assembled " + ", ".join(parts) + "."


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "").strip()
    return name or "upload.bin"


if __name__ == "__main__":
    raise SystemExit(main())
