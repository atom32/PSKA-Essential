#!/usr/bin/env bash
set -euo pipefail

PSKA_HOME="${PSKA_HOME:-/Users/xudawei/PSKA-Essential}"
HERMES_HOME_EFFECTIVE="${HERMES_HOME:-${HOME}/.hermes}"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-${HOME}/Library/LaunchAgents}"
BACKUP_ROOT="${PSKA_CHANNEL_BACKUP_ROOT:-${HERMES_HOME_EFFECTIVE}/pska-channel-backups}"

RAGFLOW_STABLE_HOME="${RAGFLOW_STABLE_HOME:-/Users/xudawei/PSKA-Components/ragflow}"
RAGFLOW_NEXT_HOME="${RAGFLOW_NEXT_HOME:-/Users/xudawei/PSKA-Components/ragflow-v0.27.0}"
GRAPHITI_HOME="${GRAPHITI_HOME:-/Users/xudawei/PSKA-Components/graphiti}"
GRAPHITI_COMPOSE_FILE="${GRAPHITI_COMPOSE_FILE:-docker-compose.pska.yml}"
GRAPHITI_ENV_FILE="${GRAPHITI_ENV_FILE:-.env.pska}"
HERMES_WEBUI_STABLE_HOME="${HERMES_WEBUI_STABLE_HOME:-/Users/xudawei/hermes-webui}"
HERMES_WEBUI_NEXT_HOME="${HERMES_WEBUI_NEXT_HOME:-/Users/xudawei/PSKA-Components/hermes-webui-next}"
HERMES_AGENT_STABLE_PYTHON="${HERMES_AGENT_STABLE_PYTHON:-${HERMES_HOME_EFFECTIVE}/hermes-agent/venv/bin/python}"
HERMES_AGENT_NEXT_HOME="${HERMES_AGENT_NEXT_HOME:-/Users/xudawei/PSKA-Components/hermes-agent-next}"
HERMES_AGENT_NEXT_PYTHON="${HERMES_AGENT_NEXT_PYTHON:-${HERMES_HOME_EFFECTIVE}/venvs/hermes-agent-next/bin/python}"

PSKA_ENV_FILE="${PSKA_ENV_FILE:-${PSKA_HOME}/.env.pska}"
PSKA_API_BASE_URL="${PSKA_API_BASE_URL:-http://127.0.0.1:8765}"
PSKA_MCP_URL="${PSKA_MCP_URL:-http://127.0.0.1:8766/mcp}"
PSKA_API_LABEL="${PSKA_API_LABEL:-com.pska.essential.api}"
PSKA_MCP_LABEL="${PSKA_MCP_LABEL:-com.pska.essential.mcp}"

RAGFLOW_STABLE_API="${RAGFLOW_STABLE_API:-http://127.0.0.1:9380}"
RAGFLOW_STABLE_WEB="${RAGFLOW_STABLE_WEB:-http://127.0.0.1:9222}"
RAGFLOW_NEXT_API="${RAGFLOW_NEXT_API:-http://127.0.0.1:9388}"
RAGFLOW_NEXT_WEB="${RAGFLOW_NEXT_WEB:-http://127.0.0.1:9228}"
RAGFLOW_NEXT_API_TOKEN="${RAGFLOW_NEXT_API_TOKEN:-${PSKA_V027_API_TOKEN:-}}"

EMBEDDING_DEV_BASE_URL="${EMBEDDING_DEV_BASE_URL:-http://127.0.0.1:6380}"
EMBEDDING_DEV_LABEL="${EMBEDDING_DEV_LABEL:-com.yuxi.infinity-emb}"

GBRAIN_BASE_URL="${GBRAIN_BASE_URL:-http://127.0.0.1:3131}"
GRAPHITI_BASE_URL="${GRAPHITI_BASE_URL:-http://127.0.0.1:8000}"
EIDOLIA_BASE_URL="${EIDOLIA_BASE_URL:-http://127.0.0.1:8797}"
EIDOLIA_HEALTH_PATH="${EIDOLIA_HEALTH_PATH:-/health}"

