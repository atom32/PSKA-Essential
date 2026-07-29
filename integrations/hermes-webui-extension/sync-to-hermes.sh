#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/pska-mini"
HERMES_HOME_EFFECTIVE="${HERMES_HOME:-${HOME}/.hermes}"
DEST_ROOT="${HERMES_WEBUI_EXTENSION_DIR:-${HERMES_HOME_EFFECTIVE}/webui-local-extensions}"
DEST_DIR="${DEST_ROOT}/pska-mini"
MANIFEST_NAME="${HERMES_WEBUI_EXTENSION_MANIFEST:-extensions.json}"
PSKA_API_BASE_URL_EFFECTIVE="${PSKA_API_BASE_URL:-http://127.0.0.1:8765}"
HERMES_WEBUI_STATE_DIR_EFFECTIVE="${HERMES_WEBUI_STATE_DIR:-${HERMES_HOME_EFFECTIVE}/webui}"
PSKA_WEBUI_AUTO_APPROVE_SIDECAR="${PSKA_WEBUI_AUTO_APPROVE_SIDECAR:-1}"

mkdir -p "${DEST_DIR}"

cp "${SRC_DIR}/manifest.json" "${DEST_DIR}/manifest.json"
cp "${SRC_DIR}/pska-mini.js" "${DEST_DIR}/pska-mini.js"
cp "${SRC_DIR}/pska-mini.css" "${DEST_DIR}/pska-mini.css"

export DEST_ROOT MANIFEST_NAME PSKA_API_BASE_URL_EFFECTIVE HERMES_WEBUI_STATE_DIR_EFFECTIVE PSKA_WEBUI_AUTO_APPROVE_SIDECAR
python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def normalized_origin(url: str) -> str:
    parsed = urlsplit((url or "http://127.0.0.1:8765").strip())
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc
    if not netloc and parsed.path:
        netloc = parsed.path.split("/", 1)[0]
    if not netloc:
        netloc = "127.0.0.1:8765"
    return urlunsplit((scheme, netloc, "", "", "")).rstrip("/")


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


dest_root = Path(os.environ["DEST_ROOT"]).expanduser()
manifest_name = os.environ["MANIFEST_NAME"]
manifest_path = Path(manifest_name).expanduser()
if not manifest_path.is_absolute():
    manifest_path = dest_root / manifest_path
origin = normalized_origin(os.environ["PSKA_API_BASE_URL_EFFECTIVE"])

entry = {
    "id": "pska-mini",
    "name": "PSKA Mini",
    "description": "Thin Hermes-WebUI controls for PSKA turn context.",
    "scripts": ["pska-mini/pska-mini.js"],
    "stylesheets": ["pska-mini/pska-mini.css"],
    "sidecar": {
        "type": "loopback",
        "origin": origin,
        "health_path": "/api/health",
    },
}

manifest = read_json(manifest_path, {"extensions": []})
if isinstance(manifest, list):
    entries = manifest
    manifest = {"extensions": entries}
elif isinstance(manifest, dict):
    entries = manifest.get("extensions")
    if not isinstance(entries, list):
        entries = []
else:
    manifest = {}
    entries = []

entries = [
    item
    for item in entries
    if not (isinstance(item, dict) and str(item.get("id", "")).strip() == "pska-mini")
]
entries.append(entry)
manifest["extensions"] = entries
write_json(manifest_path, manifest)

if os.environ.get("PSKA_WEBUI_AUTO_APPROVE_SIDECAR", "1").strip().lower() in {"1", "true", "yes", "on"}:
    state_dir = Path(os.environ["HERMES_WEBUI_STATE_DIR_EFFECTIVE"]).expanduser()
    state_path = state_dir / "extension-overrides.json"
    state = read_json(state_path, {"version": 1, "disabled_extensions": [], "sidecar_proxy_consents": {}})
    if not isinstance(state, dict):
        state = {"version": 1, "disabled_extensions": [], "sidecar_proxy_consents": {}}
    disabled = state.get("disabled_extensions")
    if not isinstance(disabled, list):
        disabled = []
    consents = state.get("sidecar_proxy_consents")
    if not isinstance(consents, dict):
        consents = {}
    consents["pska-mini"] = origin
    state["version"] = 1
    state["disabled_extensions"] = disabled
    state["sidecar_proxy_consents"] = consents
    write_json(state_path, state)
PY

printf 'Synced PSKA-mini extension into %s\n' "${DEST_DIR}"
printf 'Updated Hermes WebUI extension manifest at %s/%s\n' "${DEST_ROOT}" "${MANIFEST_NAME}"
if [[ "${PSKA_WEBUI_AUTO_APPROVE_SIDECAR}" == "1" || "${PSKA_WEBUI_AUTO_APPROVE_SIDECAR}" == "true" || "${PSKA_WEBUI_AUTO_APPROVE_SIDECAR}" == "yes" || "${PSKA_WEBUI_AUTO_APPROVE_SIDECAR}" == "on" ]]; then
  printf 'Approved pska-mini sidecar proxy for %s in %s/extension-overrides.json\n' "${PSKA_API_BASE_URL_EFFECTIVE}" "${HERMES_WEBUI_STATE_DIR_EFFECTIVE}"
fi
