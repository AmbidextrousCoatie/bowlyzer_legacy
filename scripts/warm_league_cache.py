#!/usr/bin/env python3
"""
Pre-compute persisted league JSON caches (same payloads as /league/* API).

Usage:
  uv run python scripts/warm_league_cache.py --database db_real_merged
  uv run python scripts/warm_league_cache.py --database db_real_merged --season "25/26" --league "Some League"
  uv run python scripts/warm_league_cache.py --database db_real_merged --rebuild
  uv run python scripts/warm_league_cache.py --database db_real_merged --rebuild --warm-clubs
  uv run python scripts/warm_league_cache.py --database db_real_merged --rebuild --warm-clubs --workers 8
  uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8 --benchmark
  uv run python scripts/warm_league_cache.py --database db_real_merged --benchmark-out .cache/league/bench.json
  uv run python scripts/warm_league_cache.py --database db_real_merged --warm-clubs --warm-clubs-file clubs.txt
  uv run python scripts/warm_league_cache.py --database db_real_merged --phase seasons --season "25/26" --sequential --no-progress
  uv run python scripts/warm_league_cache_shard.py --database db_real_merged --rebuild --warm-clubs
  uv run python scripts/rebuild_league_caches.py --database db_real_merged   # same as --rebuild + full grid

Environment:
  LEAGUE_CACHE_ENABLED=1 (default)   set to 0 to no-op
  LEAGUE_CACHE_DIR                   optional override for cache root
  LEAGUE_CACHE_REVISION              optional manual bump (invalidates revision namespace)
  LEAGUE_CACHE_GRANULAR_REVISION=1   per-season cache keys (default); old seasons stay valid when data grows
  LEAGUE_CACHE_GLOBAL_REVISION=1     revert to whole-file mtime invalidation (legacy layout)

Incremental updates: run WITHOUT --rebuild after merging new weeks — only changed seasons rebuild.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

Job = Tuple[str, Dict[str, str], Callable[[], Any]]
WarmResult = Tuple[str, str]
WeekCache = Dict[Tuple[str, str], List[int]]

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "league_analyzer_v1"
for _p in (LEGACY, ROOT):
    if _p.is_dir():
        sys.path.insert(0, str(_p))


_PRIMARY_WARM_LANG = None  # set on first use: Language.GERMAN


def _primary_warm_language():
    from app.services.i18n_service import Language

    global _PRIMARY_WARM_LANG
    if _PRIMARY_WARM_LANG is None:
        _PRIMARY_WARM_LANG = Language.GERMAN
    return _PRIMARY_WARM_LANG


def _warm_one_multilang(
    endpoint: str,
    database: str,
    query: Dict[str, str],
    build: Callable[[], Any],
    langs: List[Any],
    *,
    benchmark: Optional[Any] = None,
    phase: str = "",
    combo: str = "",
) -> List[Tuple[str, str]]:
    """
    Build payload once (primary language), write disk cache for each requested language.

    Secondary languages reuse the payload via catalog string / title_key localization.
    Returns one (lang, status) pair per language for progress accounting.
    """
    import time

    from app.cache.i18n_cache_localize import localize_payload_for_language
    from app.cache.league_response_cache import league_cache_put, league_cache_try_get
    from app.services.i18n_service import i18n_service

    primary = _primary_warm_language()
    out: List[Tuple[str, str]] = []
    pending: List[Any] = []

    for lang in langs:
        i18n_service.set_language(lang)
        t0 = time.perf_counter()
        cached = league_cache_try_get(endpoint, database, query)
        cache_io_ms = (time.perf_counter() - t0) * 1000.0
        if cached is not None:
            out.append((lang.value, "hit"))
            if benchmark is not None:
                benchmark.record(
                    endpoint=endpoint,
                    phase=phase,
                    combo=combo,
                    status="hit",
                    lang=lang.value,
                    cache_io_ms=cache_io_ms,
                )
        else:
            pending.append(lang)

    if not pending:
        return out

    payload = None
    build_ms = 0.0
    if primary in pending:
        i18n_service.set_language(primary)
        t0 = time.perf_counter()
        payload = build()
        build_ms = (time.perf_counter() - t0) * 1000.0
        if payload is None:
            for lang in pending:
                out.append((lang.value, "skip-empty"))
                if benchmark is not None:
                    benchmark.record(
                        endpoint=endpoint,
                        phase=phase,
                        combo=combo,
                        status="skip-empty",
                        lang=lang.value,
                        build_ms=build_ms,
                    )
            return out
    else:
        i18n_service.set_language(primary)
        payload = league_cache_try_get(endpoint, database, query)

    for lang in pending:
        if payload is None:
            out.append((lang.value, "skip-empty"))
            continue

        localize_ms = 0.0
        if lang == primary:
            to_store = payload
            status = "miss-built"
        else:
            t0 = time.perf_counter()
            to_store = localize_payload_for_language(payload, primary, lang)
            localize_ms = (time.perf_counter() - t0) * 1000.0
            status = "localized"

        i18n_service.set_language(lang)
        t0 = time.perf_counter()
        league_cache_put(endpoint, database, query, to_store)
        cache_io_ms = (time.perf_counter() - t0) * 1000.0
        out.append((lang.value, status))
        if benchmark is not None:
            benchmark.record(
                endpoint=endpoint,
                phase=phase,
                combo=combo,
                status=status,
                lang=lang.value,
                build_ms=build_ms if lang == primary else 0.0,
                localize_ms=localize_ms,
                cache_io_ms=cache_io_ms,
            )
        build_ms = 0.0

    return out


def _weeks_for_league(
    ls,
    season: str,
    league: str,
    week_cache: WeekCache,
) -> List[int]:
    key = (season, league)
    if key not in week_cache:
        try:
            week_cache[key] = list(ls.get_available_weeks(season=season, league=league))
        except Exception:
            week_cache[key] = []
    return week_cache[key]


def _season_league_jobs(
    ls,
    database: str,
    season: str,
    league: str,
    week_cache: WeekCache,
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

    weeks = _weeks_for_league(ls, season, league, week_cache)

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


def _assemble_season_league_standings(
    ls,
    database: str,
    season: str,
    division: Optional[str],
) -> Any:
    """
    Build get_season_league_standings payload from per-league week/honor caches when possible.

    Warmup already writes get_league_week_table + get_honor_scores for every week; the season
    overview only needs each league's latest week. Assembling from disk avoids recomputing
    get_league_week_table_simple + get_honor_scores for every league again.
    """
    from app.cache.league_response_cache import league_cache_try_get
    from app.utils.json_safe import json_safe
    from app.utils.league_utils import get_league_division_map, resolve_league_long_name

    dbq = {"database": database}
    leagues = ls.get_leagues(season=season)
    if not leagues:
        return json_safe({"leagues": [], "season": season})

    if division:
        division_map = get_league_division_map()
        leagues = [lg for lg in leagues if division_map.get(lg) == division]

    latest_week_by_league = ls._latest_week_by_league(season)
    league_standings: List[Dict[str, Any]] = []

    for league in leagues:
        latest_week = latest_week_by_league.get(league)
        if not latest_week:
            continue

        wk_s = str(latest_week)
        q_week = {**dbq, "season": season, "league": league, "week": wk_s}
        standings_dict = league_cache_try_get("get_league_week_table", database, q_week)
        honor_scores = league_cache_try_get("get_honor_scores", database, q_week)

        if standings_dict is None:
            td = ls.get_league_week_table_simple(season=season, league=league, week=latest_week)
            standings_dict = td.to_dict() if td else None
        if honor_scores is None:
            honor_scores = ls.get_honor_scores(
                league=league,
                season=season,
                week=latest_week,
                number_of_individual_scores=3,
                number_of_team_scores=3,
                number_of_individual_averages=3,
                number_of_team_averages=3,
            )

        if standings_dict:
            league_standings.append(
                {
                    "league": league,
                    "league_long": resolve_league_long_name(league),
                    "week": latest_week,
                    "standings": standings_dict,
                    "honor_scores": honor_scores,
                }
            )

    return json_safe({"leagues": league_standings, "season": season})


def _season_standings_jobs(
    ls,
    database: str,
    season: str,
    division: Optional[str],
) -> Tuple[str, Dict[str, str], Callable[[], Any]]:
    """
    Single get_season_league_standings job: division=None → all divisions in one payload;
    division set → query matches /league/get_season_league_standings?division=...

    Run after per-league week/honor jobs so assembly can read those cache files.
    """
    dbq = {"database": database}
    q: Dict[str, str] = {**dbq, "season": season}
    if division:
        q["division"] = division

    def _build(div: Optional[str] = division) -> Any:
        return _assemble_season_league_standings(ls, database, season, div)

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


def _build_club_matrix_payload(ls, selected_club: str = "", only_unnumbered: bool = False) -> Dict[str, Any]:
    """Same payload as GET /league/get_club_matrix (for cache warming)."""
    from app.utils.league_utils import get_league_long_name_map

    clubs = ls.get_available_clubs(only_with_unnumbered_team=only_unnumbered)
    club = (selected_club or "").strip()
    if club:
        club = ls.resolve_club_name(club, clubs)
    matrix: Dict[str, Any] = {"club": club, "seasons": [], "rows": []}
    if club:
        matrix = ls.get_club_team_season_matrix(club)
    return {
        "clubs": clubs,
        "selected_club": club,
        "only_unnumbered": only_unnumbered,
        "matrix": matrix,
        "league_long_names": get_league_long_name_map(),
    }


CLUB_MATRIX_SHARED_JOB_COUNT = 2  # team_get_teams + empty-club matrix dropdown


def collect_club_matrix_jobs(
    ls,
    database: str,
    clubs: List[str],
    *,
    quiet: bool = False,
    include_shared: bool = True,
) -> List[Tuple[str, Dict[str, str], Callable[[], Any]]]:
    """Club page: team list + clubs dropdown + one matrix per club."""
    from app.services.team_service import TeamService
    from app.utils.json_safe import json_safe

    dbq = {"database": database}
    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = []

    def _teams_payload() -> Any:
        ts = TeamService(database=database)
        return json_safe(ts.get_all_teams(league_name=None, season=None))

    if include_shared:
        jobs.append(("team_get_teams", dict(dbq), _teams_payload))
        jobs.append(
            (
                "get_club_matrix",
                dict(dbq),
                lambda: _build_club_matrix_payload(ls, "", only_unnumbered=False),
            )
        )
    for club in clubs:
        def _one_matrix(c: str = club) -> Any:
            return _build_club_matrix_payload(ls, c, only_unnumbered=False)

        jobs.append(("get_club_matrix", {**dbq, "club": club}, _one_matrix))
    return jobs


def _load_club_names_from_file(path: Path) -> List[str]:
    lines: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


WARM_PHASES = ("all", "seasons", "league-wide", "clubs")


def normalize_warm_phase(phase: str) -> str:
    value = (phase or "all").strip().lower()
    if value in WARM_PHASES:
        return value
    raise ValueError(f"invalid warm phase {phase!r}; expected one of {WARM_PHASES}")


def slice_club_names(
    clubs: List[str],
    *,
    offset: int = 0,
    limit: Optional[int] = None,
) -> List[str]:
    if offset < 0:
        raise ValueError("--clubs-offset must be >= 0")
    if limit is not None and limit < 0:
        raise ValueError("--clubs-limit must be >= 0")
    if offset > len(clubs):
        return []
    sliced = clubs[offset:]
    if limit is not None:
        sliced = sliced[:limit]
    return sliced


def club_shard_ranges(total: int, per_shard: int) -> List[Tuple[int, int]]:
    """Return (offset, limit) pairs covering [0, total)."""
    if per_shard < 1:
        raise ValueError("per_shard must be >= 1")
    if total <= 0:
        return []
    ranges: List[Tuple[int, int]] = []
    offset = 0
    while offset < total:
        ranges.append((offset, min(per_shard, total - offset)))
        offset += per_shard
    return ranges


def warm_catalog(
    ls,
    *,
    season: Optional[str] = None,
    league: Optional[str] = None,
) -> Dict[str, Any]:
    """Seasons, leagues, and clubs visible in the source (for shard orchestration)."""
    seasons = [season] if season else ls.get_seasons()
    if league:
        leagues = [league]
    else:
        leagues = sorted({lg for s in seasons for lg in ls.get_leagues(season=s)})
    clubs = ls.get_available_clubs()
    return {"seasons": seasons, "leagues": leagues, "clubs": clubs}


@dataclass(frozen=True)
class WarmShard:
    label: str
    argv: List[str]
    extra_argv: Tuple[str, ...] = ()


def build_warm_shards(
    catalog: Dict[str, Any],
    *,
    warm_clubs: bool,
    skip_seasons: bool,
    skip_meta: bool,
    skip_clubs: bool,
    meta_per_league: bool,
    clubs_per_shard: int,
    season_filter: Optional[str] = None,
    league_filter: Optional[str] = None,
) -> List[WarmShard]:
    """Process-shard plan for warm_league_cache_shard.py."""
    seasons: List[str] = list(catalog.get("seasons") or [])
    leagues: List[str] = list(catalog.get("leagues") or [])
    clubs: List[str] = list(catalog.get("clubs") or [])

    if season_filter:
        seasons = [s for s in seasons if s == season_filter]
    if league_filter:
        leagues = [lg for lg in leagues if lg == league_filter]

    shards: List[WarmShard] = []

    if not skip_seasons:
        for season in seasons:
            shards.append(
                WarmShard(
                    label=f"season:{season}",
                    argv=["--phase", "seasons", "--season", season],
                )
            )

    if not skip_meta:
        if meta_per_league:
            for league in leagues:
                shards.append(
                    WarmShard(
                        label=f"meta:{league}",
                        argv=["--phase", "league-wide", "--league", league],
                    )
                )
        else:
            shards.append(WarmShard(label="meta:all-leagues", argv=["--phase", "league-wide"]))

    if warm_clubs and not skip_clubs:
        ranges = club_shard_ranges(len(clubs), clubs_per_shard)
        if not ranges:
            shards.append(
                WarmShard(
                    label="clubs:0",
                    argv=[
                        "--phase",
                        "clubs",
                        "--warm-clubs",
                        "--clubs-offset",
                        "0",
                        "--clubs-limit",
                        "0",
                    ],
                )
            )
        for idx, (offset, limit) in enumerate(ranges):
            extra: Tuple[str, ...] = ()
            if offset > 0:
                extra = ("--skip-club-shared",)
            shards.append(
                WarmShard(
                    label=f"clubs:{idx + 1}/{len(ranges)}",
                    argv=[
                        "--phase",
                        "clubs",
                        "--warm-clubs",
                        "--clubs-offset",
                        str(offset),
                        "--clubs-limit",
                        str(limit),
                    ],
                    extra_argv=extra,
                )
            )

    return shards


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
    if query.get("club"):
        parts.append(f"club={query['club']}")
    return " | ".join(parts)


def collect_filter_dropdown_jobs(
    ls,
    database: str,
    seasons: List[str],
) -> List[Job]:
    """Liga filter APIs used on every page load (pre-warm for VPS read-only cache mount)."""
    from app.utils.league_utils import resolve_league_long_name

    dbq = {"database": database}
    jobs: List[Job] = []

    jobs.append(("get_available_seasons", dict(dbq), ls.get_seasons))

    for season in seasons:
        def _leagues(s: str = season) -> List[Dict[str, str]]:
            return [
                {
                    "short_name": league,
                    "long_name": resolve_league_long_name(league),
                    "value": league,
                }
                for league in ls.get_leagues(season=s)
            ]

        jobs.append(("get_available_leagues", {**dbq, "season": season}, _leagues))
    return jobs


def collect_jobs_for_season(
    ls,
    database: str,
    season: str,
    *,
    filter_league: Optional[str],
    standings_no_division_grid: bool,
    week_cache: WeekCache,
) -> List[Job]:
    """All cache jobs for one season (every league, then season standings assembled from week caches)."""
    jobs: List[Job] = []
    leagues = [filter_league] if filter_league else ls.get_leagues(season=season)
    for league in leagues:
        jobs.extend(_season_league_jobs(ls, database, season, league, week_cache))
    if standings_no_division_grid:
        jobs.append(_season_standings_jobs(ls, database, season, None))
    else:
        jobs.extend(_all_season_standings_jobs(ls, database, season))
    return jobs


def build_job_plan(
    ls0,
    database: str,
    seasons: List[str],
    all_leagues: List[str],
    *,
    filter_league: Optional[str],
    standings_no_division_grid: bool,
    warm_clubs: bool,
    club_names: List[str],
    phase: str = "all",
    include_club_shared: bool = True,
    quiet: bool = False,
) -> Tuple[Dict[str, List[Job]], Dict[str, List[Job]], List[Job]]:
    """
    Build all warm jobs once (main thread). Returns (season -> jobs, league -> jobs, club jobs).
    Prints progress while planning — this phase used to look hung with no bar movement.
    """
    phase = normalize_warm_phase(phase)
    week_cache: WeekCache = {}
    season_map: Dict[str, List[Job]] = {}
    if phase in ("all", "seasons"):
        n_seasons = len(seasons)
        for si, season in enumerate(seasons):
            if _SHUTDOWN.is_set():
                break
            _warm_log(f"Planning {si + 1}/{n_seasons}: season {season!r} …", quiet=quiet)
            season_map[season] = collect_jobs_for_season(
                ls0,
                database,
                season,
                filter_league=filter_league,
                standings_no_division_grid=standings_no_division_grid,
                week_cache=week_cache,
            )
            _warm_log(
                f"  season {season!r}: {len(season_map[season])} endpoint(s), "
                f"{len(week_cache)} league-week keys cached",
                quiet=quiet,
            )

    league_map: Dict[str, List[Job]] = {}
    if phase in ("all", "league-wide"):
        for li, league in enumerate(all_leagues):
            if _SHUTDOWN.is_set():
                break
            league_map[league] = _league_wide_jobs(ls0, database, league)
            if li == 0 or (li + 1) == len(all_leagues) or (li + 1) % max(1, len(all_leagues) // 5) == 0:
                _warm_log(f"  league-wide {li + 1}/{len(all_leagues)}: {league!r}", quiet=quiet)

    club_jobs: List[Job] = []
    if phase in ("all", "clubs") and warm_clubs and club_names and not _SHUTDOWN.is_set():
        _warm_log(f"Planning club matrix ({len(club_names)} clubs) …", quiet=quiet)
        club_jobs = collect_club_matrix_jobs(
            ls0,
            database,
            club_names,
            quiet=True,
            include_shared=include_club_shared,
        )

    return season_map, league_map, club_jobs


_print_lock = threading.Lock()
_SHUTDOWN = threading.Event()
_INTERRUPT_COUNT = 0


def _tqdm_write(msg: str) -> None:
    from tqdm import tqdm

    with _print_lock:
        tqdm.write(msg, file=sys.stdout)


def _warm_log(msg: str, *, quiet: bool) -> None:
    if not quiet:
        _tqdm_write(msg)


def _request_shutdown(reason: str = "interrupt", *, from_signal: bool = False) -> None:
    global _INTERRUPT_COUNT
    _SHUTDOWN.set()
    _INTERRUPT_COUNT += 1
    msg = (
        f"\n{reason}: stopping (pending tasks cancelled; "
        "in-flight work may finish briefly — Ctrl+C again to force quit)."
    )
    if from_signal:
        # Never take _print_lock from a signal handler (deadlock with tqdm/progress).
        print(msg, file=sys.stderr, flush=True)
    else:
        _tqdm_write(msg)
    if _INTERRUPT_COUNT >= 2:
        print(f"\n{reason}: force quit.", file=sys.stderr, flush=True)
        os._exit(130)


def _install_signal_handlers() -> None:
    def _handler(signum: int, _frame: Any) -> None:
        _request_shutdown("Interrupt", from_signal=True)

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handler)


class WarmProgress:
    """Thread-safe tqdm over endpoint cache operations."""

    def __init__(self, total: int, *, disable: bool, desc: str = "cache warm") -> None:
        from tqdm import tqdm

        self.total = total
        self.counts: Dict[str, int] = {"hit": 0, "built": 0, "skip": 0, "dry-run": 0, "error": 0}
        self._pbar = tqdm(
            total=total,
            desc=desc,
            unit="endpoint",
            disable=disable or total <= 0,
            dynamic_ncols=True,
            miniters=1,
            mininterval=0.3,
            file=sys.stdout,
        )

    def add_results(self, results: List[WarmResult], *, lang: str, verbose: bool) -> None:
        if not results:
            return
        from tqdm import tqdm

        with _print_lock:
            last_combo = ""
            last_status = ""
            for combo, status in results:
                bucket = status if status in self.counts else "built"
                if status in {"miss-built", "localized"}:
                    bucket = "built"
                self.counts[bucket] = self.counts.get(bucket, 0) + 1
                last_combo = combo
                last_status = status
                if verbose:
                    tqdm.write(f"  lang={lang} | {combo}  -> {status}", file=sys.stdout)
            self._pbar.update(len(results))
            short = last_combo if len(last_combo) <= 56 else ("…" + last_combo[-55:])
            self._pbar.set_postfix(
                lang=lang,
                hit=self.counts["hit"],
                built=self.counts["built"],
                skip=self.counts["skip"],
                last=f"{short} [{last_status}]",
                refresh=True,
            )

    def close(self) -> None:
        self._pbar.close()

    def summary_line(self) -> str:
        parts = [f"{k}={v}" for k, v in self.counts.items() if v]
        return ", ".join(parts) if parts else "no endpoints"


def _report_warm_results(
    progress: Optional[WarmProgress],
    results: List[WarmResult],
    *,
    lang: str,
    verbose: bool,
    start_idx: int,
    total: int,
) -> int:
    """Log or count results. When progress is active, workers already ticked per endpoint."""
    if progress is not None:
        return start_idx + len(results)
    idx = start_idx
    with _print_lock:
        for combo, status in results:
            idx += 1
            pct = (100.0 * idx / total) if total else 100.0
            print(f"[{idx}/{total}] ({pct:5.1f}%) lang={lang} | {combo}  -> {status}", flush=True)
    return idx


def _warm_one_job(
    database: str,
    endpoint: str,
    query: Dict[str, str],
    build: Callable[[], Any],
    *,
    label: str,
    langs: List[Any],
    dry_run: bool,
    progress: Optional["WarmProgress"],
    verbose: bool,
    benchmark: Optional[Any],
) -> List[WarmResult]:
    combo = f"{label} | {_job_combo_line(endpoint, query)}"
    if dry_run:
        out = [(f"{combo} | lang={lang.value}", "dry-run") for lang in langs]
        if progress is not None:
            for lang in langs:
                progress.add_results([(f"{combo} | lang={lang.value}", "dry-run")], lang=lang.value, verbose=verbose)
        return out

    lang_statuses = _warm_one_multilang(
        endpoint,
        database,
        query,
        build,
        langs,
        benchmark=benchmark,
        phase=label,
        combo=combo,
    )
    out: List[WarmResult] = []
    for lang_value, status in lang_statuses:
        row = f"{combo} | lang={lang_value}"
        out.append((row, status))
        if progress is not None:
            progress.add_results([(row, status)], lang=lang_value, verbose=verbose)
    return out


def _warm_job_list(
    database: str,
    jobs: List[Job],
    *,
    dry_run: bool,
    label: str,
    langs: List[Any],
    progress: Optional["WarmProgress"] = None,
    verbose: bool = False,
    benchmark: Optional[Any] = None,
    parallel_workers: int = 0,
    parallel_after: int = 0,
    quiet: bool = False,
) -> List[WarmResult]:
    out: List[WarmResult] = []
    if not jobs:
        return out

    head_n = min(max(0, parallel_after), len(jobs))
    head = jobs[:head_n]
    tail = jobs[head_n:]
    workers = parallel_workers if parallel_workers > 1 and tail and not dry_run else 0

    for endpoint, query, build in head:
        if _SHUTDOWN.is_set():
            break
        out.extend(
            _warm_one_job(
                database,
                endpoint,
                query,
                build,
                label=label,
                langs=langs,
                dry_run=dry_run,
                progress=progress,
                verbose=verbose,
                benchmark=benchmark,
            )
        )

    if not tail or _SHUTDOWN.is_set():
        return out

    if workers <= 1:
        for endpoint, query, build in tail:
            if _SHUTDOWN.is_set():
                break
            out.extend(
                _warm_one_job(
                    database,
                    endpoint,
                    query,
                    build,
                    label=label,
                    langs=langs,
                    dry_run=dry_run,
                    progress=progress,
                    verbose=verbose,
                    benchmark=benchmark,
                )
            )
        return out

    pool_workers = min(workers, len(tail))
    _warm_log(
        f"  {label}: parallel club matrices ({pool_workers} thread(s), {len(tail)} job(s)) …",
        quiet=quiet,
    )
    executor = ThreadPoolExecutor(max_workers=pool_workers)
    futures = []
    try:
        for endpoint, query, build in tail:
            if _SHUTDOWN.is_set():
                break
            futures.append(
                executor.submit(
                    _warm_one_job,
                    database,
                    endpoint,
                    query,
                    build,
                    label=label,
                    langs=langs,
                    dry_run=dry_run,
                    progress=progress,
                    verbose=verbose,
                    benchmark=benchmark,
                )
            )
        for fut in futures:
            if _SHUTDOWN.is_set():
                break
            try:
                out.extend(fut.result())
            except Exception as exc:
                _tqdm_write(f"  {label}: parallel job failed: {exc}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return out


def _warm_season_worker(
    app,
    database: str,
    season: str,
    langs: List[Any],
    jobs: List[Job],
    *,
    dry_run: bool,
    progress: Optional["WarmProgress"],
    verbose: bool,
    benchmark: Optional[Any],
    quiet: bool = False,
) -> List[WarmResult]:
    """One parallel task: run pre-planned jobs for a season."""
    from app.services.i18n_service import i18n_service

    with app.app_context():
        i18n_service.set_language(_primary_warm_language())
        _warm_log(f"  worker start: season {season!r} ({len(jobs)} endpoints)", quiet=quiet)
        return _warm_job_list(
            database,
            jobs,
            dry_run=dry_run,
            label=f"season={season}",
            langs=langs,
            progress=progress,
            verbose=verbose,
            benchmark=benchmark,
            quiet=quiet,
        )


def _warm_league_wide_worker(
    app,
    database: str,
    league: str,
    langs: List[Any],
    jobs: List[Job],
    *,
    dry_run: bool,
    progress: Optional["WarmProgress"],
    verbose: bool,
    benchmark: Optional[Any],
    quiet: bool = False,
) -> List[WarmResult]:
    from app.services.i18n_service import i18n_service

    with app.app_context():
        i18n_service.set_language(_primary_warm_language())
        return _warm_job_list(
            database,
            jobs,
            dry_run=dry_run,
            label=f"league={league}",
            langs=langs,
            progress=progress,
            verbose=verbose,
            benchmark=benchmark,
            quiet=quiet,
        )


def _warm_clubs_worker(
    app,
    database: str,
    langs: List[Any],
    jobs: List[Job],
    *,
    dry_run: bool,
    progress: Optional["WarmProgress"],
    verbose: bool,
    benchmark: Optional[Any],
    club_workers: int = 0,
    quiet: bool = False,
) -> List[WarmResult]:
    from app.services.i18n_service import i18n_service

    with app.app_context():
        i18n_service.set_language(_primary_warm_language())
        _warm_log(f"  worker start: clubs ({len(jobs)} endpoints)", quiet=quiet)
        parallel_workers = club_workers
        shared_n = CLUB_MATRIX_SHARED_JOB_COUNT if any(
            j[0] == "team_get_teams" for j in jobs[:CLUB_MATRIX_SHARED_JOB_COUNT]
        ) else 0
        parallel_after = shared_n if parallel_workers > 1 else 0
        return _warm_job_list(
            database,
            jobs,
            dry_run=dry_run,
            label="clubs",
            langs=langs,
            progress=progress,
            verbose=verbose,
            benchmark=benchmark,
            parallel_workers=parallel_workers,
            parallel_after=parallel_after,
            quiet=quiet,
        )


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
        help="Delete all cache files for this database (full rebuild). Omit for incremental warm "
        "(unchanged seasons hit disk cache when only recent data was appended).",
    )
    parser.add_argument(
        "--standings-no-division-grid",
        action="store_true",
        help="Only warm get_season_league_standings without division= (skip per-division variants)",
    )
    parser.add_argument(
        "--warm-clubs",
        action="store_true",
        help="Also warm /team/get_teams and /league/get_club_matrix (all clubs + club page payloads)",
    )
    parser.add_argument(
        "--warm-clubs-file",
        metavar="PATH",
        help="With --warm-clubs: warm only clubs listed in this file (one name per line); else all clubs in data",
    )
    parser.add_argument(
        "--phase",
        choices=WARM_PHASES,
        default="all",
        help="Warm only one slice: seasons (per-season grids), league-wide (meta charts), clubs, or all",
    )
    parser.add_argument(
        "--clubs-offset",
        type=int,
        default=0,
        help="With --phase clubs: skip this many clubs after sorting (for shard workers)",
    )
    parser.add_argument(
        "--clubs-limit",
        type=int,
        default=None,
        help="With --phase clubs: warm at most this many clubs (shard size)",
    )
    parser.add_argument(
        "--club-workers",
        type=int,
        default=0,
        help="With --phase clubs: thread pool for per-club matrices after shared jobs "
        "(limited by GIL; prefer smaller --clubs-per-shard in shard wrapper)",
    )
    parser.add_argument(
        "--skip-club-shared",
        action="store_true",
        help="With --phase clubs: skip team_get_teams and empty club dropdown (shard batches 2+)",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Print JSON catalog of seasons/leagues/clubs and exit (no cache writes)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List work only; do not write cache")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 4))),
        help="Parallel season/league/club workers (default: min(8, CPU count))",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Disable threading (single-threaded, old behaviour)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bar (prints one line per endpoint instead)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less logging (for shard workers); use without --no-progress for tqdm ETA in single-process warm",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log every endpoint while the progress bar runs",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Record per-endpoint build/localize/cache timings and print a summary at the end",
    )
    parser.add_argument(
        "--benchmark-out",
        metavar="PATH",
        help="Write benchmark records as JSON (implies --benchmark)",
    )
    args = parser.parse_args()
    if args.benchmark_out:
        args.benchmark = True
    if args.workers < 1:
        print("--workers must be >= 1", file=sys.stderr)
        return 1
    if args.club_workers < 0:
        print("--club-workers must be >= 0", file=sys.stderr)
        return 1
    try:
        phase = normalize_warm_phase(args.phase)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if phase == "clubs" and not args.warm_clubs:
        print("--phase clubs requires --warm-clubs", file=sys.stderr)
        return 1
    if (args.clubs_offset or args.clubs_limit is not None) and phase != "clubs":
        print("--clubs-offset/--clubs-limit require --phase clubs", file=sys.stderr)
        return 1

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
    _install_signal_handlers()
    exit_code = 0
    progress: Optional[WarmProgress] = None
    benchmark = None
    if args.benchmark:
        from app.cache.warm_benchmark import WarmBenchmark

        benchmark = WarmBenchmark(database=database)

    try:
        with app.app_context():
            import time

            from app.services.league_service import LeagueService

            quiet = args.quiet
            t_work = time.perf_counter()

            if args.rebuild and not args.dry_run:
                n = league_cache_invalidate_database(database)
                _warm_log(f"Rebuild: removed {n} cached file(s) under database={database!r}", quiet=quiet)

            _warm_log(
                "Loading league data once (this can take a while on large CSVs)…",
                quiet=quiet,
            )
            t_load = time.perf_counter()
            ls0 = LeagueService(database=database)
            if benchmark is not None:
                benchmark.data_load_ms = (time.perf_counter() - t_load) * 1000.0

            from app.cache.league_data_revision import ensure_revision_index, revision_index_summary

            t_rev = time.perf_counter()
            _warm_log(f"  [revision] {revision_index_summary(database)}", quiet=quiet)
            ensure_revision_index(database)
            if benchmark is not None:
                benchmark.revision_index_ms = (time.perf_counter() - t_rev) * 1000.0
            if args.catalog:
                import json

                catalog = warm_catalog(ls0, season=args.season, league=args.league)
                catalog["database"] = database
                print(json.dumps(catalog, ensure_ascii=False))
                return 0

            if phase in ("all", "seasons"):
                seasons = [args.season] if args.season else ls0.get_seasons()
            else:
                seasons = [args.season] if args.season else []

            if args.league:
                all_leagues = [args.league]
            elif phase in ("all", "league-wide"):
                scope_seasons = seasons if seasons else ls0.get_seasons()
                all_leagues = sorted({lg for s in scope_seasons for lg in ls0.get_leagues(season=s)})
            else:
                all_leagues = []

            _warm_log(
                f"Data ready: phase={phase!r}, {len(seasons)} season(s), "
                f"{len(all_leagues)} league(s) for aggregation.",
                quiet=quiet,
            )

            club_names: List[str] = []
            if args.warm_clubs and phase in ("all", "clubs"):
                if args.warm_clubs_file:
                    club_path = Path(args.warm_clubs_file).expanduser().resolve()
                    if not club_path.is_file():
                        print(f"warm-clubs-file not found: {club_path}", file=sys.stderr)
                        return 1
                    club_names = _load_club_names_from_file(club_path)
                else:
                    _warm_log("  [plan] listing clubs from data …", quiet=quiet)
                    club_names = ls0.get_available_clubs()
                club_names = slice_club_names(
                    club_names,
                    offset=args.clubs_offset,
                    limit=args.clubs_limit,
                )
                _warm_log(f"  [plan] club matrix jobs for {len(club_names)} club(s) …", quiet=quiet)

            _warm_log("Building job plan …", quiet=quiet)
            season_job_map, league_job_map, club_job_list = build_job_plan(
                ls0,
                database,
                seasons,
                all_leagues,
                filter_league=args.league,
                standings_no_division_grid=args.standings_no_division_grid,
                warm_clubs=args.warm_clubs and phase in ("all", "clubs"),
                club_names=club_names,
                phase=phase,
                include_club_shared=not args.skip_club_shared,
                quiet=quiet,
            )
            season_job_n = sum(len(v) for v in season_job_map.values())
            league_wide_job_n = sum(len(v) for v in league_job_map.values())
            club_job_n = len(club_job_list)
            jobs_per_lang = season_job_n + league_wide_job_n + club_job_n
            grand_total = jobs_per_lang * len(langs)
            workers = 1 if args.sequential else args.workers
            _warm_log(
                f"Plan: {jobs_per_lang} logical endpoint(s) → {grand_total} cache file(s) "
                f"({len(langs)} lang(s)) "
                f"(database={database!r}, seasons={len(seasons)}, leagues={len(all_leagues)}, "
                f"season_jobs={season_job_n}, league_wide={league_wide_job_n}, clubs={club_job_n})",
                quiet=quiet,
            )
            use_progress = not args.no_progress and grand_total > 0
            if use_progress:
                progress = WarmProgress(
                    grand_total,
                    disable=False,
                    desc=f"warm {database}",
                )
            else:
                _warm_log(
                    f"Warming caches ({workers} worker(s); one parallel task per season with all its leagues)…",
                    quiet=quiet,
                )

            lang_codes = ",".join(lang.value for lang in langs)
            _warm_log(
                f"--- languages={lang_codes} (compute once per endpoint, then localize) ---",
                quiet=quiet,
            )

            def _run_pool(tasks: List[Callable[[], List[WarmResult]]], phase: str) -> None:
                if not tasks or _SHUTDOWN.is_set():
                    return
                _warm_log(f"  {phase} ({len(tasks)} parallel task(s)) …", quiet=quiet)
                if workers == 1:
                    for fn in tasks:
                        if _SHUTDOWN.is_set():
                            break
                        fn()
                    return

                pool_workers = min(workers, len(tasks))
                executor = ThreadPoolExecutor(max_workers=pool_workers)
                futures = [executor.submit(fn) for fn in tasks]
                pending = set(futures)
                idle_waits = 0
                try:
                    while pending and not _SHUTDOWN.is_set():
                        done, pending = wait(
                            pending,
                            timeout=0.5,
                            return_when=FIRST_COMPLETED,
                        )
                        if not done:
                            if benchmark is not None:
                                benchmark.add_pool_idle(0.5)
                            idle_waits += 1
                            if idle_waits % 20 == 0:
                                _warm_log(
                                    f"  still waiting for {len(pending)} task(s) "
                                    f"({phase}) — workers busy (GIL / heavy endpoints)…",
                                    quiet=quiet,
                                )
                            continue
                        idle_waits = 0
                        for fut in done:
                            if _SHUTDOWN.is_set():
                                break
                            try:
                                fut.result()
                            except Exception as exc:
                                _warm_log(f"  worker failed: {exc}", quiet=quiet)
                finally:
                    for fut in futures:
                        fut.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)

            if phase in ("all", "seasons"):
                filter_jobs = collect_filter_dropdown_jobs(ls0, database, seasons)
                if filter_jobs and not args.dry_run:
                    _warm_log(
                        f"Warming liga filter dropdowns ({len(filter_jobs)} endpoint(s)) …",
                        quiet=quiet,
                    )
                    _warm_season_worker(
                        app,
                        database,
                        "filters",
                        langs,
                        filter_jobs,
                        dry_run=args.dry_run,
                        progress=progress,
                        verbose=args.verbose,
                        benchmark=benchmark,
                        quiet=quiet,
                    )

            if phase in ("all", "seasons"):
                season_tasks = [
                    lambda s=season, joblist=season_job_map[season]: _warm_season_worker(
                        app,
                        database,
                        s,
                        langs,
                        joblist,
                        dry_run=args.dry_run,
                        progress=progress,
                        verbose=args.verbose,
                        benchmark=benchmark,
                        quiet=quiet,
                    )
                    for season in seasons
                    if season in season_job_map
                ]
                _run_pool(season_tasks, f"seasons ({len(season_tasks)} tasks)")

            if phase in ("all", "league-wide"):
                league_tasks = [
                    lambda lg=league, joblist=league_job_map[league]: _warm_league_wide_worker(
                        app,
                        database,
                        lg,
                        langs,
                        joblist,
                        dry_run=args.dry_run,
                        progress=progress,
                        verbose=args.verbose,
                        benchmark=benchmark,
                        quiet=quiet,
                    )
                    for league in all_leagues
                    if league in league_job_map
                ]
                _run_pool(league_tasks, f"league-wide ({len(league_tasks)} tasks)")

            if phase in ("all", "clubs") and args.warm_clubs and club_job_list:
                _run_pool(
                    [
                        lambda: _warm_clubs_worker(
                            app,
                            database,
                            langs,
                            club_job_list,
                            dry_run=args.dry_run,
                            progress=progress,
                            verbose=args.verbose,
                            benchmark=benchmark,
                            club_workers=args.club_workers,
                            quiet=quiet,
                        )
                    ],
                    f"clubs (1 task, {len(club_names)} clubs)",
                )

            if _SHUTDOWN.is_set():
                exit_code = 130
            else:
                wall_s = time.perf_counter() - t_work
                summary = progress.summary_line() if progress else ""
                if args.dry_run:
                    _tqdm_write(
                        f"Dry-run finished: {grand_total} endpoint(s)."
                        + (f" ({summary})" if summary else "")
                    )
                elif quiet and not use_progress:
                    print(
                        f"warm ok phase={phase} endpoints={grand_total} {summary} wall={wall_s:.1f}s",
                        flush=True,
                    )
                else:
                    _tqdm_write(
                        f"Done. {grand_total} cache file(s). {summary} wall={wall_s:.1f}s".strip()
                    )
                    if not quiet:
                        _tqdm_write(f"Cache root: {league_cache_dir()}")
                if benchmark is not None:
                    benchmark.print_report()
                    if args.benchmark_out:
                        out_path = Path(args.benchmark_out).expanduser().resolve()
                        benchmark.write_json(out_path)
                        _tqdm_write(f"Benchmark JSON: {out_path}")
    except KeyboardInterrupt:
        _request_shutdown("KeyboardInterrupt")
        exit_code = 130
    finally:
        if progress is not None:
            progress.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