HERMES_WEBUI_STABLE_URL="${HERMES_WEBUI_STABLE_URL:-http://127.0.0.1:8787}"
HERMES_WEBUI_NEXT_URL="${HERMES_WEBUI_NEXT_URL:-http://127.0.0.1:8887}"
HERMES_CONFIG_PATH="${HERMES_CONFIG_PATH:-${HERMES_HOME_EFFECTIVE}/config.yaml}"
HERMES_EXTENSION_DIR="${HERMES_EXTENSION_DIR:-${HERMES_HOME_EFFECTIVE}/webui-local-extensions}"
HERMES_EXTENSION_MANIFEST="${HERMES_EXTENSION_MANIFEST:-extensions.json}"

APPLY=0
COMPONENT="all"
WITH_WORKER=0
STOP_STABLE_RAGFLOW=0
NO_RESTART_PSKA=0

usage() {
  cat <<'EOF'
Usage: scripts/pska_component_channel.sh <command> [options]

Commands:
  status                         Show stable/next ports and launchd labels.
  start-next                     Start side-by-side next components.
  stop-next                      Stop side-by-side next components.
  check-next                     Check side-by-side next components.
  stop-optional                  Stop optional non-dogfood components.
  promote-hermes-next            Replace stable Hermes WebUI launchd job with next WebUI/agent.
  rollback-hermes                Restore the most recent stable Hermes WebUI launchd backup.
  promote-ragflow-next           Point PSKA .env.pska at side-by-side RAGFlow v0.27.
  rollback-ragflow-env           Restore the most recent .env.pska backup.

Options:
  --component NAME               all, hermes, ragflow, ragflow-worker; stop-optional also accepts graphiti,next.
  --with-worker                  Include the v0.27 task executor for start/stop/check-next.
  --stop-stable-ragflow          After promote-ragflow-next, stop old stable RAGFlow jobs.
  --no-restart-pska              Do not restart PSKA API/MCP after .env.pska changes.
  --apply                        Actually perform mutations. Without this, mutating commands are dry-run.
  -h, --help                     Show this help.

Safe defaults:
  - status/check-next are read-only.
  - start-next/stop-next/promote/rollback require --apply.
  - stop-optional requires --apply and never stops PSKA, Hermes stable, GBrain, RAGFlow stable, embedding, or Eidolia.
  - next RAGFlow stays on 9388/9228 and isolated DB/Redis.
  - PSKA keeps using Hermes WebUI as the only frontend.
EOF
}

log() {
  printf '[pska-channel] %s\n' "$*"
}

warn() {
  printf '[pska-channel][warn] %s\n' "$*" >&2
}

die() {
  printf '[pska-channel][error] %s\n' "$*" >&2
  exit 1
}

domain() {
  printf 'gui/%s' "$(id -u)"
}

require_apply() {
  if (( ! APPLY )); then
    warn "dry-run only; add --apply to perform this action"
    return 1
  fi
  return 0
}

http_ok() {
  curl -fsS --max-time "${HTTP_PROBE_TIMEOUT:-5}" "$1" >/dev/null 2>&1
}

http_mcp_ok() {
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "${HTTP_PROBE_TIMEOUT:-5}" "$1" 2>/dev/null || true)"
  [[ "$code" == "200" || "$code" == "405" || "$code" == "406" ]]
}

docker_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi
  return 127
}

tcp_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

label_loaded() {
  launchctl print "$(domain)/$1" >/dev/null 2>&1
}

plist_path() {
  printf '%s/%s.plist\n' "${LAUNCH_AGENTS_DIR}" "$1"
}

