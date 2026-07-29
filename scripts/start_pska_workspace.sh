#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PSKA_HOME="${PSKA_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${PSKA_HOME}/.env.pska}"
STACK_ENV_FILE="${PSKA_STACK_ENV_FILE:-${HOME}/.hermes/pska-stack.env}"
HERMES_WEBUI_HOME="${HERMES_WEBUI_HOME:-${HOME}/hermes-webui}"
PSKA_COMPONENTS_HOME="${PSKA_COMPONENTS_HOME:-${HOME}/PSKA-Components}"
RAGFLOW_HOME="${RAGFLOW_HOME:-${PSKA_COMPONENTS_HOME}/ragflow}"
GRAPHITI_HOME="${GRAPHITI_HOME:-${PSKA_COMPONENTS_HOME}/graphiti}"
LOG_DIR="${PSKA_LOG_DIR:-${PSKA_HOME}/.pska-essential/logs}"
PID_DIR="${PSKA_PID_DIR:-${PSKA_HOME}/.pska-essential/pids}"

OPEN_FRONTEND=1
SKIP_RAGFLOW=0
SKIP_GRAPHITI=0
SKIP_PSKA=0
SKIP_HERMES=0
STATUS_ONLY=0
HERMES_CONFIG_CHANGED=0

usage() {
  cat <<'EOF'
Usage: scripts/start_pska_workspace.sh [options]

Starts missing local PSKA workspace components, then opens Hermes WebUI.

Options:
  --no-open        Start/check services but do not open the browser.
  --status-only    Only print health status; do not start anything.
  --skip-ragflow   Do not start/check RAGFlow.
  --skip-graphiti  Do not start/check Graphiti.
  --skip-pska      Do not start/check PSKA Product API.
  --skip-hermes    Do not start/check Hermes WebUI.
  -h, --help       Show this help.

Useful overrides:
  ENV_FILE=/path/to/.env.pska
  PSKA_STACK_ENV_FILE=~/.hermes/pska-stack.env
  PSKA_HOME=/path/to/PSKA-Essential
  HERMES_WEBUI_HOME=/path/to/hermes-webui
  HERMES_WEBUI_EXTENSION_DIR=~/.hermes/webui-local-extensions
  HERMES_WEBUI_EXTENSION_MANIFEST=extensions.json
  HERMES_WEBUI_STATE_DIR=~/.hermes/webui
  PSKA_WEBUI_AUTO_APPROVE_SIDECAR=1
  PSKA_COMPONENTS_HOME=/path/to/PSKA-Components
  PSKA_API_HOST=127.0.0.1
  PSKA_API_PORT=8765
  PSKA_API_BASE_URL=http://127.0.0.1:8765
  HERMES_WEBUI_HOST=127.0.0.1
  HERMES_WEBUI_PORT=8787
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-open) OPEN_FRONTEND=0 ;;
    --status-only) STATUS_ONLY=1; OPEN_FRONTEND=0 ;;
    --skip-ragflow) SKIP_RAGFLOW=1 ;;
    --skip-graphiti) SKIP_GRAPHITI=1 ;;
    --skip-pska) SKIP_PSKA=1 ;;
    --skip-hermes) SKIP_HERMES=1; OPEN_FRONTEND=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[pska] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() {
  printf '[pska] %s\n' "$*"
}

warn() {
  printf '[pska][warn] %s\n' "$*" >&2
}

