#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PSKA_FULL_ENV_FILE:-${SCRIPT_DIR}/.env}"
ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
export SCRIPT_DIR

log() { printf '[pska-full] %s\n' "$*"; }
warn() { printf '[pska-full] warning: %s\n' "$*" >&2; }
die() { printf '[pska-full] error: %s\n' "$*" >&2; exit 1; }

docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    die "Docker Compose is not available."
  fi
}

python_bin() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die "python3 or python is required for bootstrap templating."
  fi
}

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    die "created ${ENV_FILE}; edit it first, especially HERMES_WEBUI_PASSWORD, HERMES_GATEWAY_API_KEY, and RAGFLOW_API_KEY, then rerun."
  fi
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

abs_dir() {
  local path="$1"
  mkdir -p "${path}"
  (cd "${path}" && pwd)
}

script_path() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s\n' "${SCRIPT_DIR}/${path}"
  fi
}

resolve_paths() {
  PSKA_SUITE_HOME="$(abs_dir "$(script_path "${PSKA_SUITE_HOME:-.runtime}")")"
  PSKA_ESSENTIAL_REPO="$(abs_dir "$(script_path "${PSKA_ESSENTIAL_REPO:-../..}")")"
  HERMES_HOME_DIR="$(abs_dir "$(script_path "${HERMES_HOME_DIR:-${PSKA_SUITE_HOME}/hermes-home}")")"
  HERMES_WORKSPACE="$(abs_dir "$(script_path "${HERMES_WORKSPACE:-${PSKA_SUITE_HOME}/workspace}")")"
  EIDOLIA_REPO="${EIDOLIA_REPO:-${PSKA_SUITE_HOME}/repos/InfinityCanvas}"
  HERMES_WEBUI_REPO="${HERMES_WEBUI_REPO:-${PSKA_SUITE_HOME}/repos/hermes-webui}"
  RAGFLOW_HOME="${RAGFLOW_HOME:-${PSKA_SUITE_HOME}/repos/ragflow}"
  EIDOLIA_REPO="$(script_path "${EIDOLIA_REPO}")"
  HERMES_WEBUI_REPO="$(script_path "${HERMES_WEBUI_REPO}")"
  RAGFLOW_HOME="$(script_path "${RAGFLOW_HOME}")"
  EIDOLIA_REPO="$(abs_dir "$(dirname "${EIDOLIA_REPO}")")/$(basename "${EIDOLIA_REPO}")"
  HERMES_WEBUI_REPO="$(abs_dir "$(dirname "${HERMES_WEBUI_REPO}")")/$(basename "${HERMES_WEBUI_REPO}")"
  RAGFLOW_HOME="$(abs_dir "$(dirname "${RAGFLOW_HOME}")")/$(basename "${RAGFLOW_HOME}")"
  PSKA_RAGFLOW_ENV="${PSKA_SUITE_HOME}/ragflow.env"
  PSKA_RAGFLOW_OVERRIDE="${PSKA_SUITE_HOME}/ragflow-pska-full.override.yml"
  PSKA_RAGFLOW_SERVICE_CONF="${PSKA_SUITE_HOME}/ragflow-service_conf.yaml.template"
  export PSKA_SUITE_HOME PSKA_ESSENTIAL_REPO HERMES_HOME_DIR HERMES_WORKSPACE
  export EIDOLIA_REPO HERMES_WEBUI_REPO RAGFLOW_HOME
  export PSKA_RAGFLOW_ENV PSKA_RAGFLOW_OVERRIDE PSKA_RAGFLOW_SERVICE_CONF
}

repo_dirty() {
  local dir="$1"
  [[ -n "$(git -C "${dir}" status --porcelain 2>/dev/null || true)" ]]
}

