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

When **published** CSVs under `database/data/` changed (merged league, player hybrid, tournament configs — not legacy scrape / pipeline work files):

```powershell
.\deploy\deploy.ps1 -SyncDatabase
```

Pipeline intermediates belong on **`C:\tmp\bowlyzer\data`** (see `database/data/README.md`). `-SyncDatabase` uploads only `database/relational_csv`, `database/config`, and **files** in `database/data/` (no `legacy_scrape/` tree).

### Data size (~200 MB is normal)

| File | Typical size | In Docker image? | On VPS |
|------|----------------|------------------|--------|
| `league_results_merged.csv` | ~90 MB | **No** (`.dockerignore`) | Host `~/bowlyzer/database/data/` via mount + `-SyncDatabase` |
| `player_stats_merged_plus_tournaments.csv` | ~120 MB | **No** | Same |
| `legacy_scrape/` tree | 1+ GB | **No** | Stay on your PC (`C:\tmp\bowlyzer\data`) |

Together those two CSVs are **~210 MB on disk**. The app loads them into **RAM** at runtime (often 300–600 MB in pandas), which is what stresses a 650 MB container limit — not the read-only mount itself.

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
| 3 | `docker save` → gzip → `deploy/artifacts/bowlyzer-image.tar.gz` |
| 4 | `scp` `docker-compose.prod.yml` + image tar to `~/bowlyzer` |
| 5 | `ssh`: `docker load` + `docker compose -f docker-compose.prod.yml up -d` |
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
| OOM restart | `docker stats`; ensure `flaskapp` is not running |
| Remote step: `set: invalid option`, `/root/bowlyzer\\r`, `unknown docker command` | Windows CRLF in the piped script; `deploy.ps1` now strips CR. Re-run deploy (e.g. `-SkipBuild` if image is current). |

## Files (gitignored locally)

- `deploy/deploy.config.ps1` — your VPS host/user/path
- `deploy/artifacts/bowlyzer-image.tar.gz` — exported image (gzip; faster upload than raw `.tar`)