die() {
  printf '[pska][error] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_env_file() {
  local env_file="$1"
  [[ -f "${env_file}" ]] || return 0

  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="$(trim "${line}")"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ "${line}" =~ ^export[[:space:]]+(.+)$ ]]; then
      line="$(trim "${BASH_REMATCH[1]}")"
    fi
    [[ "${line}" == *=* ]] || continue

    key="$(trim "${line%%=*}")"
    value="$(trim "${line#*=}")"
    [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    case "${key}" in
      UID|GID|EUID|EGID|PPID) continue ;;
    esac
    # Existing shell values win over the env file so callers can override
    # ports and paths without editing secrets.
    [[ -n "${!key+x}" ]] && continue

    if [[ "${value}" =~ ^\"(.*)\"$ ]]; then
      value="${BASH_REMATCH[1]}"
    elif [[ "${value}" =~ ^\'(.*)\'$ ]]; then
      value="${BASH_REMATCH[1]}"
    else
      value="${value%%[[:space:]]\#*}"
      value="$(trim "${value}")"
    fi
    export "${key}=${value}"
  done < "${env_file}"
}

strip_trailing_slash() {
  local value="$1"
  while [[ "${value}" == */ ]]; do
    value="${value%/}"
  done
  printf '%s' "${value}"
}

http_ok() {
  local url="$1"
  curl -fsS --max-time "${HTTP_PROBE_TIMEOUT:-3}" "${url}" >/dev/null 2>&1
}

wait_for_url() {
  local name="$1" url="$2" timeout="${3:-60}"
  local start now
  start="$(date +%s)"
  while true; do
    if http_ok "${url}"; then
      log "${name} is ready: ${url}"
      return 0
    fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      warn "${name} did not become ready within ${timeout}s: ${url}"
      return 1
    fi
    sleep 2
  done
}

launch_agent_start() {
  local label="$1" plist="$2"
  command -v launchctl >/dev/null 2>&1 || return 1
  [[ -f "${plist}" ]] || return 1

  local domain="gui/$(id -u)"
  if ! launchctl print "${domain}/${label}" >/dev/null 2>&1; then
    launchctl bootstrap "${domain}" "${plist}" >/dev/null 2>&1 || true
  fi
  launchctl kickstart -k "${domain}/${label}" >/dev/null 2>&1 || return 1
}

docker_compose() {
  if command -v docker >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi
  return 127
}

shell_join() {
  local item
  printf '%q' "$1"
  shift
  for item in "$@"; do
    printf ' %q' "${item}"
  done
}

xml_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

print_status_line() {
  local name="$1" url="$2"
  if http_ok "${url}"; then
    printf '  OK   %s (%s)\n' "${name}" "${url}"
  else
    printf '  MISS %s (%s)\n' "${name}" "${url}"
  fi
}

pska_api_contract_ok() {
  local url="${PSKA_API_BASE_URL}/api/capabilities"
  local payload
  payload="$(curl -fsS --max-time "${HTTP_PROBE_TIMEOUT:-3}" "${url}" 2>/dev/null)" || return 1
  PSKA_CAPABILITIES_PAYLOAD="${payload}" python3 - <<'PY' >/dev/null 2>&1
from __future__ import annotations

import json
import os
import sys

try:
    data = json.loads(os.environ.get("PSKA_CAPABILITIES_PAYLOAD", "{}"))
except json.JSONDecodeError:
    raise SystemExit(1)

contract = data.get("product_api_contract") or {}
routes = {
    (str(route.get("method") or "").upper(), str(route.get("path") or ""))
    for route in contract.get("required_routes") or []
    if isinstance(route, dict)
}
required_routes = {
    ("GET", "/api/capabilities"),
    ("GET", "/api/provider/jobs"),
    ("POST", "/api/digest"),
    ("POST", "/api/digest-jobs"),
    ("GET", "/api/digest-jobs"),
    ("POST", "/api/digest-jobs/run-next"),
    ("POST", "/api/digest-jobs/{run_id}/run"),
    ("POST", "/api/workflows/{run_id}/memory-review"),
    ("POST", "/api/memory/search"),
    ("POST", "/api/memory/conversation-change"),
}
capabilities = data.get("capabilities") or {}
memory_capabilities = capabilities.get("memory") or {}
search_view = memory_capabilities.get("search_view") or {}
interaction_model = memory_capabilities.get("interaction_model") or {}
if contract.get("schema") != "pska.product_api_contract.v1":
    raise SystemExit(1)
if not required_routes.issubset(routes):
    raise SystemExit(1)
if search_view.get("schema") != "pska.memory_search_view.v1":
    raise SystemExit(1)
if interaction_model.get("schema") != "pska.memory_interaction_model.v1":
    raise SystemExit(1)
if interaction_model.get("primary_user_path") != "conversation":
    raise SystemExit(1)
if interaction_model.get("review_queue_role") != "exception_inbox":
    raise SystemExit(1)
if interaction_model.get("visible_memory_editor") != "conversation":
    raise SystemExit(1)
if interaction_model.get("visible_review_role") != "exception_only":
    raise SystemExit(1)
if not interaction_model.get("agent_decides_operation"):
    raise SystemExit(1)
target_resolution = interaction_model.get("target_resolution") or {}
if target_resolution.get("creates_review_item") is not False:
    raise SystemExit(1)
review_triggers = set(str(value or "") for value in interaction_model.get("review_queue_triggers") or [])
if "ambiguous_destructive" not in review_triggers:
    raise SystemExit(1)
if "broad_destructive" not in review_triggers:
    raise SystemExit(1)
if "destructive" in review_triggers or "broad" in review_triggers:
    raise SystemExit(1)
explicit_changes = interaction_model.get("conversation_explicit_user_changes") or {}
if explicit_changes.get("remember") != "conversation_policy":
    raise SystemExit(1)
if explicit_changes.get("correct_clear_target") != "conversation_policy":
    raise SystemExit(1)
if explicit_changes.get("forget_specific_fact") != "conversation_policy":
    raise SystemExit(1)
if explicit_changes.get("missing_or_ambiguous_target") != "needs_target_no_review":
    raise SystemExit(1)
if explicit_changes.get("force_review") != "exception_review":
    raise SystemExit(1)
inflow = memory_capabilities.get("inflow") or {}
if inflow.get("schema") != "pska.memory_inflow.v1":
    raise SystemExit(1)
upload_behavior = inflow.get("upload_behavior") or {}
if upload_behavior.get("writes_memory_provider") is not False:
    raise SystemExit(1)
lineage = memory_capabilities.get("lineage") or {}
if lineage.get("schema") != "pska.memory_lineage.v1":
    raise SystemExit(1)
if lineage.get("pska_authoritative_mapping_table") is not False:
    raise SystemExit(1)
sys.exit(0)
PY
}

print_pska_status_line() {
  local health_url="${PSKA_API_BASE_URL}/api/health"
  if ! http_ok "${health_url}"; then
    printf '  MISS %s (%s)\n' "PSKA Product API" "${health_url}"
    return 0
  fi
  if pska_api_contract_ok; then
    printf '  OK   %s (%s)\n' "PSKA Product API" "${health_url}"
  else
    printf '  STALE %s (%s)\n' "PSKA Product API" "${health_url}"
  fi
}

start_graphiti_if_needed() {
  local health_url="${GRAPHITI_BASE_URL}/healthcheck"
  if http_ok "${health_url}"; then
    log "Graphiti already running"
    return 0
  fi
  (( STATUS_ONLY )) && return 0
  [[ -d "${GRAPHITI_HOME}" ]] || { warn "Graphiti home not found: ${GRAPHITI_HOME}"; return 0; }
  [[ -f "${GRAPHITI_HOME}/docker-compose.pska.yml" ]] || { warn "Graphiti compose file not found"; return 0; }

  log "Starting Graphiti via Docker Compose"
  (
    cd "${GRAPHITI_HOME}"
    docker_compose -f docker-compose.pska.yml --env-file .env.pska up -d
  ) || { warn "Graphiti Docker Compose start failed"; return 0; }
  wait_for_url "Graphiti" "${health_url}" "${GRAPHITI_WAIT_SECONDS:-90}" || true
}

start_ragflow_if_needed() {
  local health_url="${RAGFLOW_BASE_URL}/api/v1/system/ping"
  if http_ok "${health_url}"; then
    log "RAGFlow already running"
    return 0
  fi
  (( STATUS_ONLY )) && return 0
  [[ -d "${RAGFLOW_HOME}" ]] || { warn "RAGFlow home not found: ${RAGFLOW_HOME}"; return 0; }

  if [[ -f "${RAGFLOW_HOME}/docker/docker-compose-base.yml" ]]; then
    log "Starting RAGFlow base services via Docker Compose"
    (
      cd "${RAGFLOW_HOME}"
      docker_compose -f docker/docker-compose-base.yml up -d
    ) || warn "RAGFlow base Docker Compose start failed"
  fi

  log "Starting RAGFlow launchd services when available"
  launch_agent_start "com.pska.ragflow" "${HOME}/Library/LaunchAgents/com.pska.ragflow.plist" \
    || warn "RAGFlow API launchd job was not started"
  launch_agent_start "com.pska.ragflow.web" "${HOME}/Library/LaunchAgents/com.pska.ragflow.web.plist" \
    || warn "RAGFlow web launchd job was not started"

  wait_for_url "RAGFlow" "${health_url}" "${RAGFLOW_WAIT_SECONDS:-120}" || true
}

pska_api_command() {
  PSKA_API_CMD=()
  if command -v uv >/dev/null 2>&1; then
    PSKA_API_CMD=("$(command -v uv)" run --project "${PSKA_HOME}" pska-essential-api --env-file "${ENV_FILE}" --host "${PSKA_API_HOST}" --port "${PSKA_API_PORT}")
  else
    require_cmd python3
    PSKA_API_CMD=("$(command -v python3)" -m pska_essential.product_api --env-file "${ENV_FILE}" --host "${PSKA_API_HOST}" --port "${PSKA_API_PORT}")
  fi
}

start_pska_api_launchd() {
  command -v launchctl >/dev/null 2>&1 || return 1
  mkdir -p "${LOG_DIR}" "${PID_DIR}"
  local log_file="${PSKA_API_LOG_FILE:-${LOG_DIR}/pska-product-api.log}"
  local plist="${PSKA_API_LAUNCH_AGENT_PLIST:-${HOME}/Library/LaunchAgents/com.pska.essential.api.plist}"
  local label="${PSKA_API_LAUNCH_AGENT_LABEL:-com.pska.essential.api}"
  local domain="gui/$(id -u)"
  local -a cmd
  pska_api_command
  cmd=("${PSKA_API_CMD[@]}")

  mkdir -p "$(dirname "${plist}")"
  local command_string escaped_command escaped_workdir escaped_log
  command_string="cd $(printf '%q' "${PSKA_HOME}") && PYTHONPATH=$(printf '%q' "${PSKA_HOME}/src${PYTHONPATH:+:${PYTHONPATH}}") exec $(shell_join "${cmd[@]}")"
  escaped_command="$(printf '%s' "${command_string}" | xml_escape)"
  escaped_workdir="$(printf '%s' "${PSKA_HOME}" | xml_escape)"
  escaped_log="$(printf '%s' "${log_file}" | xml_escape)"
  cat > "${plist}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>${escaped_command}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${escaped_workdir}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${escaped_log}</string>
  <key>StandardErrorPath</key>
  <string>${escaped_log}</string>
</dict>
</plist>
EOF
  launchctl bootout "${domain}" "${plist}" >/dev/null 2>&1 || true
  launchctl bootstrap "${domain}" "${plist}" >/dev/null 2>&1 || return 1
  launchctl kickstart -k "${domain}/${label}" >/dev/null 2>&1 || return 1
}

start_pska_api_nohup() {
  mkdir -p "${LOG_DIR}" "${PID_DIR}"
  local log_file="${PSKA_API_LOG_FILE:-${LOG_DIR}/pska-product-api.log}"
  local pid_file="${PSKA_API_PID_FILE:-${PID_DIR}/pska-product-api.pid}"
  local -a cmd
  pska_api_command
  cmd=("${PSKA_API_CMD[@]}")

  (
    cd "${PSKA_HOME}"
    PYTHONPATH="${PSKA_HOME}/src${PYTHONPATH:+:${PYTHONPATH}}" nohup "${cmd[@]}" >> "${log_file}" 2>&1 &
    printf '%s\n' "$!" > "${pid_file}"
  )
}

pska_api_is_local_host() {
  case "${PSKA_API_HOST}" in
    127.0.0.1|localhost|::1) return 0 ;;
    *) return 1 ;;
  esac
}

pska_api_port_pids() {
  command -v lsof >/dev/null 2>&1 || return 1
  pska_api_is_local_host || return 1
  lsof -tiTCP:"${PSKA_API_PORT}" -sTCP:LISTEN 2>/dev/null | awk 'NF'
}

stop_pska_api_port_processes() {
  local pid
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    warn "Stopping stale PSKA Product API process ${pid} on port ${PSKA_API_PORT}"
    kill "${pid}" >/dev/null 2>&1 || true
  done < <(pska_api_port_pids || true)
  sleep 1
}

start_pska_api_if_needed() {
  local health_url="${PSKA_API_BASE_URL}/api/health"
  if http_ok "${health_url}"; then
    if pska_api_contract_ok; then
      log "PSKA Product API already running"
      return 0
    fi
    if (( STATUS_ONLY )); then
      warn "PSKA Product API is running but does not expose the required Product API contract."
      return 0
    fi
    if pska_api_is_local_host; then
      warn "PSKA Product API is running but stale; restarting it."
      stop_pska_api_port_processes
    else
      warn "PSKA Product API at ${PSKA_API_BASE_URL} is stale, but it is not local; not restarting."
      return 0
    fi
  fi
  (( STATUS_ONLY )) && return 0
  [[ -d "${PSKA_HOME}" ]] || die "PSKA_HOME not found: ${PSKA_HOME}"
  [[ -f "${ENV_FILE}" ]] || die "env file not found: ${ENV_FILE}"

  log "Starting PSKA Product API at ${PSKA_API_BASE_URL}"
  if start_pska_api_launchd; then
    log "PSKA Product API launchd agent started"
  else
    warn "launchd start failed or unavailable; falling back to nohup"
    start_pska_api_nohup
  fi
  if ! wait_for_url "PSKA Product API" "${health_url}" "${PSKA_API_WAIT_SECONDS:-45}"; then
    warn "PSKA Product API log: ${PSKA_API_LOG_FILE:-${LOG_DIR}/pska-product-api.log}"
    tail -40 "${PSKA_API_LOG_FILE:-${LOG_DIR}/pska-product-api.log}" >&2 2>/dev/null || true
  elif pska_api_contract_ok; then
    log "PSKA Product API contract is current"
  else
    warn "PSKA Product API started, but the required Product API contract is still missing."
  fi
}

ensure_hermes_pska_mcp_config() {
  (( STATUS_ONLY )) && return 0
  (( SKIP_HERMES )) && return 0
  [[ -d "${PSKA_HOME}" ]] || die "PSKA_HOME not found: ${PSKA_HOME}"
  [[ -f "${ENV_FILE}" ]] || die "env file not found: ${ENV_FILE}"
  require_cmd python3
  mkdir -p "${HERMES_HOME_EFFECTIVE}"

  local config_file="${HERMES_HOME_EFFECTIVE}/config.yaml"
  local result
  result="$(
    HERMES_CONFIG_FILE="${config_file}" PSKA_HOME_FOR_MCP="${PSKA_HOME}" ENV_FILE_FOR_MCP="${ENV_FILE}" python3 - <<'PY'
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

config_file = Path(os.environ["HERMES_CONFIG_FILE"]).expanduser()
pska_home = str(Path(os.environ["PSKA_HOME_FOR_MCP"]).expanduser())
env_file = str(Path(os.environ["ENV_FILE_FOR_MCP"]).expanduser())

uv = shutil.which("uv")
if uv:
    pska_entry = {
        "command": uv,
        "args": [
            "run",
            "--project",
            pska_home,
            "--extra",
            "mcp",
            "pska-essential-mcp",
            "--env-file",
            env_file,
        ],
        "enabled": True,
        "timeout": 120,
        "connect_timeout": 120,
    }
else:
    pska_entry = {
        "command": shutil.which("python3") or "python3",
        "args": ["-m", "pska_essential", "--env-file", env_file],
        "env": {"PYTHONPATH": f"{pska_home}/src"},
        "enabled": True,
        "timeout": 120,
        "connect_timeout": 120,
    }

stack_env = {
    key: os.environ[key]
    for key in ("RAGFLOW_BASE_URL", "GRAPHITI_BASE_URL", "PSKA_API_BASE_URL")
    if os.environ.get(key)
}
if stack_env:
    pska_entry["env"] = {**pska_entry.get("env", {}), **stack_env}

config_file.parent.mkdir(parents=True, exist_ok=True)
text = config_file.read_text(encoding="utf-8") if config_file.exists() else ""

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

if yaml is not None:
    data = yaml.safe_load(text) if text.strip() else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        print("Hermes config root must be a YAML object", file=sys.stderr)
        raise SystemExit(2)
    servers = data.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        print("Hermes config mcp_servers must be a YAML object", file=sys.stderr)
        raise SystemExit(2)
    if servers.get("pska-essential") == pska_entry:
        print("unchanged")
        raise SystemExit(0)
    if config_file.exists():
        backup = config_file.with_suffix(config_file.suffix + f".bak-{int(time.time())}")
        backup.write_text(text, encoding="utf-8")
    servers["pska-essential"] = pska_entry
    config_file.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print("updated")
    raise SystemExit(0)

if "mcp_servers:" in text and "pska-essential:" not in text:
    print("PyYAML is required to merge pska-essential into an existing mcp_servers block", file=sys.stderr)
    raise SystemExit(2)
if "pska-essential:" in text:
    print("unchanged")
    raise SystemExit(0)

block = f'''
mcp_servers:
  pska-essential:
    command: "{pska_entry["command"]}"
    args:
{chr(10).join(f"      - {arg!r}" for arg in pska_entry["args"])}
    enabled: true
    timeout: 120
    connect_timeout: 120
'''
config_file.write_text(text.rstrip() + "\n" + block.lstrip(), encoding="utf-8")
print("updated")
PY
  )" || { warn "Failed to ensure Hermes PSKA MCP config"; return 0; }

  if [[ "${result}" == "updated" ]]; then
    HERMES_CONFIG_CHANGED=1
    log "Hermes PSKA MCP config updated: ${config_file}"
  else
    log "Hermes PSKA MCP config already present"
  fi
}

ensure_hermes_webui_extension() {
  local sync_script="${PSKA_HOME}/integrations/hermes-webui-extension/sync-to-hermes.sh"
  [[ -f "${sync_script}" ]] || die "PSKA WebUI extension sync script not found: ${sync_script}"

  log "Syncing PSKA-mini Hermes WebUI extension"
  HERMES_HOME="${HERMES_HOME_EFFECTIVE}" \
  HERMES_WEBUI_EXTENSION_DIR="${HERMES_WEBUI_EXTENSION_DIR}" \
  HERMES_WEBUI_EXTENSION_MANIFEST="${HERMES_WEBUI_EXTENSION_MANIFEST}" \
  HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR}" \
  PSKA_API_BASE_URL="${PSKA_API_BASE_URL}" \
  PSKA_WEBUI_AUTO_APPROVE_SIDECAR="${PSKA_WEBUI_AUTO_APPROVE_SIDECAR:-1}" \
    bash "${sync_script}"
}

