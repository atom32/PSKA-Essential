from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_TEI_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.8"
DEFAULT_DELIVERY_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_LOCAL_MODEL = "BAAI/bge-m3"
DEFAULT_HOST_PORT = "6380"
DEFAULT_COMPOSE_PRIVATE_URL = "http://pska-embedding:80"


def build_embedding_component_status(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return PSKA's product-level view of the embedding component.

    Embedding is deliberately modeled as a RAGFlow-side component. PSKA should
    surface whether the component is local-dev, delivery-container, external, or
    disabled, but product flows still go through PSKA -> RAGFlow instead of
    letting Hermes/WebUI call an embedding service directly.
    """

    env = environ or os.environ
    components_root = Path(_env(env, "PSKA_COMPONENTS_ROOT") or Path.home() / "PSKA-Components").expanduser()
    component_path = Path(
        _first_env(env, "PSKA_INFINITY_EMB_COMPONENT_PATH", "PSKA_EMBEDDING_COMPONENT_PATH")
        or components_root / "infinity-emb"
    ).expanduser()
    launchd_label = _env(env, "PSKA_EMBEDDING_LAUNCHD_LABEL") or "com.yuxi.infinity-emb"
    host_port = _first_env(env, "PSKA_EMBEDDING_HOST_PORT", "EMBEDDING_HOST_PORT") or DEFAULT_HOST_PORT
    explicit_url = _first_env(env, "PSKA_EMBEDDING_BASE_URL", "EMBEDDING_BASE_URL")
    host_base_url = explicit_url or f"http://127.0.0.1:{host_port}"
    ragflow_tei_url = _env(env, "RAGFLOW_TEI_BASE_URL")
    delivery_image = _env(env, "EMBEDDING_IMAGE") or DEFAULT_TEI_IMAGE
    delivery_model = _env(env, "EMBEDDING_MODEL_ID") or DEFAULT_DELIVERY_MODEL
    explicit_model = _first_env(env, "PSKA_EMBEDDING_MODEL_ID", "PSKA_V027_EMBEDDING_MODEL")
    runtime_hint = _env(env, "PSKA_EMBEDDING_RUNTIME").lower()
    enabled_value = _env(env, "EMBEDDING_ENABLED")
    embedding_enabled = enabled_value != "0"
    source_exists = component_path.exists()
    infinity_venv_exists = (component_path / ".venv").exists()
    launchd_plist = Path.home() / "Library" / "LaunchAgents" / f"{launchd_label}.plist"

    mode = _component_mode(
        runtime_hint=runtime_hint,
        embedding_enabled=embedding_enabled,
        enabled_configured=bool(enabled_value),
        source_exists=source_exists,
        infinity_venv_exists=infinity_venv_exists,
        explicit_url=bool(explicit_url),
        ragflow_tei_url=ragflow_tei_url,
    )
    model = _selected_model(
        mode=mode,
        explicit_model=explicit_model,
        delivery_model=delivery_model,
    )
    ragflow_expected_url = _ragflow_expected_url(
        mode=mode,
        ragflow_tei_url=ragflow_tei_url,
        host_base_url=host_base_url,
    )

    return {
        "schema": "pska.embedding_component_status.v1",
        "name": "embedding",
        "kind": "embedding_provider",
        "status": _status(mode),
        "mode": mode,
        "summary": _summary(mode),
        "paths": {
            "components_root": str(components_root),
            "local_component": str(component_path),
            "local_component_exists": source_exists,
            "local_venv_exists": infinity_venv_exists,
            "launchd_label": launchd_label,
            "launchd_plist": str(launchd_plist),
            "launchd_plist_exists": launchd_plist.is_file(),
        },
        "runtime": {
            "product_flow_status": _product_flow_status(mode),
            "direct_pska_dependency": False,
            "pska_starts_service": False,
            "frontend_direct_access_allowed": False,
            "hermes_direct_access_allowed": False,
            "used_by": ["RAGFlow document ingestion", "RAGFlow chunk retrieval"],
        },
        "model": {
            "configured": model,
            "delivery_default": delivery_model,
            "local_dev_default": DEFAULT_LOCAL_MODEL,
        },
        "endpoints": {
            "host_base_url": host_base_url,
            "host_health_url": f"{host_base_url.rstrip('/')}/health",
            "product_url_configured": bool(explicit_url),
            "ragflow_tei_base_url_configured": bool(ragflow_tei_url),
            "ragflow_tei_base_url": ragflow_tei_url,
            "compose_private_url": DEFAULT_COMPOSE_PRIVATE_URL,
            "ragflow_expected_url": ragflow_expected_url,
            "probed": False,
        },
        "delivery": {
            "managed_by": "deploy/full-compose",
            "runtime": "tei_container",
            "enabled": embedding_enabled,
            "image": delivery_image,
            "profile": "embedding",
            "host_port": host_port,
            "ragflow_private_url": DEFAULT_COMPOSE_PRIVATE_URL,
        },
        "local_dev": {
            "runtime": "infinity_emb",
            "enabled_by_current_machine": mode == "local_infinity_dev",
            "host_port": host_port,
            "model": explicit_model or DEFAULT_LOCAL_MODEL,
            "launchd_label": launchd_label,
        },
        "governance": {
            "adapter_boundary": "RAGFlow embedding provider configuration",
            "webui_calls_embedding_directly": False,
            "hermes_calls_embedding_directly": False,
            "allowed_flow": "Hermes/WebUI -> PSKA -> RAGFlow -> embedding",
        },
        "checks": _checks(
            mode=mode,
            source_exists=source_exists,
            infinity_venv_exists=infinity_venv_exists,
            embedding_enabled=embedding_enabled,
            delivery_image=delivery_image,
            model=model,
            ragflow_tei_url=ragflow_tei_url,
        ),
        "next_actions": _next_actions(mode),
    }


def _component_mode(
    *,
    runtime_hint: str,
    embedding_enabled: bool,
    enabled_configured: bool,
    source_exists: bool,
    infinity_venv_exists: bool,
    explicit_url: bool,
    ragflow_tei_url: str,
) -> str:
    if runtime_hint in {"disabled", "none", "off"} or not embedding_enabled:
        if ragflow_tei_url or explicit_url:
            return "external_http_embedding"
        return "disabled"
    if runtime_hint in {"local", "local_infinity", "infinity", "infinity_emb"}:
        return "local_infinity_dev"
    if runtime_hint in {"tei", "tei_container", "delivery", "compose"}:
        return "tei_container_delivery"
    if ragflow_tei_url and "pska-embedding" not in ragflow_tei_url:
        return "external_http_embedding"
    if enabled_configured:
        return "tei_container_delivery"
    if source_exists and infinity_venv_exists:
        return "local_infinity_dev"
    if explicit_url:
        return "external_http_embedding"
    return "not_configured"


def _status(mode: str) -> str:
    if mode in {"local_infinity_dev", "tei_container_delivery", "external_http_embedding"}:
        return "configured"
    if mode == "disabled":
        return "disabled"
    return "unconfigured"


def _summary(mode: str) -> str:
    summaries = {
        "local_infinity_dev": (
            "Embedding is modeled as the local Apple Silicon development service, usually "
            "Infinity Embeddings on port 6380."
        ),
        "tei_container_delivery": (
            "Embedding is modeled as the delivery TEI container used by full compose."
        ),
        "external_http_embedding": (
            "Embedding is modeled as an externally configured HTTP service."
        ),
        "disabled": (
            "PSKA-managed embedding is disabled; RAGFlow may require manual provider configuration."
        ),
        "not_configured": (
            "No embedding runtime shape is configured or detected."
        ),
    }
    return summaries.get(mode, "Embedding component status is unknown.")


def _product_flow_status(mode: str) -> str:
    if mode == "local_infinity_dev":
        return "ragflow_uses_local_dev_embedding"
    if mode == "tei_container_delivery":
        return "ragflow_uses_delivery_embedding_container"
    if mode == "external_http_embedding":
        return "ragflow_uses_external_embedding_service"
    if mode == "disabled":
        return "ragflow_embedding_provider_must_be_configured_manually"
    return "embedding_runtime_not_configured"


def _selected_model(*, mode: str, explicit_model: str, delivery_model: str) -> str:
    if explicit_model:
        return explicit_model
    if mode == "local_infinity_dev":
        return DEFAULT_LOCAL_MODEL
    return delivery_model


def _ragflow_expected_url(*, mode: str, ragflow_tei_url: str, host_base_url: str) -> str:
    if ragflow_tei_url:
        return ragflow_tei_url
    if mode == "tei_container_delivery":
        return DEFAULT_COMPOSE_PRIVATE_URL
    if mode in {"local_infinity_dev", "external_http_embedding"}:
        return host_base_url
    return ""


def _checks(
    *,
    mode: str,
    source_exists: bool,
    infinity_venv_exists: bool,
    embedding_enabled: bool,
    delivery_image: str,
    model: str,
    ragflow_tei_url: str,
) -> list[dict[str, Any]]:
    return [
        _check(
            "pska_boundary",
            "ok",
            "PSKA does not expose embedding as a direct Hermes/WebUI dependency.",
        ),
        _check(
            "local_infinity_runtime",
            "ok" if source_exists and infinity_venv_exists else "warning",
            "Local Infinity Embeddings checkout and virtualenv are present."
            if source_exists and infinity_venv_exists
            else "Local Infinity Embeddings checkout or virtualenv is missing.",
        ),
        _check(
            "delivery_tei_runtime",
            "ok" if embedding_enabled and delivery_image else "warning",
            "Delivery TEI embedding image is configured."
            if embedding_enabled and delivery_image
            else "Delivery TEI embedding image is disabled or missing.",
        ),
        _check(
            "model",
            "ok" if model else "warning",
            f"Embedding model is {model}." if model else "Embedding model is not configured.",
        ),
        _check(
            "ragflow_endpoint",
            "ok" if mode in {"local_infinity_dev", "tei_container_delivery", "external_http_embedding"} else "warning",
            (
                f"RAGFlow embedding endpoint is configured as {ragflow_tei_url}."
                if ragflow_tei_url
                else "RAGFlow will use the default endpoint for this runtime shape."
            ),
        ),
    ]


def _next_actions(mode: str) -> list[dict[str, Any]]:
    if mode == "local_infinity_dev":
        return [
            {
                "action": "keep_delivery_embedding_container_as_target",
                "label": "Keep delivery embedding image",
                "reason": "Current machine uses Infinity for development; full-compose still uses TEI for delivery.",
                "view": "settings",
            }
        ]
    if mode == "tei_container_delivery":
        return [
            {
                "action": "verify_embedding_container",
                "label": "Verify embedding container",
                "reason": "Run full-compose preflight or embedding-up before a delivery demo.",
                "command": "make full-compose-preflight && make full-compose-embedding-up",
                "view": "settings",
            }
        ]
    if mode == "disabled":
        return [
            {
                "action": "configure_embedding_provider",
                "label": "Configure embedding provider",
                "reason": "RAGFlow document parsing may block unless an embedding provider is configured.",
                "view": "settings",
            }
        ]
    return []


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _env(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name) or "").strip()


def _first_env(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = _env(env, name)
        if value:
            return value
    return ""
