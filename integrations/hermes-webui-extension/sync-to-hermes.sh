#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/pska-mini"
HERMES_HOME_EFFECTIVE="${HERMES_HOME:-${HOME}/.hermes}"
DEST_ROOT="${HERMES_WEBUI_EXTENSION_DIR:-${HERMES_HOME_EFFECTIVE}/webui-local-extensions}"
DEST_DIR="${DEST_ROOT}/pska-mini"

mkdir -p "${DEST_DIR}"

cp "${SRC_DIR}/manifest.json" "${DEST_DIR}/manifest.json"
cp "${SRC_DIR}/pska-mini.js" "${DEST_DIR}/pska-mini.js"
cp "${SRC_DIR}/pska-mini.css" "${DEST_DIR}/pska-mini.css"

printf 'Synced PSKA-mini extension into %s\n' "${DEST_DIR}"
printf 'Ensure %s references pska-mini when adding a fresh Hermes profile.\n' "${DEST_ROOT}/extensions.json"