start_hermes_if_needed() {
  local health_url="${HERMES_WEBUI_BASE_URL}/health"
  if http_ok "${health_url}"; then
    if (( HERMES_CONFIG_CHANGED )); then
      warn "Hermes WebUI is running, but PSKA MCP config changed. Restarting it."
      stop_hermes_port_processes
    elif hermes_running_environment_matches; then
      log "Hermes WebUI already running"
      return 0
    else
      if (( STATUS_ONLY )); then
        warn "Hermes WebUI is running on ${HERMES_WEBUI_BASE_URL}, but it was started with different PSKA/Hermes environment."
        return 0
      fi
      warn "Hermes WebUI is running on ${HERMES_WEBUI_BASE_URL}, but it was started with different PSKA/Hermes environment. Restarting it."
      stop_hermes_port_processes
    fi
  fi
  if http_ok "${health_url}"; then
    if hermes_running_environment_matches; then
      log "Hermes WebUI already running"
      return 0
    fi
    if (( STATUS_ONLY )); then
      warn "Hermes WebUI is running on ${HERMES_WEBUI_BASE_URL}, but it was started with different PSKA/Hermes environment."
      return 0
    fi
    warn "Hermes WebUI is running on ${HERMES_WEBUI_BASE_URL}, but it was started with different PSKA/Hermes environment. Restarting it."
    stop_hermes_port_processes
  fi
  (( STATUS_ONLY )) && return 0
  [[ -d "${HERMES_WEBUI_HOME}" ]] || die "Hermes WebUI home not found: ${HERMES_WEBUI_HOME}"

  log "Starting Hermes WebUI at ${HERMES_WEBUI_BASE_URL}"
  if start_hermes_launchd; then
    log "Hermes WebUI launchd agent started"
  else
    warn "launchd start failed or unavailable; falling back to Hermes ctl.sh"
    start_hermes_ctl
  fi
  wait_for_url "Hermes WebUI" "${health_url}" "${HERMES_WAIT_SECONDS:-60}" || true
}

