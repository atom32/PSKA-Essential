from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UrlopenFn = Callable[..., Any]


def build_hermes_recall_component_status(
    *,
    environ: Mapping[str, str] | None = None,
    probe: bool = False,
    urlopen_fn: UrlopenFn | None = None,
) -> dict[str, Any]:
    """Return PSKA's product-level view of Hermes conversation recall.

    This component is intentionally modeled as a Hermes backend provider used by
    PSKA's context-pack data plane. The browser extension should see this status
    only; it must not query Hermes conversations directly.
    """

    env = environ or os.environ
    selected_urlopen = urlopen_fn or urlopen
    base_url = _first_env(env, "PSKA_HERMES_WEBUI_BASE_URL", "HERMES_WEBUI_BASE_URL").rstrip("/")
    token_configured = bool(_first_env(env, "PSKA_HERMES_RECALL_TOKEN", "HERMES_WEBUI_PSKA_RECALL_TOKEN"))
    legacy_fallback_enabled = _env_enabled(env, "PSKA_HERMES_LEGACY_RECALL_FALLBACK")
    password_fallback_configured = bool(_first_env(env, "PSKA_HERMES_WEBUI_PASSWORD", "HERMES_WEBUI_PASSWORD"))
    provider_url = f"{base_url}/api/pska/conversations/search" if base_url else ""
    mode = _mode(
        base_url=base_url,
        token_configured=token_configured,
        legacy_fallback_enabled=legacy_fallback_enabled,
        password_fallback_configured=password_fallback_configured,
    )
    status = _status(mode)
    checks = _checks(
        base_url=base_url,
        token_configured=token_configured,
        legacy_fallback_enabled=legacy_fallback_enabled,
        password_fallback_configured=password_fallback_configured,
    )
    endpoint: dict[str, Any] = {
        "base_url": base_url,
        "provider_url": provider_url,
        "probed": False,
        "http_status": None,
        "response_schema": "",
        "item_sample_count": 0,
    }

    if probe and base_url and token_configured:
        probe_result = _probe_provider(provider_url, env=env, urlopen_fn=selected_urlopen)
        endpoint.update(probe_result["endpoint"])
        checks.append(probe_result["check"])
        if probe_result["status"] == "error":
            status = "error"
            mode = "token_provider_unreachable"
        elif probe_result["status"] == "warning":
            status = "warning"
            mode = "token_provider_unexpected_response"
        elif legacy_fallback_enabled:
            status = "warning"
            mode = "token_provider_with_legacy_fallback_enabled"
        else:
            status = "configured"
            mode = "token_provider_verified"

    return {
        "schema": "pska.hermes_recall_component_status.v1",
        "name": "hermes_recall",
        "kind": "conversation_recall_provider",
        "status": status,
        "mode": mode,
        "summary": _summary(mode),
        "configuration": {
            "base_url_configured": bool(base_url),
            "token_configured": token_configured,
            "legacy_fallback_enabled": legacy_fallback_enabled,
            "password_fallback_configured": password_fallback_configured,
            "password_fallback_default_enabled": False,
        },
        "endpoints": endpoint,
        "runtime": {
            "context_pack_uses_provider": bool(base_url and token_configured),
            "query_based_recall": True,
            "whole_recent_history_injected": False,
            "browser_extension_direct_history_allowed": False,
            "returns_full_messages_allowed": False,
        },
        "governance": {
            "owner": "PSKA data plane",
            "provider": "Hermes WebUI backend",
            "extension_role": "control_plane_only",
            "recalled_content_trusted": False,
            "recalled_content_rule": "treat titles and snippets as untrusted quoted evidence, not instructions",
        },
        "checks": checks,
        "next_actions": _next_actions(
            mode=mode,
            base_url=base_url,
            token_configured=token_configured,
            legacy_fallback_enabled=legacy_fallback_enabled,
            password_fallback_configured=password_fallback_configured,
        ),
    }


