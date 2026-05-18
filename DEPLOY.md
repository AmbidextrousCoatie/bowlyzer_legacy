# Bowl-A-Lyzer — Docker deployment (1 GB VPS)

Production runs a **single container**: Gunicorn serves the Flask JSON API and the React SPA build from `frontend/dist` on port **8000**. No Node.js at runtime.

## Prerequisites (server)

- Docker Engine + Docker Compose plugin
- Optional: 2–4 GB swap for **image builds** on a 1 GB machine (runtime needs ~700–900 MB)

```bash
# Example swap (run once, adjust if you already have swap)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Build and run

### Recommended: deploy from Windows (`deploy/deploy.ps1`)

Build on your PC, upload the image, restart on the VPS (no build on 1 GB RAM):

```powershell
Copy-Item deploy\deploy.config.example.ps1 deploy\deploy.config.ps1
# edit RemoteHost, RemoteUser, RemoteDir
.\deploy\deploy.ps1
```

Add `-SyncDatabase` when `database/` CSVs changed. Full details: [`deploy/README.md`](deploy/README.md).

### Alternative: build on the server

```bash
git clone <your-repo> bowlyzer && cd bowlyzer
export FLASK_SECRET_KEY="$(openssl rand -hex 32)"
docker compose build
docker compose up -d
```

Default URL: `http://<server-ip>:8080` (host port from `BOWLYZER_HOST_PORT`, default **8080**).

CSV data under `database/` is bind-mounted read-only so you can refresh data without rebuilding.

## Expose to the public internet

### Option A — map host port 80 (simple)

```bash
# docker-compose.yml or override:
# ports: ["80:8000"]
docker compose up -d
```

Open firewall:

```bash
sudo ufw allow 80/tcp
sudo ufw enable
```

### Option B — reverse proxy + TLS (recommended)

Keep the app on `127.0.0.1:8080` and put Caddy or nginx in front.

**Caddy** (`/etc/caddy/Caddyfile`):

```caddy
bowlyzer.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
sudo apt install caddy
sudo systemctl reload caddy
sudo ufw allow 80,443/tcp
```

**nginx** (snippet):

```nginx
server {
    listen 80;
    server_name bowlyzer.example.com;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Use Certbot or Caddy automatic HTTPS for TLS.

## Resource tuning (1 GB RAM)

Defaults in `deploy/gunicorn.conf.py` and `docker-compose.yml`:

| Setting | Value | Why |
|--------|-------|-----|
| `GUNICORN_WORKERS` | 1 | pandas loads are memory-heavy |
| `GUNICORN_THREADS` | 2 | modest concurrency without extra processes |
| `mem_limit` | 900m | leave headroom for the kernel |

Override via environment:

```bash
GUNICORN_WORKERS=1 GUNICORN_THREADS=2 docker compose up -d
```

**Build on a small VPS:** prefer building on CI or your dev machine (`docker buildx build --platform linux/amd64 -t bowlyzer .`) and pulling the image. Local build on 1 GB + swap works but is slow.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FLASK_SECRET_KEY` | `change-me-in-production` | Session signing — **set in production** |
| `PORT` | `8000` | Gunicorn bind port inside container |
| `BOWLYZER_HOST_PORT` | `8080` | Host port in `docker compose` |
| `BOWLYZER_SPA_DIR` | `/app/frontend/dist` | React build path |
| `LOG_LEVEL` | `info` | Gunicorn log level |

**Dev-only (do not set on VPS):** `TOURNAMENT_BENCHMARK` — tournament section
timing to stdout; see [Tournament performance profiling](#tournament-performance-profiling-dev-only).

## Health check

Container healthcheck requests `GET /liga` (SPA shell). Logs:

```bash
docker compose logs -f bowlyzer
```

## Local dev (unchanged)

```bash
./start.sh   # Flask :5000 + Vite :5173
```

### Tournament performance profiling (dev only)

Use this when investigating slow `GET /tournament/get_section` (e.g. large
fields, regressions after pandas changes). **Do not set in production** — it
only adds stdout timing; the flag has no effect unless the env var is set.

| Variable | Default | Purpose |
|----------|---------|---------|
| `TOURNAMENT_BENCHMARK` | *(unset)* | When `1`, `true`, `yes`, or `on`: print per-step timings for `get_tournament_section` and field-progress detail to the Flask process stdout |

**Typical workflow (Windows PowerShell or bash):**

```bash
# Terminal 1 — enable timing in the server process
export TOURNAMENT_BENCHMARK=1          # bash
# $env:TOURNAMENT_BENCHMARK = "1"      # PowerShell
uv run python wsgi.py                  # or ./start.sh (export in same shell first)

# Terminal 2 — cold + warm HTTP benchmark (repo root)
uv run python scripts/benchmark_tournament_section.py \
  --season "25/26" \
  --tournament "Your Event Name" \
  --database db_tournament_regions_2026_gf \
  --clear-cache
```

The script sets `TOURNAMENT_BENCHMARK=1` for its own process but **the Flask
server must have the variable too** to print the step breakdown. Watch Terminal
1 for output like `=== tournament benchmark: get_tournament_section ===`.

Options:

- `--base http://127.0.0.1:5000` — API base URL (default Flask dev port)
- `--clear-cache` — delete `.cache/league` before the cold run
- `--round N` — optional round filter

Related disk cache (production-safe, on by default): `LEAGUE_CACHE_ENABLED`,
`LEAGUE_CACHE_DIR`, `LEAGUE_CACHE_REVISION` (see `app/cache/league_response_cache.py`).

Production build smoke test:

```bash
cd frontend && pnpm build
cd .. && uv run gunicorn -c deploy/gunicorn.conf.py wsgi:app
# open http://127.0.0.1:8000/liga
```

## Legacy URLs

Old Jinja paths redirect to React routes (301, query string preserved), e.g. `/league/stats` → `/liga`, `/team/stats` → `/mannschaft`.
