# Manual deploy from Windows (docker save → VPS)

Build the image on your PC, upload it, and restart the container on the VPS.
No registry and no `docker compose build` on the server (important on 1 GB RAM).

## One-time setup

1. **SSH key login** to the VPS. Prefer user **`bowlyzer`** after `deploy/vps/setup-bowlyzer-user.sh` (root only for initial setup).
2. **Docker** on the VPS (already done).
3. **On the VPS once:** ensure legacy Gunicorn stays off and nginx proxies to `:8080`:
   ```bash
   sudo systemctl disable flaskapp
   # nginx: proxy_pass http://127.0.0.1:8080;
   ```
4. **On the VPS once** (as `bowlyzer`):
   ```bash
   sudo bash /path/to/repo/deploy/vps/setup-bowlyzer-user.sh --migrate-from-root
   sudo bash /path/to/repo/deploy/vps/cleanup-disk.sh
   echo "FLASK_SECRET_KEY=$(openssl rand -hex 32)" > ~/bowlyzer/.env
   chmod 600 ~/bowlyzer/.env
   ```
   See [`docs/VPS_DISK_AND_USER.md`](../docs/VPS_DISK_AND_USER.md) if disk is >90% full.
5. **On Windows:** copy config and edit:
   ```powershell
   Copy-Item deploy\deploy.config.example.ps1 deploy\deploy.config.ps1
   notepad deploy\deploy.config.ps1
   ```

## Stop on the VPS (host struggling / before redeploy)

```powershell
.\deploy\stop-remote.ps1
.\deploy\stop-remote.ps1 -PruneImages   # also docker image prune -f
```

If SSH is very slow, run on the VPS console as `bowlyzer`:

```bash
cd ~/bowlyzer
docker compose -f docker-compose.prod.yml down --remove-orphans
```

Last resort as **root** (stops all containers):

```bash
sudo systemctl stop docker
```

## Deploy a new version

**Docker Desktop (or another local Docker engine) must be running** — the script builds on your PC.

From the repo root in PowerShell:

```powershell
.\deploy\deploy.ps1
```

When **published** data under `database/data/` changed (merged league Parquet, tournament configs — not legacy scrape / pipeline work files):

```powershell
.\deploy\deploy.ps1 -SyncDatabase
```

### Data only (no image rebuild)

After `build_published_dataset.py`, push Parquet/JSON and restart the container (~seconds, no Docker Desktop required):

```powershell
.\deploy\deploy-data.ps1
# or: .\deploy\deploy.ps1 -DataOnly
```

Uploads `database/data/*.parquet`, `*.json`, plus `relational_csv/` and `config/`, then `docker compose restart bowlyzer`. Add `-SyncDatabaseCsv` if you need large CSV copies on the VPS.

### Pre-warmed API cache (club page, league grids, tournaments)

Build the cache on your PC (after published data is built), then ship it:

```powershell
# 1) Published data: historical + legacy scrape + GF + tournaments (Spieler merges at runtime)
uv run python scripts/build_published_dataset.py --with-legacy-scrape

# 2) Full API cache rebuild (league + clubs + Spieler + Turnier)
uv run python scripts/rebuild_league_caches.py --all-published --workers 8

# League only (same as before)
uv run python scripts/rebuild_league_caches.py --database db_real_merged

# Or incremental warm + clubs only
uv run python scripts/warm_league_cache.py --database db_real_merged --rebuild --warm-clubs --workers 6

# Multi-process warm (tqdm ETA over shards; add --verbose for full child logs)
uv run python scripts/warm_cache_shard.py --all-published --rebuild --warm-all --max-parallel 12
# League + clubs only (skip meta charts):
uv run python scripts/warm_cache_shard.py --database db_real_merged --rebuild --warm-clubs --skip-meta --clubs-per-shard 8 --max-parallel 8
# Legacy name still works (forwards to warm_cache_shard.py):
uv run python scripts/warm_league_cache_shard.py --database db_real_merged --rebuild --warm-clubs --max-parallel 8

# Deploy data + cache (shipped cache :ro + ./.cache/league-runtime :rw for cache misses)
.\deploy\deploy.ps1 -SyncDatabase -SyncCache
# data-only after warming:
.\deploy\deploy-data.ps1 -SyncDatabase -SyncCache
```

