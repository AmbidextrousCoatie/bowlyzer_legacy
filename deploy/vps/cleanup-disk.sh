#!/usr/bin/env bash
# Disk recovery on a small VPS (run as root).
#
# Usage:
#   sudo bash cleanup-disk.sh           # safe prune (recommended first)
#   sudo bash cleanup-disk.sh --aggressive   # also remove ALL unused images (not just dangling)

set -euo pipefail

AGGRESSIVE=0
for arg in "$@"; do
  case "$arg" in
    --aggressive) AGGRESSIVE=1 ;;
    -h|--help)
      echo "Usage: cleanup-disk.sh [--aggressive]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

log() { printf '[cleanup] %s\n' "$*"; }

log "disk before:"
df -h / | tail -1

# --- deploy tarballs (~80MB each; duplicate of loaded image) ---
for f in \
  /root/bowlyzer-image.tar \
  /root/bowlyzer-image.tar.gz \
  /root/bowlyzer/bowlyzer-image.tar \
  /root/bowlyzer/bowlyzer-image.tar.gz \
  /home/bowlyzer/bowlyzer/bowlyzer-image.tar \
  /home/bowlyzer/bowlyzer/bowlyzer-image.tar.gz; do
  if [[ -f "$f" ]]; then
    log "removing deploy tarball: $f ($(du -h "$f" | cut -f1))"
    rm -f "$f"
  fi
done

if command -v docker >/dev/null 2>&1; then
  log "docker system df (before)"
  docker system df || true

  # Truncate huge container logs (common on long-running VPS).
  if [[ -d /var/lib/docker/containers ]]; then
    while IFS= read -r -d '' logfile; do
      sz=$(stat -c '%s' "$logfile" 2>/dev/null || echo 0)
      if [[ "$sz" -gt 10485760 ]]; then
        log "truncating log $(du -h "$logfile" | cut -f1): $logfile"
        truncate -s 0 "$logfile"
      fi
    done < <(find /var/lib/docker/containers -name '*-json.log' -print0 2>/dev/null)
  fi

  log "prune stopped containers, unused networks, dangling images"
  docker system prune -f

  if [[ "${AGGRESSIVE}" -eq 1 ]]; then
    log "aggressive: remove every image not used by a running container"
    docker image prune -a -f
    docker builder prune -a -f 2>/dev/null || true
    docker volume prune -f 2>/dev/null || true
  else
    log "prune unused images older than 24h (use --aggressive for all unused)"
    docker image prune -a -f --filter "until=24h" 2>/dev/null || docker image prune -f
  fi

  # Drop duplicate bowlyzer tags if multiple IDs exist (keep image used by running app).
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q bowlyzer; then
    running_img="$(docker ps --filter 'name=bowlyzer' --format '{{.Image}}' | head -1)"
    log "running bowlyzer container image: ${running_img}"
  fi

  log "docker system df (after)"
  docker system df || true
fi

# apt cache
if command -v apt-get >/dev/null 2>&1; then
  log "apt clean"
  apt-get clean -y 2>/dev/null || apt-get clean
fi

# systemd journals on small disks
if command -v journalctl >/dev/null 2>&1; then
  log "vacuum journal to 80M"
  journalctl --vacuum-size=80M 2>/dev/null || true
fi

log "disk after:"
df -h / | tail -1
log "done (re-run with --aggressive if still tight)"
