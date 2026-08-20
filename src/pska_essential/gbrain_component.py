from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping


CommandResolver = Callable[[str], str | None]


def build_gbrain_component_status(
    *,
    environ: Mapping[str, str] | None = None,
    command_resolver: CommandResolver = shutil.which,
) -> dict[str, Any]:
    """Return PSKA's product-level view of the optional GBrain component.

    This is intentionally status-only. PSKA does not start GBrain and does not
    register it directly with Hermes. GBrain participates only when PSKA itself
    is configured to use the governed HTTP MemoryPort adapter.
    """

    env = environ or os.environ
    components_root = Path(_env(env, "PSKA_COMPONENTS_ROOT") or Path.home() / "PSKA-Components").expanduser()
    component_path = Path(_env(env, "PSKA_GBRAIN_COMPONENT_PATH") or components_root / "gbrain").expanduser()
    registry_path = Path(_env(env, "PSKA_COMPONENTS_REGISTRY") or components_root / "components.yaml").expanduser()
    package_json = component_path / "package.json"
    source_exists = component_path.exists()
    package = _read_package_json(package_json)
    gbrain_bin = _command_path("gbrain", env=env, env_key="GBRAIN_BIN", command_resolver=command_resolver)
    bun_bin = _command_path("bun", env=env, env_key="BUN_BIN", command_resolver=command_resolver)
    mcp_url = _first_env(env, "GBRAIN_MCP_URL", "GBRAIN_HTTP_MCP_URL")
    issuer_url = _first_env(env, "GBRAIN_ISSUER_URL", "GBRAIN_REMOTE_ISSUER_URL")
    auth_configured = _auth_configured(env)
    memory_provider = _env(env, "PSKA_MEMORY_PROVIDER").lower()
    selected_as_memory_provider = memory_provider == "gbrain"
    mode = _component_mode(
        source_exists=source_exists,
        package_present=bool(package),
        gbrain_bin=bool(gbrain_bin),
        bun_bin=bool(bun_bin),
        mcp_url=bool(mcp_url),
        auth_configured=auth_configured,
        selected_as_memory_provider=selected_as_memory_provider,
    )
    runtime = _runtime_status(
        selected_as_memory_provider=selected_as_memory_provider,
        http_ready=bool(mcp_url and auth_configured),
    )

    return {
        "schema": "pska.gbrain_component_status.v1",
        "name": "gbrain",
        "kind": "brain_provider",
        "status": "candidate",
        "mode": mode,
        "summary": _summary(mode),
        "paths": {
            "components_root": str(components_root),
            "registry": str(registry_path),
            "registry_exists": registry_path.is_file(),
            "component": str(component_path),
            "source_exists": source_exists,
            "package_json": str(package_json),
            "package_json_exists": package_json.is_file(),
        },
        "package": {
            "name": str(package.get("name") or ""),
            "version": str(package.get("version") or ""),
            "description": str(package.get("description") or ""),
        },
        "executables": {
            "gbrain": {"available": bool(gbrain_bin), "path": gbrain_bin},
            "bun": {"available": bool(bun_bin), "path": bun_bin},
        },
        "transport": {
            "preferred": "mcp_streamable_http",
            "mcp_url_configured": bool(mcp_url),
            "mcp_url": mcp_url,
            "issuer_url_configured": bool(issuer_url),
            "issuer_url": issuer_url,
            "auth_configured": auth_configured,
            "stdio_product_flow_allowed": False,
        },
        "pska": {
            "memory_provider": memory_provider,
            "selected_as_memory_provider": selected_as_memory_provider,
            "adapter_boundary": "MemoryPort",
        },
        "runtime": runtime,
        "governance": {
            "direct_hermes_mcp_allowed": False,
            "durable_memory": "review_gate_required",
            "provenance_required": True,
            "direct_agent_write": "forbidden",
            "allowed_flow": "Hermes -> PSKA -> GBrain HTTP MCP adapter",
        },
        "capabilities": [
            "recall",
            "entity",
            "context_pack",
            "delta",
            "remember_after_review",
        ],
        "checks": _checks(
            source_exists=source_exists,
            package_present=bool(package),
            gbrain_bin=bool(gbrain_bin),
            bun_bin=bool(bun_bin),
            mcp_url=bool(mcp_url),
            auth_configured=auth_configured,
            selected_as_memory_provider=selected_as_memory_provider,
        ),
        "next_actions": _next_actions(
            mode=mode,
            source_exists=source_exists,
            gbrain_bin=bool(gbrain_bin),
            bun_bin=bool(bun_bin),
            mcp_url=bool(mcp_url),
            auth_configured=auth_configured,
            selected_as_memory_provider=selected_as_memory_provider,
        ),
    }