hermes_python() {
  if [[ -n "${HERMES_WEBUI_PYTHON:-}" ]]; then
    printf '%s\n' "${HERMES_WEBUI_PYTHON}"
    return
  fi
  if [[ -x "${HERMES_HOME_EFFECTIVE}/hermes-agent/venv/bin/python" ]]; then
    printf '%s\n' "${HERMES_HOME_EFFECTIVE}/hermes-agent/venv/bin/python"
    return
  fi
  command -v python3 || command -v python || return 1
}

start_hermes_launchd() {
  command -v launchctl >/dev/null 2>&1 || return 1
  local python_exe
  python_exe="$(hermes_python)" || return 1
  mkdir -p "${HERMES_HOME_EFFECTIVE}" "$(dirname "${HERMES_WEBUI_LOG_FILE:-${HERMES_HOME_EFFECTIVE}/webui.log}")"
  local log_file="${HERMES_WEBUI_LOG_FILE:-${HERMES_HOME_EFFECTIVE}/webui.log}"
  local plist="${HERMES_WEBUI_LAUNCH_AGENT_PLIST:-${HOME}/Library/LaunchAgents/com.pska.hermes-webui.plist}"
  local label="${HERMES_WEBUI_LAUNCH_AGENT_LABEL:-com.pska.hermes-webui}"
  local domain="gui/$(id -u)"
  local command_string escaped_command escaped_workdir escaped_log
  command_string="cd $(printf '%q' "${HERMES_WEBUI_HOME}") && HERMES_HOME=$(printf '%q' "${HERMES_HOME_EFFECTIVE}") HERMES_WEBUI_STATE_DIR=$(printf '%q' "${HERMES_WEBUI_STATE_DIR}") PSKA_API_BASE_URL=$(printf '%q' "${PSKA_API_BASE_URL}") HERMES_WEBUI_HOST=$(printf '%q' "${HERMES_WEBUI_HOST}") HERMES_WEBUI_PORT=$(printf '%q' "${HERMES_WEBUI_PORT}") HERMES_WEBUI_EXTENSION_DIR=$(printf '%q' "${HERMES_WEBUI_EXTENSION_DIR}") HERMES_WEBUI_EXTENSION_MANIFEST=$(printf '%q' "${HERMES_WEBUI_EXTENSION_MANIFEST}") exec $(printf '%q' "${python_exe}") $(printf '%q' "${HERMES_WEBUI_HOME}/bootstrap.py") --no-browser --foreground --host $(printf '%q' "${HERMES_WEBUI_HOST}") $(printf '%q' "${HERMES_WEBUI_PORT}")"
  escaped_command="$(printf '%s' "${command_string}" | xml_escape)"
  escaped_workdir="$(printf '%s' "${HERMES_WEBUI_HOME}" | xml_escape)"
  escaped_log="$(printf '%s' "${log_file}" | xml_escape)"
  mkdir -p "$(dirname "${plist}")"
  cat > "${plist}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>${escaped_command}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${escaped_workdir}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${escaped_log}</string>
  <key>StandardErrorPath</key>
  <string>${escaped_log}</string>
</dict>
</plist>
EOF
  launchctl bootout "${domain}" "${plist}" >/dev/null 2>&1 || true
  launchctl bootstrap "${domain}" "${plist}" >/dev/null 2>&1 || return 1
  launchctl kickstart -k "${domain}/${label}" >/dev/null 2>&1 || return 1
}

