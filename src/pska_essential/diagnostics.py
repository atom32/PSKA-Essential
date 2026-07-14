from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from pska_essential.audit import audit_event
from pska_essential.capabilities import memory_capabilities
from pska_essential.contracts import to_jsonable
from pska_essential.governance import build_workspace_policy_from_env
from pska_essential.readiness import evaluate_kb_readiness
from pska_essential.runtime_context import build_runtime_workspace_context


KbGatewayFactory = Callable[[], Any]


def build_runtime_diagnostics(*, service: Any, kb_gateway_factory: KbGatewayFactory) -> dict[str, Any]:
    checks = [
        _ok("product_api", "Product API is serving requests."),
        _review_store_check(service),
        _kb_gateway_check(kb_gateway_factory),
        _retrieval_check(service),
        _memory_check(service),
    ]
    return {
        "status": _overall_status(checks),
        "providers": {
            "retrieval": _provider_name("PSKA_RETRIEVAL_PROVIDER", getattr(service, "retrieval", None)),
            "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower() or "custom",
            "memory": _provider_name("PSKA_MEMORY_PROVIDER", getattr(service, "memory", None)),
            "dev_fake": _env_enabled("PSKA_DEV_FAKE"),
        },
        "workspace": build_runtime_workspace_context().to_dict(),
        "governance": build_workspace_policy_from_env().to_dict(),
        "capabilities": {
            "memory": memory_capabilities(service.memory),
        },
        "checks": checks,
    }


def run_retrieval_probe(
    service: Any,
    gateway: Any,
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    limit: int = 1,
    use_kg: bool = False,
) -> dict[str, Any]:
    selected_dataset_ids = _normalized_ids(dataset_ids)
    selected_document_ids = _normalized_ids(document_ids or [])
    if not selected_dataset_ids:
        raise ValueError("dataset_ids is required")
    normalized_question = question.strip() or "PSKA retrieval probe"
    scope = {
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "use_kg": bool(use_kg),
    }
    provider = _provider_name("PSKA_RETRIEVAL_PROVIDER", getattr(service, "retrieval", None))
    readiness = evaluate_kb_readiness(
        gateway,
        dataset_ids=selected_dataset_ids,
        document_ids=selected_document_ids,
    )
    if not readiness["ready"]:
        return {
            "status": "not_ready",
            "provider": provider,
            "message": "Selected knowledge scope is not ready, so retrieval probe was not run.",
            "query": normalized_question,
            "scope": scope,
            "readiness": readiness,
            "context_count": 0,
            "source_refs": [],
        }
    try:
        packets = service.retrieval.retrieve(
            normalized_question,
            scope,
            max(1, int(limit or 1)),
            options={"diagnostic": True, "use_kg": bool(use_kg)},
        )
    except Exception as exc:  # noqa: BLE001 - probe must return explicit provider errors.
        return {
            "status": "error",
            "provider": provider,
            "message": _retrieval_probe_error_message(exc),
            "query": normalized_question,
            "scope": scope,
            "readiness": readiness,
            "context_count": 0,
            "source_refs": [],
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }
    source_refs = [packet.source_ref for packet in packets]
    status = "ok" if packets else "warning"
    return {
        "status": status,
        "provider": provider,
        "message": (
            f"Retrieval provider returned {len(packets)} context packet(s)."
            if packets
            else "Retrieval provider responded but returned no context packets."
        ),
        "query": normalized_question,
        "scope": scope,
        "readiness": readiness,
        "context_count": len(packets),
        "source_refs": to_jsonable(source_refs),
    }


def add_retrieval_probe_audit(store: Any, probe: dict[str, Any]) -> None:
    scope = probe.get("scope") or {}
    dataset_ids = [str(item) for item in scope.get("dataset_ids") or []]
    document_ids = [str(item) for item in scope.get("document_ids") or []]
    error = probe.get("error") or {}
    store.add_audit_event(
        audit_event(
            "retrieval.probe",
            "retrieval_scope",
            ",".join(dataset_ids) or "unknown",
            provider=str(probe.get("provider") or ""),
            status=str(probe.get("status") or ""),
            dataset_ids=dataset_ids,
            document_ids=document_ids,
            use_kg=bool(scope.get("use_kg", False)),
            context_count=int(probe.get("context_count") or 0),
            readiness_status=str((probe.get("readiness") or {}).get("status") or ""),
            error_type=str(error.get("type") or ""),
            error_message=str(error.get("message") or ""),
        )
    )


def _review_store_check(service: Any) -> dict[str, Any]:
    try:
        service.store.list_reviews(limit=1)
    except Exception as exc:  # noqa: BLE001 - diagnostics must report explicit failures.
        return _error("review_store", f"Review store is unavailable: {exc}")
    return _ok("review_store", "Review store is available.")