xml_escape() {
  sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

shell_quote() {
  printf '%q' "$1"
}

status_url() {
  local name="$1" url="$2"
  if http_ok "$url"; then
    printf '  OK   %-24s %s\n' "$name" "$url"
  else
    printf '  MISS %-24s %s\n' "$name" "$url"
  fi
}

status_mcp_url() {
  local name="$1" url="$2"
  if http_mcp_ok "$url"; then
    printf '  OK   %-24s %s\n' "$name" "$url"
  else
    printf '  MISS %-24s %s\n' "$name" "$url"
  fi
}

status_label() {
  local label="$1"
  if label_loaded "$label"; then
    printf '  OK   %-32s loaded\n' "$label"
  else
    printf '  MISS %-32s not loaded\n' "$label"
  fi
}

print_pska_runtime_summary() {
  local json
  command -v python3 >/dev/null 2>&1 || return 0
  if ! json="$(curl -fsS --max-time "${HTTP_PROBE_TIMEOUT:-5}" "${PSKA_API_BASE_URL}/api/workspace/status?compact=1&view=channel&next_action_limit=0" 2>/dev/null)"; then
    return 0
  fi
  printf '%s' "$json" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
status = payload.get("workspace_status") or {}
providers = status.get("providers") or {}
components = status.get("components") or {}
embedding = components.get("embedding") or {}
gbrain = components.get("gbrain") or {}
memory = status.get("memory") or {}
kb = status.get("kb") or {}
providers_retrieval = providers.get("retrieval", "")
providers_kb = providers.get("kb", "")
providers_memory = providers.get("memory", "")
kb_status = kb.get("status", "")
kb_ready = kb.get("ready_dataset_count", 0)
kb_total = kb.get("dataset_count", 0)
memory_backend = memory.get("backend", "")
memory_cards = memory.get("card_count", 0)
embedding_mode = embedding.get("mode", "")
embedding_model = (embedding.get("model") or {}).get("configured", "")

print("[pska-channel] PSKA runtime")
print(f"  providers              retrieval={providers_retrieval} kb={providers_kb} memory={providers_memory}")
print(f"  kb                     status={kb_status} ready={kb_ready}/{kb_total}")
print(f"  memory                 backend={memory_backend} cards={memory_cards}")
print(f"  embedding              mode={embedding_mode} model={embedding_model}")
if gbrain:
    gbrain_selected = bool(gbrain.get("selected_as_memory_provider"))
    gbrain_mode = gbrain.get("mode", "")
    print(f"  gbrain                 selected={gbrain_selected} mode={gbrain_mode}")
'
}

print_status() {
  print_pska_runtime_summary

  log "primary HTTP endpoints"
  status_url "PSKA API" "${PSKA_API_BASE_URL}/api/health"
  status_mcp_url "PSKA HTTP MCP" "${PSKA_MCP_URL}"
  status_url "Hermes WebUI stable" "${HERMES_WEBUI_STABLE_URL}/health"

  log "provider HTTP endpoints"
  status_url "RAGFlow stable API" "${RAGFLOW_STABLE_API}/api/v1/system/ping"
  status_url "RAGFlow stable Web" "${RAGFLOW_STABLE_WEB}/"
  status_url "GBrain memory" "${GBRAIN_BASE_URL}/health"
  status_url "Embedding dev" "${EMBEDDING_DEV_BASE_URL}/health"
  status_url "Eidolia" "${EIDOLIA_BASE_URL}${EIDOLIA_HEALTH_PATH}"

  log "optional/side-by-side HTTP endpoints"
  status_url "Graphiti optional" "${GRAPHITI_BASE_URL}/healthcheck"
  status_url "RAGFlow next API" "${RAGFLOW_NEXT_API}/api/v1/system/ping"
  status_url "RAGFlow next Web" "${RAGFLOW_NEXT_WEB}/"
  status_url "Hermes WebUI next" "${HERMES_WEBUI_NEXT_URL}/health"

  log "launchd labels"
  status_label "com.pska.ragflow"
  status_label "com.pska.ragflow.web"
  status_label "com.pska.ragflow.task-executor"
  status_label "com.pska.ragflow.next"
  status_label "com.pska.ragflow.web.next"
  status_label "com.pska.ragflow.task-executor.next"
  status_label "${EMBEDDING_DEV_LABEL}"
  status_label "com.pska.gbrain-http"
  status_label "com.pska.eidolia"
  status_label "com.pska.hermes-webui"
  status_label "com.pska.hermes-webui.next"
}

write_shell_job_plist() {
  local label="$1" workdir="$2" command_string="$3" log_file="$4" keep_alive="${5:-false}" run_at_load="${6:-true}"
  local plist
  plist="$(plist_path "$label")"
  mkdir -p "$(dirname "$plist")" "$(dirname "$log_file")"

  local escaped_command escaped_workdir escaped_log
  escaped_command="$(printf '%s' "$command_string" | xml_escape)"
  escaped_workdir="$(printf '%s' "$workdir" | xml_escape)"
  escaped_log="$(printf '%s' "$log_file" | xml_escape)"

  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
    printf '%s\n' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
    printf '%s\n' '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    printf '%s\n' '<plist version="1.0">'
    printf '%s\n' '<dict>'
    printf '%s\n' '  <key>Label</key>'
    printf '  <string>%s</string>\n' "$label"
    printf '%s\n' '  <key>ProgramArguments</key>'
    printf '%s\n' '  <array>'
    printf '%s\n' '    <string>/bin/bash</string>'
    printf '%s\n' '    <string>-lc</string>'
    printf '    <string>%s</string>\n' "$escaped_command"
    printf '%s\n' '  </array>'
    printf '%s\n' '  <key>WorkingDirectory</key>'
    printf '  <string>%s</string>\n' "$escaped_workdir"
    printf '%s\n' '  <key>RunAtLoad</key>'
    if [[ "$run_at_load" == "true" ]]; then printf '%s\n' '  <true/>'; else printf '%s\n' '  <false/>'; fi
    printf '%s\n' '  <key>KeepAlive</key>'
    if [[ "$keep_alive" == "true" ]]; then printf '%s\n' '  <true/>'; else printf '%s\n' '  <false/>'; fi
    printf '%s\n' '  <key>StandardOutPath</key>'
    printf '  <string>%s</string>\n' "$escaped_log"
    printf '%s\n' '  <key>StandardErrorPath</key>'
    printf '  <string>%s</string>\n' "$escaped_log"
    printf '%s\n' '</dict>'
    printf '%s\n' '</plist>'
  } > "$plist"
  plutil -lint "$plist" >/dev/null
}