start_hermes_ctl() {
  [[ -x "${HERMES_WEBUI_HOME}/ctl.sh" ]] || die "Hermes ctl.sh not executable: ${HERMES_WEBUI_HOME}/ctl.sh"
  (
    cd "${HERMES_WEBUI_HOME}"
    HERMES_HOME="${HERMES_HOME_EFFECTIVE}" \
    HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR}" \
    PSKA_API_BASE_URL="${PSKA_API_BASE_URL}" \
    HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST}" \
    HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT}" \
    HERMES_WEBUI_EXTENSION_DIR="${HERMES_WEBUI_EXTENSION_DIR}" \
    HERMES_WEBUI_EXTENSION_MANIFEST="${HERMES_WEBUI_EXTENSION_MANIFEST}" \
      ./ctl.sh start "${HERMES_WEBUI_PORT}" --host "${HERMES_WEBUI_HOST}"
  )
}

hermes_port_pids() {
  command -v lsof >/dev/null 2>&1 || return 1
  lsof -tiTCP:"${HERMES_WEBUI_PORT}" -sTCP:LISTEN 2>/dev/null | awk 'NF'
}

process_env_value() {
  local pid="$1" key="$2"
  ps eww -p "${pid}" -o command= 2>/dev/null \
    | tr ' ' '\n' \
    | awk -F= -v key="${key}" '$1 == key { sub(/^[^=]*=/, ""); print; exit }'
}

