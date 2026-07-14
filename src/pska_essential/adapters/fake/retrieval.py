from __future__ import annotations

from typing import Any, Callable

from pska_essential.contracts import ContextPacket, SourceContext, SourceRef


class FakeRetrievalAdapter:
    backend_name = "fake"

    def __init__(
        self,
        corpus: list[dict[str, Any]] | None = None,
        corpus_loader: Callable[[dict[str, Any] | None], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.corpus_loader = corpus_loader
        self.corpus = corpus or [
            {
                "id": "demo-1",
                "title": "PSKA-Essential Doctrine",
                "text": "PSKA-Essential is an agent knowledge workflow gate. It retrieves context, proposes candidate knowledge, requires review, and only then applies memory.",
            },
            {
                "id": "demo-2",
                "title": "Adapter Boundary",
                "text": "RAGFlow, Graphiti, Hermes, and company GraphRAG systems stay behind adapters. Public MCP contracts do not expose raw backend payloads.",
            },
        ]

    def retrieve(
        self,
        query: str,
        scope: dict[str, Any],
        limit: int,
        options: dict[str, Any] | None = None,
    ) -> list[ContextPacket]:
        query_words = {word.lower() for word in query.split() if word.strip()}
        scored = []
        for item in self._corpus(scope):
            text = str(item["text"])
            score = sum(1 for word in query_words if word in text.lower())
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        packets = []
        for index, (score, item) in enumerate(scored[:limit], start=1):
            source_ref = SourceRef(
                adapter=self.backend_name,
                dataset_id=str(item.get("dataset_id") or scope.get("dataset_ids", ["demo"])[0])
                if scope.get("dataset_ids") or item.get("dataset_id")
                else "demo",
                document_id=str(item.get("document_id") or item["id"]),
                chunk_id=f"{item['id']}#chunk-1",
                title=str(item["title"]),
                metadata={"content_excerpt": str(item["text"])[:500]},
            )
            packets.append(
                ContextPacket(
                    context_id=f"ctx_fake_{index}_{item['id']}",
                    text=str(item["text"]),
                    source_ref=source_ref,
                    score=float(score),
                    title=str(item["title"]),
                )
            )
        return packets

    def read_source(self, source_ref: SourceRef) -> SourceContext:
        scope = {"dataset_ids": [source_ref.dataset_id]} if source_ref.dataset_id else {}
        for item in self._corpus(scope):
            if str(item.get("document_id") or item["id"]) == source_ref.document_id:
                return SourceContext(source_ref=source_ref, text=str(item["text"]), metadata={"title": item["title"]})
        return SourceContext(
            source_ref=source_ref,
            text=str(source_ref.metadata.get("content_excerpt") or ""),
            metadata={"missing": True},
        )

    def _corpus(self, scope: dict[str, Any] | None) -> list[dict[str, Any]]:
        if self.corpus_loader:
            loaded = self.corpus_loader(scope)
            if loaded:
                return loaded
        return self.corpus