backup_file() {
  local path="$1" name="$2" stamp dest
  stamp="$(date +%Y%m%d-%H%M%S)"
  dest="${BACKUP_ROOT}/${stamp}/${name}"
  mkdir -p "$(dirname "$dest")"
  cp "$path" "$dest"
  printf '%s\n' "$dest"
}

latest_backup() {
  local pattern="$1"
  find "$BACKUP_ROOT" -type f -name "$pattern" 2>/dev/null | sort -r | head -1
}

bootstrap_label() {
  local label="$1"
  local plist
  plist="$(plist_path "$label")"
  launchctl bootout "$(domain)" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$(domain)" "$plist"
  launchctl enable "$(domain)/$label" >/dev/null 2>&1 || true
  launchctl kickstart -k "$(domain)/$label"
}

bootout_label() {
  local label="$1"
  local plist
  plist="$(plist_path "$label")"
  launchctl bootout "$(domain)/$label" >/dev/null 2>&1 || launchctl bootout "$(domain)" "$plist" >/dev/null 2>&1 || true
}

wait_for_label_unloaded() {
  local label="$1" attempts="${2:-20}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    if ! label_loaded "$label"; then
      return 0
    fi
    sleep 0.5
  done
  warn "launchd label still appears loaded after stop: $label"
  return 1
}

