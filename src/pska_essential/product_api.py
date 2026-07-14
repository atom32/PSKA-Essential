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

from pska_essential.agentic_loop import run_agentic_question
from pska_essential.audit import audit_event
from pska_essential.config import build_service_from_env
from pska_essential.contracts import SourceRef, to_jsonable
from pska_essential.governance import build_workspace_policy_from_env
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.readiness import build_not_ready_ask_result, build_readiness_loop_step, evaluate_kb_readiness
from pska_essential.workflow import WorkflowError, WorkflowService


KbGatewayFactory = Callable[[], Any]


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
    state = ProductApiState(
        service=service or build_service_from_env(),
        kb_gateway_factory=kb_gateway_factory,
        static_dir=Path(static_dir) if static_dir else Path(__file__).with_name("web"),
    )
    server = ThreadingHTTPServer((host, port), _handler_class(state))
    server.daemon_threads = True
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PSKA-Essential Product API and frontend.")
    parser.add_argument("--host", default=os.getenv("PSKA_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PSKA_API_PORT", "8765")))
    args = parser.parse_args()

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
                        "governance": build_workspace_policy_from_env().to_dict(),
                    }
                )
                return

            if method == "GET" and path == "/api/policy":
                self._send_json({"ok": True, "governance": build_workspace_policy_from_env().to_dict()})
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
                self._send_json(
                    {
                        "ok": True,
                        "dataset": gateway.create_dataset(
                            name=_required_str(payload, "name"),
                            description=str(payload.get("description") or ""),
                            chunk_method=str(payload.get("chunk_method") or "naive"),
                        ),
                    },
                    HTTPStatus.CREATED,
                )
                return

            if method == "POST" and path == "/api/kb/ingest":
                self._handle_ingest()
                return

            if method == "POST" and path == "/api/kb/readiness":
                payload = self._read_json()
                readiness = evaluate_kb_readiness(
                    state.kb_gateway_factory(),
                    dataset_ids=_required_list(payload, "dataset_ids"),
                    document_ids=[str(item) for item in payload.get("document_ids") or []],
                )
                self._send_json({"ok": True, "readiness": readiness})
                return

            dataset_readiness = _match(path, "/api/kb/datasets/", "/readiness")
            if method == "GET" and dataset_readiness:
                document_ids = _csv_values(query.get("document_ids") or query.get("document_id") or "")
                readiness = evaluate_kb_readiness(
                    state.kb_gateway_factory(),
                    dataset_ids=[dataset_readiness],
                    document_ids=document_ids,
                )
                self._send_json({"ok": True, "readiness": readiness})
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
                self._send_json(
                    {
                        "ok": True,
                        "parse": gateway.parse_documents(
                            dataset_id=dataset_parse,
                            document_ids=_required_list(payload, "document_ids"),
                            wait=bool(payload.get("wait", False)),
                            timeout_seconds=float(payload.get("timeout_seconds") or 300.0),
                        ),
                    }
                )
                return

            if method == "POST" and path == "/api/ask":
                payload = self._read_json()
                question = _required_str(payload, "question")
                dataset_ids = _required_list(payload, "dataset_ids")
                document_ids = [str(item) for item in payload.get("document_ids") or []]
                proposal_kind = str(payload.get("proposal_kind") or "writing_brief")
                create_review = payload.get("create_review") if "create_review" in payload else None
                use_kg = bool(payload.get("use_kg", False))
                readiness = evaluate_kb_readiness(
                    state.kb_gateway_factory(),
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                )
                if not readiness["ready"]:
                    state.service.store.add_audit_event(
                        audit_event(
                            "kb.readiness.blocked",
                            "kb_scope",
                            ",".join(dataset_ids),
                            question=question,
                            dataset_ids=dataset_ids,
                            document_ids=document_ids,
                            readiness=readiness,
                        )
                    )
                    result = build_not_ready_ask_result(
                        question=question,
                        dataset_ids=dataset_ids,
                        document_ids=document_ids,
                        readiness=readiness,
                        proposal_kind=proposal_kind,
                        create_review=create_review,
                        use_kg=use_kg,
                    )
                    self._send_json({"ok": True, **result})
                    return
                result = run_agentic_question(
                    state.service,
                    question=question,
                    dataset_ids=dataset_ids,
                    document_ids=document_ids,
                    limit=int(payload.get("limit") or 5),
                    proposal_kind=proposal_kind,
                    create_review=create_review,
                    use_kg=use_kg,
                    max_iterations=int(payload.get("max_iterations") or 2),
                    min_context_packets=int(payload.get("min_context_packets") or 1),
                    preflight_steps=[build_readiness_loop_step(readiness)],
                )
                self._send_json({"ok": True, **result})
                return

            if method == "GET" and path == "/api/workflows":
                limit = _int_param(query.get("limit"), 50)
                workflows = state.service.store.list_workflows(limit=limit)
                self._send_json({"ok": True, "workflows": to_jsonable(workflows)})
                return

            workflow_id = _match(path, "/api/workflows/", "")
            if method == "GET" and workflow_id and "/" not in workflow_id:
                self._send_json({"ok": True, "workflow": to_jsonable(state.service.state(workflow_id))})
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

            if method == "GET" and path == "/api/reviews":
                status = query.get("status") or None
                limit = _int_param(query.get("limit"), 50)
                self._send_json({"ok": True, "reviews": state.service.store.list_reviews(status=status, limit=limit)})
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

            review_apply = _match(path, "/api/reviews/", "/apply-memory")
            if method == "POST" and review_apply:
                applied = state.service.memory_apply(review_apply)
                self._send_json({"ok": True, "applied": to_jsonable(applied)})
                return

            if method == "GET" and path == "/api/audit":
                self._send_json({"ok": True, "events": to_jsonable(state.service.store.list_audit_events())})
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
                    result = state.kb_gateway_factory().ingest_files(
                        file_paths=paths,
                        dataset_name=fields.get("dataset_name") or None,
                        dataset_id=fields.get("dataset_id") or None,
                        description=fields.get("description") or "",
                        chunk_method=fields.get("chunk_method") or "naive",
                        parse=_bool_value(fields.get("parse"), True),
                        wait=_bool_value(fields.get("wait"), False),
                        timeout_seconds=float(fields.get("timeout_seconds") or 300.0),
                    )
                self._send_json({"ok": True, "ingest": result}, HTTPStatus.CREATED)
                return

            payload = self._read_json()
            result = state.kb_gateway_factory().ingest_files(
                file_paths=_required_list(payload, "file_paths"),
                dataset_name=payload.get("dataset_name") or None,
                dataset_id=payload.get("dataset_id") or None,
                description=str(payload.get("description") or ""),
                chunk_method=str(payload.get("chunk_method") or "naive"),
                parse=bool(payload.get("parse", True)),
                wait=bool(payload.get("wait", False)),
                timeout_seconds=float(payload.get("timeout_seconds") or 300.0),
            )
            self._send_json({"ok": True, "ingest": result}, HTTPStatus.CREATED)

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


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ApiError(f"{key} is required", HTTPStatus.BAD_REQUEST)
    return value


def _required_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ApiError(f"{key} must be a non-empty list", HTTPStatus.BAD_REQUEST)
    return [str(item) for item in value if str(item)]


def _int_param(value: str | None, default: int) -> int:
    if not value:
        return default
    return int(value)


def _bool_value(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "").strip()
    return name or "upload.bin"


if __name__ == "__main__":
    raise SystemExit(main())