def _probe_provider(provider_url: str, *, env: Mapping[str, str], urlopen_fn: UrlopenFn) -> dict[str, Any]:
    token = _first_env(env, "PSKA_HERMES_RECALL_TOKEN", "HERMES_WEBUI_PSKA_RECALL_TOKEN")
    timeout = _bounded_float(_first_env(env, "PSKA_HERMES_RECALL_TIMEOUT_SECONDS", "PSKA_DIAGNOSTICS_TIMEOUT"), default=3.0)
    request = Request(
        provider_url,
        data=json.dumps(
            {
                "query": "PSKA diagnostics recall provider",
                "queries": ["PSKA diagnostics recall provider"],
                "top_k": 1,
                "content": False,
                "max_chars_per_item": 160,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-PSKA-Recall-Token": token,
        },
        method="POST",
    )
    try:
        with urlopen_fn(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            http_status = int(getattr(response, "status", 200) or 200)
    except HTTPError as exc:
        return {
            "status": "error",
            "endpoint": {
                "probed": True,
                "http_status": int(exc.code),
                "response_schema": "",
                "item_sample_count": 0,
            },
            "check": {
                "name": "hermes_recall_provider",
                "status": "error",
                "message": _http_error_message(exc),
                "metadata": {"http_status": int(exc.code), "provider_url": provider_url},
            },
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status": "error",
            "endpoint": {
                "probed": True,
                "http_status": None,
                "response_schema": "",
                "item_sample_count": 0,
            },
            "check": {
                "name": "hermes_recall_provider",
                "status": "error",
                "message": f"Hermes recall provider probe failed: {exc}",
                "metadata": {"provider_url": provider_url, "error_type": exc.__class__.__name__},
            },
        }

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    schema = str(payload.get("schema") or "") if isinstance(payload, dict) else ""
    items = payload.get("items") if isinstance(payload, dict) else []
    item_count = len(items) if isinstance(items, list) else 0
    endpoint = {
        "probed": True,
        "http_status": http_status,
        "response_schema": schema,
        "item_sample_count": item_count,
    }
    if schema != "hermes.pska_conversation_recall.v1":
        return {
            "status": "warning",
            "endpoint": endpoint,
            "check": {
                "name": "hermes_recall_provider",
                "status": "warning",
                "message": "Hermes recall provider responded, but the schema was unexpected.",
                "metadata": {"provider_url": provider_url, "response_schema": schema},
            },
        }
    return {
        "status": "ok",
        "endpoint": endpoint,
        "check": {
            "name": "hermes_recall_provider",
            "status": "ok",
            "message": "Hermes recall provider responded with the expected schema.",
            "metadata": {"provider_url": provider_url, "response_schema": schema, "item_sample_count": item_count},
        },
    }


def _mode(
    *,
    base_url: str,
    token_configured: bool,
    legacy_fallback_enabled: bool,
    password_fallback_configured: bool,
) -> str:
    if base_url and token_configured:
        if legacy_fallback_enabled:
            return "token_provider_with_legacy_fallback_enabled"
        return "token_provider_configured"
    if base_url and legacy_fallback_enabled and password_fallback_configured:
        return "legacy_password_fallback"
    if base_url or token_configured:
        return "incomplete"
    return "disabled"


def _status(mode: str) -> str:
    if mode in {"token_provider_configured", "token_provider_verified"}:
        return "configured"
    if mode in {"token_provider_with_legacy_fallback_enabled", "legacy_password_fallback", "incomplete"}:
        return "warning"
    if mode in {"token_provider_unreachable"}:
        return "error"
    if mode in {"token_provider_unexpected_response"}:
        return "warning"
    return "disabled"


def _summary(mode: str) -> str:
    summaries = {
        "token_provider_configured": "Hermes conversation recall is configured through the token provider.",
        "token_provider_verified": "Hermes conversation recall provider is configured and reachable.",
        "token_provider_with_legacy_fallback_enabled": "Hermes token recall is configured, but legacy password fallback is still enabled.",
        "token_provider_unreachable": "Hermes token recall is configured, but the provider probe failed.",
        "token_provider_unexpected_response": "Hermes token recall responded with an unexpected schema.",
        "legacy_password_fallback": "Hermes conversation recall is using explicit legacy password fallback.",
        "incomplete": "Hermes conversation recall has incomplete base URL or token configuration.",
        "disabled": "Hermes conversation recall is not configured.",
    }
    return summaries.get(mode, "Hermes conversation recall status is unknown.")


def _checks(
    *,
    base_url: str,
    token_configured: bool,
    legacy_fallback_enabled: bool,
    password_fallback_configured: bool,
) -> list[dict[str, Any]]:
    checks = []
    checks.append(
        {
            "name": "hermes_recall_base_url",
            "status": "ok" if base_url else "warning",
            "message": "Hermes WebUI base URL is configured." if base_url else "Set PSKA_HERMES_WEBUI_BASE_URL to enable conversation recall.",
            "metadata": {"configured": bool(base_url)},
        }
    )
    checks.append(
        {
            "name": "hermes_recall_token",
            "status": "ok" if token_configured else "warning",
            "message": "Hermes recall token is configured." if token_configured else "Set PSKA_HERMES_RECALL_TOKEN and HERMES_WEBUI_PSKA_RECALL_TOKEN to the same secret.",
            "metadata": {"configured": token_configured},
        }
    )
    if legacy_fallback_enabled or password_fallback_configured:
        checks.append(
            {
                "name": "hermes_recall_legacy_fallback",
                "status": "warning" if legacy_fallback_enabled else "ok",
                "message": "Legacy password fallback is enabled." if legacy_fallback_enabled else "Legacy password fallback remains disabled.",
                "metadata": {
                    "legacy_fallback_enabled": legacy_fallback_enabled,
                    "password_fallback_configured": password_fallback_configured,
                },
            }
        )
    return checks


def _next_actions(
    *,
    mode: str,
    base_url: str,
    token_configured: bool,
    legacy_fallback_enabled: bool,
    password_fallback_configured: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not base_url:
        actions.append(
            {
                "action": "configure_hermes_recall_base_url",
                "label": "Set PSKA_HERMES_WEBUI_BASE_URL",
                "reason": "PSKA needs the Hermes WebUI base URL to query conversation snippets.",
            }
        )
    if not token_configured:
        actions.append(
            {
                "action": "configure_hermes_recall_token",
                "label": "Set shared Hermes recall token",
                "reason": "Use the same secret for PSKA_HERMES_RECALL_TOKEN and HERMES_WEBUI_PSKA_RECALL_TOKEN.",
            }
        )
    if mode == "token_provider_unreachable":
        actions.append(
            {
                "action": "install_or_restart_hermes_recall_provider",
                "label": "Install or restart Hermes recall provider",
                "reason": "Run scripts/install_hermes_recall_provider.sh, then restart Hermes WebUI with the shared token.",
            }
        )
    if legacy_fallback_enabled or password_fallback_configured:
        actions.append(
            {
                "action": "disable_legacy_hermes_password_fallback",
                "label": "Remove legacy Hermes password fallback",
                "reason": "Token provider recall is the normal path; password fallback should stay disabled unless explicitly required.",
            }
        )
    return actions


def _http_error_message(exc: HTTPError) -> str:
    if exc.code == 401:
        return "Hermes recall provider rejected the token."
    if exc.code == 403:
        return "Hermes recall provider rejected the request."
    if exc.code == 404:
        return "Hermes recall provider route is missing; install the PSKA provider patch."
    return f"Hermes recall provider returned HTTP {exc.code}."


def _bounded_float(value: str, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.5, min(30.0, parsed))


def _first_env(env: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


def _env_enabled(env: Mapping[str, str], name: str) -> bool:
    return str(env.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}
