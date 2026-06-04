#!/usr/bin/env bash
# Sync Clubmeisterschaft Donaubowler XLSX from Dropbox (rclone) and import into production database/.
# Intended for VPS cron during an ongoing tournament (Clubmeisterschaft Donaubowler 2026).
# (Clubpokal is a separate multi-month KO competition — not this pipeline.)
#
# See docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md for one-time setup and dry-run week.
#
# Examples:
#   ./scripts/clubmeisterschaft_auto_import.sh --dry-run
#   ./scripts/clubmeisterschaft_auto_import.sh
#   CLUBMEISTERSCHAFT_RCLONE_SRC="dropbox:Clubmeisterschaft 2026" ./scripts/clubmeisterschaft_auto_import.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BOWLYZER_DIR="${BOWLYZER_DIR:-/home/bowlyzer/bowlyzer}"
COMPOSE_FILE="${COMPOSE_FILE:-${BOWLYZER_DIR}/docker-compose.prod.yml}"
DOCKER_IMAGE="${DOCKER_IMAGE:-bowlyzer:release}"

CLUBMEISTERSCHAFT_INBOX="${CLUBMEISTERSCHAFT_INBOX:-/var/lib/bowlyzer/clubmeisterschaft/inbox}"
CLUBMEISTERSCHAFT_WORK="${CLUBMEISTERSCHAFT_WORK:-/var/lib/bowlyzer/clubmeisterschaft/work}"
STATE_DIR="${STATE_DIR:-/var/lib/bowlyzer/clubmeisterschaft}"
LAST_HASH_FILE="${LAST_HASH_FILE:-${STATE_DIR}/.last_import_sha256}"
LOCK_FILE="${LOCK_FILE:-/var/run/clubmeisterschaft_import.lock}"

# Dropbox path via rclone remote (e.g. dropbox:Folder/Clubmeisterschaft.xlsx or dropbox:Folder/)
CLUBMEISTERSCHAFT_RCLONE_SRC="${CLUBMEISTERSCHAFT_RCLONE_SRC:-}"

STABLE_WAIT_SEC="${STABLE_WAIT_SEC:-30}"
IMPORT_DATE="${IMPORT_DATE:-2026-05-15}"
IMPORT_SEASON="${IMPORT_SEASON:-}"
IMPORT_YEAR="${IMPORT_YEAR:-2026}"

DRY_RUN=0
SYNC_ONLY=0
SKIP_RESTART=0
FORCE=0

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

usage() {
  cat <<'EOF'
Usage: clubmeisterschaft_auto_import.sh [options]

  --dry-run       Sync (if configured) and report; do not import or restart app
  --sync-only     Only rclone sync; no import/restart
  --skip-restart  Import but do not restart bowlyzer container
  --force         Import even if file hash unchanged
  -h, --help      This help

Environment (override defaults):
  BOWLYZER_DIR                    Deploy dir with database/ and docker-compose.prod.yml
  CLUBMEISTERSCHAFT_RCLONE_SRC    rclone source (required for remote sync)
  CLUBMEISTERSCHAFT_INBOX         Local directory for synced .xlsx
  DOCKER_IMAGE                    Image tag (default bowlyzer:release)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --sync-only) SYNC_ONLY=1 ;;
    --skip-restart) SKIP_RESTART=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

mkdir -p "${CLUBMEISTERSCHAFT_INBOX}" "${CLUBMEISTERSCHAFT_WORK}" "${STATE_DIR}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  die "Another import is running (lock ${LOCK_FILE})"
fi

if [[ -n "${CLUBMEISTERSCHAFT_RCLONE_SRC}" ]]; then
  if ! command -v rclone >/dev/null 2>&1; then
    die "rclone not installed but CLUBMEISTERSCHAFT_RCLONE_SRC is set"
  fi
  log "rclone sync ${CLUBMEISTERSCHAFT_RCLONE_SRC} -> ${CLUBMEISTERSCHAFT_INBOX}"
  # Always sync for real (--dry-run only skips import/restart, not rclone).
  rclone sync "${CLUBMEISTERSCHAFT_RCLONE_SRC}" "${CLUBMEISTERSCHAFT_INBOX}" --exclude '~$*' --exclude '.~*'
