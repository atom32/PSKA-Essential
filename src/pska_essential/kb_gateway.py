from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class KbGatewayError(RuntimeError):
    pass


class RagflowKnowledgeGateway:
    """Thin RAGFlow KB operations used by PSKA MCP tools.

    RAGFlow owns datasets, uploads, parsing, and optional structure graphs.
    This gateway only normalizes those operations into a small PSKA-facing
    surface so agents do not need direct RAGFlow tool access.
    """

    backend_name = "ragflow"

    def __init__(self, *, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        if not base_url:
            raise KbGatewayError("RAGFLOW_BASE_URL is required")
        if not api_key:
            raise KbGatewayError("RAGFLOW_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_datasets(self, *, name: str | None = None, page_size: int = 30) -> list[dict[str, Any]]:
        params = {"page": 1, "page_size": page_size, "orderby": "create_time", "desc": True}
        # RAGFlow currently reports a permission error for unknown `name`
        # filters. List visible datasets first and filter client-side so
        # "ensure dataset" can create a new one when it does not exist.
        data = self._json("GET", "/datasets", params=params)
        rows = data if isinstance(data, list) else data.get("data", data.get("datasets", []))
        datasets = [_dataset_summary(row) for row in rows]
        if name:
            return [dataset for dataset in datasets if dataset.get("name") == name]
        return datasets

    def create_dataset(
        self,
        *,
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        permission: str = "me",
        parser_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "permission": permission,
        }
        if parser_config:
            payload["parser_config"] = parser_config
        return _dataset_summary(self._json("POST", "/datasets", payload=payload))

    def ensure_dataset(self, *, name: str, description: str = "", chunk_method: str = "naive") -> dict[str, Any]:
        matches = self.list_datasets(name=name, page_size=50)
        for dataset in matches:
            if dataset.get("name") == name:
                return {"created": False, "dataset": dataset}
        dataset = self.create_dataset(name=name, description=description, chunk_method=chunk_method)
        return {"created": True, "dataset": dataset}

    def upload_documents(self, *, dataset_id: str, file_paths: list[str]) -> list[dict[str, Any]]:
        if not dataset_id:
            raise KbGatewayError("dataset_id is required")
        paths = [_checked_file(path) for path in file_paths]
        body, content_type = _multipart_files(paths)
        data = self._request(
            "POST",
            f"/datasets/{dataset_id}/documents",
            body=body,
            headers={"Content-Type": content_type},
        )
        rows = data if isinstance(data, list) else data.get("documents", data.get("docs", []))
        return [_document_summary(row, dataset_id=dataset_id) for row in rows]

    def list_documents(
        self,
        *,
        dataset_id: str,
        document_id: str | None = None,
        name: str | None = None,
        page_size: int = 30,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": 1, "page_size": page_size, "orderby": "create_time", "desc": True}
        if document_id:
            params["id"] = document_id
        if name:
            params["name"] = name
        data = self._json("GET", f"/datasets/{dataset_id}/documents", params=params)
        rows = data if isinstance(data, list) else data.get("docs", [])
        return [_document_summary(row, dataset_id=dataset_id) for row in rows]

    def parse_documents(
        self,
        *,
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        ids = [str(doc_id) for doc_id in document_ids if doc_id]
        if not ids:
            raise KbGatewayError("document_ids is required")
        self._json("POST", f"/datasets/{dataset_id}/chunks", payload={"document_ids": ids})
        result: dict[str, Any] = {
            "backend": self.backend_name,
            "dataset_id": dataset_id,
            "document_ids": ids,
            "parse_started": True,
        }
        if wait:
            result["documents"] = self.wait_for_documents(
                dataset_id=dataset_id,
                document_ids=ids,
                timeout_seconds=timeout_seconds,
            )
        return result

    def wait_for_documents(
        self,
        *,
        dataset_id: str,
        document_ids: list[str],
        timeout_seconds: float = 300.0,
    ) -> list[dict[str, Any]]:
        deadline = time.time() + timeout_seconds
        pending = {str(doc_id) for doc_id in document_ids if doc_id}
        latest: dict[str, dict[str, Any]] = {}
        while pending and time.time() < deadline:
            for doc_id in list(pending):
                docs = self.list_documents(dataset_id=dataset_id, document_id=doc_id, page_size=1)
                if not docs:
                    continue
                doc = docs[0]
                latest[doc_id] = doc
                if _document_terminal(doc):
                    pending.discard(doc_id)
            if pending:
                time.sleep(1.0)
        if pending:
            raise KbGatewayError(f"document parsing timed out: {sorted(pending)}")
        return [latest[doc_id] for doc_id in document_ids if doc_id in latest]

    def document_graph(self, *, dataset_id: str, document_id: str) -> dict[str, Any]:
        data = self._json("GET", f"/datasets/{dataset_id}/documents/{document_id}/structure/graph")
        templates = data.get("templates", []) if isinstance(data, dict) else []
        return {
            "backend": self.backend_name,
            "dataset_id": dataset_id,
            "document_id": document_id,
            "templates": templates,
            "note": "RAGFlow structure graph is optional and may be empty unless compilation templates were configured before parsing.",
        }

    def ingest_files(
        self,
        *,
        file_paths: list[str],
        dataset_id: str | None = None,
        dataset_name: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        parse: bool = True,
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        dataset: dict[str, Any]
        created = False
        if dataset_id:
            matches = self.list_datasets(page_size=100)
            dataset = next((item for item in matches if item.get("dataset_id") == dataset_id), {"dataset_id": dataset_id})
        else:
            if not dataset_name:
                raise KbGatewayError("dataset_name is required when dataset_id is not provided")
            ensured = self.ensure_dataset(name=dataset_name, description=description, chunk_method=chunk_method)
            created = bool(ensured["created"])
            dataset = ensured["dataset"]
            dataset_id = str(dataset["dataset_id"])

        documents = self.upload_documents(dataset_id=dataset_id, file_paths=file_paths)
        result: dict[str, Any] = {
            "backend": self.backend_name,
            "dataset_created": created,
            "dataset": dataset,
            "documents": documents,
        }
        if parse:
            parse_result = self.parse_documents(
                dataset_id=dataset_id,
                document_ids=[doc["document_id"] for doc in documents],
                wait=wait,
                timeout_seconds=timeout_seconds,
            )
            result["parse"] = parse_result
            if wait and parse_result.get("documents"):
                result["documents"] = parse_result["documents"]
        return result

    def _json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        return self._request(method, path, body=body, headers=headers, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        query = f"?{urlencode({k: v for k, v in (params or {}).items() if v is not None})}" if params else ""
        req = Request(
            f"{self.base_url}/api/v1{path}{query}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                **(headers or {}),
            },
            method=method,
        )
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except URLError as exc:
            raise KbGatewayError(str(exc)) from exc
        if not raw:
            return {}
        envelope = json.loads(raw)
        if envelope.get("code") != 0:
            raise KbGatewayError(str(envelope.get("message") or "RAGFlow KB operation failed"))
        return envelope.get("data") or {}


def build_kb_gateway_from_env() -> RagflowKnowledgeGateway:
    provider = os.getenv("PSKA_KB_PROVIDER", "ragflow").strip().lower()
    if provider != "ragflow":
        raise KbGatewayError(f"unsupported KB provider: {provider}")
    return RagflowKnowledgeGateway(
        base_url=os.getenv("RAGFLOW_BASE_URL", "http://127.0.0.1:9380"),
        api_key=os.getenv("RAGFLOW_API_KEY", ""),
        timeout=float(os.getenv("RAGFLOW_TIMEOUT", "30")),
    )


def _dataset_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": "ragflow",
        "dataset_id": str(row.get("id") or row.get("dataset_id") or ""),
        "name": row.get("name") or "",
        "description": row.get("description") or "",
        "document_count": int(row.get("document_count") or 0),
        "chunk_count": int(row.get("chunk_count") or 0),
        "chunk_method": row.get("chunk_method") or "",
        "embedding_model": row.get("embedding_model") or row.get("embd_id") or "",
        "permission": row.get("permission") or "",
    }


def _document_summary(row: dict[str, Any], *, dataset_id: str) -> dict[str, Any]:
    progress = row.get("progress")
    try:
        progress = float(progress)
    except (TypeError, ValueError):
        progress = 0.0
    return {
        "backend": "ragflow",
        "dataset_id": str(row.get("dataset_id") or row.get("kb_id") or dataset_id),
        "document_id": str(row.get("id") or row.get("document_id") or ""),
        "name": row.get("name") or row.get("document_name") or "",
        "chunk_method": row.get("chunk_method") or row.get("parser_id") or "",
        "chunk_count": int(row.get("chunk_count") or row.get("chunk_num") or 0),
        "token_count": int(row.get("token_count") or row.get("token_num") or 0),
        "progress": progress,
        "progress_msg": row.get("progress_msg") or "",
        "run": str(row.get("run") or ""),
        "status": str(row.get("status") or ""),
    }


def _document_terminal(doc: dict[str, Any]) -> bool:
    run = str(doc.get("run") or "").upper()
    if run in {"DONE", "FAIL", "CANCEL"}:
        return True
    if float(doc.get("progress") or 0.0) >= 1.0:
        return True
    if int(doc.get("chunk_count") or 0) > 0 and run not in {"1", "RUNNING"}:
        return True
    return False


def _checked_file(path: str) -> Path:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise KbGatewayError(f"file not found: {path}")
    return file_path


def _multipart_files(paths: list[Path]) -> tuple[bytes, str]:
    boundary = f"pska-{uuid4().hex}"
    chunks: list[bytes] = []
    for path in paths:
        name = path.name.replace('"', '\\"')
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
