#!/usr/bin/env python3
"""
Warm heavy API disk caches (season standings, player search, all-players lifetime, tournament).

See also: ``warm_cache_shard.py`` for parallel multi-process warm.

Usage:
  uv run python scripts/warm_essential_caches.py
  uv run python scripts/warm_essential_caches.py --database db_real_merged
  LEAGUE_CACHE_WARM_MAX_SEASONS=5 uv run python scripts/warm_essential_caches.py

Environment:
  LEAGUE_CACHE_ENABLED=1 (default)
  LEAGUE_CACHE_WARM_MAX_SEASONS   optional limit (latest N seasons); unset = all
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=os.environ.get("LEAGUE_CACHE_WARM_DATABASE", "db_real_merged"),
        help="League database id (default: db_real_merged)",
    )
    args = parser.parse_args()

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")
    # Avoid racing the daemon thread started by create_app().
    os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

    from app import create_app
    from app.cache.cache_warmup import warm_essential_caches

    app = create_app()
    with app.app_context():
        warm_essential_caches(args.database.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
