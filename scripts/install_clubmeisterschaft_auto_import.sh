#!/usr/bin/env bash
# Install Clubmeisterschaft auto-import for user bowlyzer (no root).
#
#   ./scripts/install_clubmeisterschaft_auto_import.sh
#   ./scripts/install_clubmeisterschaft_auto_import.sh --enable-timer
#
# Root is only needed once for timer without login:
#   sudo ./scripts/install_clubmeisterschaft_linger.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

strip_crlf() {
  local path
  for path in "${REPO_ROOT}"/scripts/*.sh; do
    [[ -f "${path}" ]] || continue
    sed -i 's/\r$//' "${path}"
  done
}

realpath_safe() {
  readlink -f "$1" 2>/dev/null || realpath "$1" 2>/dev/null || echo "$1"
}

# ``install`` fails when src and dest resolve to the same path (e.g. RemoteDir == ~/bowlyzer).
install_if_different() {
  local src="$1" dest="$2" mode="${3:-644}"
  local src_real dest_real
  src_real="$(realpath_safe "${src}")"
  mkdir -p "$(dirname "${dest}")"
  if [[ -f "${dest}" ]]; then
    dest_real="$(realpath_safe "${dest}")"
    if [[ "${src_real}" == "${dest_real}" ]]; then
      return 0
    fi
  fi
  install -m "${mode}" "${src}" "${dest}"
}

ENABLE_TIMER=0
for arg in "$@"; do
  case "$arg" in
    --enable-timer) ENABLE_TIMER=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: install_clubmeisterschaft_auto_import.sh [--enable-timer]

Run as user bowlyzer (not root). Installs:
  ~/bin/clubmeisterschaft_auto_import.sh
  ~/.config/bowlyzer/clubmeisterschaft-import.env
  ~/.config/systemd/user/clubmeisterschaft-import.{service,timer}

Timer without login requires once (root):
  sudo ./scripts/install_clubmeisterschaft_linger.sh
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run as bowlyzer, not root." >&2
  echo "  sudo -u bowlyzer $0 $*" >&2
  echo "Root is only for: sudo ./scripts/install_clubmeisterschaft_linger.sh" >&2
  exit 1
fi

strip_crlf

BOWLYZER_HOME="${HOME}"
BOWLYZER_DIR="${BOWLYZER_DIR:-${BOWLYZER_HOME}/bowlyzer}"
CONFIG_DIR="${BOWLYZER_HOME}/.config/bowlyzer"
BIN_DIR="${BOWLYZER_HOME}/bin"
WORK_ROOT="${BOWLYZER_DIR}/work"
SYSTEMD_USER_DIR="${BOWLYZER_HOME}/.config/systemd/user"

mkdir -p \
  "${CONFIG_DIR}" \
  "${BIN_DIR}" \
  "${WORK_ROOT}/clubmeisterschaft/inbox" \
  "${WORK_ROOT}/clubmeisterschaft/work" \
  "${WORK_ROOT}/clubmeisterschaft/archive" \
  "${WORK_ROOT}/tournament_inputs" \
  "${SYSTEMD_USER_DIR}"

ln -sf "${REPO_ROOT}/scripts/clubmeisterschaft_auto_import.sh" \
  "${BIN_DIR}/clubmeisterschaft_auto_import.sh"

mkdir -p "${BOWLYZER_DIR}/scripts/data" "${BOWLYZER_DIR}/database/work/tournaments"
install_if_different "${REPO_ROOT}/scripts/publish_tournament_parquet.py" \
  "${BOWLYZER_DIR}/scripts/publish_tournament_parquet.py"
install_if_different "${REPO_ROOT}/scripts/send_notify_email.py" \
  "${BOWLYZER_DIR}/scripts/send_notify_email.py"
if [[ -f "${REPO_ROOT}/scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py" ]]; then
  install_if_different "${REPO_ROOT}/scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py" \
    "${BOWLYZER_DIR}/scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py"
fi

ENV_FILE="${CONFIG_DIR}/clubmeisterschaft-import.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 "${REPO_ROOT}/deploy/vps/clubmeisterschaft-import.env.example" "${ENV_FILE}"
  echo "Created ${ENV_FILE} — edit CLUBMEISTERSCHAFT_RCLONE_SRC before use."
else
  echo "Keeping existing ${ENV_FILE}"
fi

install -m 644 "${REPO_ROOT}/deploy/vps/user/clubmeisterschaft-import.service" \
  "${SYSTEMD_USER_DIR}/clubmeisterschaft-import.service"
install -m 644 "${REPO_ROOT}/deploy/vps/user/clubmeisterschaft-import.timer" \
  "${SYSTEMD_USER_DIR}/clubmeisterschaft-import.timer"

systemctl --user daemon-reload

echo "Installed (user $(id -un)):"
echo "  ${BIN_DIR}/clubmeisterschaft_auto_import.sh"
echo "  ${ENV_FILE}"
echo "  user systemd: clubmeisterschaft-import.{service,timer}"

if [[ "${ENABLE_TIMER}" -eq 1 ]]; then
  systemctl --user enable --now clubmeisterschaft-import.timer
  systemctl --user list-timers clubmeisterschaft-import.timer --no-pager
  echo ""
  echo "Timer enabled for user session."
  if ! loginctl show-user "$(id -un)" -p Linger 2>/dev/null | grep -q 'yes'; then
    echo "For timer after reboot without login, run once as root:"
    echo "  sudo ${REPO_ROOT}/scripts/install_clubmeisterschaft_linger.sh"
  fi
else
  echo ""
  echo "Dry-run:"
  echo "  rclone config   # as $(id -un)"
  echo "  nano ${ENV_FILE}"
  echo "  set -a && source ${ENV_FILE} && set +a"
  echo "  clubmeisterschaft_auto_import.sh --sync-only"
  echo "  clubmeisterschaft_auto_import.sh --dry-run"
  echo "  clubmeisterschaft_auto_import.sh"
  echo ""
  echo "Then: $0 --enable-timer"
fi