Cache roots:

| Path | Role |
|------|------|
| `.cache/league/` | Pre-warmed JSON (local build + VPS **read-only** mount) |
| `.cache/league-runtime/` | VPS **read-write** overlay — cache misses, `revision_index.json` patches, hot queries |

Locally only `.cache/league/` is used unless you set `LEAGUE_CACHE_RUNTIME_DIR`. **Revision** must match the Parquet/CSV you deploy — warm **after** `build_published_dataset.py`, then deploy data and cache in the same release. `-SyncCache` packs shipped cache into `deploy/artifacts/league-cache.tar.gz` and clears `league-runtime/` on the VPS.

**Important:** `deploy-data.ps1` only updates files on the VPS host. The running container must include Python that reads `entries/` (recent `bowlyzer:release` image). Data-only deploy without a new image → cache files sit on disk but the app ignores them. After image + cache deploy, check responses: `curl -sI 'https://www.bowlyzer.online/league/get_club_matrix?database=db_real_merged&club=Donaubowler+Regensburg' | findstr X-League-Cache` should show `HIT`.

Pipeline intermediates belong on **`C:\tmp\bowlyzer\data`** (see `database/data/README.md`). `-SyncDatabase` uploads `database/relational_csv`, `database/config`, and **`*.parquet` / `*.json`** in `database/data/`, plus **`tournament_manual_postprocessed.csv`** when needed. Use **`-SyncDatabaseCsv`** only if you still need huge CSV copies on the VPS (e.g. full `league_results_merged.csv`).

**Tournament data:** After `build_published_dataset.py`, the app reads **`tournaments_postprocessed.parquet`** on the VPS (GF + manual club imports merged locally). You do **not** need to sync `database/input/gf_tables_export/` — that path is dev-only and baked into the image.

**Compose mount:** prod binds only `database/data`, `relational_csv`, and `config` — not the whole `database/` folder (that would hide `database.paths` from the image and crash Gunicorn with `ModuleNotFoundError`).

### Request analytics (anonymized)

API requests are appended as **JSONL** to **`~/logs/analytics/requests.log`** on the VPS (bind-mount `/home/bowlyzer/logs/analytics`).

| Field | Meaning |
|-------|---------|
| `visitor_id` | SHA-256(truncated IP + daily salt)[:16] — no raw IP stored |
| `path`, `params` | Route + query string (`season`, `league`, `database`, …) |
| `cache_status` | `X-League-Cache` when present (`HIT` / `MISS`) |
| `duration_ms` | Server time for the request |

Env (in `docker-compose.prod.yml`): `ANALYTICS_ENABLED=1`, `ANALYTICS_REQUEST_LOG=/app/logs/analytics/requests.log`. Optional `ANALYTICS_SALT` (defaults to `FLASK_SECRET_KEY`). Set `ANALYTICS_ENABLED=0` to disable.

One-time on an existing VPS:

```bash
mkdir -p ~/logs/analytics
chmod 755 ~/logs/analytics
# redeploy image + updated compose, then:
docker compose -f ~/bowlyzer/docker-compose.prod.yml up -d --force-recreate
```

### Data size

| File | Typical size | In Docker image? | On VPS |
|------|----------------|------------------|--------|
| `league_results_merged.parquet` | ~3–8 MB | **No** | Host `~/bowlyzer/database/data/` via mount + `-SyncDatabase` |
| `league_results_merged.csv` (optional) | ~90 MB | **No** | Only with `-SyncDatabaseCsv` |
| `player_stats_merged_plus_tournaments.parquet` | ~5–15 MB | **No** | Same |
| `legacy_scrape/` tree | 1+ GB | **No** | Stay on your PC (`C:\tmp\bowlyzer\data`) |

The app loads Parquet into **RAM** (often 300–600 MB in pandas for full history), which is what stresses a 650 MB container limit — not the read-only mount itself.

**First deploy** (or after wiping `~/bowlyzer/database/data`): run once with `-SyncDatabase`. Later deploys: `.\deploy\deploy.ps1` only (image has code + SPA; data stays on the host).

Build only (no upload):

