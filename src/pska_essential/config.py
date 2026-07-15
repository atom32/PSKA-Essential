from __future__ import annotations

import os

from pska_essential.adapters.company_graphrag_stub import CompanyGraphRagStubAdapter
from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.adapters.graphiti import GraphitiMemoryAdapter
from pska_essential.adapters.ragflow import RagflowRetrievalAdapter
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService


def build_service_from_env() -> WorkflowService:
    dev_fake = _env_enabled("PSKA_DEV_FAKE")
    retrieval_provider = _required_provider("PSKA_RETRIEVAL_PROVIDER", dev_fake)
    memory_provider = _required_provider("PSKA_MEMORY_PROVIDER", dev_fake)

    company_stub = CompanyGraphRagStubAdapter()

    if retrieval_provider == "fake":
        _require_dev_fake("PSKA_RETRIEVAL_PROVIDER", dev_fake)
        retrieval = FakeRetrievalAdapter(
            corpus_loader=_fake_kb_corpus_loader if _kb_provider_is_fake(dev_fake) else None
        )
    elif retrieval_provider == "ragflow":
        _require_env("RAGFLOW_BASE_URL", "RAGFLOW_API_KEY", provider="RAGFlow retrieval")
        retrieval = RagflowRetrievalAdapter(
            base_url=os.getenv("RAGFLOW_BASE_URL"),
            api_key=os.getenv("RAGFLOW_API_KEY"),
        )
    elif retrieval_provider in {"company", "company_graphrag_stub"}:
        retrieval = company_stub
    else:
        raise ValueError(f"unsupported retrieval provider: {retrieval_provider}")

    if memory_provider == "fake":
        _require_dev_fake("PSKA_MEMORY_PROVIDER", dev_fake)
        memory = FakeMemoryAdapter()
    elif memory_provider == "graphiti":
        _require_env("GRAPHITI_BASE_URL", provider="Graphiti memory")
        memory = GraphitiMemoryAdapter(
            base_url=os.getenv("GRAPHITI_BASE_URL"),
            group_id=os.getenv("GRAPHITI_GROUP_ID", "pska-essential"),
        )
    elif memory_provider in {"company", "company_graphrag_stub"}:
        memory = company_stub
    else:
        raise ValueError(f"unsupported memory provider: {memory_provider}")

    return WorkflowService(
        retrieval=retrieval,
        memory=memory,
        store=SQLiteReviewStore(os.getenv("PSKA_REVIEW_DB", ".pska-essential/review.sqlite3")),
    )


def _required_provider(name: str, dev_fake: bool) -> str:
    value = os.getenv(name, "").strip().lower()
    if value:
        return value
    if dev_fake:
        return "fake"
    raise ValueError(
        f"{name} is required. Configure an explicit provider; "
        "set PSKA_DEV_FAKE=1 only for local development or tests."
    )


def _require_dev_fake(name: str, dev_fake: bool) -> None:
    if not dev_fake:
        raise ValueError(f"{name}=fake is allowed only when PSKA_DEV_FAKE=1")


def _require_env(*names: str, provider: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError(f"{provider} is missing required env: {', '.join(missing)}")


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _kb_provider_is_fake(dev_fake: bool) -> bool:
    provider = os.getenv("PSKA_KB_PROVIDER", "").strip().lower()
    return provider == "fake" or (not provider and dev_fake)


def _fake_kb_corpus_loader(scope):
    gateway = build_kb_gateway_from_env()
    if getattr(gateway, "backend_name", "") != "fake":
        return []
    return gateway.retrieval_corpus(scope or {})
