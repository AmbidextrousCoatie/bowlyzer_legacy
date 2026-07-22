#!/usr/bin/env bash
# Sync Clubmeisterschaft Donaubowler XLSX from Dropbox (rclone) and import into production database/.
# Intended for VPS during an ongoing tournament (Clubmeisterschaft Donaubowler 2026).
# (Clubpokal is a separate multi-month KO competition — not this pipeline.)
#
# Pipeline:
#   1. rclone sync (dedicated Dropbox folder -> inbox)
#   2. stable-file wait + importer fingerprint (skip if unchanged); archive dated copy on change
#   3. docker: import_clubmeisterschaft_donaubowler_xlsx.py -> tournament_manual_postprocessed.csv
#   4. docker: publish_tournament_parquet.py (host GF snapshot + manual -> parquet)
#
# See docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md for Dropbox + dry-run setup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BOWLYZER_DIR="${BOWLYZER_DIR:-/home/bowlyzer/bowlyzer}"
COMPOSE_FILE="${COMPOSE_FILE:-${BOWLYZER_DIR}/docker-compose.prod.yml}"
DOCKER_IMAGE="${DOCKER_IMAGE:-bowlyzer:release}"

CLUBMEISTERSCHAFT_INBOX="${CLUBMEISTERSCHAFT_INBOX:-${BOWLYZER_DIR}/work/clubmeisterschaft/inbox}"
CLUBMEISTERSCHAFT_WORK="${CLUBMEISTERSCHAFT_WORK:-${BOWLYZER_DIR}/work/clubmeisterschaft/work}"
STATE_DIR="${STATE_DIR:-${BOWLYZER_DIR}/work/clubmeisterschaft}"
CLUBMEISTERSCHAFT_ARCHIVE="${CLUBMEISTERSCHAFT_ARCHIVE:-${STATE_DIR}/archive}"
TOURNAMENT_INPUTS_DIR="${TOURNAMENT_INPUTS_DIR:-${BOWLYZER_DIR}/work/tournament_inputs}"
GF_TOURNAMENT_CSV="${GF_TOURNAMENT_CSV:-${TOURNAMENT_INPUTS_DIR}/gf_tournaments_2026__combined_postprocessed.csv}"
MANUAL_TOURNAMENT_CSV="${MANUAL_TOURNAMENT_CSV:-${BOWLYZER_DIR}/database/work/tournaments/tournament_manual_postprocessed.csv}"
TOURNAMENTS_PUBLISHED_CSV="${TOURNAMENTS_PUBLISHED_CSV:-${BOWLYZER_DIR}/database/data/tournaments_postprocessed.csv}"

LAST_HASH_FILE="${LAST_HASH_FILE:-${STATE_DIR}/.last_import_sha256}"
LOCK_FILE="${LOCK_FILE:-${STATE_DIR}/import.lock}"

# rclone remote path (e.g. dropbox_bowlyzer:Clubmeisterschaft_Donaubowler)
# For a directly shared file: dropbox_bowlyzer:Clubpokal DB 2026.xlsx + SHARED_FILES=1
CLUBMEISTERSCHAFT_RCLONE_SRC="${CLUBMEISTERSCHAFT_RCLONE_SRC:-}"
# 1 = file shared directly (not in your Dropbox tree); uses rclone cat + --dropbox-shared-files
CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES="${CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES:-0}"
# 1 = shared folder not yet in tree; first path segment is the shared folder name
CLUBMEISTERSCHAFT_RCLONE_SHARED_FOLDERS="${CLUBMEISTERSCHAFT_RCLONE_SHARED_FOLDERS:-0}"
# Optional: Dropbox shared link (?dl=1 added if missing); curl fallback when rclone shared-files fails
CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL="${CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL:-}"

# Optional exact workbook name in inbox; else newest .xlsx (excluding dated backups).
CLUBMEISTERSCHAFT_XLSX_NAME="${CLUBMEISTERSCHAFT_XLSX_NAME:-Clubpokal DB 2026.xlsx}"