write_next_plists() {
  local ragflow_path node_path hermes_command
  ragflow_path="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  node_path="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.nvm/versions/node/v22.22.3/bin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

  write_shell_job_plist \
    "com.pska.ragflow.next" \
    "$RAGFLOW_NEXT_HOME" \
    "cd $(shell_quote "$RAGFLOW_NEXT_HOME") && PATH=$(shell_quote "$ragflow_path") exec ./pska-run-ragflow-server-v027.sh" \
    "$RAGFLOW_NEXT_HOME/.pska-ragflow-server-next.log" \
    false true

  write_shell_job_plist \
    "com.pska.ragflow.web.next" \
    "$RAGFLOW_NEXT_HOME/web" \
    "cd $(shell_quote "$RAGFLOW_NEXT_HOME") && PATH=$(shell_quote "$node_path") exec ./pska-run-ragflow-web-v027.sh" \
    "$RAGFLOW_NEXT_HOME/.pska-ragflow-web-next.log" \
    false true

  write_shell_job_plist \
    "com.pska.ragflow.task-executor.next" \
    "$RAGFLOW_NEXT_HOME" \
    "cd $(shell_quote "$RAGFLOW_NEXT_HOME") && PATH=$(shell_quote "$ragflow_path") exec ./pska-run-ragflow-task-executor-v027.sh" \
    "$RAGFLOW_NEXT_HOME/.pska-ragflow-task-executor-next.log" \
    true true

  hermes_command="cd $(shell_quote "$HERMES_WEBUI_NEXT_HOME") && HERMES_HOME=$(shell_quote "$HERMES_HOME_EFFECTIVE") HERMES_WEBUI_STATE_DIR=$(shell_quote "${HERMES_HOME_EFFECTIVE}/webui-next") HERMES_WEBUI_AGENT_DIR=$(shell_quote "$HERMES_AGENT_NEXT_HOME") HERMES_WEBUI_PYTHON=$(shell_quote "$HERMES_AGENT_NEXT_PYTHON") HERMES_CONFIG_PATH=$(shell_quote "$HERMES_CONFIG_PATH") HERMES_WEBUI_HOST=127.0.0.1 HERMES_WEBUI_PORT=8887 PSKA_API_BASE_URL=$(shell_quote "$PSKA_API_BASE_URL") HERMES_WEBUI_EXTENSION_DIR=$(shell_quote "$HERMES_EXTENSION_DIR") HERMES_WEBUI_EXTENSION_MANIFEST=$(shell_quote "$HERMES_EXTENSION_MANIFEST") exec ./pska-run-hermes-webui-next.sh"
  write_shell_job_plist \
    "com.pska.hermes-webui.next" \
    "$HERMES_WEBUI_NEXT_HOME" \
    "$hermes_command" \
    "${HERMES_HOME_EFFECTIVE}/webui-next.log" \
    true true
}

start_next_ragflow() {
  if (( ! APPLY )); then
    log "would write next RAGFlow plists and start com.pska.ragflow.next + com.pska.ragflow.web.next"
    (( WITH_WORKER )) && log "would also start com.pska.ragflow.task-executor.next"
    return 0
  fi
  [[ -d "$RAGFLOW_NEXT_HOME" ]] || die "RAGFLOW_NEXT_HOME not found: $RAGFLOW_NEXT_HOME"
  if [[ -n "$RAGFLOW_NEXT_API_TOKEN" ]]; then
    (cd "$RAGFLOW_NEXT_HOME" && ./pska-prepare-v027-db.sh && PSKA_V027_API_TOKEN="$RAGFLOW_NEXT_API_TOKEN" ./pska-seed-v027-dev-user.sh >/dev/null)
  else
    (cd "$RAGFLOW_NEXT_HOME" && ./pska-prepare-v027-db.sh && ./pska-seed-v027-dev-user.sh >/dev/null)
  fi
  write_next_plists
  bootstrap_label "com.pska.ragflow.next"
  bootstrap_label "com.pska.ragflow.web.next"
  if (( WITH_WORKER )); then
    bootstrap_label "com.pska.ragflow.task-executor.next"
  fi
}