else
  log "CLUBMEISTERSCHAFT_RCLONE_SRC unset — using existing file(s) in ${CLUBMEISTERSCHAFT_INBOX}"
fi

if [[ "${SYNC_ONLY}" -eq 1 ]]; then
  log "sync-only: done"
  exit 0
fi

XLSX_SRC=""
if compgen -G "${CLUBMEISTERSCHAFT_INBOX}"'/*.xlsx' >/dev/null; then
  # shellcheck disable=SC2012
  XLSX_SRC="$(ls -t "${CLUBMEISTERSCHAFT_INBOX}"/*.xlsx 2>/dev/null | grep -v '/~\$' | grep -v '/\.~' | head -1)"
fi
if [[ -z "${XLSX_SRC}" || ! -f "${XLSX_SRC}" ]]; then
  die "No .xlsx in ${CLUBMEISTERSCHAFT_INBOX}"
fi
log "workbook: ${XLSX_SRC}"

# Wait for stable size/mtime (Excel saves can be multi-step).
size1=$(stat -c '%s' "${XLSX_SRC}")
mtime1=$(stat -c '%Y' "${XLSX_SRC}")
log "waiting ${STABLE_WAIT_SEC}s for stable workbook"
sleep "${STABLE_WAIT_SEC}"
size2=$(stat -c '%s' "${XLSX_SRC}")
mtime2=$(stat -c '%Y' "${XLSX_SRC}")
if [[ "${size1}" != "${size2}" || "${mtime1}" != "${mtime2}" ]]; then
  die "Workbook still changing (size ${size1}->${size2}, mtime ${mtime1}->${mtime2}); retry next cron"
fi

XLSX_WORK="${CLUBMEISTERSCHAFT_WORK}/clubmeisterschaft_import.xlsx"
cp -f "${XLSX_SRC}" "${XLSX_WORK}"

NEW_HASH="$(sha256sum "${XLSX_WORK}" | awk '{print $1}')"
OLD_HASH=""
if [[ -f "${LAST_HASH_FILE}" ]]; then
  OLD_HASH="$(tr -d ' \n\r' < "${LAST_HASH_FILE}")"
fi

if [[ "${FORCE}" -eq 0 && "${NEW_HASH}" == "${OLD_HASH}" ]]; then
  log "unchanged (${NEW_HASH:0:12}…); skip import"
  exit 0
fi

log "workbook changed (${OLD_HASH:-none} -> ${NEW_HASH:0:12}…)"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "dry-run: would import ${XLSX_WORK} into ${BOWLYZER_DIR}/database/ and restart bowlyzer"
  exit 0
fi

[[ -d "${BOWLYZER_DIR}/database" ]] || die "Missing ${BOWLYZER_DIR}/database"
[[ -f "${COMPOSE_FILE}" ]] || die "Missing compose file ${COMPOSE_FILE}"
docker image inspect "${DOCKER_IMAGE}" >/dev/null 2>&1 || die "Docker image not found: ${DOCKER_IMAGE}"

IMPORT_ARGS=(
  database/input/import_clubmeisterschaft_donaubowler_xlsx.py
  --xlsx "/in/clubmeisterschaft_import.xlsx"
  --date "${IMPORT_DATE}"
  --year "${IMPORT_YEAR}"
)
if [[ -n "${IMPORT_SEASON}" ]]; then
  IMPORT_ARGS+=(--season "${IMPORT_SEASON}")
fi

log "import via ${DOCKER_IMAGE}"
docker run --rm \
  -v "${BOWLYZER_DIR}/database/data:/app/database/data" \
  -v "${BOWLYZER_DIR}/database/relational_csv:/app/database/relational_csv:ro" \
  -v "${BOWLYZER_DIR}/database/config:/app/database/config:ro" \
  -v "${XLSX_WORK}:/in/clubmeisterschaft_import.xlsx:ro" \
  --entrypoint python \
  "${DOCKER_IMAGE}" \
  "${IMPORT_ARGS[@]}"

printf '%s\n' "${NEW_HASH}" > "${LAST_HASH_FILE}"

if [[ "${SKIP_RESTART}" -eq 1 ]]; then
  log "skip-restart: import complete"
  exit 0
fi

log "restarting bowlyzer (reload CSV + clear in-process tournament cache)"
docker compose -f "${COMPOSE_FILE}" restart bowlyzer
log "done"