STABLE_WAIT_SEC="${STABLE_WAIT_SEC:-30}"
IMPORT_DATE="${IMPORT_DATE:-2026-05-15}"
IMPORT_SEASON="${IMPORT_SEASON:-}"
IMPORT_YEAR="${IMPORT_YEAR:-2026}"

# Parquet mtime invalidates in-process + disk cache; restart usually unnecessary.
SKIP_RESTART="${SKIP_RESTART:-1}"

DRY_RUN=0
SYNC_ONLY=0
FORCE=0

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

run_workbook_fingerprint() {
  local xlsx="$1"
  local fp_args=(
    scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py
    --fingerprint
    --xlsx "/in/clubmeisterschaft_import.xlsx"
    --date "${IMPORT_DATE}"
    --year "${IMPORT_YEAR}"
  )
  if [[ -n "${IMPORT_SEASON}" ]]; then
    fp_args+=(--season "${IMPORT_SEASON}")
  fi
  docker run --rm \
    "${IMPORT_MOUNTS[@]}" \
    -v "${xlsx}:/in/clubmeisterschaft_import.xlsx:ro" \
    --entrypoint python \
    "${DOCKER_IMAGE}" \
    "${fp_args[@]}"
}

resolve_dated_workbook_archive_path() {
  local archive_dir="$1" stem="$2" date_tag="$3"
  local dest="${archive_dir}/${stem}_${date_tag}.xlsx"
  local n=2
  while [[ -e "${dest}" ]]; do
    dest="${archive_dir}/${stem}_${date_tag}_${n}.xlsx"
    n=$((n + 1))
  done
  printf '%s' "${dest}"
}

archive_imported_workbook() {
  local src="$1"
  local name="${CLUBMEISTERSCHAFT_XLSX_NAME:-Clubpokal DB 2026.xlsx}"
  local stem="${name%.xlsx}"
  local date_tag
  date_tag="$(date +%Y_%m_%d)"
  mkdir -p "${CLUBMEISTERSCHAFT_ARCHIVE}"
  local dest
  dest="$(resolve_dated_workbook_archive_path "${CLUBMEISTERSCHAFT_ARCHIVE}" "${stem}" "${date_tag}")"
  cp -f "${src}" "${dest}"
  printf '%s' "${dest}"
}

dropbox_shared_download_url() {
  local url="$1"
  url="${url//dl=0/dl=1}"
  if [[ "${url}" != *"dl="* ]]; then
    if [[ "${url}" == *"?"* ]]; then
      url="${url}&dl=1"
    else
      url="${url}?dl=1"
    fi
  fi
  printf '%s' "${url}"
}

download_workbook_from_shared_url() {
  local url="$1" dest="$2"
  command -v curl >/dev/null 2>&1 || die "curl required for CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL"
  local dl_url
  dl_url="$(dropbox_shared_download_url "${url}")"
  curl -fsSL --retry 3 -o "${dest}.part" "${dl_url}"
  mv -f "${dest}.part" "${dest}"
}

send_import_notification() {
  local subject="$1"
  local run_log="$2"
  if [[ -z "${CLUBMEISTERSCHAFT_NOTIFY_EMAIL:-}" ]]; then
    log "notify: CLUBMEISTERSCHAFT_NOTIFY_EMAIL unset; skip email"
    return 0
  fi

  local notify_script="${NOTIFY_SCRIPT:-}"
  if [[ -z "${notify_script}" ]]; then
    if [[ -f "${SCRIPT_DIR}/send_notify_email.py" ]]; then
      notify_script="${SCRIPT_DIR}/send_notify_email.py"
    elif [[ -f "${BOWLYZER_DIR}/scripts/send_notify_email.py" ]]; then
      notify_script="${BOWLYZER_DIR}/scripts/send_notify_email.py"
    fi
  fi
  if [[ -z "${notify_script}" || ! -f "${notify_script}" ]]; then
    log "notify: missing send_notify_email.py; skip email"
    return 0
  fi
  if [[ -z "${NOTIFY_SMTP_HOST:-}" ]]; then
    log "notify: NOTIFY_SMTP_HOST unset; skip email to ${CLUBMEISTERSCHAFT_NOTIFY_EMAIL}"
    return 0
  fi
  if [[ ! -f "${run_log}" ]]; then
    log "notify: missing run log ${run_log}; skip email"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    if ! python3 "${notify_script}" \
      --to "${CLUBMEISTERSCHAFT_NOTIFY_EMAIL}" \
      --subject "${subject}" \
      --body-file "${run_log}"; then
      log "notify: email failed (import succeeded)"
    fi
    return 0
  fi
  log "notify: python3 not found; skip email"
}

