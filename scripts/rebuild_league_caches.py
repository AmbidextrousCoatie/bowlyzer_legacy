#!/usr/bin/env python3
"""
Invalidate persisted league caches for a database, then warm everything.

For routine updates (new weeks in the current season only), prefer incremental warm
without --rebuild so unchanged seasons stay on disk cache:
  uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8

Published stack (league + scrape merge + tournaments):

  # 1) Build data (scrape included by default)
  uv run python scripts/build_published_dataset.py --write-csv

  # 2) Rebuild all API disk caches
  uv run python scripts/rebuild_league_caches.py --all-published --workers 8

See docs/DATA_PIPELINE.md for full scenarios.

- All seasons in the source
- For each season: get_season_league_standings without division= (all divisions)
  and one cached response per division code that has data that season
- All league-scoped endpoints per (season, league) and league-wide aggregation tables
- With --warm-clubs (default): team list + get_club_matrix for every club (club page)
- Global page jobs (with seasons phase): home_stats, get_club_rankings (club empty state), …
- With --warm-club-legends (default with --all-published): get_club_legends per club
  (separate warm phase from club matrix — expensive player aggregations)
- With --all-published: also player_search (db_player_merged_hybrid) + tournament caches

Usage:
  uv run python scripts/rebuild_league_caches.py --database db_real_merged
  uv run python scripts/rebuild_league_caches.py --all-published --workers 8
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

PUBLISHED_LEAGUE_DATABASE = "db_real_merged"
PUBLISHED_PLAYER_DATABASE = "db_player_merged_hybrid"
PUBLISHED_TOURNAMENT_DATABASE = "db_tournament_regions_2026_gf"


def _load_warm_module():
    warm_path = Path(__file__).resolve().parent / "warm_league_cache.py"
    spec = importlib.util.spec_from_file_location("warm_league_cache_run", warm_path)
    if spec is None or spec.loader is None:
        print("Could not load warm_league_cache.py", file=sys.stderr)
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_cache_shard_all_published(
    *,
    workers: int,
    dry_run: bool,
    skip_players: bool,
    skip_tournament: bool,
) -> int:
    import subprocess

    cmd = [
        "uv",
        "run",
        "python",
        str(Path(__file__).resolve().parent / "warm_cache_shard.py"),
        "--all-published",
        "--warm-all",
        "--rebuild",
        "--max-parallel",
        str(max(1, workers)),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if skip_players:
        cmd.append("--skip-players")
    if skip_tournament:
        cmd.append("--skip-tournament")
    proc = subprocess.run(cmd, cwd=ROOT)
    return int(proc.returncode)


def _run_league_rebuild(
    database: str,
    *,
    languages: str,
    dry_run: bool,
    warm_clubs: bool,
    warm_club_legends: bool,
    workers: int,
) -> int:
    mod = _load_warm_module()
    if mod is None:
        return 1

    argv_bak = sys.argv[:]
    try:
        sys.argv = [
            str(Path(__file__).resolve().parent / "warm_league_cache.py"),
            "--database",
            database.strip(),
            "--languages",
            languages,
            "--rebuild",
        ]
        if dry_run:
            sys.argv.append("--dry-run")
        if warm_clubs:
            sys.argv.append("--warm-clubs")
        if warm_club_legends:
            sys.argv.append("--warm-club-legends")
        if workers > 0:
            sys.argv.extend(["--workers", str(workers)])
        return int(mod.main())
    finally:
        sys.argv = argv_bak


def _run_player_rebuild(*, dry_run: bool) -> int:
    if dry_run:
        print(f"[dry-run] warm player_search for {PUBLISHED_PLAYER_DATABASE!r}")
        return 0

    import os

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")
    os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

    from app import create_app
    from app.cache.cache_warmup import warm_player_catalog_cache

    app = create_app()
    with app.app_context():
        stats = warm_player_catalog_cache(PUBLISHED_PLAYER_DATABASE, rebuild=True)
    return 1 if stats.get("errors") else 0


def _run_tournament_rebuild(*, dry_run: bool) -> int:
    import os

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")
    os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

    tour_path = Path(__file__).resolve().parent / "warm_tournament_cache.py"
    spec = importlib.util.spec_from_file_location("warm_tournament_cache_run", tour_path)
    if spec is None or spec.loader is None:
        print("Could not load warm_tournament_cache.py", file=sys.stderr)
        return 1
    tour_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = tour_mod
    spec.loader.exec_module(tour_mod)

    from app import create_app

    app = create_app()
    with app.app_context():
        stats = tour_mod.warm_tournament_caches(
            PUBLISHED_TOURNAMENT_DATABASE,
            rebuild=True,
            dry_run=dry_run,
        )
    return 1 if stats.get("errors") else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild league response caches (invalidate + full warm including season×division standings)."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="Single league source id, e.g. db_real_merged")
    target.add_argument(
        "--all-published",
        action="store_true",
        help=(
            "Warm full published stack: league (db_real_merged + clubs), "
            f"player ({PUBLISHED_PLAYER_DATABASE}), "
            f"tournament ({PUBLISHED_TOURNAMENT_DATABASE})"
        ),
    )
    parser.add_argument(
        "--languages",
        default="de,en",
        help="Comma-separated i18n languages to warm (default: de,en)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print jobs only; no delete, no write")
    parser.add_argument(
        "--no-warm-clubs",
        action="store_true",
        help="Skip club matrix + team_get_teams cache jobs (faster; smaller cache)",
    )
    parser.add_argument(
        "--no-warm-club-legends",
        action="store_true",
        help="Skip get_club_legends per club (player highlight aggregations)",
    )
    parser.add_argument(
        "--warm-club-legends",
        action="store_true",
        help="Warm get_club_legends per club (default with --all-published)",
    )
    parser.add_argument(
        "--skip-player",
        action="store_true",
        help="With --all-published: skip player_search warm",
    )
    parser.add_argument(
        "--skip-tournament",
        action="store_true",
        help="With --all-published: skip tournament warm",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Parallel season/league workers for league warm (0 = warm_league_cache default)",
    )
    args = parser.parse_args()

    warm_clubs = not args.no_warm_clubs
    warm_club_legends = args.warm_club_legends or (
        args.all_published and not args.no_warm_club_legends
    )

    if args.all_published:
        if args.workers > 0:
            print(
                f"=== published stack via warm_cache_shard.py (max_parallel={args.workers}) ==="
            )
            return _run_cache_shard_all_published(
                workers=args.workers,
                dry_run=args.dry_run,
                skip_players=args.skip_player,
                skip_tournament=args.skip_tournament,
            )

        print("=== published league cache (db_real_merged + clubs + club legends) ===")
        code = _run_league_rebuild(
            PUBLISHED_LEAGUE_DATABASE,
            languages=args.languages,
            dry_run=args.dry_run,
            warm_clubs=warm_clubs,
            warm_club_legends=warm_club_legends,
            workers=args.workers,
        )
        if code != 0:
            return code

        if not args.skip_player:
            print(f"=== player catalog cache ({PUBLISHED_PLAYER_DATABASE}) ===")
            code = _run_player_rebuild(dry_run=args.dry_run)
            if code != 0:
                return code

        if not args.skip_tournament:
            print(f"=== tournament cache ({PUBLISHED_TOURNAMENT_DATABASE}) ===")
            code = _run_tournament_rebuild(dry_run=args.dry_run)
            if code != 0:
                return code

        print("=== all published caches done ===")
        return 0

    return _run_league_rebuild(
        args.database.strip(),
        languages=args.languages,
        dry_run=args.dry_run,
        warm_clubs=warm_clubs,
        warm_club_legends=warm_club_legends,
        workers=args.workers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
