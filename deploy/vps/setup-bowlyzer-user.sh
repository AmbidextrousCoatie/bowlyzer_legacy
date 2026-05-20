#!/usr/bin/env bash
# One-time VPS setup: dedicated bowlyzer user for deploy + Docker (run as root).
#
# Does NOT remove flaskuser / legacy flaskapp — only prepares Docker-based deploy.
#
# Usage:
#   sudo bash deploy/vps/setup-bowlyzer-user.sh
#   sudo bash deploy/vps/setup-bowlyzer-user.sh --migrate-from-root

set -euo pipefail

BOWLYZER_USER="${BOWLYZER_USER:-bowlyzer}"
BOWLYZER_HOME="/home/${BOWLYZER_USER}"
DEPLOY_DIR="${BOWLYZER_HOME}/bowlyzer"
MIGRATE=0

for arg in "$@"; do
  case "$arg" in
    --migrate-from-root) MIGRATE=1 ;;
    -h|--help)
      echo "Usage: setup-bowlyzer-user.sh [--migrate-from-root]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

if ! id "${BOWLYZER_USER}" &>/dev/null; then
  echo "Creating user ${BOWLYZER_USER} (UID 1000 to match container user)"
  if ! getent passwd 1000 >/dev/null; then
    useradd -m -u 1000 -s /bin/bash "${BOWLYZER_USER}"
  else
    existing="$(getent passwd 1000 | cut -d: -f1)"
    if [[ "${existing}" != "${BOWLYZER_USER}" ]]; then
      echo "WARNING: UID 1000 is already used by '${existing}'."
      echo "         Container runs as UID 1000 — fix ownership or adjust compose user: directive."
    fi
    useradd -m -s /bin/bash "${BOWLYZER_USER}"
  fi
else
  echo "User ${BOWLYZER_USER} already exists (uid $(id -u "${BOWLYZER_USER}"))"
fi

if ! getent group docker >/dev/null; then
  echo "ERROR: docker group missing — install Docker first." >&2
  exit 1
fi
usermod -aG docker "${BOWLYZER_USER}"

mkdir -p "${DEPLOY_DIR}"
mkdir -p /var/lib/bowlyzer/clubmeisterschaft/{inbox,work}
chown -R "${BOWLYZER_USER}:${BOWLYZER_USER}" "${BOWLYZER_HOME}" /var/lib/bowlyzer

if [[ "${MIGRATE}" -eq 1 && -d /root/bowlyzer ]]; then
  echo "Migrating /root/bowlyzer -> ${DEPLOY_DIR}"
  if [[ -f /root/bowlyzer/.env ]]; then
    install -o "${BOWLYZER_USER}" -g "${BOWLYZER_USER}" -m 600 /root/bowlyzer/.env "${DEPLOY_DIR}/.env"
  fi
  if [[ -d /root/bowlyzer/database ]]; then
    rsync -a /root/bowlyzer/database/ "${DEPLOY_DIR}/database/"
  fi
  if [[ -f /root/bowlyzer/docker-compose.prod.yml ]]; then
    install -o "${BOWLYZER_USER}" -g "${BOWLYZER_USER}" -m 644 /root/bowlyzer/docker-compose.prod.yml "${DEPLOY_DIR}/"
  fi
  chown -R "${BOWLYZER_USER}:${BOWLYZER_USER}" "${DEPLOY_DIR}"
fi

# Stale deploy artifacts
rm -f /root/bowlyzer-image.tar /root/bowlyzer-image.tar.gz "${DEPLOY_DIR}/bowlyzer-image.tar" "${DEPLOY_DIR}/bowlyzer-image.tar.gz" 2>/dev/null || true

echo ""
echo "Setup complete."
echo "  Deploy dir: ${DEPLOY_DIR}"
echo "  Deploy as:  ${BOWLYZER_USER}@$(hostname -f)"
echo ""
echo "Next:"
echo "  1. Copy your SSH public key to ${BOWLYZER_HOME}/.ssh/authorized_keys"
echo "  2. In deploy/deploy.config.ps1 set RemoteUser=${BOWLYZER_USER} RemoteDir=${DEPLOY_DIR}"
echo "  3. Run deploy/vps/cleanup-disk.sh if disk is still tight"
echo "  4. Disable legacy flaskapp if still enabled: systemctl disable --now flaskapp"