usage() {
  cat <<'EOF'
Usage: clubmeisterschaft_auto_import.sh [options]

  --dry-run       Sync (if configured) and report; do not import or publish
  --sync-only     Only rclone sync; no import
  --skip-restart  Do not restart bowlyzer (default via SKIP_RESTART=1 in env)
  --restart       Restart bowlyzer after successful publish
  --force         Import even if workbook fingerprint unchanged
  -h, --help      This help

Environment (see deploy/vps/clubmeisterschaft-import.env.example):
  CLUBMEISTERSCHAFT_RCLONE_SRC    rclone source (folder, or file if SHARED_FILES=1)
  CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES   1 for directly shared single file
  CLUBMEISTERSCHAFT_RCLONE_SHARED_FOLDERS 1 for shared folder not in Dropbox tree
  GF_TOURNAMENT_CSV               Host GF regional snapshot (not from Docker image)
  CLUBMEISTERSCHAFT_NOTIFY_EMAIL  Comma-separated; email when workbook hash changes
  CLUBMEISTERSCHAFT_ARCHIVE       Dated workbook copies on fingerprint change (default: STATE_DIR/archive)
  NOTIFY_SMTP_HOST                SMTP relay (required for notifications)
  SKIP_RESTART                    1 = no container restart (default)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --sync-only) SYNC_ONLY=1 ;;
    --skip-restart) SKIP_RESTART=1 ;;
    --restart) SKIP_RESTART=0 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

mkdir -p "${CLUBMEISTERSCHAFT_INBOX}" "${CLUBMEISTERSCHAFT_WORK}" "${STATE_DIR}" "${TOURNAMENT_INPUTS_DIR}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  die "Another import is running (lock ${LOCK_FILE})"
fi

RUN_LOG="$(mktemp "${STATE_DIR}/import-run.XXXXXX.log")"
cleanup_run_log() {
  rm -f "${RUN_LOG}"
}
trap cleanup_run_log EXIT
exec > >(tee -a "${RUN_LOG}") 2>&1

# --- Step 1: Dropbox -> inbox ---
DEST_NAME="${CLUBMEISTERSCHAFT_XLSX_NAME:-Clubpokal DB 2026.xlsx}"
INBOX_XLSX="${CLUBMEISTERSCHAFT_INBOX}/${DEST_NAME}"

if [[ -n "${CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL}" ]]; then
  log "step 1: curl shared link -> ${INBOX_XLSX}"
  download_workbook_from_shared_url "${CLUBMEISTERSCHAFT_DROPBOX_SHARED_URL}" "${INBOX_XLSX}"
