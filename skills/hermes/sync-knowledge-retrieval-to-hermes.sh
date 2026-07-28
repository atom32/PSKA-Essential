#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/knowledge-retrieval"
HERMES_HOME_EFFECTIVE="${HERMES_HOME:-${HOME}/.hermes}"
DEST_DIR="${HERMES_SKILLS_DIR:-${HERMES_HOME_EFFECTIVE}/skills/research}/knowledge-retrieval"

mkdir -p "${DEST_DIR}/references"

cp "${SRC_DIR}/SKILL.md" "${DEST_DIR}/SKILL.md"
cp "${SRC_DIR}/references/pska-graphiti-failure.md" "${DEST_DIR}/references/pska-graphiti-failure.md"

printf 'Synced knowledge-retrieval skill into %s\n' "${DEST_DIR}"