def _read_package_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _component_mode(
    *,
    source_exists: bool,
    package_present: bool,
    gbrain_bin: bool,
    bun_bin: bool,
    mcp_url: bool,
    auth_configured: bool,
    selected_as_memory_provider: bool,
) -> str:
    if not source_exists:
        return "missing_source"
    if selected_as_memory_provider and mcp_url and auth_configured:
        return "pska_memory_provider_configured"
    if selected_as_memory_provider:
        return "pska_memory_provider_incomplete"
    if mcp_url and auth_configured:
        return "http_mcp_configured_adapter_available"
    if mcp_url:
        return "http_mcp_url_only_adapter_available"
    if gbrain_bin:
        return "local_cli_available_not_connected"
    if bun_bin and package_present:
        return "source_checkout_needs_link"
    if package_present:
        return "source_only"
    return "source_incomplete"


def _summary(mode: str) -> str:
    summaries = {
        "missing_source": "GBrain source is not present in PSKA-Components.",
        "source_incomplete": "GBrain component path exists but does not look like a usable checkout.",
        "source_only": "GBrain source is present, but the runtime command and HTTP MCP connection are not configured.",
        "source_checkout_needs_link": "GBrain source and Bun are present, but the gbrain command is not available to PSKA.",
        "local_cli_available_not_connected": "GBrain CLI is available, but PSKA has no HTTP MCP endpoint configured.",
        "http_mcp_url_only_adapter_available": "GBrain HTTP MCP URL is configured, but auth is incomplete and PSKA is not selecting it as memory provider.",
        "http_mcp_configured_adapter_available": "GBrain HTTP MCP settings are present; PSKA has an adapter but is not selecting it as memory provider.",
        "pska_memory_provider_incomplete": "PSKA_MEMORY_PROVIDER is gbrain, but GBrain HTTP MCP URL or auth is incomplete.",
        "pska_memory_provider_configured": "GBrain is selected as PSKA's governed memory provider through HTTP MCP.",
    }
    return summaries.get(mode, "GBrain component status is unknown.")


def _runtime_status(*, selected_as_memory_provider: bool, http_ready: bool) -> dict[str, Any]:
    if selected_as_memory_provider and http_ready:
        return {
            "pska_adapter": "configured",
            "product_flow_status": "participates_via_pska_memory_provider",
            "starts_service": False,
            "participates_in_memory_search": True,
            "participates_in_agentic_context_brief": True,
            "participates_in_jarvis_briefing": True,
        }
    if selected_as_memory_provider:
        return {
            "pska_adapter": "configured_but_incomplete",
            "product_flow_status": "gbrain_memory_provider_missing_http_settings",
            "starts_service": False,
            "participates_in_memory_search": False,
            "participates_in_agentic_context_brief": False,
            "participates_in_jarvis_briefing": False,
        }
    return {
        "pska_adapter": "available_not_selected",
        "product_flow_status": "candidate_visible_not_in_recall_path",
        "starts_service": False,
        "participates_in_memory_search": False,
        "participates_in_agentic_context_brief": False,
        "participates_in_jarvis_briefing": False,
    }


def _checks(
    *,
    source_exists: bool,
    package_present: bool,
    gbrain_bin: bool,
    bun_bin: bool,
    mcp_url: bool,
    auth_configured: bool,
    selected_as_memory_provider: bool,
) -> list[dict[str, Any]]:
    adapter_check = _adapter_check(
        selected_as_memory_provider=selected_as_memory_provider,
        http_ready=bool(mcp_url and auth_configured),
    )
    return [
        _check(
            "source_checkout",
            "ok" if source_exists and package_present else "warning",
            "GBrain source checkout and package metadata are present."
            if source_exists and package_present
            else "GBrain source checkout or package metadata is missing.",
        ),
        _check(
            "gbrain_cli",
            "ok" if gbrain_bin else "warning",
            "gbrain executable is available." if gbrain_bin else "gbrain executable is not available.",
        ),
        _check(
            "bun_runtime",
            "ok" if bun_bin else "warning",
            "Bun runtime is available for source checkout operations."
            if bun_bin
            else "Bun runtime is not available for source checkout operations.",
        ),
        _check(
            "http_mcp_url",
            "ok" if mcp_url else "warning",
            "GBrain HTTP MCP endpoint is configured."
            if mcp_url
            else "GBrain HTTP MCP endpoint is not configured.",
        ),
        _check(
            "http_auth",
            "ok" if auth_configured else "warning",
            "GBrain HTTP MCP auth material is configured."
            if auth_configured
            else "GBrain HTTP MCP auth material is not configured.",
        ),
        adapter_check,
    ]