hermes_running_environment_matches() {
  local pid found=0 home_value state_dir_value pska_value extension_dir_value extension_manifest_value
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    found=1
    home_value="$(process_env_value "${pid}" HERMES_HOME || true)"
    state_dir_value="$(process_env_value "${pid}" HERMES_WEBUI_STATE_DIR || true)"
    pska_value="$(process_env_value "${pid}" PSKA_API_BASE_URL || true)"
    extension_dir_value="$(process_env_value "${pid}" HERMES_WEBUI_EXTENSION_DIR || true)"
    extension_manifest_value="$(process_env_value "${pid}" HERMES_WEBUI_EXTENSION_MANIFEST || true)"
    if [[ -n "${home_value}" && "${home_value}" != "${HERMES_HOME_EFFECTIVE}" ]]; then
      return 1
    fi
    if [[ -n "${pska_value}" && "$(strip_trailing_slash "${pska_value}")" != "${PSKA_API_BASE_URL}" ]]; then
      return 1
    fi
    if [[ -n "${HERMES_WEBUI_STATE_DIR:-}" && "${state_dir_value}" != "${HERMES_WEBUI_STATE_DIR}" ]]; then
      return 1
    fi
    if [[ -n "${HERMES_WEBUI_EXTENSION_DIR:-}" && "${extension_dir_value}" != "${HERMES_WEBUI_EXTENSION_DIR}" ]]; then
      return 1
    fi
    if [[ -n "${HERMES_WEBUI_EXTENSION_MANIFEST:-}" && "${extension_manifest_value}" != "${HERMES_WEBUI_EXTENSION_MANIFEST}" ]]; then
      return 1
    fi
  done < <(hermes_port_pids || true)
  (( found == 1 ))
}

