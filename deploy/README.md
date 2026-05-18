# Manual deploy from Windows (docker save → VPS)

Build the image on your PC, upload it, and restart the container on the VPS.
No registry and no `docker compose build` on the server (important on 1 GB RAM).

## One-time setup

1. **SSH key login** to the VPS (`ssh root@your-server` works without a password prompt).
2. **Docker** on the VPS (already done).
3. **On the VPS once:** ensure legacy Gunicorn stays off and nginx proxies to `:8080`:
   ```bash
   sudo systemctl disable flaskapp
   # nginx: proxy_pass http://127.0.0.1:8080;
   ```
4. **On the VPS once:** create `.env` in the deploy directory with a real secret:
   ```bash
   mkdir -p ~/bowlyzer
   echo "FLASK_SECRET_KEY=$(openssl rand -hex 32)" > ~/bowlyzer/.env
   ```
5. **On Windows:** copy config and edit:
   ```powershell
   Copy-Item deploy\deploy.config.example.ps1 deploy\deploy.config.ps1
   notepad deploy\deploy.config.ps1
   ```

## Deploy a new version

From the repo root in PowerShell:

```powershell
.\deploy\deploy.ps1
```

When CSV data under `database/` changed:

```powershell
.\deploy\deploy.ps1 -SyncDatabase
```

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
| 3 | `docker save` → `deploy/artifacts/bowlyzer-image.tar` |
| 4 | `scp` `docker-compose.prod.yml` + image tar to `~/bowlyzer` |
| 5 | `ssh`: `docker load` + `docker compose -f docker-compose.prod.yml up -d` |
| 6 | `curl` smoke check on `http://127.0.0.1:8080/liga` |

Production compose uses **`mem_limit: 650m`** (fits ~848 MiB VPS). App listens on host **8080**; nginx serves HTTPS on 80/443.

## Troubleshooting

| Issue | Check |
|-------|--------|
| `Required command not found: ssh` | Install “OpenSSH Client” (Windows optional features) |
| Wrong image name after build | `docker images` — project must be `bowlyzer_deploy-bowlyzer:latest` (repo folder name) |
| Site 502 | `ssh root@vps 'docker compose -f ~/bowlyzer/docker-compose.prod.yml logs --tail 30'` |
| OOM restart | `docker stats`; ensure `flaskapp` is not running |

## Files (gitignored locally)

- `deploy/deploy.config.ps1` — your VPS host/user/path
- `deploy/artifacts/bowlyzer-image.tar` — exported image
