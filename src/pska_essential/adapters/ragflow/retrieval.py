from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pska_essential.contracts import ContextPacket, SourceContext, SourceRef


class RagflowAdapterError(RuntimeError):
    pass


class RagflowRetrievalAdapter:
    """RAGFlow retrieval adapter.

    The adapter maps SDK/HTTP chunks into PSKA contracts and does not expose
    raw RAGFlow payloads through MCP.
    """

    backend_name = "ragflow"

    def __init__(
        self,
        *,
        client: Any | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    def retrieve(
        self,
        query: str,
        scope: dict[str, Any],
        limit: int,
        options: dict[str, Any] | None = None,
    ) -> list[ContextPacket]:
        dataset_ids = _string_list(scope.get("dataset_ids") or scope.get("knowledge_base_ids"))
        document_ids = _string_list(scope.get("document_ids"))
        if self.client is not None and hasattr(self.client, "retrieve"):
            chunks = self.client.retrieve(
                dataset_ids=dataset_ids,
                document_ids=document_ids,
                question=query,
                page_size=limit,
                top_k=int((options or {}).get("top_k", max(limit, 10))),
                similarity_threshold=float((options or {}).get("similarity_threshold", 0.0)),
                use_kg=bool((options or {}).get("use_kg", scope.get("use_kg", False))),
            )
            return [self._chunk_to_context(chunk, index) for index, chunk in enumerate(chunks[:limit], start=1)]
        if self.base_url and self.api_key:
            data = self._http_retrieve(query, dataset_ids, document_ids, limit, options or {})
            chunks = data.get("chunks") or []
            return [self._chunk_to_context(chunk, index) for index, chunk in enumerate(chunks[:limit], start=1)]
        raise RagflowAdapterError("RAGFlow adapter requires either a ragflow SDK client or base_url/api_key")

    def read_source(self, source_ref: SourceRef) -> SourceContext:
        excerpt = str(source_ref.metadata.get("content_excerpt") or "")
        return SourceContext(
            source_ref=source_ref,
            text=excerpt,
            metadata={
                "adapter": self.backend_name,
                "note": "RAGFlow source reads use stored citation excerpts in v1; full reads belong behind this adapter.",
            },
        )

    def _http_retrieve(
        self,
        query: str,
        dataset_ids: list[str],
        document_ids: list[str],
        limit: int,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "dataset_ids": dataset_ids,
            "document_ids": document_ids,
            "question": query,
            "page": 1,
            "page_size": limit,
            "top_k": int(options.get("top_k", max(limit, 10))),
            "similarity_threshold": float(options.get("similarity_threshold", 0.0)),
            "vector_similarity_weight": float(options.get("vector_similarity_weight", 0.3)),
            "use_kg": bool(options.get("use_kg", False)),
        }
        req = Request(
            f"{self.base_url}/api/v1/retrieval",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=float(options.get("timeout", 30))) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RagflowAdapterError(str(exc)) from exc
        if envelope.get("code") != 0:
            raise RagflowAdapterError(str(envelope.get("message") or "RAGFlow retrieval failed"))
        return dict(envelope.get("data") or {})

    def _chunk_to_context(self, chunk: Any, index: int) -> ContextPacket:
        data = _object_to_dict(chunk)
        text = str(data.get("content") or data.get("content_with_weight") or "")
        document_id = _optional_str(data.get("document_id") or data.get("doc_id"))
        chunk_id = _optional_str(data.get("id") or data.get("chunk_id"))
        dataset_id = _optional_str(data.get("dataset_id") or data.get("kb_id"))
        title = _optional_str(data.get("document_name") or data.get("document_keyword") or data.get("title"))
        source_ref = SourceRef(
            adapter=self.backend_name,
            dataset_id=dataset_id,
            document_id=document_id,
            chunk_id=chunk_id,
            title=title,
            external_id=chunk_id or document_id,
            metadata={
                "positions": data.get("positions") or [],
                "content_excerpt": text[:1000],
            },
        )
        return ContextPacket(
            context_id=f"ctx_ragflow_{index}_{chunk_id or document_id or 'chunk'}",
            text=text,
            source_ref=source_ref,
            score=float(data.get("similarity") or data.get("score") or 0.0),
            title=title,
            metadata={
                "vector_similarity": data.get("vector_similarity"),
                "term_similarity": data.get("term_similarity"),
                "doc_type": data.get("doc_type"),
            },
        )


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    result: dict[str, Any] = {}
    for name in (
        "id",
        "chunk_id",
        "content",
        "content_with_weight",
        "dataset_id",
        "kb_id",
        "document_id",
        "doc_id",
        "document_name",
        "document_keyword",
        "title",
        "similarity",
        "score",
        "vector_similarity",
        "term_similarity",
        "positions",
        "doc_type",
    ):
        if hasattr(value, name):
            result[name] = getattr(value, name)
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
