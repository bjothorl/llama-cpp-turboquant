#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="llama-agent-router.service"
SRC="${SCRIPT_DIR}/${UNIT_NAME}"
DEST="${HOME}/.config/systemd/user/${UNIT_NAME}"

if [[ ! -f "${SRC}" ]]; then
    echo "error: ${SRC} not found" >&2
    exit 1
fi

mkdir -p "${HOME}/.config/systemd/user"
cp "${SRC}" "${DEST}"
echo "installed ${DEST}"

systemctl --user daemon-reload
echo "reloaded user systemd"

if systemctl --user is-active --quiet "${UNIT_NAME}" 2>/dev/null; then
    systemctl --user restart "${UNIT_NAME}"
    echo "restarted ${UNIT_NAME}"
else
    echo "service not running; start with: systemctl --user enable --now ${UNIT_NAME}"
fi