```powershell
.\deploy\deploy.ps1 -SkipUpload
```

Override host without config file:

```powershell
.\deploy\deploy.ps1 -RemoteHost 212.227.57.223
```

## What the script does

| Step | Action |
|------|--------|
| 1 | `docker compose build` |
| 2 | Tag `bowlyzer_deploy-bowlyzer:latest` → `bowlyzer:release` |
| 3 | `docker save` → `deploy/artifacts/bowlyzer-image.tar` (add `-ZipContainerImage` for `.tar.gz`) |
| 4 | `scp` `docker-compose.prod.yml` + image tar to `~/bowlyzer` |
| 5 | `ssh`: `docker load` + `compose up -d` (bind-mounts `database/data`, `relational_csv`, `config` only) |
| 6 | `curl` smoke check on `http://127.0.0.1:8080/liga` |

Production compose uses **`mem_limit: 650m`** (fits ~848 MiB VPS). App listens on host **8080**; nginx serves HTTPS on 80/443.

## Clubmeisterschaft auto-import (vacation / ongoing tournament)

When the data owner updates the **Clubmeisterschaft Donaubowler** Excel in Dropbox, the VPS can import automatically (rclone + systemd). **Not** for Clubpokal (separate format, later).

1. Deploy current image: `.\deploy\deploy.ps1 -SyncDatabase`
2. Install on VPS: `.\deploy\install_clubmeisterschaft_auto_import.ps1`
3. Follow dry-run week: [`docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md`](../docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md)

Enable timer after dry-run: `.\deploy\install_clubmeisterschaft_auto_import.ps1 -EnableTimer`

## Troubleshooting

| Issue | Check |
|-------|--------|
| `DEPLOY ABORTED: Docker engine is not running` | Start **Docker Desktop** on Windows; wait until the engine is up; `docker version` should show Client and Server. |
| `Required command not found: ssh` | Install “OpenSSH Client” (Windows optional features) |
| Wrong image name after build | `docker images` — project must be `bowlyzer_deploy-bowlyzer:latest` (repo folder name) |
| Site 502 | `ssh root@vps 'docker compose -f ~/bowlyzer/docker-compose.prod.yml logs --tail 30'` |
| `No module named 'database.paths'` | Prod compose must **not** mount `./database:/app/database` — use subdirs only (see `docker-compose.prod.yml`) |
| OOM restart | `docker stats`; ensure `flaskapp` is not running |
| Remote step: `set: invalid option`, `/root/bowlyzer\\r`, `unknown docker command` | Windows CRLF in the piped script; `deploy.ps1` now strips CR. Re-run deploy (e.g. `-SkipBuild` if image is current). |
| League API **200**, tournament **500** on `:8080` | `ls -la ~/bowlyzer/database/data/tournaments_postprocessed.*` — need Parquet from `build_published_dataset.py` + `-SyncDatabase`. Old images resolved tournament source only when the **CSV** existed, then loaded **league** Parquet → OOM. Redeploy image with the `data_file_exists` fix. |
| Tournament **404** on HTTPS but **500** on `127.0.0.1:8080` | nginx `proxy_intercept_errors on` + `error_page 500 … /50x.html` turns upstream 500 into **404**. Fix the app error first; compare `curl -s http://127.0.0.1:8080/tournament/get_available_seasons` vs HTTPS body. |
| Liga API **404** on HTTPS, **500** on `:8080` for `get_available_leagues` | HTTPS 404 is often nginx masking upstream **500** (`proxy_intercept_errors`). On `:8080`, run `curl -s '…/get_available_leagues?season=08-09&database=db_real_merged' | head` for the JSON error. Common: **read-only** `.cache/league` mount + cache miss → old code failed on `league_cache_put` (fixed: serve JSON anyway). Pre-warm filter endpoints and `-SyncCache`. See [`deploy/vps/nginx-season-query.md`](vps/nginx-season-query.md). |

## Files (gitignored locally)

- `deploy/deploy.config.ps1` — your VPS host/user/path
- `deploy/artifacts/bowlyzer-image.tar` — exported image (default; uncompressed)
- `deploy/artifacts/bowlyzer-image.tar.gz` — only when `-ZipContainerImage` is set
