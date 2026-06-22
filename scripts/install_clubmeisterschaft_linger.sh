#!/usr/bin/env bash
# One-time root hook: allow bowlyzer user timers to run without an active login session.
# Required for clubmeisterschaft-import.timer after reboot.
#
#   sudo ./scripts/install_clubmeisterschaft_linger.sh

set -euo pipefail

BOWLYZER_USER="${BOWLYZER_USER:-bowlyzer}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! id "${BOWLYZER_USER}" >/dev/null 2>&1; then
  echo "User ${BOWLYZER_USER} does not exist." >&2
  exit 1
fi

loginctl enable-linger "${BOWLYZER_USER}"
echo "Linger enabled for ${BOWLYZER_USER} (user systemd runs at boot)."
