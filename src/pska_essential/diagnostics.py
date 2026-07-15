from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from pska_essential.agentic_loop import run_agentic_question_with_readiness
from pska_essential.audit import audit_event
from pska_essential.capabilities import memory_capabilities
from pska_essential.contracts import to_jsonable
from pska_essential.governance import DURABLE_PROPOSAL_KINDS, build_workspace_policy_from_env
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
    try:
        readiness = evaluate_kb_readiness(
            gateway,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )
    except Exception as exc:  # noqa: BLE001 - probes should report backend readiness failures.
        return {
            "status": "readiness_error",
            "provider": provider,
            "message": f"Readiness check failed before retrieval: {exc}",
            "query": normalized_question,
            "scope": scope,
            "readiness": None,
            "context_count": 0,
            "source_refs": [],
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }
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


def run_live_closed_loop_probe(
    service: Any,
    gateway: Any,
    *,
    question: str,
    dataset_ids: list[str],
    document_ids: list[str] | None = None,
    limit: int = 3,
    proposal_kind: str = "writing_brief",
    use_kg: bool = False,
    export_format: str = "json",
    source_inspection_limit: int = 1,
) -> dict[str, Any]:
    """Run a real configured-provider closed-loop check.

    This is a product diagnostic, not a test fixture: fake KB or fake
    retrieval providers are rejected so a successful result proves that the
    configured live substrates can support a sourced Ask/export workflow.
    """

    selected_dataset_ids = _normalized_ids(dataset_ids)
    selected_document_ids = _normalized_ids(document_ids or [])
    if not selected_dataset_ids:
        raise ValueError("dataset_ids is required")

    normalized_question = question.strip() or "PSKA live closed-loop probe"
    normalized_proposal_kind = proposal_kind.strip().lower() or "writing_brief"
    selected_limit = max(1, int(limit or 1))
    selected_source_inspection_limit = max(0, int(source_inspection_limit or 0))
    providers = {
        "kb": str(getattr(gateway, "backend_name", None) or os.getenv("PSKA_KB_PROVIDER", "") or "custom").lower(),
        "retrieval": _provider_name("PSKA_RETRIEVAL_PROVIDER", getattr(service, "retrieval", None)),
        "memory": _provider_name("PSKA_MEMORY_PROVIDER", getattr(service, "memory", None)),
    }
    scope = {
        "dataset_ids": selected_dataset_ids,
        "document_ids": selected_document_ids,
        "use_kg": bool(use_kg),
    }
    steps: list[dict[str, Any]] = []

    def add_step(name: str, status: str, message: str, **metadata: Any) -> None:
        steps.append({"name": name, "status": status, "message": message, "metadata": metadata})

    fake_providers = [name for name in ("kb", "retrieval") if providers.get(name) == "fake"]
    if normalized_proposal_kind in DURABLE_PROPOSAL_KINDS:
        add_step(
            "governance.check",
            "blocked",
            "Live closed-loop probe is transient-only and must not write durable workspace knowledge.",
            proposal_kind=normalized_proposal_kind,
        )
        return {
            "kind": "live_closed_loop_probe",
            "status": "invalid_configuration",
            "message": (
                "Live closed-loop probe only supports transient work products. "
                "Use the normal Ask/review/apply workflow for durable memory or graph changes."
            ),
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "context_count": 0,
            "export": None,
        }

    if fake_providers:
        add_step(
            "provider.check",
            "blocked",
            "Live closed-loop probe requires non-fake KB and retrieval providers.",
            fake_providers=fake_providers,
        )
        return {
            "kind": "live_closed_loop_probe",
            "status": "invalid_configuration",
            "message": (
                "Live closed-loop probe requires real configured KB and retrieval providers. "
                "Fake adapters remain limited to explicit local development and tests."
            ),
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "context_count": 0,
            "export": None,
        }

    add_step("provider.check", "complete", "Configured providers are not fake.", providers=providers)
    try:
        readiness = evaluate_kb_readiness(
            gateway,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should return explicit readiness failures.
        add_step("kb.readiness", "error", f"Readiness check failed: {exc}", error_type=exc.__class__.__name__)
        return {
            "kind": "live_closed_loop_probe",
            "status": "readiness_error",
            "message": f"Readiness check failed before retrieval: {exc}",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": None,
            "context_count": 0,
            "export": None,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
    add_step(
        "kb.readiness",
        "complete" if readiness.get("ready") else "blocked",
        readiness.get("message") or "Selected knowledge scope readiness checked.",
        readiness_status=readiness.get("status"),
        blocking=readiness.get("blocking") or [],
    )
    if not readiness.get("ready"):
        return {
            "kind": "live_closed_loop_probe",
            "status": "not_ready",
            "message": "Selected knowledge scope is not ready; retrieval and Ask were not run.",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": readiness,
            "context_count": 0,
            "export": None,
        }

    retrieval_probe = run_retrieval_probe(
        service,
        gateway,
        question=normalized_question,
        dataset_ids=selected_dataset_ids,
        document_ids=selected_document_ids,
        limit=1,
        use_kg=use_kg,
    )
    add_step(
        "retrieval.probe",
        "complete" if retrieval_probe.get("status") == "ok" else str(retrieval_probe.get("status") or "error"),
        retrieval_probe.get("message") or "Retrieval probe finished.",
        context_count=int(retrieval_probe.get("context_count") or 0),
    )
    if retrieval_probe.get("status") != "ok":
        probe_status = str(retrieval_probe.get("status") or "error")
        return {
            "kind": "live_closed_loop_probe",
            "status": f"retrieval_{probe_status}",
            "message": "Retrieval did not return usable context; Ask/export were not run.",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": readiness,
            "retrieval_probe": retrieval_probe,
            "context_count": 0,
            "export": None,
        }

    try:
        ask_result = run_agentic_question_with_readiness(
            service,
            gateway,
            question=normalized_question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=selected_limit,
            proposal_kind=normalized_proposal_kind,
            use_kg=use_kg,
            max_iterations=2,
            min_context_packets=1,
            retrieval_queries=[],
            source_inspection_limit=selected_source_inspection_limit,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should return explicit failures.
        add_step("agentic.ask", "error", f"Agentic Ask failed: {exc}", error_type=exc.__class__.__name__)
        return {
            "kind": "live_closed_loop_probe",
            "status": "agentic_error",
            "message": f"Agentic Ask failed: {exc}",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": readiness,
            "retrieval_probe": retrieval_probe,
            "context_count": 0,
            "export": None,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }

    ask_status = str(ask_result.get("status") or "unknown")
    context_count = len(ask_result.get("context_packets") or [])
    run_id = str(((ask_result.get("run") or {}).get("run_id")) or "")
    add_step(
        "agentic.ask",
        "complete" if ask_status == "ready" else ask_status,
        "Agentic Ask produced a sourced work product." if ask_status == "ready" else "Agentic Ask did not become ready.",
        ask_status=ask_status,
        run_id=run_id,
        context_count=context_count,
    )
    if ask_status != "ready":
        return {
            "kind": "live_closed_loop_probe",
            "status": f"agentic_{ask_status}",
            "message": "Agentic Ask did not produce a ready sourced work product; export was not run.",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": readiness,
            "retrieval_probe": retrieval_probe,
            "ask": _ask_probe_summary(ask_result),
            "context_count": context_count,
            "export": None,
        }

    try:
        exported = service.export_brief(run_id, export_format)
    except Exception as exc:  # noqa: BLE001 - diagnostics should return explicit failures.
        add_step("workflow.export", "error", f"Workflow export failed: {exc}", run_id=run_id)
        return {
            "kind": "live_closed_loop_probe",
            "status": "export_error",
            "message": f"Workflow export failed: {exc}",
            "providers": providers,
            "query": normalized_question,
            "scope": scope,
            "steps": steps,
            "readiness": readiness,
            "retrieval_probe": retrieval_probe,
            "ask": _ask_probe_summary(ask_result),
            "context_count": context_count,
            "run_id": run_id,
            "export": None,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }

    export_summary = _export_probe_summary(exported)
    add_step(
        "workflow.export",
        "complete",
        "Exported sourced work product.",
        run_id=run_id,
        requested_format=export_format,
        **export_summary,
    )
    return {
        "kind": "live_closed_loop_probe",
        "status": "ok",
        "message": "Live configured providers completed readiness, retrieval, Ask, source inspection, and export.",
        "providers": providers,
        "query": normalized_question,
        "scope": scope,
        "steps": steps,
        "readiness": readiness,
        "retrieval_probe": retrieval_probe,
        "ask": _ask_probe_summary(ask_result),
        "context_count": context_count,
        "source_count": int(export_summary.get("source_count") or 0),
        "source_inspection_count": int(export_summary.get("source_inspection_count") or 0),
        "run_id": run_id,
        "export": export_summary,
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


def add_live_closed_loop_probe_audit(store: Any, probe: dict[str, Any]) -> None:
    scope = probe.get("scope") or {}
    dataset_ids = [str(item) for item in scope.get("dataset_ids") or []]
    document_ids = [str(item) for item in scope.get("document_ids") or []]
    providers = probe.get("providers") or {}
    readiness = probe.get("readiness") or {}
    retrieval_probe = probe.get("retrieval_probe") or {}
    error = probe.get("error") or {}
    run_id = str(probe.get("run_id") or "")
    store.add_audit_event(
        audit_event(
            "closed_loop.probe",
            "workflow" if run_id else "retrieval_scope",
            run_id or ",".join(dataset_ids) or "unknown",
            status=str(probe.get("status") or ""),
            dataset_ids=dataset_ids,
            document_ids=document_ids,
            providers=providers,
            readiness_status=str(readiness.get("status") or ""),
            retrieval_status=str(retrieval_probe.get("status") or ""),
            context_count=int(probe.get("context_count") or 0),
            source_count=int(probe.get("source_count") or 0),
            source_inspection_count=int(probe.get("source_inspection_count") or 0),
            exported=bool(probe.get("export")),
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


def _ask_probe_summary(ask_result: dict[str, Any]) -> dict[str, Any]:
    run = ask_result.get("run") or {}
    proposal = ask_result.get("proposal") or {}
    loop = ask_result.get("loop") or {}
    return {
        "status": ask_result.get("status"),
        "run_id": run.get("run_id"),
        "proposal_id": proposal.get("proposal_id"),
        "proposal_kind": proposal.get("kind"),
        "context_count": len(ask_result.get("context_packets") or []),
        "source_count": len({json.dumps(packet.get("source_ref") or {}, sort_keys=True) for packet in ask_result.get("context_packets") or []}),
        "source_inspection_count": int(loop.get("source_inspection_count") or 0),
        "review_required": bool(loop.get("review_required", False)),
        "durable_proposal": bool(loop.get("durable_proposal", False)),
    }


def _export_probe_summary(exported: Any) -> dict[str, Any]:
    if isinstance(exported, dict):
        traceability = exported.get("traceability") or {}
        latest_proposal = exported.get("latest_proposal") or {}
        return {
            "exported": True,
            "format": "json",
            "source_count": int(traceability.get("source_count") or 0),
            "context_count": int(traceability.get("context_count") or 0),
            "source_inspection_count": int(traceability.get("source_inspection_count") or 0),
            "proposal_kind": latest_proposal.get("kind") or "",
        }
    text = str(exported)
    return {
        "exported": True,
        "format": "text",
        "byte_length": len(text.encode("utf-8")),
    }


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