stop_hermes_port_processes() {
  local pid
  while IFS= read -r pid; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    warn "Stopping stale Hermes WebUI process ${pid} on port ${HERMES_WEBUI_PORT}"
    kill "${pid}" >/dev/null 2>&1 || true
  done < <(hermes_port_pids || true)
  sleep 1
}

open_hermes() {
  (( OPEN_FRONTEND )) || return 0
  if command -v open >/dev/null 2>&1; then
    log "Opening Hermes WebUI: ${HERMES_WEBUI_BASE_URL}"
    open "${HERMES_WEBUI_BASE_URL}"
  else
    log "Hermes WebUI: ${HERMES_WEBUI_BASE_URL}"
  fi
}

require_cmd curl
load_env_file "${STACK_ENV_FILE}"
load_env_file "${ENV_FILE}"

_pska_host_was_set="${PSKA_API_HOST+x}"
_pska_port_was_set="${PSKA_API_PORT+x}"
PSKA_API_HOST="${PSKA_API_HOST:-127.0.0.1}"
PSKA_API_PORT="${PSKA_API_PORT:-8765}"
PSKA_API_BASE_URL="${PSKA_API_BASE_URL:-http://${PSKA_API_HOST}:${PSKA_API_PORT}}"
PSKA_API_BASE_URL="$(strip_trailing_slash "${PSKA_API_BASE_URL}")"

