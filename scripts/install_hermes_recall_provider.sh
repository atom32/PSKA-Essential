#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PSKA_HOME="${PSKA_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
HERMES_WEBUI_HOME="${HERMES_WEBUI_HOME:-${HOME}/hermes-webui}"
PATCH_FILE="${HERMES_RECALL_PROVIDER_PATCH:-${PSKA_HOME}/integrations/hermes-webui-recall-provider/pska-conversation-recall-provider.patch}"
MODE="apply"
RUN_TESTS=1

usage() {
  cat <<'EOF'
Usage: scripts/install_hermes_recall_provider.sh [options] [HERMES_WEBUI_HOME]

Installs or verifies the PSKA conversation recall provider in a Hermes WebUI
checkout. The provider exposes POST /api/pska/conversations/search for PSKA
context-pack history recall and POST /api/pska/conversations/import for bounded
history imports.

Options:
  --check       Only verify whether the provider is installed.
  --apply       Apply the provider patch when missing. This is the default.
  --test        Run Hermes py_compile and focused pytest checks. Default.
  --no-test     Do not run checks after applying or finding the provider.
  -h, --help    Show this help.

Environment:
  HERMES_WEBUI_HOME=/path/to/hermes-webui
  HERMES_RECALL_PROVIDER_PATCH=/path/to/pska-conversation-recall-provider.patch
EOF
}

log() {
  printf '[pska-hermes-recall] %s\n' "$*"
}

warn() {
  printf '[pska-hermes-recall][warn] %s\n' "$*" >&2
}

die() {
  printf '[pska-hermes-recall][error] %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check" ;;
    --apply) MODE="apply" ;;
    --test) RUN_TESTS=1 ;;
    --no-test) RUN_TESTS=0 ;;
    -h|--help) usage; exit 0 ;;
    -*)
      usage >&2
      die "unknown option: $1"
      ;;
    *)
      HERMES_WEBUI_HOME="$1"
      ;;
  esac
  shift
done

provider_source_ok() {
  local root="$1"
  [[ -f "${root}/api/auth.py" && -f "${root}/api/routes.py" ]] || return 1
  grep -q "def pska_recall_token_auth_ok" "${root}/api/auth.py" || return 1
  grep -q "HERMES_WEBUI_PSKA_RECALL_TOKEN" "${root}/api/auth.py" || return 1
  grep -q '"/api/pska/conversations/search"' "${root}/api/routes.py" || return 1
  grep -q '"/api/pska/conversations/import"' "${root}/api/routes.py" || return 1
  grep -q "def _handle_pska_conversations_search" "${root}/api/routes.py" || return 1
  grep -q "def _handle_pska_conversations_import" "${root}/api/routes.py" || return 1
  if [[ -f "${root}/tests/test_pska_conversation_recall_provider.py" ]]; then
    grep -q '"messages" not in item' "${root}/tests/test_pska_conversation_recall_provider.py" || return 1
    grep -q "hermes.pska_conversation_history_import.v1" "${root}/tests/test_pska_conversation_recall_provider.py" || return 1
  fi
}

run_provider_checks() {
  local root="$1"
  (( RUN_TESTS )) || return 0
  log "Running Hermes provider checks"
  (
    cd "${root}"
    python3 -m py_compile api/auth.py api/routes.py
    python3 -m pytest tests/test_pska_conversation_recall_provider.py tests/test_sessions_search_profile_scope.py
  )
}

[[ -d "${HERMES_WEBUI_HOME}" ]] || die "Hermes WebUI home not found: ${HERMES_WEBUI_HOME}"
[[ -f "${PATCH_FILE}" ]] || die "provider patch not found: ${PATCH_FILE}"
git -C "${HERMES_WEBUI_HOME}" rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git checkout: ${HERMES_WEBUI_HOME}"

if provider_source_ok "${HERMES_WEBUI_HOME}"; then
  log "Provider already installed in ${HERMES_WEBUI_HOME}"
  run_provider_checks "${HERMES_WEBUI_HOME}"
  exit 0
fi

if [[ "${MODE}" == "check" ]]; then
  warn "Provider is not installed in ${HERMES_WEBUI_HOME}"
  exit 1
fi

if git -C "${HERMES_WEBUI_HOME}" apply --reverse --check "${PATCH_FILE}" >/dev/null 2>&1; then
  warn "Patch appears to be applied, but required contract markers are missing."
  die "inspect ${HERMES_WEBUI_HOME}/api/auth.py and api/routes.py before continuing"
fi

log "Checking provider patch against ${HERMES_WEBUI_HOME}"
git -C "${HERMES_WEBUI_HOME}" apply --check "${PATCH_FILE}" \
  || die "provider patch does not apply cleanly; update the patch for this Hermes checkout"

log "Applying provider patch"
git -C "${HERMES_WEBUI_HOME}" apply "${PATCH_FILE}"

provider_source_ok "${HERMES_WEBUI_HOME}" \
  || die "provider patch applied, but required contract markers are still missing"

run_provider_checks "${HERMES_WEBUI_HOME}"
log "Provider installed in ${HERMES_WEBUI_HOME}"
