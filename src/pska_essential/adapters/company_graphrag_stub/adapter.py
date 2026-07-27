from __future__ import annotations

from typing import Any
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
            if _fact_in_scope(fact, scope)
            and not fact.invalid_at
            and (not words or any(word in fact.text.lower() for word in words))
        ]
        return _rank_memory_facts(matches)[:limit]

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        fact = MemoryFact(
            fact_id=f"company_mem_{uuid4().hex}",
            text=reviewed_patch.text,
            source_refs=reviewed_patch.source_refs,
            metadata={"company_stub": True, **reviewed_patch.metadata},
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
            if fact.fact_id == reviewed_update.target_id and _metadata_in_scope(fact.metadata, reviewed_update.metadata):
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
                fact.metadata.update(reviewed_update.metadata)
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
            if fact.fact_id == reviewed_delete.target_id and _metadata_in_scope(fact.metadata, reviewed_delete.metadata):
                fact.invalid_at = utc_now_iso()
                fact.metadata.update(reviewed_delete.metadata)
                fact.metadata["delete_reason"] = reviewed_delete.reason
                return MemoryApplyResult(
                    applied=True,
                    target_id=fact.fact_id,
                    backend=self.backend_name,
                    message="Company GraphRAG stub deactivated reviewed memory",
                    metadata={"operation": "delete"},
                )
        raise ValueError(f"memory fact not found: {reviewed_delete.target_id}")


def _fact_in_scope(fact: MemoryFact, scope: dict) -> bool:
    return _metadata_in_scope(fact.metadata, scope)


def _metadata_in_scope(metadata: dict, scope: dict) -> bool:
    expected = str(scope.get("memory_namespace") or "")
    actual = str(metadata.get("memory_namespace") or "")
    if expected:
        return actual == expected
    return actual == ""


def _rank_memory_facts(facts: list[MemoryFact]) -> list[MemoryFact]:
    return sorted(facts, key=_memory_fact_sort_key, reverse=True)


def _memory_fact_sort_key(fact: MemoryFact) -> tuple[str, str]:
    metadata = fact.metadata or {}
    timestamp = (
        fact.valid_at
        or _metadata_timestamp(metadata, "applied_at")
        or _metadata_timestamp(metadata, "updated_at")
        or _metadata_timestamp(metadata, "created_at")
        or _metadata_timestamp(metadata, "observed_at")
        or ""
    )
    return (timestamp, fact.fact_id)


def _metadata_timestamp(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""