ensure_repo() {
  local name="$1" url="$2" ref="$3" dir="$4"
  if [[ ! -d "${dir}/.git" ]]; then
    if [[ -d "${dir}" && -n "$(find "${dir}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      die "${name} destination exists but is not a git repo: ${dir}"
    fi
    log "cloning ${name} (${ref}) -> ${dir}"
    git clone --depth 1 --branch "${ref}" "${url}" "${dir}" || {
      rm -rf "${dir}"
      git clone "${url}" "${dir}"
      git -C "${dir}" checkout "${ref}"
    }
    return
  fi
  if [[ "${PSKA_FULL_UPDATE_REPOS:-0}" != "1" ]]; then
    log "${name} exists; leaving it as-is (set PSKA_FULL_UPDATE_REPOS=1 to fetch/checkout ${ref})."
    return
  fi
  if repo_dirty "${dir}"; then
    warn "${name} has local changes; not updating ${dir}."
    return
  fi
  log "updating ${name} -> ${ref}"
  git -C "${dir}" fetch --tags --prune
  git -C "${dir}" checkout "${ref}"
  git -C "${dir}" pull --ff-only || true
}

ensure_repos() {
  mkdir -p "${PSKA_SUITE_HOME}/repos"
  ensure_repo "Eidolia" "${EIDOLIA_REPO_URL:-https://github.com/atom32/InfinityCanvas.git}" "${EIDOLIA_REF:-main}" "${EIDOLIA_REPO}"
  ensure_repo "Hermes-WebUI" "${HERMES_WEBUI_REPO_URL:-https://github.com/nesquena/hermes-webui.git}" "${HERMES_WEBUI_REF:-master}" "${HERMES_WEBUI_REPO}"
  ensure_repo "RAGFlow" "${RAGFLOW_REPO_URL:-https://github.com/infiniflow/ragflow.git}" "${RAGFLOW_REF:-v0.26.4}" "${RAGFLOW_HOME}"
}

write_pska_env() {
  local py
  py="$(python_bin)"
  "${py}" - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["HERMES_HOME_DIR"])
home.mkdir(parents=True, exist_ok=True)
values = {
    "PSKA_DEV_FAKE": os.getenv("PSKA_DEV_FAKE", ""),
    "PSKA_RETRIEVAL_PROVIDER": os.getenv("PSKA_RETRIEVAL_PROVIDER", "ragflow"),
    "PSKA_KB_PROVIDER": os.getenv("PSKA_KB_PROVIDER", "ragflow"),
    "PSKA_MEMORY_PROVIDER": os.getenv("PSKA_MEMORY_PROVIDER", "sqlite"),
    "PSKA_REVIEW_DB": "/data/review.sqlite3",
    "PSKA_MEMORY_DB": "/data/memory.sqlite3",
    "PSKA_GOVERNANCE_DURABLE_MEMORY": os.getenv("PSKA_GOVERNANCE_DURABLE_MEMORY", "manual_review"),
    "PSKA_WORKSPACE_ID": os.getenv("PSKA_WORKSPACE_ID", "default"),
    "PSKA_TENANT_ID": os.getenv("PSKA_TENANT_ID", ""),
    "RAGFLOW_BASE_URL": os.getenv("RAGFLOW_BASE_URL", "http://host.docker.internal:9380"),
    "RAGFLOW_API_KEY": os.getenv("RAGFLOW_API_KEY", ""),
    "RAGFLOW_TIMEOUT": os.getenv("RAGFLOW_TIMEOUT", "30"),
    "PSKA_DIAGNOSTICS_TIMEOUT": os.getenv("PSKA_DIAGNOSTICS_TIMEOUT", "3"),
    "GRAPHITI_BASE_URL": "",
    "GRAPHITI_GROUP_ID": "pska-essential",
}
lines = [
    "# Generated by deploy/full-compose/bootstrap.sh.",
    "# Used by PSKA Product API and Hermes Agent PSKA MCP.",
]
for key, value in values.items():
    lines.append(f"{key}={json.dumps(str(value), ensure_ascii=False)}")
(home / "pska.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

write_hermes_config() {
  local config="${HERMES_HOME_DIR}/config.yaml"
  local py
  py="$(python_bin)"
  if [[ -f "${config}" && "${PSKA_FULL_OVERWRITE_HERMES_CONFIG:-0}" != "1" ]]; then
    log "Hermes config exists; leaving ${config} unchanged."
    return
  fi
  "${py}" - <<'PY'
import os
from pathlib import Path
from string import Template

script_dir = Path(os.environ["SCRIPT_DIR"])
home = Path(os.environ["HERMES_HOME_DIR"])
template = (script_dir / "hermes" / "config.yaml.template").read_text(encoding="utf-8")
mapping = {
    "HERMES_MODEL_DEFAULT": os.getenv("HERMES_MODEL_DEFAULT", "deepseek-v4-flash"),
    "HERMES_MODEL_PROVIDER": os.getenv("HERMES_MODEL_PROVIDER", "deepseek"),
    "HERMES_MODEL_BASE_URL": os.getenv("HERMES_MODEL_BASE_URL", "https://api.deepseek.com/v1"),
    "HERMES_AGENT_MAX_TURNS": os.getenv("HERMES_AGENT_MAX_TURNS", "150"),
}
home.mkdir(parents=True, exist_ok=True)
(home / "config.yaml").write_text(Template(template).safe_substitute(mapping), encoding="utf-8")
PY
}

write_extension_state() {
  local py
  py="$(python_bin)"
  "${py}" - <<'PY'
import json
import os
from pathlib import Path

state_dir = Path(os.environ["HERMES_HOME_DIR"]) / "webui"
state_dir.mkdir(parents=True, exist_ok=True)
path = state_dir / "extension-overrides.json"
if path.exists():
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
else:
    state = {}
state["version"] = 1
state.setdefault("disabled_extensions", [])
consents = state.setdefault("sidecar_proxy_consents", {})
consents["pska-mini"] = "http://127.0.0.1:8765"
consents["eidolia"] = "http://127.0.0.1:8797"
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

write_ragflow_env() {
  local py ragflow_env
  py="$(python_bin)"
  ragflow_env="${RAGFLOW_HOME}/docker/.env"
  [[ -f "${ragflow_env}" ]] || die "RAGFlow env template not found: ${ragflow_env}"
  "${py}" - "${ragflow_env}" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
dest = Path(os.environ["PSKA_RAGFLOW_ENV"])
extra = [item.strip() for item in os.getenv("RAGFLOW_EXTRA_PROFILES", "").split(",") if item.strip()]
embedding_enabled = os.getenv("EMBEDDING_ENABLED", "1") != "0"
if embedding_enabled:
    extra = [item for item in extra if not item.startswith("tei-")]
profiles = [os.getenv("DOC_ENGINE", "elasticsearch"), os.getenv("DEVICE", "cpu"), *extra]
embedding_port = os.getenv("EMBEDDING_HOST_PORT", "6380")
tei_base_url = os.getenv("RAGFLOW_TEI_BASE_URL") or (
    "http://pska-embedding:80"
    if embedding_enabled
    else f"http://host.docker.internal:{embedding_port}"
)
updates = {
    "DOC_ENGINE": os.getenv("DOC_ENGINE", "elasticsearch"),
    "DEVICE": os.getenv("DEVICE", "cpu"),
    "COMPOSE_PROFILES": ",".join(profiles),
    "RAGFLOW_IMAGE": os.getenv("RAGFLOW_IMAGE", "infiniflow/ragflow:v0.26.4"),
    "SVR_HTTP_PORT": os.getenv("RAGFLOW_HOST_PORT", "9380"),
    "SVR_WEB_HTTP_PORT": os.getenv("RAGFLOW_WEB_HTTP_PORT", "8080"),
    "SVR_WEB_HTTPS_PORT": os.getenv("RAGFLOW_WEB_HTTPS_PORT", "8443"),
    "ADMIN_SVR_HTTP_PORT": os.getenv("RAGFLOW_ADMIN_PORT", "9381"),
    "SVR_MCP_PORT": os.getenv("RAGFLOW_MCP_PORT", "9382"),
    "GO_HTTP_PORT": os.getenv("RAGFLOW_GO_HTTP_PORT", "9384"),
    "GO_ADMIN_PORT": os.getenv("RAGFLOW_GO_ADMIN_PORT", "9383"),
    "EXPOSE_MYSQL_PORT": os.getenv("RAGFLOW_MYSQL_PORT", "13306"),
    "REDIS_PORT": os.getenv("RAGFLOW_REDIS_PORT", "16379"),
    "MINIO_PORT": os.getenv("RAGFLOW_MINIO_PORT", "19000"),
    "MINIO_CONSOLE_PORT": os.getenv("RAGFLOW_MINIO_CONSOLE_PORT", "19001"),
    "ES_PORT": os.getenv("RAGFLOW_ES_PORT", "19200"),
    "OS_PORT": os.getenv("RAGFLOW_OS_PORT", "19201"),
    "MEM_LIMIT": os.getenv("RAGFLOW_MEM_LIMIT", "8073741824"),
    "REGISTER_ENABLED": os.getenv("RAGFLOW_REGISTER_ENABLED", "1"),
    "MYSQL_PASSWORD": os.getenv("RAGFLOW_MYSQL_PASSWORD", "pska_full_mysql_change_me"),
    "REDIS_PASSWORD": os.getenv("RAGFLOW_REDIS_PASSWORD", "pska_full_redis_change_me"),
    "MINIO_USER": os.getenv("RAGFLOW_MINIO_USER", "rag_flow"),
    "MINIO_PASSWORD": os.getenv("RAGFLOW_MINIO_PASSWORD", "pska_full_minio_change_me"),
    "ELASTIC_PASSWORD": os.getenv("RAGFLOW_ELASTIC_PASSWORD", "pska_full_elastic_change_me"),
    "OPENSEARCH_PASSWORD": os.getenv("RAGFLOW_OPENSEARCH_PASSWORD", "PskA_full_OpenSearch_01!"),
    "TEI_IMAGE_CPU": os.getenv("EMBEDDING_IMAGE") or "ghcr.io/huggingface/text-embeddings-inference:cpu-1.8",
    "TEI_MODEL": os.getenv("EMBEDDING_MODEL_ID") or "BAAI/bge-small-en-v1.5",
    "TEI_HOST": os.getenv("RAGFLOW_TEI_HOST") or ("pska-embedding" if embedding_enabled else "host.docker.internal"),
    "TEI_PORT": "80" if embedding_enabled else embedding_port,
    "TEI_BASE_URL": tei_base_url,
    "TZ": os.getenv("TZ", "Asia/Shanghai"),
}
optional = {
    "MACOS": os.getenv("RAGFLOW_MACOS", ""),
    "HF_ENDPOINT": os.getenv("HF_ENDPOINT", ""),
}
updates.update({key: value for key, value in optional.items() if value})

lines = source.read_text(encoding="utf-8").splitlines()
seen = set()
out = [
    "# Generated by deploy/full-compose/bootstrap.sh.",
    f"# Source template: {source}",
    "# Keep this file under PSKA_SUITE_HOME so the upstream RAGFlow checkout stays clean.",
]
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        out.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

write_ragflow_service_conf() {
  local py source
  py="$(python_bin)"
  source="${RAGFLOW_HOME}/docker/service_conf.yaml.template"
  [[ -f "${source}" ]] || die "RAGFlow service config template not found: ${source}"
  "${py}" - "${source}" "${PSKA_RAGFLOW_SERVICE_CONF}" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
dest = Path(sys.argv[2])
embedding_enabled = os.getenv("EMBEDDING_ENABLED", "1") != "0"
embedding_port = os.getenv("EMBEDDING_HOST_PORT", "6380")
explicit_base_url = os.getenv("RAGFLOW_TEI_BASE_URL")
base_url = explicit_base_url or (
    "http://pska-embedding:80"
    if embedding_enabled
    else f"http://host.docker.internal:{embedding_port}"
)
text = source.read_text(encoding="utf-8")
old = "      base_url: 'http://${TEI_HOST}:80'"
if old not in text:
    raise SystemExit(f"unsupported RAGFlow service_conf template; TEI base_url marker not found in {source}")
if embedding_enabled or explicit_base_url:
    text = text.replace(old, f"      base_url: '{base_url}'", 1)
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(text, encoding="utf-8")
PY
}

write_ragflow_override() {
  local py
  py="$(python_bin)"
  "${py}" - <<'PY'
import json
import os
from pathlib import Path

override = Path(os.environ["PSKA_RAGFLOW_OVERRIDE"])
service_conf = Path(os.environ["PSKA_RAGFLOW_SERVICE_CONF"])
doc_engine = os.getenv("DOC_ENGINE", "elasticsearch")
device = os.getenv("DEVICE", "cpu")
extra = [item.strip() for item in os.getenv("RAGFLOW_EXTRA_PROFILES", "").split(",") if item.strip()]
embedding_marker = os.getenv("RAGFLOW_EMBEDDING_PROFILE_MARKER", "tei-cpu")
embedding_enabled = os.getenv("EMBEDDING_ENABLED", "1") != "0"
profiles = [doc_engine, device]
profiles.extend(
    item
    for item in extra
    if item not in profiles and (not embedding_enabled or not item.startswith("tei-"))
)
if embedding_enabled and embedding_marker:
    profiles.append(embedding_marker)
container_profiles = ",".join(profiles)
embedding_port = os.getenv("EMBEDDING_HOST_PORT", "6380")
explicit_base_url = os.getenv("RAGFLOW_TEI_BASE_URL")
tei_base_url = explicit_base_url or (
    "http://pska-embedding:80"
    if embedding_enabled
    else f"http://host.docker.internal:{embedding_port}"
)
tei_model = os.getenv("EMBEDDING_MODEL_ID") or "BAAI/bge-small-en-v1.5"
volume = f"{service_conf}:/ragflow/conf/service_conf.yaml.template:ro"
mysql_password = os.getenv("RAGFLOW_MYSQL_PASSWORD", "pska_full_mysql_change_me")
redis_password = os.getenv("RAGFLOW_REDIS_PASSWORD", "pska_full_redis_change_me")
minio_user = os.getenv("RAGFLOW_MINIO_USER", "rag_flow")
minio_password = os.getenv("RAGFLOW_MINIO_PASSWORD", "pska_full_minio_change_me")
elastic_password = os.getenv("RAGFLOW_ELASTIC_PASSWORD", "pska_full_elastic_change_me")
opensearch_password = os.getenv("RAGFLOW_OPENSEARCH_PASSWORD", "PskA_full_OpenSearch_01!")
tei_base_url_lines = []
if embedding_enabled or explicit_base_url:
    tei_base_url_lines = [f"      TEI_BASE_URL: {json.dumps(tei_base_url)}"]

def env_lines(values):
    return [f"      {key}: {json.dumps(str(value))}" for key, value in values.items()]

ragflow_runtime_env = {
    "COMPOSE_PROFILES": container_profiles,
    "TEI_MODEL": tei_model,
    "MYSQL_PASSWORD": mysql_password,
    "REDIS_PASSWORD": redis_password,
    "MINIO_USER": minio_user,
    "MINIO_PASSWORD": minio_password,
    "ELASTIC_PASSWORD": elastic_password,
    "OPENSEARCH_PASSWORD": opensearch_password,
}
override.parent.mkdir(parents=True, exist_ok=True)
pska_suite_network_name = f"{os.getenv('PSKA_FULL_PROJECT', 'pska-full')}_pska-suite"
ragflow_extra_network_lines = (
    [
        "    networks:",
        "      - default",
        "      - pska_suite",
    ]
    if embedding_enabled
    else []
)
external_network_lines = (
    [
        "networks:",
        "  pska_suite:",
        "    external: true",
        f"    name: {json.dumps(pska_suite_network_name)}",
    ]
    if embedding_enabled
    else []
)
override.write_text(
    "\n".join(
        [
            "# Generated by deploy/full-compose/bootstrap.sh.",
            "services:",
            "  es01:",
            "    environment:",
            *env_lines({"ELASTIC_PASSWORD": elastic_password}),
            "  opensearch01:",
            "    environment:",
            *env_lines({"OPENSEARCH_PASSWORD": opensearch_password, "OPENSEARCH_INITIAL_ADMIN_PASSWORD": opensearch_password}),
            "  mysql:",
            "    environment:",
            *env_lines({"MYSQL_PASSWORD": mysql_password, "MYSQL_ROOT_PASSWORD": mysql_password}),
            "  minio:",
            "    environment:",
            *env_lines({"MINIO_USER": minio_user, "MINIO_PASSWORD": minio_password, "MINIO_ROOT_USER": minio_user, "MINIO_ROOT_PASSWORD": minio_password}),
            "  redis:",
            "    environment:",
            *env_lines({"REDIS_PASSWORD": redis_password}),
            "  ragflow-cpu:",
            "    environment:",
            *env_lines(ragflow_runtime_env),
            *tei_base_url_lines,
            *ragflow_extra_network_lines,
            "    volumes:",
            f"      - {json.dumps(volume)}",
            "  ragflow-gpu:",
            "    environment:",
            *env_lines(ragflow_runtime_env),
            *tei_base_url_lines,
            *ragflow_extra_network_lines,
            "    volumes:",
            f"      - {json.dumps(volume)}",
            *external_network_lines,
            "",
        ]
    ),
    encoding="utf-8",
)
PY
}

validate_for_up() {
  if [[ "${HERMES_WEBUI_BIND:-0.0.0.0}" != "127.0.0.1" && "${HERMES_WEBUI_PASSWORD:-}" =~ ^(|change-me)$ ]]; then
    die "HERMES_WEBUI_BIND is not loopback, but HERMES_WEBUI_PASSWORD is empty/change-me."
  fi
  case "${HERMES_WEBUI_CHAT_BACKEND:-gateway}" in
    gateway|api_server|api-server)
      if [[ -z "${HERMES_GATEWAY_API_KEY:-}" || "${HERMES_GATEWAY_API_KEY:-}" == "change-me" || "${HERMES_GATEWAY_API_KEY:-}" == "change-me-gateway-key" ]]; then
        die "HERMES_WEBUI_CHAT_BACKEND uses gateway, but HERMES_GATEWAY_API_KEY is empty/change-me."
      fi
      ;;
  esac
}

suite_compose() {
  local args=("--project-name" "${PSKA_FULL_PROJECT:-pska-full}" "--env-file" "${ENV_FILE}" "-f" "${SCRIPT_DIR}/docker-compose.yml")
  if [[ "${EMBEDDING_ENABLED:-1}" != "0" ]]; then
    args+=("--profile" "embedding")
  fi
  docker_compose "${args[@]}" "$@"
}

ragflow_compose() {
  local profiles=("${DOC_ENGINE:-elasticsearch}" "${DEVICE:-cpu}")
  local item
  local _extra_profiles=()
  IFS=',' read -ra _extra_profiles <<< "${RAGFLOW_EXTRA_PROFILES:-}"
  for item in "${_extra_profiles[@]}"; do
    item="${item// }"
    [[ -z "${item}" ]] && continue
    if [[ "${EMBEDDING_ENABLED:-1}" != "0" && "${item}" == tei-* ]]; then
      continue
    fi
    profiles+=("${item}")
  done
  local args=("--env-file" "${PSKA_RAGFLOW_ENV}" "-f" "docker-compose.yml")
  if [[ -n "${PSKA_RAGFLOW_OVERRIDE:-}" && -f "${PSKA_RAGFLOW_OVERRIDE}" ]]; then
    args+=("-f" "${PSKA_RAGFLOW_OVERRIDE}")
  fi
  for item in "${profiles[@]}"; do
    args+=("--profile" "${item}")
  done
  (cd "${RAGFLOW_HOME}/docker" && COMPOSE_PROJECT_NAME="${RAGFLOW_PROJECT:-ragflow}" docker_compose "${args[@]}" "$@")
}

start_embedding_if_enabled() {
  if [[ "${EMBEDDING_ENABLED:-1}" == "0" ]]; then
    warn "EMBEDDING_ENABLED=0; PSKA-managed embedding service will not be started."
    return
  fi
  log "starting local embedding service (${EMBEDDING_MODEL_ID:-BAAI/bge-small-en-v1.5})"
  suite_compose up -d embedding
  log "Embedding API: http://127.0.0.1:${EMBEDDING_HOST_PORT:-6380}"
}

cmd_init() {
  load_env
  resolve_paths
  ensure_repos
  write_pska_env
  write_hermes_config
  write_extension_state
  write_ragflow_env
  write_ragflow_service_conf
  write_ragflow_override
  log "initialized runtime under ${PSKA_SUITE_HOME}"
}

cmd_ragflow_up() {
  cmd_init
  start_embedding_if_enabled
  log "starting RAGFlow upstream compose"
  ragflow_compose up -d
  log "RAGFlow UI: http://127.0.0.1:${RAGFLOW_WEB_HTTP_PORT:-8080}"
  log "RAGFlow API: http://127.0.0.1:${RAGFLOW_HOST_PORT:-9380}"
}

cmd_up() {
  cmd_init
  validate_for_up
  start_embedding_if_enabled
  log "starting RAGFlow upstream compose"
  ragflow_compose up -d
  if [[ "${PSKA_RETRIEVAL_PROVIDER:-ragflow}" == "ragflow" && -z "${RAGFLOW_API_KEY:-}" ]]; then
    warn "RAGFLOW_API_KEY is empty. RAGFlow is started so you can create/configure the key."
    warn "Open http://127.0.0.1:${RAGFLOW_WEB_HTTP_PORT:-8080}, create an API key/model provider, put it in ${ENV_FILE}, then rerun ./bootstrap.sh up."
    exit 2
  fi
  log "starting PSKA suite compose"
  suite_compose up -d --build
}

cmd_embedding_up() {
  cmd_init
  start_embedding_if_enabled
}

cmd_down() {
  load_env
  resolve_paths
  suite_compose down
  if [[ -d "${RAGFLOW_HOME}/docker" ]]; then
    ragflow_compose down
  fi
}

cmd_status() {
  load_env
  resolve_paths
  printf '\n# PSKA suite\n'
  suite_compose ps || true
  if [[ -d "${RAGFLOW_HOME}/docker" ]]; then
    printf '\n# RAGFlow\n'
    ragflow_compose ps || true
  fi
}

cmd_logs() {
  load_env
  resolve_paths
  suite_compose logs -f "${@:2}"
}

cmd="${1:-up}"
case "${cmd:-up}" in
  init) cmd_init ;;
  embedding-up) cmd_embedding_up ;;
  up) cmd_up ;;
  ragflow-up) cmd_ragflow_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  logs) cmd_logs "$@" ;;
  *)
    cat <<'USAGE'
Usage: ./bootstrap.sh [init|embedding-up|ragflow-up|up|status|logs|down]

  init        Clone/check repos and generate Hermes/PSKA config.
  embedding-up  Start the local embedding service only.
  ragflow-up  Start only RAGFlow so you can create the first API key.
  up          Start RAGFlow, then PSKA suite when RAGFLOW_API_KEY is set.
  status      Show both compose projects.
  logs        Follow PSKA suite logs; pass service names after logs.
  down        Stop PSKA suite and RAGFlow, preserving volumes.
USAGE
    exit 2
    ;;
esac
