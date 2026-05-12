#!/usr/bin/env python3
"""
Invalidate persisted league caches for a database, then warm everything:

- All seasons in the source
- For each season: get_season_league_standings without division= (all divisions)
  and one cached response per division code that has data that season
  (same combinations the UI uses when switching division filters)
- All league-scoped endpoints per (season, league) and league-wide aggregation tables

Usage:
  uv run python scripts/rebuild_league_caches.py --database db_real_merged
  uv run python scripts/rebuild_league_caches.py --database db_real_merged --dry-run

Equivalent to:
  uv run python scripts/warm_league_cache.py --database ... --rebuild

Environment: same as warm_league_cache.py (LEAGUE_CACHE_DIR, LEAGUE_CACHE_REVISION, …).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "league_analyzer_v1"
for _p in (LEGACY, ROOT):
    if _p.is_dir():
        sys.path.insert(0, str(_p))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild league response caches (invalidate + full warm including season×division standings)."
    )
    parser.add_argument("--database", required=True, help="Source id, e.g. db_real_merged")
    parser.add_argument(
        "--languages",
        default="de,en",
        help="Comma-separated i18n languages (default: de,en)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print jobs only; no delete, no write")
    args = parser.parse_args()

    warm_path = Path(__file__).resolve().parent / "warm_league_cache.py"
    spec = importlib.util.spec_from_file_location("warm_league_cache_run", warm_path)
    if spec is None or spec.loader is None:
        print("Could not load warm_league_cache.py", file=sys.stderr)
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    argv_bak = sys.argv[:]
    try:
        sys.argv = [
            str(warm_path),
            "--database",
            args.database.strip(),
            "--languages",
            args.languages,
            "--rebuild",
        ]
        if args.dry_run:
            sys.argv.append("--dry-run")
        return int(mod.main())
    finally:
        sys.argv = argv_bak


if __name__ == "__main__":
    raise SystemExit(main())
