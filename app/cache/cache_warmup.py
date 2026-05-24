"""
Warm the heaviest disk-backed API caches after data load.

Focused on Liga season overview (per-season standings) and Spieler player search catalog.
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
