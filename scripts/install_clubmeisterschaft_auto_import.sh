#!/usr/bin/env bash
# Install Clubmeisterschaft auto-import on the VPS (run as root via ssh).
# Usage (from repo root on VPS, or pipe over ssh):
#   sudo ./scripts/install_clubmeisterschaft_auto_import.sh
#   sudo ./scripts/install_clubmeisterschaft_auto_import.sh --enable-timer   # after dry-run week

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENABLE_TIMER=0
for arg in "$@"; do
  case "$arg" in
    --enable-timer) ENABLE_TIMER=1 ;;
    -h|--help)
      echo "Usage: install_clubmeisterschaft_auto_import.sh [--enable-timer]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

install -m 755 "${REPO_ROOT}/scripts/clubmeisterschaft_auto_import.sh" /usr/local/bin/clubmeisterschaft_auto_import.sh

mkdir -p /var/lib/bowlyzer/clubmeisterschaft/{inbox,work}
mkdir -p /etc/bowlyzer

if [[ ! -f /etc/bowlyzer/clubmeisterschaft-import.env ]]; then
  install -m 600 "${REPO_ROOT}/deploy/vps/clubmeisterschaft-import.env.example" \
    /etc/bowlyzer/clubmeisterschaft-import.env
  echo "Created /etc/bowlyzer/clubmeisterschaft-import.env — edit CLUBMEISTERSCHAFT_RCLONE_SRC before use."
else
  echo "Keeping existing /etc/bowlyzer/clubmeisterschaft-import.env"
fi

install -m 644 "${REPO_ROOT}/deploy/vps/clubmeisterschaft-import.service" \
  /etc/systemd/system/clubmeisterschaft-import.service
install -m 644 "${REPO_ROOT}/deploy/vps/clubmeisterschaft-import.timer" \
  /etc/systemd/system/clubmeisterschaft-import.timer

systemctl daemon-reload

echo "Installed:"
echo "  /usr/local/bin/clubmeisterschaft_auto_import.sh"
echo "  /etc/bowlyzer/clubmeisterschaft-import.env"
echo "  systemd units clubmeisterschaft-import.{service,timer}"

if [[ "${ENABLE_TIMER}" -eq 1 ]]; then
  systemctl enable --now clubmeisterschaft-import.timer
  systemctl list-timers clubmeisterschaft-import.timer --no-pager
  echo "Timer enabled."
else
  echo ""
  echo "Dry-run week: edit env, configure rclone, then run manually:"
  echo "  set -a && source /etc/bowlyzer/clubmeisterschaft-import.env && set +a"
  echo "  clubmeisterschaft_auto_import.sh --sync-only"
  echo "  clubmeisterschaft_auto_import.sh --dry-run"
  echo "  clubmeisterschaft_auto_import.sh"
  echo ""
  echo "After dry-run: sudo $0 --enable-timer"
fi
