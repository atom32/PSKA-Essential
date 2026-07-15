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
    max_page_size = 100

    def __init__(self, *, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        if not base_url:
            raise KbGatewayError("RAGFLOW_BASE_URL is required")
        if not api_key:
            raise KbGatewayError("RAGFLOW_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_datasets(self, *, name: str | None = None, page_size: int = 30) -> list[dict[str, Any]]:
        params = {"page": 1, "page_size": _ragflow_page_size(page_size), "orderby": "create_time", "desc": True}
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
        embedding_model: str = "",
        permission: str = "me",
        parser_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "permission": permission,
        }
        if embedding_model:
            payload["embedding_model"] = embedding_model
        if parser_config:
            payload["parser_config"] = parser_config
        return _dataset_summary(self._json("POST", "/datasets", payload=payload))

    def delete_datasets(
        self,
        *,
        dataset_ids: list[str] | None = None,
        dataset_names: list[str] | None = None,
        delete_all: bool = False,
    ) -> dict[str, Any]:
        ids = [str(dataset_id) for dataset_id in dataset_ids or [] if str(dataset_id).strip()]
        names = _normalized_strings(dataset_names)
        if names and not delete_all:
            resolved_ids, missing_names = self._dataset_ids_for_names(names)
            if missing_names:
                raise KbGatewayError(f"no dataset matched name(s): {', '.join(missing_names)}")
            ids = _deduped(ids + resolved_ids)
        if not ids and not delete_all:
            raise KbGatewayError("dataset_ids or dataset_names is required unless delete_all is true")
        data = self._json("DELETE", "/datasets", payload={"ids": ids or None, "delete_all": bool(delete_all)})
        return {
            "backend": self.backend_name,
            "dataset_ids": ids,
            "dataset_names": names,
            "deleted_dataset_ids": ids if not delete_all else [],
            "delete_all": bool(delete_all),
            "deleted": True,
            "result": data,
        }

    def _dataset_ids_for_names(self, dataset_names: list[str]) -> tuple[list[str], list[str]]:
        datasets = self.list_datasets(page_size=self.max_page_size)
        ids: list[str] = []
        matched_names: set[str] = set()
        requested = set(dataset_names)
        for dataset in datasets:
            name = str(dataset.get("name") or "")
            dataset_id = str(dataset.get("dataset_id") or "")
            if name in requested and dataset_id:
                ids.append(dataset_id)
                matched_names.add(name)
        missing = [name for name in dataset_names if name not in matched_names]
        return ids, missing

    def ensure_dataset(
        self,
        *,
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
    ) -> dict[str, Any]:
        matches = self.list_datasets(name=name, page_size=50)
        for dataset in matches:
            if dataset.get("name") == name:
                _ensure_embedding_model_compatible(dataset, embedding_model)
                return {"created": False, "dataset": dataset}
        dataset = self.create_dataset(
            name=name,
            description=description,
            chunk_method=chunk_method,
            embedding_model=embedding_model,
        )
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
        params: dict[str, Any] = {"page": 1, "page_size": _ragflow_page_size(page_size), "orderby": "create_time", "desc": True}
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
        embedding_model: str = "",
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
            ensured = self.ensure_dataset(
                name=dataset_name,
                description=description,
                chunk_method=chunk_method,
                embedding_model=embedding_model,
            )
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


class FakeKnowledgeGateway:
    """Explicit development/test KB gateway.

    This gateway is available only when `PSKA_DEV_FAKE=1`. It lets Product API
    and frontend flows exercise KB behavior without silently falling back from a
    configured provider.
    """

    backend_name = "fake"

    def __init__(self) -> None:
        self.datasets: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, list[dict[str, Any]]] = {}
        self.document_text: dict[str, str] = {}
        self.document_parse_errors: dict[str, str] = {}

    def list_datasets(self, *, name: str | None = None, page_size: int = 30) -> list[dict[str, Any]]:
        datasets = list(self.datasets.values())
        if name:
            datasets = [dataset for dataset in datasets if dataset.get("name") == name]
        return [dict(dataset) for dataset in datasets[:page_size]]

    def create_dataset(
        self,
        *,
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
    ) -> dict[str, Any]:
        dataset_id = f"fake_ds_{uuid4().hex[:12]}"
        dataset = {
            "backend": self.backend_name,
            "dataset_id": dataset_id,
            "name": name,
            "description": description,
            "document_count": 0,
            "chunk_count": 0,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model or "fake",
            "permission": "me",
        }
        self.datasets[dataset_id] = dataset
        self.documents[dataset_id] = []
        return dict(dataset)

    def delete_datasets(
        self,
        *,
        dataset_ids: list[str] | None = None,
        dataset_names: list[str] | None = None,
        delete_all: bool = False,
    ) -> dict[str, Any]:
        ids = [str(dataset_id) for dataset_id in dataset_ids or [] if str(dataset_id).strip()]
        names = _normalized_strings(dataset_names)
        if names and not delete_all:
            resolved_ids, missing_names = self._dataset_ids_for_names(names)
            if missing_names:
                raise KbGatewayError(f"no dataset matched name(s): {', '.join(missing_names)}")
            ids = _deduped(ids + resolved_ids)
        if not ids and not delete_all:
            raise KbGatewayError("dataset_ids or dataset_names is required unless delete_all is true")
        if delete_all:
            deleted_ids = list(self.datasets.keys())
            self.datasets.clear()
            self.documents.clear()
            self.document_text.clear()
            self.document_parse_errors.clear()
        else:
            deleted_ids = [dataset_id for dataset_id in ids if dataset_id in self.datasets]
            for dataset_id in ids:
                docs = self.documents.pop(dataset_id, [])
                for doc in docs:
                    document_id = str(doc.get("document_id") or "")
                    self.document_text.pop(document_id, None)
                    self.document_parse_errors.pop(document_id, None)
                self.datasets.pop(dataset_id, None)
        return {
            "backend": self.backend_name,
            "dataset_ids": ids,
            "dataset_names": names,
            "deleted_dataset_ids": deleted_ids,
            "delete_all": bool(delete_all),
            "deleted": True,
        }

    def _dataset_ids_for_names(self, dataset_names: list[str]) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        matched_names: set[str] = set()
        requested = set(dataset_names)
        for dataset in self.datasets.values():
            name = str(dataset.get("name") or "")
            dataset_id = str(dataset.get("dataset_id") or "")
            if name in requested and dataset_id:
                ids.append(dataset_id)
                matched_names.add(name)
        missing = [name for name in dataset_names if name not in matched_names]
        return ids, missing

    def ensure_dataset(
        self,
        *,
        name: str,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
    ) -> dict[str, Any]:
        for dataset in self.datasets.values():
            if dataset.get("name") == name:
                _ensure_embedding_model_compatible(dataset, embedding_model)
                return {"created": False, "dataset": dict(dataset)}
        return {
            "created": True,
            "dataset": self.create_dataset(
                name=name,
                description=description,
                chunk_method=chunk_method,
                embedding_model=embedding_model,
            ),
        }

    def list_documents(
        self,
        *,
        dataset_id: str,
        document_id: str | None = None,
        name: str | None = None,
        page_size: int = 30,
    ) -> list[dict[str, Any]]:
        docs = list(self.documents.get(dataset_id, []))
        if document_id:
            docs = [doc for doc in docs if doc.get("document_id") == document_id]
        if name:
            docs = [doc for doc in docs if doc.get("name") == name]
        return [dict(doc) for doc in docs[:page_size]]

    def upload_documents(self, *, dataset_id: str, file_paths: list[str]) -> list[dict[str, Any]]:
        if dataset_id not in self.datasets:
            self.datasets[dataset_id] = {
                "backend": self.backend_name,
                "dataset_id": dataset_id,
                "name": dataset_id,
                "description": "",
                "document_count": 0,
                "chunk_count": 0,
                "chunk_method": "naive",
                "embedding_model": "fake",
                "permission": "me",
            }
            self.documents[dataset_id] = []
        docs = []
        for file_path in file_paths:
            path = _checked_file(file_path)
            document_id = f"fake_doc_{uuid4().hex[:12]}"
            text, parse_error = _read_fake_document_text(path)
            doc = {
                "backend": self.backend_name,
                "dataset_id": dataset_id,
                "document_id": document_id,
                "name": path.name,
                "chunk_method": "naive",
                "chunk_count": 0,
                "token_count": 0,
                "progress": 0.0,
                "progress_msg": "uploaded",
                "run": "UNSTART",
                "status": "uploaded",
            }
            self.document_text[document_id] = text
            if parse_error:
                self.document_parse_errors[document_id] = parse_error
            docs.append(doc)
            self.documents.setdefault(dataset_id, []).append(doc)
        self.datasets[dataset_id]["document_count"] = len(self.documents.get(dataset_id, []))
        return [dict(doc) for doc in docs]

    def parse_documents(
        self,
        *,
        dataset_id: str,
        document_ids: list[str],
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        docs = self.documents.get(dataset_id, [])
        for doc in docs:
            if doc.get("document_id") in document_ids:
                document_id = str(doc.get("document_id") or "")
                parse_error = self.document_parse_errors.get(document_id, "")
                if parse_error:
                    doc["chunk_count"] = 0
                    doc["token_count"] = 0
                    doc["progress"] = 1.0
                    doc["progress_msg"] = parse_error
                    doc["run"] = "FAIL"
                    doc["status"] = "failed"
                else:
                    doc["chunk_count"] = max(int(doc.get("chunk_count") or 0), 1)
                    doc["token_count"] = max(int(doc.get("token_count") or 0), 8)
                    doc["progress"] = 1.0
                    doc["progress_msg"] = "ready"
                    doc["run"] = "DONE"
                    doc["status"] = "ready"
        self.datasets[dataset_id]["chunk_count"] = sum(int(doc.get("chunk_count") or 0) for doc in docs)
        result: dict[str, Any] = {
            "backend": self.backend_name,
            "dataset_id": dataset_id,
            "document_ids": document_ids,
            "parse_started": True,
        }
        if wait:
            result["documents"] = self.list_documents(dataset_id=dataset_id, page_size=100)
        return result

    def document_graph(self, *, dataset_id: str, document_id: str) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "dataset_id": dataset_id,
            "document_id": document_id,
            "templates": [],
            "note": "Fake KB gateway does not build structure graphs.",
        }

    def retrieval_corpus(self, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        scope = dict(scope or {})
        dataset_ids = [str(item) for item in scope.get("dataset_ids") or self.datasets.keys()]
        document_ids = {str(item) for item in scope.get("document_ids") or []}
        corpus: list[dict[str, Any]] = []
        for dataset_id in dataset_ids:
            for doc in self.documents.get(dataset_id, []):
                document_id = str(doc.get("document_id") or "")
                if document_ids and document_id not in document_ids:
                    continue
                if int(doc.get("chunk_count") or 0) <= 0:
                    continue
                text = self.document_text.get(document_id, "")
                if not text:
                    continue
                corpus.append(
                    {
                        "id": document_id,
                        "dataset_id": dataset_id,
                        "document_id": document_id,
                        "title": doc.get("name") or document_id,
                        "text": text,
                    }
                )
        return corpus

    def ingest_files(
        self,
        *,
        file_paths: list[str],
        dataset_id: str | None = None,
        dataset_name: str | None = None,
        description: str = "",
        chunk_method: str = "naive",
        embedding_model: str = "",
        parse: bool = True,
        wait: bool = False,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        created = False
        if dataset_id:
            dataset = self.datasets.get(dataset_id, {"dataset_id": dataset_id, "name": dataset_id})
        else:
            if not dataset_name:
                raise KbGatewayError("dataset_name is required when dataset_id is not provided")
            ensured = self.ensure_dataset(
                name=dataset_name,
                description=description,
                chunk_method=chunk_method,
                embedding_model=embedding_model,
            )
            created = bool(ensured["created"])
            dataset = ensured["dataset"]
            dataset_id = str(dataset["dataset_id"])
        documents = self.upload_documents(dataset_id=dataset_id, file_paths=file_paths)
        result: dict[str, Any] = {
            "backend": self.backend_name,
            "dataset_created": created,
            "dataset": dict(self.datasets.get(dataset_id, dataset)),
            "documents": documents,
        }
        if parse:
            result["parse"] = self.parse_documents(
                dataset_id=dataset_id,
                document_ids=[doc["document_id"] for doc in documents],
                wait=wait,
                timeout_seconds=timeout_seconds,
            )
            result["documents"] = self.list_documents(dataset_id=dataset_id, page_size=100)
        return result


_FAKE_KB_GATEWAY = FakeKnowledgeGateway()


def reset_fake_kb_gateway() -> FakeKnowledgeGateway:
    """Reset the explicit development/test fake KB gateway."""

    global _FAKE_KB_GATEWAY
    _FAKE_KB_GATEWAY = FakeKnowledgeGateway()
    return _FAKE_KB_GATEWAY


def build_kb_gateway_from_env() -> RagflowKnowledgeGateway | FakeKnowledgeGateway:
    provider = os.getenv("PSKA_KB_PROVIDER", "").strip().lower()
    if not provider:
        if _env_enabled("PSKA_DEV_FAKE"):
            provider = "fake"
        else:
            raise KbGatewayError("PSKA_KB_PROVIDER is required")
    if provider == "fake":
        if not _env_enabled("PSKA_DEV_FAKE"):
            raise KbGatewayError("PSKA_KB_PROVIDER=fake is allowed only when PSKA_DEV_FAKE=1")
        return _FAKE_KB_GATEWAY
    if provider != "ragflow":
        raise KbGatewayError(f"unsupported KB provider: {provider}")
    missing = _missing_env("RAGFLOW_BASE_URL", "RAGFLOW_API_KEY")
    if missing:
        raise KbGatewayError(f"RAGFlow KB gateway is missing required env: {', '.join(missing)}")
    return RagflowKnowledgeGateway(
        base_url=os.environ["RAGFLOW_BASE_URL"],
        api_key=os.environ["RAGFLOW_API_KEY"],
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


def _ensure_embedding_model_compatible(dataset: dict[str, Any], requested_embedding_model: str) -> None:
    requested = str(requested_embedding_model or "").strip()
    existing = str(dataset.get("embedding_model") or "").strip()
    if requested and existing and requested != existing:
        raise KbGatewayError(
            "existing dataset uses a different embedding_model; delete/recreate the dataset "
            f"or omit embedding_model to reuse it: dataset_id={dataset.get('dataset_id')}, "
            f"existing={existing}, requested={requested}"
        )


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


def _ragflow_page_size(value: Any) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 30
    return min(max(size, 1), RagflowKnowledgeGateway.max_page_size)


def _normalized_strings(values: list[str] | None) -> list[str]:
    return _deduped([str(value).strip() for value in values or [] if str(value).strip()])


def _deduped(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _checked_file(path: str) -> Path:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise KbGatewayError(f"file not found: {path}")
    return file_path


def _read_fake_document_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf" or raw.startswith(b"%PDF"):
        return "", _fake_unsupported_document_message(path)
    if b"\x00" in raw[:4096]:
        return "", _fake_unsupported_document_message(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "", _fake_unsupported_document_message(path)
    return text[:20000], ""


def _fake_unsupported_document_message(path: Path) -> str:
    return (
        f"Fake KB can only parse UTF-8 text files; '{path.name}' needs a real KB "
        "provider such as RAGFlow for parsing, OCR, embedding, and indexing."
    )


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


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _missing_env(*names: str) -> list[str]:
    return [name for name in names if not os.getenv(name, "").strip()]
