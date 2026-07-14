from __future__ import annotations

from uuid import uuid4

from pska_essential.contracts import (
    ContextPacket,
    MemoryApplyResult,
    MemoryDelete,
    MemoryFact,
    MemoryPatch,
    MemoryUpdate,
    SourceContext,
    SourceRef,
    utc_now_iso,
)


class CompanyGraphRagStubAdapter:
    """Replacement-contract stub for a future company GraphRAG platform."""

    backend_name = "company_graphrag_stub"
    memory_capabilities = {
        "search": True,
        "apply": True,
        "update": True,
        "delete": True,
    }

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
            if not fact.invalid_at and (not words or any(word in fact.text.lower() for word in words))
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

    def update(self, reviewed_update: MemoryUpdate) -> MemoryApplyResult:
        for fact in self.memory:
            if fact.fact_id == reviewed_update.target_id:
                previous_text = fact.text
                version = int(fact.metadata.get("version", 1)) + 1
                fact.metadata.setdefault("versions", []).append(
                    {
                        "version": version - 1,
                        "text": previous_text,
                        "updated_at": utc_now_iso(),
                        "reason": reviewed_update.reason,
                    }
                )
                fact.text = reviewed_update.text
                fact.source_refs = reviewed_update.source_refs
                fact.metadata["update_reason"] = reviewed_update.reason
                fact.metadata["version"] = version
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Company GraphRAG stub updated reviewed memory",
                    metadata={"operation": "update", "version": version, "previous_text": previous_text},
                )
        raise ValueError(f"memory fact not found: {reviewed_update.target_id}")

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        for fact in self.memory:
            if fact.fact_id == reviewed_delete.target_id:
                fact.invalid_at = utc_now_iso()
                fact.metadata["delete_reason"] = reviewed_delete.reason
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Company GraphRAG stub deactivated reviewed memory",
                    metadata={"operation": "delete"},
                )
        raise ValueError(f"memory fact not found: {reviewed_delete.target_id}")