def _kb_gateway_check(kb_gateway_factory: KbGatewayFactory) -> dict[str, Any]:
    try:
        gateway = kb_gateway_factory()
        provider = getattr(gateway, "backend_name", "custom")
        datasets = gateway.list_datasets(page_size=1)
    except Exception as exc:  # noqa: BLE001 - diagnostics must report explicit failures.
        return _error("kb_gateway", f"Knowledge base gateway is unavailable: {exc}")
    return _ok(
        "kb_gateway",
        "Knowledge base gateway is reachable.",
        provider=provider,
        dataset_sample_count=len(datasets),
    )


def _retrieval_check(service: Any) -> dict[str, Any]:
    provider = _provider_name("PSKA_RETRIEVAL_PROVIDER", getattr(service, "retrieval", None))
    if provider == "fake":
        return _fake_check("retrieval_provider")
    if provider == "ragflow":
        missing = _missing_env("RAGFLOW_BASE_URL", "RAGFLOW_API_KEY")
        if missing:
            return _error("retrieval_provider", f"RAGFlow retrieval is missing required env: {', '.join(missing)}")
        return _http_json_or_text_check(
            "retrieval_provider",
            os.environ["RAGFLOW_BASE_URL"].rstrip("/") + "/api/v1/system/ping",
            provider=provider,
            ok_message="RAGFlow retrieval backend is reachable.",
        )
    if provider in {"company", "company_graphrag_stub"}:
        return _ok("retrieval_provider", "Company GraphRAG retrieval stub is configured.", provider=provider)
    return _warning("retrieval_provider", f"Retrieval provider is configured through an injected adapter: {provider}")


def _memory_check(service: Any) -> dict[str, Any]:
    provider = _provider_name("PSKA_MEMORY_PROVIDER", getattr(service, "memory", None))
    if provider == "fake":
        return _fake_check("memory_provider")
    if provider == "graphiti":
        missing = _missing_env("GRAPHITI_BASE_URL")
        if missing:
            return _error("memory_provider", "Graphiti memory is missing required env: GRAPHITI_BASE_URL")
        return _http_json_or_text_check(
            "memory_provider",
            os.environ["GRAPHITI_BASE_URL"].rstrip("/") + "/healthcheck",
            provider=provider,
            ok_message="Graphiti memory backend is reachable.",
        )
    if provider in {"company", "company_graphrag_stub"}:
        return _ok("memory_provider", "Company GraphRAG memory stub is configured.", provider=provider)
    return _warning("memory_provider", f"Memory provider is configured through an injected adapter: {provider}")


def _http_json_or_text_check(name: str, url: str, *, provider: str, ok_message: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=float(os.getenv("PSKA_DIAGNOSTICS_TIMEOUT", "3"))) as response:
            raw = response.read().decode("utf-8")
    except URLError as exc:
        return _error(name, f"{provider} health check failed: {exc}", provider=provider)
    status = "ok"
    if raw:
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw.strip()
        if payload not in ("pong", {"status": "healthy"}):
            status = "warning"
    check = _check(name, status, ok_message, provider=provider)
    check["metadata"]["health_checked"] = True
    return check


def _fake_check(name: str) -> dict[str, Any]:
    if _env_enabled("PSKA_DEV_FAKE"):
        return _ok(name, "Explicit fake provider is enabled for local development.", provider="fake")
    return _warning(name, "Fake provider is injected without PSKA_DEV_FAKE=1; use only in tests.", provider="fake")


def _provider_name(env_name: str, adapter: Any) -> str:
    env_value = os.getenv(env_name, "").strip().lower()
    if env_value:
        return env_value
    return str(getattr(adapter, "backend_name", None) or "custom").strip().lower()


def _missing_env(*names: str) -> list[str]:
    return [name for name in names if not os.getenv(name, "").strip()]


def _normalized_ids(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _retrieval_probe_error_message(exc: Exception) -> str:
    raw = str(exc) or exc.__class__.__name__
    if "not found for model" in raw and "Provider" in raw:
        return (
            f"Retrieval provider failed: {raw}. "
            "Check the KB embedding model and model-provider configuration before running Ask."
        )
    return f"Retrieval provider failed: {raw}"


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _ok(name: str, message: str, **metadata: Any) -> dict[str, Any]:
    return _check(name, "ok", message, **metadata)


def _warning(name: str, message: str, **metadata: Any) -> dict[str, Any]:
    return _check(name, "warning", message, **metadata)


def _error(name: str, message: str, **metadata: Any) -> dict[str, Any]:
    return _check(name, "error", message, **metadata)


def _check(name: str, status: str, message: str, **metadata: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, "metadata": metadata}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}