def _adapter_check(*, selected_as_memory_provider: bool, http_ready: bool) -> dict[str, str]:
    if selected_as_memory_provider and http_ready:
        return _check("pska_brain_adapter", "ok", "PSKA GBrain MemoryPort adapter is selected and configured.")
    if selected_as_memory_provider:
        return _check(
            "pska_brain_adapter",
            "warning",
            "PSKA GBrain MemoryPort adapter is selected, but HTTP MCP URL or auth is incomplete.",
        )
    return _check(
        "pska_brain_adapter",
        "ok",
        "PSKA GBrain MemoryPort adapter is implemented but not selected.",
    )


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _next_actions(
    *,
    mode: str,
    source_exists: bool,
    gbrain_bin: bool,
    bun_bin: bool,
    mcp_url: bool,
    auth_configured: bool,
    selected_as_memory_provider: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not source_exists:
        actions.append(
            _action(
                "install_gbrain_source",
                "Place GBrain under PSKA-Components",
                "Clone or restore the GBrain checkout before PSKA can evaluate it as a component.",
            )
        )
    if source_exists and not bun_bin:
        actions.append(
            _action(
                "install_bun_for_gbrain",
                "Install Bun for GBrain source operations",
                "The local GBrain checkout is TypeScript/Bun-based; Bun is needed to build or link the command.",
            )
        )
    if source_exists and bun_bin and not gbrain_bin:
        actions.append(
            _action(
                "link_gbrain_command",
                "Link the GBrain command",
                "Run the GBrain checkout install/link flow so PSKA can verify the command locally.",
            )
        )
    if not mcp_url:
        actions.append(
            _action(
                "configure_gbrain_http_mcp",
                "Configure GBrain HTTP MCP",
                "Start GBrain with its HTTP MCP server and set GBRAIN_MCP_URL to the /mcp endpoint.",
            )
        )
    if mcp_url and not auth_configured:
        actions.append(
            _action(
                "configure_gbrain_http_auth",
                "Configure GBrain HTTP auth",
                "Set a bearer token or OAuth client credentials for the configured GBrain HTTP MCP endpoint.",
            )
        )
    if mcp_url and auth_configured and not selected_as_memory_provider:
        actions.append(
            _action(
                "select_gbrain_memory_provider",
                "Select GBrain as PSKA memory provider",
                "Set PSKA_MEMORY_PROVIDER=gbrain when you want GBrain to participate in governed memory search and writes.",
            )
        )
    if selected_as_memory_provider and mcp_url and auth_configured:
        actions.append(
            _action(
                "probe_gbrain_http_mcp",
                "Probe GBrain HTTP MCP through PSKA",
                "Run a PSKA memory search/apply smoke test before relying on GBrain for a demo.",
                status="recommended",
            )
        )
    if mode.startswith("http_mcp"):
        actions.append(
            _action(
                "probe_gbrain_http_mcp",
                "Probe GBrain HTTP MCP",
                "Verify tools/list and the seven memory verbs through PSKA, not Hermes direct wiring.",
                status="pending",
            )
        )
    return actions


def _action(action: str, label: str, reason: str, *, status: str = "action_required") -> dict[str, str]:
    return {"action": action, "label": label, "reason": reason, "status": status}


def _command_path(
    command: str,
    *,
    env: Mapping[str, str],
    env_key: str,
    command_resolver: CommandResolver,
) -> str:
    override = _env(env, env_key)
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    resolved = command_resolver(command)
    return str(resolved or "")


def _auth_configured(env: Mapping[str, str]) -> bool:
    if _first_env(env, "GBRAIN_REMOTE_TOKEN", "GBRAIN_MCP_TOKEN", "GBRAIN_BEARER_TOKEN"):
        return True
    client_id = _first_env(env, "GBRAIN_OAUTH_CLIENT_ID", "GBRAIN_REMOTE_CLIENT_ID")
    client_secret = _first_env(env, "GBRAIN_OAUTH_CLIENT_SECRET", "GBRAIN_REMOTE_CLIENT_SECRET")
    return bool(client_id and client_secret)


def _first_env(env: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = _env(env, key)
        if value:
            return value
    return ""


def _env(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key) or "").strip()
