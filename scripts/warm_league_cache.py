#!/usr/bin/env python3
"""
Pre-compute persisted league JSON caches (same payloads as /league/* API).

Usage:
  uv run python scripts/warm_league_cache.py --database db_real_merged
  uv run python scripts/warm_league_cache.py --database db_real_merged --season "25/26" --league "Some League"
  uv run python scripts/warm_league_cache.py --database db_real_merged --rebuild
  uv run python scripts/rebuild_league_caches.py --database db_real_merged   # same as --rebuild + full grid

Environment:
  LEAGUE_CACHE_ENABLED=1 (default)   set to 0 to no-op
  LEAGUE_CACHE_DIR                   optional override for cache root
  LEAGUE_CACHE_REVISION              optional manual bump (invalidates revision namespace)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "league_analyzer_v1"
for _p in (LEGACY, ROOT):
    if _p.is_dir():
        sys.path.insert(0, str(_p))


def _warm_one(
    endpoint: str,
    database: str,
    query: Dict[str, str],
    build: Callable[[], Any],
) -> str:
    from app.cache.league_response_cache import league_cache_put, league_cache_try_get

    if league_cache_try_get(endpoint, database, query) is not None:
        return "hit"
    payload = build()
    if payload is None:
        return "skip-empty"
    league_cache_put(endpoint, database, query, payload)
    return "miss-built"


def _season_league_jobs(
    ls,
    database: str,
    season: str,
    league: str,
) -> List[Tuple[str, Dict[str, str], Callable[[], Any]]]:
    dbq = {"database": database}
    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = []

    q_st = {**dbq, "league": league, "season": season}
    jobs.append(
        (
            "get_season_timetable",
            q_st,
            lambda: ls.get_season_timetable(league=league, season=season),
        )
    )
    jobs.append(
        (
            "get_league_history",
            {**dbq, "season": season, "league": league},
            lambda: ls.get_league_history_table_data(league_name=league, season=season).to_dict(),
        )
    )
    jobs.append(
        (
            "get_team_points",
            {**dbq, "season": season, "league": league},
            lambda: ls.get_team_points_simple(league_name=league, season=season),
        )
    )
    jobs.append(
        (
            "get_team_positions",
            {**dbq, "season": season, "league": league},
            lambda: ls.get_team_positions_simple(league_name=league, season=season),
        )
    )
    jobs.append(
        (
            "get_team_averages",
            {**dbq, "season": season, "league": league},
            lambda: ls.get_team_averages_simple(league_name=league, season=season),
        )
    )
    jobs.append(
        (
            "get_individual_averages",
            {**dbq, "league": league, "season": season},
            lambda: ls.get_individual_averages(league=league, season=season, week=None, team=None).to_dict(),
        )
    )
    jobs.append(
        (
            "get_team_vs_team_comparison",
            {**dbq, "league": league, "season": season},
            lambda: ls.get_team_vs_team_comparison_table(league, season, None).to_dict(),
        )
    )

    try:
        weeks = ls.get_available_weeks(season=season, league=league)
    except Exception:
        weeks = []

    for wk in weeks:
        wk_s = str(wk)

        def _week_table_builder(w: int = wk) -> Any:
            td = ls.get_league_week_table_simple(season=season, league=league, week=w)
            return td.to_dict() if td else None

        def _honor_builder(w: int = wk) -> Any:
            return ls.get_honor_scores(
                league=league,
                season=season,
                week=w,
                number_of_individual_scores=3,
                number_of_team_scores=3,
                number_of_individual_averages=3,
                number_of_team_averages=3,
            )

        jobs.append(
            (
                "get_league_week_table",
                {**dbq, "season": season, "league": league, "week": wk_s},
                _week_table_builder,
            )
        )
        jobs.append(
            (
                "get_honor_scores",
                {**dbq, "season": season, "league": league, "week": wk_s},
                _honor_builder,
            )
        )

    return jobs


def _league_wide_jobs(ls, database: str, league: str) -> List[Tuple[str, Dict[str, str], Callable[[], Any]]]:
    dbq = {"database": database}
    ql = {**dbq, "league": league}
    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = [
        (
            "get_league_averages_history",
            {**ql, "debug": "false"},
            lambda: ls.get_league_averages_history(league=league, debug=False),
        ),
        (
            "get_points_to_win_history",
            {**ql, "debug": "false"},
            lambda: ls.get_points_to_win_history(league=league, debug=False),
        ),
        (
            "get_top_team_performances",
            ql,
            lambda: ls.get_top_team_performances(league=league).to_dict(),
        ),
        (
            "get_top_individual_performances",
            ql,
            lambda: ls.get_top_individual_performances(league=league).to_dict(),
        ),
        (
            "get_record_games",
            ql,
            lambda: ls.get_record_games(league=league).to_dict(),
        ),
        (
            "get_record_individual_games",
            ql,
            lambda: ls.get_record_individual_games(league=league).to_dict(),
        ),
        (
            "get_record_team_games",
            ql,
            lambda: ls.get_record_team_games(league=league).to_dict(),
        ),
    ]
    return jobs


def division_codes_for_season(ls, season: str) -> List[str]:
    """Division codes that have at least one league with data in this season (state/south/north)."""
    from app.utils.league_utils import get_league_division_map

    leagues = ls.get_leagues(season=season)
    division_map = get_league_division_map()
    codes = {division_map[lg] for lg in leagues if division_map.get(lg)}
    return sorted(codes)


def _season_standings_jobs(
    ls,
    database: str,
    season: str,
    division: Optional[str],
) -> Tuple[str, Dict[str, str], Callable[[], Any]]:
    """
    Single get_season_league_standings job: division=None → all divisions in one payload;
    division set → query matches /league/get_season_league_standings?division=...
    """
    dbq = {"database": database}
    q: Dict[str, str] = {**dbq, "season": season}
    if division:
        q["division"] = division

    def _build(div: Optional[str] = division) -> Any:
        return ls.get_season_league_standings(season=season, division=div)

    return ("get_season_league_standings", q, _build)


def _all_season_standings_jobs(
    ls,
    database: str,
    season: str,
) -> List[Tuple[str, Dict[str, str], Callable[[], Any]]]:
    """All division variants for one season: no filter + each division code."""
    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = [
        _season_standings_jobs(ls, database, season, None)
    ]
    for code in division_codes_for_season(ls, season):
        jobs.append(_season_standings_jobs(ls, database, season, code))
    return jobs


def _job_combo_line(endpoint: str, query: Dict[str, str]) -> str:
    """Short human-readable description of this cache entry."""
    parts: List[str] = [endpoint]
    if query.get("season"):
        parts.append(f"season={query['season']}")
    if query.get("division"):
        parts.append(f"division={query['division']}")
    if query.get("league"):
        parts.append(f"league={query['league']}")
    if query.get("week"):
        parts.append(f"week={query['week']}")
    return " | ".join(parts)


def collect_warm_jobs(
    database: str,
    ls0,
    seasons: List[str],
    all_leagues: List[str],
    *,
    filter_league: Optional[str],
    standings_no_division_grid: bool,
) -> List[Tuple[str, Dict[str, str], Callable[[], Any]]]:
    """Single-language job list (same structural work repeated per i18n language).

    Uses the passed-in LeagueService only — never constructs a new one per league
    (that would reload the CSV each time and stall plan building for minutes).
    """
    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = []
    n_seasons = len(seasons)
    for si, season in enumerate(seasons):
        print(f"  [plan] season {si + 1}/{n_seasons}: {season!r} …", flush=True)
        leagues = [filter_league] if filter_league else ls0.get_leagues(season=season)
        if standings_no_division_grid:
            jobs.append(_season_standings_jobs(ls0, database, season, None))
        else:
            jobs.extend(_all_season_standings_jobs(ls0, database, season))
        n_lg = len(leagues)
        for li, league in enumerate(leagues):
            if li == 0 or (li + 1) == n_lg or (li + 1) % max(1, n_lg // 5) == 0:
                print(f"    [plan]   league {li + 1}/{n_lg} in {season!r} …", flush=True)
            jobs.extend(_season_league_jobs(ls0, database, season, league))
    print(f"  [plan] league-wide aggregation jobs for {len(all_leagues)} league(s) …", flush=True)
    for league in all_leagues:
        jobs.extend(_league_wide_jobs(ls0, database, league))
    print(f"  [plan] done: {len(jobs)} job(s) queued.", flush=True)
    return jobs


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Warm persisted league API caches.")
    parser.add_argument("--database", required=True, help="Source id, e.g. db_real_merged")
    parser.add_argument("--season", help="Limit to one season (else all seasons in source)")
    parser.add_argument("--league", help="Limit to one league (else all leagues per season)")
    parser.add_argument(
        "--languages",
        default="de,en",
        help="Comma-separated i18n languages to warm (default: de,en)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing cache files for this database id, then warm from scratch",
    )
    parser.add_argument(
        "--standings-no-division-grid",
        action="store_true",
        help="Only warm get_season_league_standings without division= (skip per-division variants)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List work only; do not write cache")
    args = parser.parse_args()

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")

    from app import create_app
    from app.cache.league_response_cache import (
        is_league_cache_enabled,
        league_cache_dir,
        league_cache_invalidate_database,
    )
    from app.services.i18n_service import Language, i18n_service

    if not is_league_cache_enabled():
        print("LEAGUE_CACHE_ENABLED is off; nothing to do.", flush=True)
        return 0

    langs: List[Language] = []
    for raw in args.languages.split(","):
        code = raw.strip().lower()
        if code == "de":
            langs.append(Language.GERMAN)
        elif code == "en":
            langs.append(Language.ENGLISH)
    if not langs:
        langs = [Language.GERMAN, Language.ENGLISH]

    app = create_app()
    database = args.database.strip()

    with app.app_context():
        from app.services.league_service import LeagueService

        if args.rebuild and not args.dry_run:
            n = league_cache_invalidate_database(database)
            print(f"Rebuild: removed {n} cached file(s) under database={database!r}", flush=True)

        print(
            "Loading league data once (this can take a while on large CSVs)…",
            flush=True,
        )
        ls0 = LeagueService(database=database)
        seasons = [args.season] if args.season else ls0.get_seasons()
        if args.league:
            all_leagues = [args.league]
        else:
            all_leagues = sorted({lg for s in seasons for lg in ls0.get_leagues(season=s)})
        print(
            f"Data ready: {len(seasons)} season(s), {len(all_leagues)} league(s) for aggregation.",
            flush=True,
        )

        print("Building job plan…", flush=True)
        plan = collect_warm_jobs(
            database,
            ls0,
            seasons,
            all_leagues,
            filter_league=args.league,
            standings_no_division_grid=args.standings_no_division_grid,
        )
        jobs_per_lang = len(plan)
        grand_total = jobs_per_lang * len(langs)
        print(
            f"Plan: {jobs_per_lang} job(s) × {len(langs)} language(s) = {grand_total} total "
            f"(database={database!r}, seasons={len(seasons)}, leagues={len(all_leagues)})",
            flush=True,
        )
        print("Warming caches (each line is one endpoint)…", flush=True)

        idx = 0
        for lang in langs:
            i18n_service.set_language(lang)
            print(f"--- language={lang.value} ({jobs_per_lang} jobs) ---", flush=True)
            for endpoint, query, build in plan:
                idx += 1
                combo = _job_combo_line(endpoint, query)
                pct = (100.0 * idx / grand_total) if grand_total else 100.0
                prefix = f"[{idx}/{grand_total}] ({pct:5.1f}%) lang={lang.value} | {combo}"
                if args.dry_run:
                    print(f"{prefix}  -> dry-run", flush=True)
                    continue
                status = _warm_one(endpoint, database, query, build)
                print(f"{prefix}  -> {status}", flush=True)

        if args.dry_run:
            print(f"Dry-run finished: {grand_total} operations.", flush=True)
        else:
            print(f"Done. Cache root: {league_cache_dir()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
