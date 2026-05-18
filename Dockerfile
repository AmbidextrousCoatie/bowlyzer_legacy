# syntax=docker/dockerfile:1

# --- Frontend (build only; not shipped) ---
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV NODE_OPTIONS=--max-old-space-size=768
RUN pnpm run build

# --- Python dependencies ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend-deps
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# --- Runtime image ---
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BOWLYZER_ROOT=/app \
    BOWLYZER_SPA_DIR=/app/frontend/dist \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

# pandas/numpy may need libgomp on slim images
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=backend-deps /app/.venv /app/.venv
COPY pyproject.toml uv.lock wsgi.py ./
COPY app ./app
COPY business_logic ./business_logic
COPY data_access ./data_access
COPY database ./database
COPY pipeline ./pipeline
COPY deploy ./deploy
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/liga')" || exit 1

CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "wsgi:app"]