elif [[ -n "${CLUBMEISTERSCHAFT_RCLONE_SRC}" ]]; then
  if ! command -v rclone >/dev/null 2>&1; then
    die "rclone not installed but CLUBMEISTERSCHAFT_RCLONE_SRC is set"
  fi

  RCLONE_FLAGS=()
  if [[ "${CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES}" == "1" ]]; then
    RCLONE_FLAGS+=(--dropbox-shared-files)
  fi
  if [[ "${CLUBMEISTERSCHAFT_RCLONE_SHARED_FOLDERS}" == "1" ]]; then
    RCLONE_FLAGS+=(--dropbox-shared-folders)
  fi

  if [[ "${CLUBMEISTERSCHAFT_RCLONE_SHARED_FILES}" == "1" ]]; then
    log "step 1: rclone cat (shared file) ${CLUBMEISTERSCHAFT_RCLONE_SRC} -> ${INBOX_XLSX}"
    TMP_DL="${CLUBMEISTERSCHAFT_WORK}/.dropbox_shared_download.part"
    rclone cat "${CLUBMEISTERSCHAFT_RCLONE_SRC}" "${RCLONE_FLAGS[@]}" > "${TMP_DL}"
    mv -f "${TMP_DL}" "${INBOX_XLSX}"
  elif [[ "${CLUBMEISTERSCHAFT_RCLONE_SHARED_FOLDERS}" == "1" ]]; then
    log "step 1: rclone sync (shared folder) ${CLUBMEISTERSCHAFT_RCLONE_SRC} -> ${CLUBMEISTERSCHAFT_INBOX}"
    rclone sync "${CLUBMEISTERSCHAFT_RCLONE_SRC}" "${CLUBMEISTERSCHAFT_INBOX}" \
      "${RCLONE_FLAGS[@]}" \
      --exclude '~$*' \
      --exclude '.~*' \
      --exclude '.~lock.*' \
      --exclude 'Clubpokal DB 2026_*.xlsx'
  else
    log "step 1: rclone sync ${CLUBMEISTERSCHAFT_RCLONE_SRC} -> ${CLUBMEISTERSCHAFT_INBOX}"
    rclone sync "${CLUBMEISTERSCHAFT_RCLONE_SRC}" "${CLUBMEISTERSCHAFT_INBOX}" \
      --exclude '~$*' \
      --exclude '.~*' \
      --exclude '.~lock.*' \
      --exclude 'Clubpokal DB 2026_*.xlsx'
  fi
else
  log "step 1: CLUBMEISTERSCHAFT_RCLONE_SRC unset — using existing file(s) in ${CLUBMEISTERSCHAFT_INBOX}"
fi

if [[ "${SYNC_ONLY}" -eq 1 ]]; then
  log "sync-only: done"
  exit 0
fi