start_next_hermes() {
  if (( ! APPLY )); then
    log "would write next Hermes WebUI plist and start com.pska.hermes-webui.next"
    return 0
  fi
  [[ -d "$HERMES_WEBUI_NEXT_HOME" ]] || die "HERMES_WEBUI_NEXT_HOME not found: $HERMES_WEBUI_NEXT_HOME"
  [[ -x "$HERMES_AGENT_NEXT_PYTHON" ]] || die "HERMES_AGENT_NEXT_PYTHON not executable: $HERMES_AGENT_NEXT_PYTHON"
  write_next_plists
  bootstrap_label "com.pska.hermes-webui.next"
}

stop_next_ragflow() {
  if (( ! APPLY )); then
    log "would stop com.pska.ragflow.next and com.pska.ragflow.web.next"
    (( WITH_WORKER )) && log "would also stop com.pska.ragflow.task-executor.next"
    return 0
  fi
  bootout_label "com.pska.ragflow.web.next"
  bootout_label "com.pska.ragflow.next"
  bootout_label "com.pska.ragflow.task-executor.next"
  wait_for_label_unloaded "com.pska.ragflow.web.next" || true
  wait_for_label_unloaded "com.pska.ragflow.next" || true
  wait_for_label_unloaded "com.pska.ragflow.task-executor.next" || true
}

stop_next_hermes() {
  if (( ! APPLY )); then
    log "would stop com.pska.hermes-webui.next"
    return 0
  fi
  bootout_label "com.pska.hermes-webui.next"
  wait_for_label_unloaded "com.pska.hermes-webui.next" || true
}

stop_optional_graphiti() {
  if (( ! APPLY )); then
    log "would stop optional Graphiti/Neo4j via ${GRAPHITI_HOME}/${GRAPHITI_COMPOSE_FILE}"
    log "would preserve Neo4j volume because this uses docker compose down without -v"
    return 0
  fi
  [[ -d "$GRAPHITI_HOME" ]] || die "GRAPHITI_HOME not found: $GRAPHITI_HOME"
  [[ -f "${GRAPHITI_HOME}/${GRAPHITI_COMPOSE_FILE}" ]] || die "Graphiti compose file not found: ${GRAPHITI_HOME}/${GRAPHITI_COMPOSE_FILE}"
  docker_compose version >/dev/null 2>&1 || die "docker compose is required to stop optional Graphiti"
  (
    cd "$GRAPHITI_HOME"
    if [[ -f "$GRAPHITI_ENV_FILE" ]]; then
      docker_compose -f "$GRAPHITI_COMPOSE_FILE" --env-file "$GRAPHITI_ENV_FILE" down
    else
      docker_compose -f "$GRAPHITI_COMPOSE_FILE" down
    fi
  )
}

stop_optional_next() {
  stop_next_hermes
  stop_next_ragflow
}

check_next_ragflow() {
  status_url "RAGFlow next API" "${RAGFLOW_NEXT_API}/api/v1/system/ping"
  status_url "RAGFlow next Web" "${RAGFLOW_NEXT_WEB}/api/v1/system/ping"
}

check_next_hermes() {
  status_url "Hermes WebUI next" "${HERMES_WEBUI_NEXT_URL}/health"
  if http_ok "${HERMES_WEBUI_NEXT_URL}/health" && [[ -x "${HERMES_WEBUI_NEXT_HOME}/pska-check-hermes-webui-next.sh" ]]; then
    (cd "$HERMES_WEBUI_NEXT_HOME" && ./pska-check-hermes-webui-next.sh)
  fi
}

set_env_value() {
  local file="$1" key="$2" value="$3" tmp seen=0
  tmp="$(mktemp "${TMPDIR:-/tmp}/pska-env.XXXXXX")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$key="* || "$line" == "export $key="* ]]; then
      printf '%s=%s\n' "$key" "$value" >> "$tmp"
      seen=1
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$file"
  if (( ! seen )); then
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$file"
}

