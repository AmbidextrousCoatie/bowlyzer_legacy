"""
Warm the heaviest disk-backed API caches after data load.

Focused on Liga season overview (per-season standings), Spieler player search catalog,
and all-players lifetime stats (per season + merged career).
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional

from app.config.database_config import database_config
from app.services.i18n_service import Language, i18n_service
from app.utils.json_safe import json_safe
from app.utils.league_player_sources import resolve_player_database_id

_WARMUP_LOCK = threading.Lock()
_WARMUP_STARTED = False


def is_warmup_on_start_enabled() -> bool:
    return os.environ.get("LEAGUE_CACHE_WARM_ON_START", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def warmup_database_id() -> str:
    return (
        os.environ.get("LEAGUE_CACHE_WARM_DATABASE", "").strip()
        or database_config.get_default_source()
    )


def max_seasons_for_warmup() -> Optional[int]:
    raw = os.environ.get("LEAGUE_CACHE_WARM_MAX_SEASONS", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def seasons_for_warmup(seasons: List[str]) -> List[str]:
    limit = max_seasons_for_warmup()
    if not limit or len(seasons) <= limit:
        return list(seasons)
    return sorted(seasons)[-limit:]


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
    return "built"


def warm_all_players_lifetime_caches(
    player_database: str,
    seasons: List[str],
    player_service: Any,
    *,
    log: Callable[[str], None] = print,
    tally: Callable[[str], None] | None = None,
) -> Dict[str, int]:
    """
    Warm ``get_lifetime_stats`` for all-players scope: each season, then ``season=all``.

    The career entry is assembled from per-season cache files when possible so a data
    update in only the latest season can be refreshed incrementally.
    """
    from app.cache.league_response_cache import league_cache_try_get
    from app.services.player_service import PlayerService

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}

    def _tally(status: str) -> None:
        if tally is not None:
            tally(status)
            return
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        elif status == "skip-empty":
            stats["skip_empty"] += 1

    dbq = {"database": player_database}

    status = _warm_one(
        "player_get_available_seasons",
        player_database,
        dict(dbq),
        lambda: player_service.get_all_seasons(),
    )
    _tally(status)
    log(f"  player_get_available_seasons (all players) -> {status}")

    for season in seasons:
        query = {**dbq, "season": season}

        def _build_season(s: str = season) -> Any:
            payload = player_service.get_aggregate_lifetime_stats(season=s)
            return json_safe(payload) if payload is not None else None

        try:
            status = _warm_one("get_lifetime_stats", player_database, query, _build_season)
            _tally(status)
            log(f"  get_lifetime_stats all-players season={season!r} -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"  get_lifetime_stats all-players season={season!r} ERROR: {exc}")

    query_all = {**dbq, "season": "all"}

    def _build_all() -> Any:
        parts = []
        for season in seasons:
            hit = league_cache_try_get(
                "get_lifetime_stats",
                player_database,
                {**dbq, "season": season},
            )
            if hit is None:
                payload = player_service.get_aggregate_lifetime_stats(season="all")
                return json_safe(payload) if payload is not None else None
            parts.append(hit)
        merged = PlayerService.merge_aggregate_lifetime_payloads(parts)
        return json_safe(merged) if merged is not None else None

    try:
        status = _warm_one("get_lifetime_stats", player_database, query_all, _build_all)
        _tally(status)
        log(f"  get_lifetime_stats all-players season=all -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  get_lifetime_stats all-players season=all ERROR: {exc}")

    return stats


def warm_player_catalog_cache(
    player_database: str = "db_player_merged_hybrid",
    *,
    rebuild: bool = False,
    log: Callable[[str], None] = print,
) -> Dict[str, int]:
    """
    Pre-build ``player_search`` (empty query) for Spieler dropdown.

    Uses ``db_player_merged_hybrid`` by default — the backing id for ``?database=db_real_merged``.
    """
    from app.cache.league_response_cache import (
        is_league_cache_enabled,
        league_cache_invalidate_database,
    )
    from app.services.player_service import PlayerService
    from data_access.shared_pandas_store import get_shared_pandas_adapter

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    if not is_league_cache_enabled():
        log("Player cache warmup skipped: LEAGUE_CACHE_ENABLED is off.")
        return stats

    if rebuild:
        n = league_cache_invalidate_database(player_database)
        log(f"Rebuild: removed {n} cached file(s) under database={player_database!r}")

    log(f"Player cache warmup: loading {player_database!r} …")
    get_shared_pandas_adapter(player_database)
    player_service = PlayerService(database=player_database)
    player_query = {"database": player_database, "search": ""}

    for lang in (Language.GERMAN, Language.ENGLISH):
        i18n_service.set_language(lang)
        try:
            status = _warm_one(
                "player_search",
                player_database,
                player_query,
                lambda: json_safe(player_service.get_all_players()),
            )
            if status == "built":
                stats["built"] += 1
            elif status == "hit":
                stats["hit"] += 1
            elif status == "skip-empty":
                stats["skip_empty"] += 1
            log(f"  [{lang.value}] player_search -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"  [{lang.value}] player_search ERROR: {exc}")

    lifetime_seasons = seasons_for_warmup(player_service.get_all_seasons())
    log(f"Player cache warmup: {len(lifetime_seasons)} season(s) for all-players lifetime stats.")
    lt_stats = warm_all_players_lifetime_caches(
        player_database,
        lifetime_seasons,
        player_service,
        log=log,
    )
    for key in ("built", "hit", "skip_empty", "errors"):
        stats[key] += lt_stats.get(key, 0)

    for endpoint, query, build in (
        (
            "get_highest_individual_games",
            {"database": player_database, "limit": "10"},
            lambda: json_safe(player_service.get_highest_individual_games(limit=10)),
        ),
        (
            "get_club_300",
            {"database": player_database},
            lambda: json_safe(player_service.get_club_300_games()),
        ),
    ):
        try:
            status = _warm_one(endpoint, player_database, query, build)
            if status == "built":
                stats["built"] += 1
            elif status == "hit":
                stats["hit"] += 1
            elif status == "skip-empty":
                stats["skip_empty"] += 1
            log(f"  {endpoint} -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"  {endpoint} ERROR: {exc}")

    return stats


def warm_essential_caches(
    league_database: str,
    *,
    log: Callable[[str], None] = print,
) -> Dict[str, int]:
    """
    Pre-build disk cache entries for slow endpoints.

    Returns counts: built, hit, skip_empty, errors.
    """
    from app.cache.league_response_cache import is_league_cache_enabled
    from app.services.league_service import LeagueService
    from app.services.player_service import PlayerService
    from app.services.team_service import TeamService
    from data_access.shared_pandas_store import get_shared_pandas_adapter

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    if not is_league_cache_enabled():
        log("Cache warmup skipped: LEAGUE_CACHE_ENABLED is off.")
        return stats

    player_database = resolve_player_database_id(league_database)
    langs = [Language.GERMAN, Language.ENGLISH]

    log(f"Cache warmup: loading data ({league_database=!r}, player={player_database!r}) …")
    get_shared_pandas_adapter(league_database)
    if player_database != league_database:
        get_shared_pandas_adapter(player_database)

    league_service = LeagueService(database=league_database)
    player_service = PlayerService(database=player_database)

    seasons = seasons_for_warmup(league_service.get_seasons())
    log(f"Cache warmup: {len(seasons)} season(s) for standings.")

    def _tally(status: str) -> None:
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        elif status == "skip-empty":
            stats["skip_empty"] += 1

    dbq = {"database": league_database}

    for lang in langs:
        i18n_service.set_language(lang)

        status = _warm_one(
            "get_available_seasons",
            league_database,
            dict(dbq),
            lambda: league_service.get_seasons(),
        )
        _tally(status)
        log(f"  [{lang.value}] get_available_seasons -> {status}")

        status = _warm_one(
            "team_get_teams",
            league_database,
            dict(dbq),
            lambda: TeamService(database=league_database).get_all_teams(),
        )
        _tally(status)
        log(f"  [{lang.value}] team_get_teams -> {status}")

        for season in seasons:
            query = {**dbq, "season": season}

            def _standings_build(s: str = season) -> Any:
                return league_service.get_season_league_standings(season=s, division=None)

            status = _warm_one("get_season_league_standings", league_database, query, _standings_build)
            _tally(status)
            log(f"  [{lang.value}] get_season_league_standings season={season!r} -> {status}")

    for lang in langs:
        i18n_service.set_language(lang)
        player_query = {"database": player_database, "search": ""}
        try:
            status = _warm_one(
                "player_search",
                player_database,
                player_query,
                lambda: json_safe(player_service.get_all_players()),
            )
            _tally(status)
            log(f"  [{lang.value}] player_search (catalog) -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"  [{lang.value}] player_search ERROR: {exc}")

    lifetime_seasons = seasons_for_warmup(player_service.get_all_seasons())
    log(f"Cache warmup: {len(lifetime_seasons)} season(s) for all-players lifetime stats.")
    lt_stats = warm_all_players_lifetime_caches(
        player_database,
        lifetime_seasons,
        player_service,
        log=log,
        tally=_tally,
    )
    stats["errors"] += lt_stats.get("errors", 0)

    for endpoint, query, build in (
        (
            "get_highest_individual_games",
            {"database": player_database, "limit": "10"},
            lambda: json_safe(player_service.get_highest_individual_games(limit=10)),
        ),
        (
            "get_club_300",
            {"database": player_database},
            lambda: json_safe(player_service.get_club_300_games()),
        ),
    ):
        try:
            status = _warm_one(endpoint, player_database, query, build)
            _tally(status)
            log(f"  {endpoint} -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"  {endpoint} ERROR: {exc}")

    log(
        "Cache warmup done: "
        f"built={stats['built']} hit={stats['hit']} "
        f"skip_empty={stats['skip_empty']} errors={stats['errors']}"
    )
    return stats


def start_cache_warmup_background(app, league_database: str | None = None) -> bool:
    """Start daemon thread once per process (no-op if disabled or already started)."""
    global _WARMUP_STARTED
    if not is_warmup_on_start_enabled():
        return False
    with _WARMUP_LOCK:
        if _WARMUP_STARTED:
            return False
        _WARMUP_STARTED = True

    database = league_database or warmup_database_id()

    def _run() -> None:
        with app.app_context():
            try:
                warm_essential_caches(database)
            except Exception as exc:
                print(f"Cache warmup failed: {exc}", flush=True)

    thread = threading.Thread(target=_run, name="bowlyzer-cache-warmup", daemon=True)
    thread.start()
    print(f"Cache warmup started in background for database={database!r}", flush=True)
    return True
