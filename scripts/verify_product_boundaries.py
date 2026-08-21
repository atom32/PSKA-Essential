#!/usr/bin/env python3
"""Verify PSKA product boundary invariants.

This is a repository-level guard for the product path:

Hermes WebUI -> pska-mini sidecar -> PSKA Product API / HTTP MCP -> adapters.

It intentionally scans only product configs, startup scripts, extension code,
and demo entrypoints. Research docs may mention alternatives such as stdio MCP,
but the daily product path must stay HTTP MCP and provider-gated.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BoundaryFailure(AssertionError):
    pass


def main() -> int:
    checks: list[str] = []
    try:
        verify_hermes_config(checks)
        verify_start_workspace(checks)
        verify_full_compose(checks)
        verify_webui_extension(checks)
        verify_demo_entrypoints(checks)
        verify_readme_boundary(checks)
    except BoundaryFailure as exc:
        print(f"PSKA product boundary verification failed: {exc}", file=sys.stderr)
        return 1

    print("PSKA product boundary verification passed:")
    for check in checks:
        print(f"- {check}")
    return 0


def verify_hermes_config(checks: list[str]) -> None:
    path = ROOT / "skills" / "hermes" / "config.example.yaml"
    text = read_text(path)
    require(text, 'url: "http://127.0.0.1:8766/mcp"', path, "Hermes must point at PSKA HTTP MCP")
    forbid(text, r"(?m)^\s+command:\s*", path, "Hermes PSKA config must not use stdio command")
    forbid(text, r"(?m)^\s+args:\s*", path, "Hermes PSKA config must not use stdio args")
    forbid(text, r"(?m)^\s{2}(ragflow|graphiti|gbrain|zep|mem0):\s*$", path, "Hermes must not expose provider MCP servers")
    require(text, "pska_workspace_status", path, "Hermes daily surface must include PSKA workspace status")
    require(text, "pska_agentic_context_brief", path, "Hermes daily surface must include PSKA agentic context")
    checks.append("Hermes config example uses PSKA HTTP MCP only")


def verify_start_workspace(checks: list[str]) -> None:
    path = ROOT / "scripts" / "start_pska_workspace.sh"
    text = read_text(path)
    require(text, "PSKA_MCP_BASE_URL=http://127.0.0.1:8766/mcp", path, "workspace script must advertise HTTP MCP")
    require(text, "--transport streamable-http", path, "workspace script must start streamable HTTP MCP")
    forbid(text, r"--transport\s+stdio", path, "workspace script must not start stdio MCP")
    require(text, "ensure_hermes_pska_mcp_config", path, "workspace script must enforce Hermes PSKA MCP config")
    require(text, '"url": pska_mcp_base_url', path, "Hermes config writer must write URL-based MCP")
    checks.append("workspace startup keeps PSKA MCP on HTTP transport")


def verify_full_compose(checks: list[str]) -> None:
    compose_path = ROOT / "deploy" / "full-compose" / "docker-compose.yml"
    compose = read_text(compose_path)
    require(compose, "pska-mcp:", compose_path, "full compose must include PSKA MCP service")
    require(compose, "pska-essential-mcp", compose_path, "full compose must run PSKA MCP entrypoint")
    require(compose, "- streamable-http", compose_path, "full compose MCP must use streamable HTTP")
    require(compose, "- \"8766\"", compose_path, "full compose MCP must expose port 8766")
    require(compose, "- /mcp", compose_path, "full compose MCP must use /mcp path")
    forbid(compose, r"-\s*stdio\b", compose_path, "full compose MCP must not use stdio")

    hermes_template = ROOT / "deploy" / "full-compose" / "hermes" / "config.yaml.template"
    hermes = read_text(hermes_template)
    require(hermes, "url: http://pska-mcp:8766/mcp", hermes_template, "compose Hermes config must point at PSKA MCP URL")
    forbid(hermes, r"(?m)^\s+command:\s*", hermes_template, "compose Hermes config must not use stdio command")
    forbid(hermes, r"(?m)^\s{2}(ragflow|graphiti|gbrain|zep|mem0):\s*$", hermes_template, "compose Hermes must not expose provider MCP servers")
    checks.append("full compose routes Hermes Agent to PSKA HTTP MCP")


def verify_webui_extension(checks: list[str]) -> None:
    manifest_path = ROOT / "integrations" / "hermes-webui-extension" / "pska-mini" / "manifest.json"
    manifest = json.loads(read_text(manifest_path))
    sidecar = manifest.get("sidecar") or {}
    assert_equal(manifest.get("id"), "pska-mini", manifest_path, "extension id")
    assert_equal(sidecar.get("type"), "loopback", manifest_path, "extension sidecar type")
    assert_equal(sidecar.get("origin"), "http://127.0.0.1:8765", manifest_path, "extension sidecar origin")
    assert_equal(sidecar.get("health_path"), "/api/health", manifest_path, "extension sidecar health")

    script_path = ROOT / "integrations" / "hermes-webui-extension" / "pska-mini" / "pska-mini.js"
    script = read_text(script_path)
    require(script, "sidecarProxyBase(EXT_ID)", script_path, "extension must use WebUI sidecar proxy")
    require(script, '"/api/chat/start"', script_path, "extension must bridge the Hermes chat turn")
    require(script, "PSKA-Mini Runtime Scope", script_path, "extension must inject explicit PSKA runtime scope")
    require(script, 'const SKILL_NAME = "knowledge-retrieval"', script_path, "extension must force the PSKA-aware Hermes skill")
    forbid_provider_urls(script, script_path)
    forbid(script, r"\b(RAGFLOW_API_KEY|GRAPHITI_BASE_URL|GBRAIN_MCP_URL|OPENAI_API_KEY)\b", script_path, "browser extension must not learn provider secrets or provider env")
    forbid(script, r"/api/v1/(datasets|chats|system|document)", script_path, "browser extension must not call RAGFlow native API")
    forbid(script, r"/api/pska/(ask|kb/ingest|memory/search|digest-jobs|reviews|sources/read)", script_path, "extension must not rely on legacy PSKA proxy routes")
    checks.append("pska-mini stays a thin WebUI sidecar extension")


def verify_demo_entrypoints(checks: list[str]) -> None:
    plan_path = ROOT / "demo" / "browser" / "hermes_pska_extension_demo" / "demo_plan.json"
    plan = json.loads(read_text(plan_path))
    assert_equal(plan.get("entrypoint"), "Hermes WebUI", plan_path, "demo entrypoint")
    assert_equal(plan.get("tts"), "none", plan_path, "demo TTS mode")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 10:
        raise BoundaryFailure(f"{plan_path} expected 10 Hermes extension demo scenes")

    matrix_path = ROOT / "demo" / "browser" / "hermes_pska_extension_demo" / "FEATURE_EVIDENCE_MATRIX.zh.md"
    matrix = read_text(matrix_path)
    require(matrix, "知识助手没有另起独立前端", matrix_path, "feature matrix must state no independent PSKA frontend")
    require(matrix, "不跳到独立问答页", matrix_path, "feature matrix must keep chat inside Hermes WebUI")
    require(matrix, "浏览器不直接连接底层资料库或记忆库", matrix_path, "feature matrix must forbid browser provider direct calls")

    legacy_packager = read_text(ROOT / "scripts" / "build_browser_demo_video.py")
    require(legacy_packager, "PSKA has no independent product frontend", ROOT / "scripts" / "build_browser_demo_video.py", "legacy browser demo builder must stay disabled")
    checks.append("demo entrypoint remains Hermes WebUI extension only")


def verify_readme_boundary(checks: list[str]) -> None:
    path = ROOT / "README.md"
    text = read_text(path)
    require(text, "uv run pska-essential-mcp --env-file .env.pska --transport streamable-http --host 0.0.0.0 --port 8766 --path /mcp", path, "README must document HTTP MCP startup")
    require(text, "Browser code and Hermes agents must not call RAGFlow, Graphiti,", path, "README must state provider direct-call boundary")
    require(text, "The repository still contains a bundled local UI for development diagnostics and", path, "README must distinguish diagnostic UI from product workspace")
    checks.append("README states HTTP MCP and no direct provider calls")


def forbid_provider_urls(text: str, path: Path) -> None:
    provider_ports = "9380|9388|9222|9228|8000|6380|3131"
    forbid(
        text,
        rf"https?://(?:127\.0\.0\.1|localhost|host\.docker\.internal):(?:{provider_ports})\b",
        path,
        "browser extension must not call provider loopback URLs directly",
    )


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BoundaryFailure(f"missing required file: {path}") from exc


def require(text: str, needle: str, path: Path, message: str) -> None:
    if needle not in text:
        raise BoundaryFailure(f"{path}: {message}; missing {needle!r}")


def forbid(text: str, pattern: str, path: Path, message: str) -> None:
    match = re.search(pattern, text)
    if match:
        raise BoundaryFailure(f"{path}: {message}; matched {match.group(0)!r}")


def assert_equal(actual, expected, path: Path, label: str) -> None:
    if actual != expected:
        raise BoundaryFailure(f"{path}: expected {label}={expected!r}, got {actual!r}")


if __name__ == "__main__":
    raise SystemExit(main())
