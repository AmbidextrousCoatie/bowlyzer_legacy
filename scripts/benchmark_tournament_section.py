#!/usr/bin/env -S uv run python
"""
Cold/warm benchmark for GET /tournament/get_section.

Full documentation: DEPLOY.md § "Tournament performance profiling (dev only)".

Requires Flask on :5000 (``uv run python wsgi.py`` or ``./start.sh``).

Important: set TOURNAMENT_BENCHMARK=1 on the **server** process as well, or you
only get wall-clock times here without the per-step breakdown in Flask stdout.

Example (bash, repo root):

  export TOURNAMENT_BENCHMARK=1
  uv run python wsgi.py   # terminal 1

  uv run python scripts/benchmark_tournament_section.py \\
    --season "25/26" \\
    --tournament "Bayerische Meisterschaft - Männer Einzel" \\
    --database db_tournament_regions_2026_gf \\
    --clear-cache

PowerShell::

  $env:TOURNAMENT_BENCHMARK = "1"
  uv run python wsgi.py

  uv run python scripts/benchmark_tournament_section.py `
    --season "25/26" `
    --tournament "Bayerische Meisterschaft - Männer Einzel" `
    --database db_tournament_regions_2026_gf `
    --clear-cache

Options:
  --clear-cache   Remove .cache/league before the cold run.
  --base URL      API base (default http://127.0.0.1:5000).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _fetch(base: str, params: dict[str, str]) -> tuple[int, int, float]:
    qs = urllib.parse.urlencode(params)
    url = f"{base.rstrip('/')}/tournament/get_section?{qs}"
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=600) as resp:
        body = resp.read()
    elapsed = time.perf_counter() - t0
    return resp.status, len(body), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark tournament get_section")
    parser.add_argument("--base", default="http://127.0.0.1:5000", help="Flask base URL")
    parser.add_argument("--season", required=True)
    parser.add_argument("--tournament", required=True)
    parser.add_argument("--database", default="db_tournament_regions_2026_gf")
    parser.add_argument("--round", default="", help="optional round number")
    parser.add_argument("--clear-cache", action="store_true", help="remove .cache/league before cold run")
    args = parser.parse_args()

    os.environ["TOURNAMENT_BENCHMARK"] = "1"

    params = {
        "season": args.season,
        "tournament": args.tournament,
        "database": args.database,
    }
    if args.round:
        params["round"] = args.round

    cache_dir = os.path.join(_REPO_ROOT, ".cache", "league")
    if args.clear_cache and os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir)
        print(f"cleared {cache_dir}")

    print("=== cold run (watch Flask console for step breakdown) ===")
    status, nbytes, elapsed = _fetch(args.base, params)
    print(f"HTTP {status} | {nbytes:,} bytes | wall {elapsed:.3f}s\n")

    print("=== warm run (disk cache should hit at route) ===")
    status2, nbytes2, elapsed2 = _fetch(args.base, params)
    print(f"HTTP {status2} | {nbytes2:,} bytes | wall {elapsed2:.3f}s")

    return 0 if status == 200 and status2 == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