restart_pska_if_needed() {
  (( NO_RESTART_PSKA )) && return 0
  if (( ! APPLY )); then
    log "would restart PSKA API/MCP launchd jobs"
    return 0
  fi
  launchctl kickstart -k "$(domain)/${PSKA_API_LABEL}" >/dev/null 2>&1 || warn "could not restart ${PSKA_API_LABEL}"
  launchctl kickstart -k "$(domain)/${PSKA_MCP_LABEL}" >/dev/null 2>&1 || warn "could not restart ${PSKA_MCP_LABEL}"
}

promote_ragflow_next() {
  if (( ! APPLY )); then
    log "would start/check RAGFlow v0.27 and update ${PSKA_ENV_FILE} RAGFLOW_BASE_URL to ${RAGFLOW_NEXT_API}"
    log "would update RAGFLOW_API_KEY from explicit RAGFLOW_NEXT_API_TOKEN without printing it"
    restart_pska_if_needed
    (( STOP_STABLE_RAGFLOW )) && log "would stop stable RAGFlow launchd jobs"
    return 0
  fi
  [[ -f "$PSKA_ENV_FILE" ]] || die "PSKA_ENV_FILE not found: $PSKA_ENV_FILE"
  [[ -n "$RAGFLOW_NEXT_API_TOKEN" ]] || die "RAGFLOW_NEXT_API_TOKEN must be set for promote-ragflow-next --apply"
  start_next_ragflow
  http_ok "${RAGFLOW_NEXT_API}/api/v1/system/ping" || die "RAGFlow next API is not healthy"
  backup_file "$PSKA_ENV_FILE" ".env.pska" >/dev/null
  set_env_value "$PSKA_ENV_FILE" "RAGFLOW_BASE_URL" "$RAGFLOW_NEXT_API"
  set_env_value "$PSKA_ENV_FILE" "RAGFLOW_API_KEY" "$RAGFLOW_NEXT_API_TOKEN"
  restart_pska_if_needed
  if (( STOP_STABLE_RAGFLOW )); then
    bootout_label "com.pska.ragflow.web"
    bootout_label "com.pska.ragflow"
    bootout_label "com.pska.ragflow.task-executor"
  fi
}

rollback_ragflow_env() {
  local backup
  backup="$(latest_backup ".env.pska")"
  [[ -n "$backup" ]] || die "no .env.pska backup found under $BACKUP_ROOT"
  if (( ! APPLY )); then
    log "would restore $backup to $PSKA_ENV_FILE"
    restart_pska_if_needed
    return 0
  fi
  cp "$backup" "$PSKA_ENV_FILE"
  restart_pska_if_needed
}

write_stable_hermes_next_plist() {
  local label command_string
  label="com.pska.hermes-webui"
  command_string="cd $(shell_quote "$HERMES_WEBUI_NEXT_HOME") && export HERMES_HOME=$(shell_quote "$HERMES_HOME_EFFECTIVE") HERMES_WEBUI_STATE_DIR=$(shell_quote "${HERMES_HOME_EFFECTIVE}/webui") HERMES_WEBUI_AGENT_DIR=$(shell_quote "$HERMES_AGENT_NEXT_HOME") HERMES_WEBUI_PYTHON=$(shell_quote "$HERMES_AGENT_NEXT_PYTHON") HERMES_CONFIG_PATH=$(shell_quote "$HERMES_CONFIG_PATH") HERMES_WEBUI_HOST=0.0.0.0 HERMES_WEBUI_PORT=8787 PSKA_API_BASE_URL=$(shell_quote "$PSKA_API_BASE_URL") HERMES_WEBUI_EXTENSION_DIR=$(shell_quote "$HERMES_EXTENSION_DIR") HERMES_WEBUI_EXTENSION_MANIFEST=$(shell_quote "$HERMES_EXTENSION_MANIFEST") && ./pska-sync-extension-next.sh >/dev/null && exec $(shell_quote "$HERMES_AGENT_NEXT_PYTHON") $(shell_quote "${HERMES_WEBUI_NEXT_HOME}/bootstrap.py") --no-browser --foreground --host 0.0.0.0 8787"
  write_shell_job_plist "$label" "$HERMES_WEBUI_NEXT_HOME" "$command_string" "${HERMES_HOME_EFFECTIVE}/webui.log" true true
}