# --- Step 2: pick workbook, stable wait, hash ---
resolve_workbook_path() {
  local inbox="$1" name="$2"
  if [[ -n "${name}" && -f "${inbox}/${name}" ]]; then
    printf '%s\n' "${inbox}/${name}"
    return 0
  fi
  if [[ -n "${name}" ]]; then
    local nested=""
    nested="$(find "${inbox}" -mindepth 1 -maxdepth 2 -type f -name "${name}" 2>/dev/null | head -1)"
    if [[ -n "${nested}" && -f "${nested}" ]]; then
      printf '%s\n' "${nested}"
      return 0
    fi
  fi
  local candidate=""
  candidate="$(find "${inbox}" -maxdepth 2 -type f -name '*.xlsx' 2>/dev/null \
    | grep -v '/~\$' | grep -v '/\.~' | grep -v '_20[0-9][0-9]_' \
    | while IFS= read -r f; do
        [[ -f "${f}" ]] || continue
        printf '%s\t%s\n' "$(stat -c '%Y' "${f}")" "${f}"
      done \
    | sort -t $'\t' -k1,1rn | head -1 | cut -f2-)"
  if [[ -n "${candidate}" && -f "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  return 1
}

XLSX_SRC=""
if resolved="$(resolve_workbook_path "${CLUBMEISTERSCHAFT_INBOX}" "${CLUBMEISTERSCHAFT_XLSX_NAME}")"; then
  XLSX_SRC="${resolved}"
fi
if [[ -z "${XLSX_SRC}" || ! -f "${XLSX_SRC}" ]]; then
  die "No .xlsx in ${CLUBMEISTERSCHAFT_INBOX} (set CLUBMEISTERSCHAFT_XLSX_NAME; check rclone sync path is the folder, not the file)"
fi
log "step 2: workbook ${XLSX_SRC}"

size1=$(stat -c '%s' "${XLSX_SRC}")
mtime1=$(stat -c '%Y' "${XLSX_SRC}")
log "waiting ${STABLE_WAIT_SEC}s for stable workbook"
sleep "${STABLE_WAIT_SEC}"
size2=$(stat -c '%s' "${XLSX_SRC}")
mtime2=$(stat -c '%Y' "${XLSX_SRC}")
if [[ "${size1}" != "${size2}" || "${mtime1}" != "${mtime2}" ]]; then
  die "Workbook still changing (size ${size1}->${size2}); retry next timer tick"
fi

XLSX_WORK="${CLUBMEISTERSCHAFT_WORK}/clubmeisterschaft_import.xlsx"
cp -f "${XLSX_SRC}" "${XLSX_WORK}"

IMPORTER_SCRIPT="${IMPORTER_SCRIPT:-${BOWLYZER_DIR}/scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py}"
IMPORT_MOUNTS=()
if [[ -f "${IMPORTER_SCRIPT}" ]]; then
  IMPORT_MOUNTS=(-v "${IMPORTER_SCRIPT}:/app/scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py:ro")
else
  die "Missing importer ${IMPORTER_SCRIPT} (run install_clubmeisterschaft_auto_import.sh)"
fi

docker image inspect "${DOCKER_IMAGE}" >/dev/null 2>&1 || die "Docker image not found: ${DOCKER_IMAGE}"

log "step 2b: workbook fingerprint via ${DOCKER_IMAGE}"
NEW_HASH="$(run_workbook_fingerprint "${XLSX_WORK}")" || die "Workbook fingerprint failed"
OLD_HASH=""
if [[ -f "${LAST_HASH_FILE}" ]]; then
  OLD_HASH="$(tr -d ' \n\r' < "${LAST_HASH_FILE}")"
fi

if [[ "${FORCE}" -eq 0 && "${NEW_HASH}" == "${OLD_HASH}" ]]; then
  log "unchanged (fingerprint ${NEW_HASH:0:12}…); skip import"
  exit 0
fi

log "workbook changed (fingerprint ${OLD_HASH:-none} -> ${NEW_HASH:0:12}…)"

ARCHIVE_DEST=""
ARCHIVE_DEST="$(resolve_dated_workbook_archive_path \
  "${CLUBMEISTERSCHAFT_ARCHIVE}" \
  "${CLUBMEISTERSCHAFT_XLSX_NAME%.xlsx}" \
  "$(date +%Y_%m_%d)")"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "dry-run: would archive ${XLSX_WORK} -> ${ARCHIVE_DEST}"
  log "dry-run: would import ${XLSX_WORK}, merge tournaments -> ${TOURNAMENTS_PUBLISHED_CSV}"
  exit 0
fi

ARCHIVE_DEST="$(archive_imported_workbook "${XLSX_WORK}")"
log "archived workbook -> ${ARCHIVE_DEST}"

[[ -d "${BOWLYZER_DIR}/database/data" ]] || die "Missing ${BOWLYZER_DIR}/database/data"
[[ -f "${COMPOSE_FILE}" ]] || die "Missing compose file ${COMPOSE_FILE}"
[[ -f "${GF_TOURNAMENT_CSV}" ]] || die "Missing GF tournament snapshot ${GF_TOURNAMENT_CSV} (deploy with -SyncDatabase or bootstrap script)"

DOCKER_DATA_MOUNT=(-v "${BOWLYZER_DIR}/database/data:/app/database/data")
DOCKER_WORK_MOUNT=(-v "${BOWLYZER_DIR}/database/work:/app/database/work")
DOCKER_RO_MOUNTS=(
  -v "${BOWLYZER_DIR}/database/relational_csv:/app/database/relational_csv:ro"
  -v "${BOWLYZER_DIR}/database/config:/app/database/config:ro"
)

# --- Step 3: Excel -> manual tournament CSV ---
IMPORT_ARGS=(
  scripts/data/import_clubmeisterschaft_donaubowler_xlsx.py
  --xlsx "/in/clubmeisterschaft_import.xlsx"
  --date "${IMPORT_DATE}"
  --year "${IMPORT_YEAR}"
)
if [[ -n "${IMPORT_SEASON}" ]]; then
  IMPORT_ARGS+=(--season "${IMPORT_SEASON}")
fi

log "step 3: import via ${DOCKER_IMAGE}"
docker run --rm \
  "${DOCKER_DATA_MOUNT[@]}" \
  "${DOCKER_WORK_MOUNT[@]}" \
  "${DOCKER_RO_MOUNTS[@]}" \
  "${IMPORT_MOUNTS[@]}" \
  -v "${XLSX_WORK}:/in/clubmeisterschaft_import.xlsx:ro" \
  --entrypoint python \
  "${DOCKER_IMAGE}" \
  "${IMPORT_ARGS[@]}"

[[ -f "${MANUAL_TOURNAMENT_CSV}" ]] || die "Import did not produce ${MANUAL_TOURNAMENT_CSV}"

PUBLISH_SCRIPT="${PUBLISH_SCRIPT:-}"
if [[ -z "${PUBLISH_SCRIPT}" ]]; then
  if [[ -f "${SCRIPT_DIR}/publish_tournament_parquet.py" ]]; then
    PUBLISH_SCRIPT="${SCRIPT_DIR}/publish_tournament_parquet.py"
  elif [[ -f "${BOWLYZER_DIR}/scripts/publish_tournament_parquet.py" ]]; then
    PUBLISH_SCRIPT="${BOWLYZER_DIR}/scripts/publish_tournament_parquet.py"
  else
    PUBLISH_SCRIPT="${SCRIPT_DIR}/publish_tournament_parquet.py"
  fi
fi
[[ -f "${PUBLISH_SCRIPT}" ]] || die "Missing ${PUBLISH_SCRIPT} (run install_clubmeisterschaft_auto_import.ps1 from PC)"

# --- Step 4: GF snapshot + manual -> tournaments_postprocessed.parquet ---
log "step 4: rebuild tournaments_postprocessed (GF host snapshot + manual)"
docker run --rm \
  "${DOCKER_DATA_MOUNT[@]}" \
  "${DOCKER_WORK_MOUNT[@]}" \
  -v "${GF_TOURNAMENT_CSV}:/in/gf_tournaments.csv:ro" \
  -v "${PUBLISH_SCRIPT}:/app/scripts/publish_tournament_parquet.py:ro" \
  --entrypoint python \
  "${DOCKER_IMAGE}" \
  /app/scripts/publish_tournament_parquet.py \
  --gf-tournaments /in/gf_tournaments.csv \
  --manual-tournaments "/app/database/work/tournaments/$(basename "${MANUAL_TOURNAMENT_CSV}")" \
  --tournaments-out "/app/database/data/$(basename "${TOURNAMENTS_PUBLISHED_CSV%.csv}.csv")"

PARQUET_OUT="${TOURNAMENTS_PUBLISHED_CSV%.csv}.parquet"
[[ -f "${PARQUET_OUT}" ]] || die "Expected parquet at ${PARQUET_OUT}"

printf '%s\n' "${NEW_HASH}" > "${LAST_HASH_FILE}"
log "published ${PARQUET_OUT} ($(stat -c '%s' "${PARQUET_OUT}") bytes)"

if [[ "${SKIP_RESTART}" -eq 1 ]]; then
  log "skip-restart: app reloads parquet on next request (mtime cache)"
  log "done"
  send_import_notification "Bowlyzer: Clubmeisterschaft import updated" "${RUN_LOG}"
  exit 0
fi

log "restarting bowlyzer"
docker compose -f "${COMPOSE_FILE}" restart bowlyzer
log "done"
send_import_notification "Bowlyzer: Clubmeisterschaft import updated" "${RUN_LOG}"
