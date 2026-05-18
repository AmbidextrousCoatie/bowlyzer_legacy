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

On the server (or build locally and `docker push`):

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

## Health check

Container healthcheck requests `GET /liga` (SPA shell). Logs:

```bash
docker compose logs -f bowlyzer
```

## Local dev (unchanged)

```bash
./start.sh   # Flask :5000 + Vite :5173
```

Production build smoke test:

```bash
cd frontend && pnpm build
cd .. && uv run gunicorn -c deploy/gunicorn.conf.py wsgi:app
# open http://127.0.0.1:8000/liga
```

## Legacy URLs

Old Jinja paths redirect to React routes (301, query string preserved), e.g. `/league/stats` → `/liga`, `/team/stats` → `/mannschaft`.
