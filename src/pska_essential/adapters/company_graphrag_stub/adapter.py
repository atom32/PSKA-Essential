from __future__ import annotations

from uuid import uuid4

from pska_essential.contracts import (
    ContextPacket,
    MemoryApplyResult,
    MemoryFact,
    MemoryPatch,
    SourceContext,
    SourceRef,
)


class CompanyGraphRagStubAdapter:
    """Replacement-contract stub for a future company GraphRAG platform."""

    backend_name = "company_graphrag_stub"

    def __init__(self) -> None:
        self.memory: list[MemoryFact] = []
        self.documents = [
            {
                "id": "company-demo-1",
                "title": "Company GraphRAG Contract",
                "text": "The company GraphRAG platform can replace RAGFlow and Graphiti when it implements PSKA RetrievalPort and MemoryPort.",
            }
        ]

    def retrieve(self, query, scope, limit, options=None) -> list[ContextPacket]:
        packets = []
        for index, doc in enumerate(self.documents[:limit], start=1):
            ref = SourceRef(
                adapter=self.backend_name,
                dataset_id="company-demo",
                document_id=doc["id"],
                chunk_id=f"{doc['id']}#chunk-1",
                title=doc["title"],
                metadata={"content_excerpt": doc["text"]},
            )
            packets.append(
                ContextPacket(
                    context_id=f"ctx_company_{index}",
                    text=doc["text"],
                    source_ref=ref,
                    score=1.0,
                    title=doc["title"],
                )
            )
        return packets

    def read_source(self, source_ref: SourceRef) -> SourceContext:
        for doc in self.documents:
            if doc["id"] == source_ref.document_id:
                return SourceContext(source_ref=source_ref, text=doc["text"], metadata={"title": doc["title"]})
        return SourceContext(source_ref=source_ref, text="", metadata={"missing": True})

    def search(self, query: str, scope: dict, limit: int) -> list[MemoryFact]:
        words = {word.lower() for word in query.split() if word.strip()}
        matches = [
            fact
            for fact in self.memory
            if not words or any(word in fact.text.lower() for word in words)
        ]
        return matches[:limit]

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        fact = MemoryFact(
            fact_id=f"company_mem_{uuid4().hex}",
            text=reviewed_patch.text,
            source_refs=reviewed_patch.source_refs,
            metadata={"company_stub": True},
        )
        self.memory.append(fact)
        return MemoryApplyResult(
            applied=True,
            target_id=fact.fact_id,
            backend=self.backend_name,
            message="Company GraphRAG stub accepted reviewed patch",
        )