promote_hermes_next() {
  local plist
  plist="$(plist_path "com.pska.hermes-webui")"
  if (( ! APPLY )); then
    log "would back up $plist and replace stable Hermes WebUI with next WebUI/agent on port 8787"
    return 0
  fi
  [[ -f "$plist" ]] || die "stable Hermes WebUI plist not found: $plist"
  [[ -x "$HERMES_AGENT_NEXT_PYTHON" ]] || die "HERMES_AGENT_NEXT_PYTHON not executable: $HERMES_AGENT_NEXT_PYTHON"
  if grep -F "$HERMES_WEBUI_NEXT_HOME" "$plist" >/dev/null 2>&1; then
    log "stable Hermes WebUI already points at next; refreshing plist without replacing rollback backup"
  else
    backup_file "$plist" "com.pska.hermes-webui.plist" >/dev/null
  fi
  write_stable_hermes_next_plist
  bootstrap_label "com.pska.hermes-webui"
}

rollback_hermes() {
  local backup plist
  backup="$(latest_backup "com.pska.hermes-webui.plist")"
  plist="$(plist_path "com.pska.hermes-webui")"
  [[ -n "$backup" ]] || die "no Hermes WebUI plist backup found under $BACKUP_ROOT"
  if (( ! APPLY )); then
    log "would restore $backup to $plist and restart com.pska.hermes-webui"
    return 0
  fi
  cp "$backup" "$plist"
  plutil -lint "$plist" >/dev/null
  bootstrap_label "com.pska.hermes-webui"
}

run_start_next() {
  case "$COMPONENT" in
    all) start_next_ragflow; start_next_hermes ;;
    ragflow) start_next_ragflow ;;
    ragflow-worker) WITH_WORKER=1; start_next_ragflow ;;
    hermes) start_next_hermes ;;
    *) die "unknown component: $COMPONENT" ;;
  esac
}

run_stop_next() {
  case "$COMPONENT" in
    all) stop_next_hermes; stop_next_ragflow ;;
    ragflow) stop_next_ragflow ;;
    ragflow-worker) WITH_WORKER=1; stop_next_ragflow ;;
    hermes) stop_next_hermes ;;
    *) die "unknown component: $COMPONENT" ;;
  esac
}

run_stop_optional() {
  case "$COMPONENT" in
    all) stop_optional_next; stop_optional_graphiti ;;
    graphiti) stop_optional_graphiti ;;
    next) stop_optional_next ;;
    hermes) stop_next_hermes ;;
    ragflow|ragflow-worker) stop_next_ragflow ;;
    *) die "unknown stop-optional component: $COMPONENT" ;;
  esac
}

run_check_next() {
  case "$COMPONENT" in
    all) check_next_ragflow; check_next_hermes ;;
    ragflow|ragflow-worker) check_next_ragflow ;;
    hermes) check_next_hermes ;;
    *) die "unknown component: $COMPONENT" ;;
  esac
}

command="${1:-status}"
if [[ $# -gt 0 ]]; then
  shift
fi
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --component) shift; COMPONENT="${1:-}" ;;
    --with-worker) WITH_WORKER=1 ;;
    --stop-stable-ragflow) STOP_STABLE_RAGFLOW=1 ;;
    --no-restart-pska) NO_RESTART_PSKA=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

case "$command" in
  status) print_status ;;
  start-next) run_start_next ;;
  stop-next) run_stop_next ;;
  check-next) run_check_next ;;
  stop-optional) run_stop_optional ;;
  promote-hermes-next) promote_hermes_next ;;
  rollback-hermes) rollback_hermes ;;
  promote-ragflow-next) promote_ragflow_next ;;
  rollback-ragflow-env) rollback_ragflow_env ;;
  -h|--help|help) usage ;;
  *) die "unknown command: $command" ;;
esac