if [[ -n "${PSKA_API_BASE_URL:-}" ]]; then
  _api_host_port="${PSKA_API_BASE_URL#http://}"
  _api_host_port="${_api_host_port#https://}"
  _api_host_port="${_api_host_port%%/*}"
  if [[ "${_api_host_port}" == *:* ]]; then
    if [[ -z "${_pska_host_was_set}" ]]; then
      PSKA_API_HOST="${_api_host_port%:*}"
    fi
    if [[ -z "${_pska_port_was_set}" ]]; then
      PSKA_API_PORT="${_api_host_port##*:}"
    fi
  fi
fi

RAGFLOW_BASE_URL="$(strip_trailing_slash "${RAGFLOW_BASE_URL:-http://127.0.0.1:9380}")"
GRAPHITI_BASE_URL="$(strip_trailing_slash "${GRAPHITI_BASE_URL:-http://127.0.0.1:8000}")"
_hermes_host_was_set="${HERMES_WEBUI_HOST+x}"
_hermes_port_was_set="${HERMES_WEBUI_PORT+x}"
HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-127.0.0.1}"
HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8787}"
HERMES_WEBUI_BASE_URL="${HERMES_WEBUI_BASE_URL:-http://${HERMES_WEBUI_HOST}:${HERMES_WEBUI_PORT}}"
HERMES_WEBUI_BASE_URL="$(strip_trailing_slash "${HERMES_WEBUI_BASE_URL}")"
_hermes_host_port="${HERMES_WEBUI_BASE_URL#http://}"
_hermes_host_port="${_hermes_host_port#https://}"
_hermes_host_port="${_hermes_host_port%%/*}"
if [[ "${_hermes_host_port}" == *:* ]]; then
  if [[ -z "${_hermes_host_was_set}" ]]; then
    HERMES_WEBUI_HOST="${_hermes_host_port%:*}"
  fi
  if [[ -z "${_hermes_port_was_set}" ]]; then
    HERMES_WEBUI_PORT="${_hermes_host_port##*:}"
  fi
fi
HERMES_HOME_EFFECTIVE="${HERMES_HOME:-${HOME}/.hermes}"
HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR:-${HERMES_HOME_EFFECTIVE}/webui}"
HERMES_WEBUI_EXTENSION_DIR="${HERMES_WEBUI_EXTENSION_DIR:-${HERMES_HOME_EFFECTIVE}/webui-local-extensions}"
HERMES_WEBUI_EXTENSION_MANIFEST="${HERMES_WEBUI_EXTENSION_MANIFEST:-extensions.json}"

log "Using stack env file: ${STACK_ENV_FILE}"
log "Using env file: ${ENV_FILE}"
log "PSKA API: ${PSKA_API_BASE_URL}"
log "Hermes WebUI: ${HERMES_WEBUI_BASE_URL}"

if (( STATUS_ONLY )); then
  echo "Status:"
  (( SKIP_RAGFLOW )) || print_status_line "RAGFlow" "${RAGFLOW_BASE_URL}/api/v1/system/ping"
  (( SKIP_GRAPHITI )) || print_status_line "Graphiti" "${GRAPHITI_BASE_URL}/healthcheck"
  (( SKIP_PSKA )) || print_pska_status_line
  (( SKIP_HERMES )) || print_status_line "Hermes WebUI" "${HERMES_WEBUI_BASE_URL}/health"
  exit 0
fi

(( SKIP_RAGFLOW )) || start_ragflow_if_needed
(( SKIP_GRAPHITI )) || start_graphiti_if_needed
(( SKIP_PSKA )) || start_pska_api_if_needed
ensure_hermes_pska_mcp_config
(( SKIP_HERMES )) || ensure_hermes_webui_extension
(( SKIP_HERMES )) || start_hermes_if_needed

if (( ! SKIP_HERMES && ! SKIP_PSKA )); then
  log "PSKA-mini is provided through the WebUI local extension sidecar"
fi

open_hermes
