#!/usr/bin/env bash
# Start backend (Flask API on :5050) and frontend (Vite on :5173) together.
# Stops cleanly on SIGINT (Ctrl+C) or SIGTERM by signalling each child's
# process group (so descendants like the actual flask/node processes die too).

set -euo pipefail
set -m  # job control: each backgrounded job becomes a process-group leader

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=5050
FRONTEND_PORT=5173

stopping=0
cleanup() {
  (( stopping )) && return
  stopping=1
  echo
  echo "==> stopping services"
  for pid in "${BE_PID:-}" "${FE_PID:-}"; do
    [[ -n "$pid" ]] || continue
    # Negative PID = process group; with `set -m`, BE_PID/FE_PID are pgids.
    kill -TERM "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "==> stopped"
}
trap 'cleanup; exit 0' INT TERM
trap cleanup EXIT

echo "==> backend: uv run flask on :$BACKEND_PORT"
cd "$ROOT"
uv run flask --app wsgi run --port "$BACKEND_PORT" --no-debug &
BE_PID=$!

echo "==> frontend: pnpm dev on :$FRONTEND_PORT (HMR enabled)"
cd "$ROOT/frontend"
pnpm dev --port "$FRONTEND_PORT" --strictPort &
FE_PID=$!

echo
echo "==> backend  http://localhost:$BACKEND_PORT"
echo "==> frontend http://localhost:$FRONTEND_PORT"
echo "==> Ctrl+C or SIGTERM to stop"

# `wait` (no -n) is signal-interruptible: when a trap is installed, an incoming
# signal aborts the wait, the trap fires, and we exit cleanly.
wait
