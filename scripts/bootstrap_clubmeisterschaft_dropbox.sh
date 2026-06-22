#!/usr/bin/env bash
# One-time VPS bootstrap: rclone Dropbox (dedicated account) + verify club import paths.
# Run on the VPS as user bowlyzer after deploy.ps1 -SyncDatabase.
#
#   ./scripts/bootstrap_clubmeisterschaft_dropbox.sh

set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

if [[ "$(id -u)" -eq 0 ]]; then
  die "Run as bowlyzer, not root: sudo -u bowlyzer $0"
fi

if ! command -v rclone >/dev/null 2>&1; then
  die "Install rclone first: sudo apt install -y rclone"
fi

ENV_FILE="${HOME}/.config/bowlyzer/clubmeisterschaft-import.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  die "Missing ${ENV_FILE}. Run: ./scripts/install_clubmeisterschaft_auto_import.sh"
fi

IMPORT_BIN="${HOME}/bin/clubmeisterschaft_auto_import.sh"
if [[ ! -x "${IMPORT_BIN}" && ! -L "${IMPORT_BIN}" ]]; then
  die "Missing ${IMPORT_BIN}. Run: ./scripts/install_clubmeisterschaft_auto_import.sh"
fi

echo "==> rclone remotes"
rclone listremotes || true

if ! rclone listremotes | grep -q '^dropbox:$'; then
  echo ""
  echo "Configure a dedicated Dropbox account (not your personal one):"
  echo "  rclone config"
  echo "    n) New remote"
  echo "    name: dropbox"
  echo "    type: dropbox"
  echo "    follow OAuth in browser (use the service Dropbox user)"
  echo ""
  read -r -p "Press Enter when rclone remote 'dropbox:' exists, or Ctrl-C to abort..."
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

echo ""
echo "==> env"
echo "  CLUBMEISTERSCHAFT_RCLONE_SRC=${CLUBMEISTERSCHAFT_RCLONE_SRC:-<unset>}"
echo "  GF_TOURNAMENT_CSV=${GF_TOURNAMENT_CSV:-<unset>}"
echo "  BOWLYZER_DIR=${BOWLYZER_DIR:-<unset>}"

[[ -n "${CLUBMEISTERSCHAFT_RCLONE_SRC:-}" ]] || die "Set CLUBMEISTERSCHAFT_RCLONE_SRC in ${ENV_FILE}"
[[ -f "${GF_TOURNAMENT_CSV:-}" ]] || die "Missing GF snapshot at ${GF_TOURNAMENT_CSV}. Run deploy.ps1 -SyncDatabase from PC."

echo ""
echo "==> list Dropbox (your files)"
rclone ls "${CLUBMEISTERSCHAFT_RCLONE_SRC%%:*}:" | head -20 || true

echo ""
echo "==> list directly shared files (--dropbox-shared-files)"
rclone ls "${CLUBMEISTERSCHAFT_RCLONE_SRC%%:*}:" --dropbox-shared-files | head -20 || true

echo ""
echo "==> list shared folders (--dropbox-shared-folders)"
rclone lsd "${CLUBMEISTERSCHAFT_RCLONE_SRC%%:*}:" --dropbox-shared-folders || true

echo ""
echo "==> list configured source"
rclone lsd "${CLUBMEISTERSCHAFT_RCLONE_SRC}" 2>/dev/null || rclone ls "${CLUBMEISTERSCHAFT_RCLONE_SRC}" | head -20 || true

echo ""
echo "==> sync test (inbox only)"
"${IMPORT_BIN}" --sync-only

echo ""
echo "Inbox:"
ls -la "${CLUBMEISTERSCHAFT_INBOX:-${BOWLYZER_DIR}/work/clubmeisterschaft/inbox}" || true

echo ""
echo "Next:"
echo "  clubmeisterschaft_auto_import.sh --dry-run"
echo "  clubmeisterschaft_auto_import.sh"
echo "  ./scripts/install_clubmeisterschaft_auto_import.sh --enable-timer"
echo "  sudo ./scripts/install_clubmeisterschaft_linger.sh   # once, for timer after reboot"
