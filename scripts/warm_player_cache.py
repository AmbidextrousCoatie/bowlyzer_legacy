#!/usr/bin/env python3
"""
Pre-compute persisted player API disk caches (Spieler page).

Phases (for ``warm_cache_shard.py`` or manual runs):
  search          — ``player_search`` (empty query)
  seasons-list    — ``player_get_available_seasons`` (all players)
  lifetime-season — ``get_lifetime_stats`` all-players for one ``--season``
  lifetime-career — ``get_lifetime_stats`` ``season=all`` (live aggregate)
  highest-games   — ``get_highest_individual_games`` all-players ``season=all``
  highest-games-season — ``get_highest_individual_games`` all-players for one ``--season``
  player-highest-games — ``get_highest_individual_games`` for one ``--player-name`` / ``--player-id``
  player-highest-games-batch — same for ``--player-offset`` / ``--player-limit`` catalog slice
  club-300        — ``get_club_300`` (all perfect games, no club filter)
  club-300-batch  — ``get_club_300`` for ``--club-offset`` / ``--club-limit`` (games *for* each club)
  myclub-spieler  — club-filtered Spieler stack for one ``--club`` (search, seasons,
                    lifetime ``season=all``, highest games); games played *for* that club
                    only (Club / Team label), not full alumni careers
  myclub-spieler-batch — same for ``--club-offset`` / ``--club-limit`` over canonical clubs

Usage:
  uv run python scripts/warm_player_cache.py --database db_player_merged_hybrid
  uv run python scripts/warm_player_cache.py --database db_player_merged_hybrid --phase lifetime-season --season 25/26
  uv run python scripts/warm_player_cache.py --database db_player_merged_hybrid --phase lifetime-career
  uv run python scripts/warm_player_cache.py --database db_player_merged_hybrid --phase myclub-spieler --club "Donaubowler Regensburg"
  uv run python scripts/warm_player_cache.py --database db_player_merged_hybrid --catalog

Hit/miss: each job skips work when a valid on-disk cache entry exists (``league_cache_try_get``).
``--rebuild`` deletes all cache files for this database first — not required for incremental warm.

Environment: same as ``warm_league_cache.py`` (``LEAGUE_CACHE_ENABLED``, ``LEAGUE_CACHE_DIR``, …).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


@dataclass(frozen=True)
class PlayerWarmShard:
    label: str
    argv: Tuple[str, ...]


def _player_warm_slug(player: Dict[str, str]) -> str:
    pid = str(player.get("id") or "").strip()
    raw = pid or str(player.get("name") or "unknown").strip()
    slug = re.sub(r"[^\w.-]+", "_", raw).strip("_") or "player"
    return slug[:48]


# Per-player highest-games warm only career (``season=all``); season filters build on demand.
HIGHEST_GAMES_WARM_INCLUDE_PLAYER_SEASONS = False
PLAYERS_PER_HIGHEST_GAMES_WARM_SHARD = 50
# Club-filtered Spieler page (``?myClub=…``) — batch size for parallel shards.
CLUBS_PER_MYCLUB_SPIELER_SHARD = 8


def _club_batch_ranges(total: int, per_shard: int) -> List[Tuple[int, int]]:
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


def build_player_warm_shards(
    seasons: List[str],
    players: List[Dict[str, str]] | None = None,
    *,
    clubs: List[str] | None = None,
    clubs_file: str | None = None,
    skip_search: bool = False,
    skip_lifetime: bool = False,
    skip_myclub: bool = False,
    include_career_merge: bool = True,
    players_per_highest_shard: int = PLAYERS_PER_HIGHEST_GAMES_WARM_SHARD,
    clubs_per_myclub_shard: int = CLUBS_PER_MYCLUB_SPIELER_SHARD,
) -> List[PlayerWarmShard]:
    shards: List[PlayerWarmShard] = []
    if not skip_search:
        shards.append(PlayerWarmShard("player:search", ("--phase", "search")))
        shards.append(PlayerWarmShard("player:seasons", ("--phase", "seasons-list")))
    if not skip_lifetime:
        for season in seasons:
            shards.append(
                PlayerWarmShard(
                    f"player:lifetime:{season}",
                    ("--phase", "lifetime-season", "--season", season),
                )
            )
        if include_career_merge:
            shards.append(PlayerWarmShard("player:lifetime:all", ("--phase", "lifetime-career")))
        shards.append(PlayerWarmShard("player:highest-games", ("--phase", "highest-games")))
        for season in seasons:
            shards.append(
                PlayerWarmShard(
                    f"player:highest-games:{season}",
                    ("--phase", "highest-games-season", "--season", season),
                )
            )
        shards.append(PlayerWarmShard("player:club-300", ("--phase", "club-300")))
        player_list = [
            p
            for p in (players or [])
            if str(p.get("name") or "").strip()
        ]
        batch_size = max(1, int(players_per_highest_shard))
        total_batches = (len(player_list) + batch_size - 1) // batch_size if player_list else 0
        for batch_idx, offset in enumerate(range(0, len(player_list), batch_size)):
            limit = min(batch_size, len(player_list) - offset)
            label = (
                f"player:highest-games-batch:{batch_idx + 1}/{total_batches}"
                if total_batches > 1
                else "player:highest-games-batch:1/1"
            )
            shards.append(
                PlayerWarmShard(
                    label,
                    (
                        "--phase",
                        "player-highest-games-batch",
                        "--player-offset",
                        str(offset),
                        "--player-limit",
                        str(limit),
                    ),
                )
            )
    if not skip_myclub:
        club_list = [str(c).strip() for c in (clubs or []) if str(c).strip()]
        club_ranges = _club_batch_ranges(len(club_list), max(1, int(clubs_per_myclub_shard)))
        clubs_file_argv: Tuple[str, ...] = (
            ("--clubs-file", clubs_file) if clubs_file else ()
        )
        for batch_idx, (offset, limit) in enumerate(club_ranges):
            n = len(club_ranges)
            suffix = f"{batch_idx + 1}/{n}" if n > 1 else "1/1"
            batch_argv = (
                "--club-offset",
                str(offset),
                "--club-limit",
                str(limit),
            ) + clubs_file_argv
            shards.append(
                PlayerWarmShard(
                    f"player:club-300:{suffix}",
                    ("--phase", "club-300-batch") + batch_argv,
                )
            )
            shards.append(
                PlayerWarmShard(
                    f"player:myclub-spieler:{suffix}",
                    ("--phase", "myclub-spieler-batch") + batch_argv,
                )
            )
    return shards


def warm_player_search(player_service: Any, database: str, *, log: Callable[[str], None]) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database, "search": ""}
    try:
        status = _warm_one(
            "player_search",
            database,
            query,
            lambda: json_safe(player_service.get_all_players()),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  player_search -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  player_search ERROR: {exc}")
    return stats


def warm_player_seasons_list(player_service: Any, database: str, *, log: Callable[[str], None]) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database}
    try:
        status = _warm_one(
            "player_get_available_seasons",
            database,
            query,
            lambda: json_safe(player_service.get_all_seasons()),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  player_get_available_seasons (all players) -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  player_get_available_seasons ERROR: {exc}")
    return stats


def warm_player_lifetime_season(
    player_service: Any,
    database: str,
    season: str,
    *,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database, "season": season}
    try:
        status = _warm_one(
            "get_lifetime_stats",
            database,
            query,
            lambda s=season: json_safe(player_service.get_aggregate_lifetime_stats(season=s)),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  get_lifetime_stats all-players season={season!r} -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  get_lifetime_stats all-players season={season!r} ERROR: {exc}")
    return stats


def warm_player_lifetime_career(
    player_service: Any,
    database: str,
    seasons: List[str],
    *,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database, "season": "all"}

    def _build() -> Any:
        payload = player_service.get_aggregate_lifetime_stats(season="all")
        return json_safe(payload) if payload is not None else None

    try:
        status = _warm_one("get_lifetime_stats", database, query, _build)
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  get_lifetime_stats all-players season=all -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  get_lifetime_stats all-players season=all ERROR: {exc}")
    return stats


def warm_player_highest_games(
    player_service: Any,
    database: str,
    *,
    limit: int = 10,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database, "limit": str(limit), "season": "all"}
    try:
        status = _warm_one(
            "get_highest_individual_games",
            database,
            query,
            lambda: json_safe(player_service.get_highest_individual_games(limit=limit)),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  get_highest_individual_games all-players season=all limit={limit} -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  get_highest_individual_games all-players season=all ERROR: {exc}")
    return stats


def warm_player_highest_games_season(
    player_service: Any,
    database: str,
    season: str,
    *,
    limit: int = 10,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    query = {"database": database, "limit": str(limit), "season": season}
    try:
        status = _warm_one(
            "get_highest_individual_games",
            database,
            query,
            lambda s=season: json_safe(
                player_service.get_highest_individual_games(limit=limit, season=s)
            ),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(
            f"  get_highest_individual_games all-players season={season!r} "
            f"limit={limit} -> {status}"
        )
    except Exception as exc:
        stats["errors"] += 1
        log(
            f"  get_highest_individual_games all-players season={season!r} ERROR: {exc}"
        )
    return stats


def warm_player_highest_games_for_player(
    player_service: Any,
    database: str,
    player_name: str,
    player_id: str = "",
    *,
    limit: int = 10,
    include_player_seasons: bool = HIGHEST_GAMES_WARM_INCLUDE_PLAYER_SEASONS,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    pid = str(player_id or "").strip()
    seasons = ["all"]
    if include_player_seasons:
        seasons.extend(player_service.get_player_seasons(player_name, player_id=pid))
    seen: set[str] = set()
    for season in seasons:
        season_key = str(season).strip() or "all"
        if season_key in seen:
            continue
        seen.add(season_key)
        query = {
            "database": database,
            "limit": str(limit),
            "season": season_key,
            "player_name": player_name,
            "player_id": pid,
        }
        try:
            status = _warm_one(
                "get_highest_individual_games",
                database,
                query,
                lambda s=season_key: json_safe(
                    player_service.get_highest_individual_games(
                        limit=limit,
                        player_name=player_name,
                        player_id=pid,
                        season=s,
                    )
                ),
            )
            if status == "built":
                stats["built"] += 1
            elif status == "hit":
                stats["hit"] += 1
            else:
                stats["skip_empty"] += 1
            log(
                f"  get_highest_individual_games player={player_name!r} "
                f"season={season_key!r} -> {status}"
            )
        except Exception as exc:
            stats["errors"] += 1
            log(
                f"  get_highest_individual_games player={player_name!r} "
                f"season={season_key!r} ERROR: {exc}"
            )
    return stats


def warm_all_player_highest_games(
    player_service: Any,
    database: str,
    *,
    limit: int = 10,
    log: Callable[[str], None],
) -> Dict[str, int]:
    players = player_service.get_all_players()
    return warm_player_highest_games_batch(
        player_service,
        database,
        players,
        limit=limit,
        log=log,
    )


def warm_player_highest_games_batch(
    player_service: Any,
    database: str,
    players: List[Dict[str, str]],
    *,
    limit: int = 10,
    log: Callable[[str], None],
) -> Dict[str, int]:
    totals = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    for player in players:
        name = str(player.get("name") or "").strip()
        if not name:
            continue
        part = warm_player_highest_games_for_player(
            player_service,
            database,
            name,
            str(player.get("id") or "").strip(),
            limit=limit,
            log=log,
        )
        for key in totals:
            totals[key] += part.get(key, 0)
    return totals


def warm_player_club_300(
    player_service: Any,
    database: str,
    *,
    club: str | None = None,
    log: Callable[[str], None],
) -> Dict[str, int]:
    from app.utils.json_safe import json_safe

    club_name = str(club or "").strip()
    # Route always keys on ``club`` (empty string = unscoped).
    query = {"database": database, "club": club_name}
    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    label = f"club={club_name!r}" if club_name else "all"
    try:
        status = _warm_one(
            "get_club_300",
            database,
            query,
            lambda: json_safe(
                player_service.get_club_300_games(club=club_name or None)
            ),
        )
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        else:
            stats["skip_empty"] += 1
        log(f"  get_club_300 {label} -> {status}")
    except Exception as exc:
        stats["errors"] += 1
        log(f"  get_club_300 {label} ERROR: {exc}")
    return stats


def warm_player_club_300_batch(
    player_service: Any,
    database: str,
    clubs: List[str],
    *,
    log: Callable[[str], None],
) -> Dict[str, int]:
    totals = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    for club in clubs:
        part = warm_player_club_300(player_service, database, club=club, log=log)
        for key in totals:
            totals[key] += part.get(key, 0)
    return totals


def _merge_warm_stats(*parts: Dict[str, int]) -> Dict[str, int]:
    totals = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    for part in parts:
        for key in totals:
            totals[key] += part.get(key, 0)
    return totals


def warm_player_myclub_spieler(
    player_service: Any,
    database: str,
    club: str,
    *,
    limit: int = 10,
    log: Callable[[str], None],
) -> Dict[str, int]:
    """Warm caches for ``/spieler?myClub=…`` (club-filtered all-time stack)."""
    from app.utils.json_safe import json_safe

    club_name = str(club or "").strip()
    if not club_name:
        return {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}

    log(f"  myClub Spieler club={club_name!r}")
    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}

    jobs: List[Tuple[str, Dict[str, str], Callable[[], Any]]] = [
        (
            "player_search",
            {"database": database, "search": "", "club": club_name},
            lambda: json_safe(player_service.search_players("", club=club_name)),
        ),
        (
            "player_get_available_seasons",
            {"database": database, "club": club_name},
            lambda: json_safe(player_service.get_all_seasons(club=club_name)),
        ),
        (
            "get_lifetime_stats",
            {"database": database, "season": "all", "club": club_name},
            lambda: json_safe(
                player_service.get_aggregate_lifetime_stats(season="all", club=club_name)
            ),
        ),
        (
            "get_highest_individual_games",
            {
                "database": database,
                "limit": str(limit),
                "season": "all",
                "club": club_name,
            },
            lambda: json_safe(
                player_service.get_highest_individual_games(limit=limit, club=club_name)
            ),
        ),
    ]

    for endpoint, query, build in jobs:
        try:
            status = _warm_one(endpoint, database, query, build)
            if status == "built":
                stats["built"] += 1
            elif status == "hit":
                stats["hit"] += 1
            else:
                stats["skip_empty"] += 1
            log(f"    {endpoint} club={club_name!r} -> {status}")
        except Exception as exc:
            stats["errors"] += 1
            log(f"    {endpoint} club={club_name!r} ERROR: {exc}")
    return stats


def warm_player_myclub_spieler_batch(
    player_service: Any,
    database: str,
    clubs: List[str],
    *,
    log: Callable[[str], None],
) -> Dict[str, int]:
    totals = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0}
    for club in clubs:
        part = warm_player_myclub_spieler(player_service, database, club, log=log)
        for key in totals:
            totals[key] += part.get(key, 0)
    return totals


def _canonical_clubs(player_service: Any, clubs: List[str] | None = None) -> List[str]:
    if clubs is not None:
        return [str(c).strip() for c in clubs if str(c).strip()]
    from app.services.league_service import LeagueService

    return LeagueService(database=player_service.database).get_available_clubs()


def run_player_warm_phase(
    database: str,
    phase: str,
    *,
    season: str | None = None,
    seasons: List[str] | None = None,
    player_name: str | None = None,
    player_id: str | None = None,
    player_offset: int | None = None,
    player_limit: int | None = None,
    club: str | None = None,
    club_offset: int | None = None,
    club_limit: int | None = None,
    clubs: List[str] | None = None,
    log: Callable[[str], None] = print,
) -> Dict[str, int]:
    from app.services.player_service import PlayerService
    from data_access.shared_pandas_store import get_shared_pandas_adapter

    get_shared_pandas_adapter(database)
    player_service = PlayerService(database=database)
    season_list = seasons if seasons is not None else player_service.get_all_seasons()

    if phase == "search":
        return warm_player_search(player_service, database, log=log)
    if phase == "seasons-list":
        return warm_player_seasons_list(player_service, database, log=log)
    if phase == "lifetime-season":
        if not season:
            raise ValueError("--season is required for lifetime-season")
        return warm_player_lifetime_season(player_service, database, season, log=log)
    if phase == "lifetime-career":
        return warm_player_lifetime_career(player_service, database, season_list, log=log)
    if phase == "highest-games":
        return warm_player_highest_games(player_service, database, log=log)
    if phase == "highest-games-season":
        if not season:
            raise ValueError("--season is required for highest-games-season")
        return warm_player_highest_games_season(player_service, database, season, log=log)
    if phase == "player-highest-games":
        if not player_name:
            raise ValueError("--player-name is required for player-highest-games")
        return warm_player_highest_games_for_player(
            player_service,
            database,
            player_name,
            str(player_id or "").strip(),
            log=log,
        )
    if phase == "player-highest-games-batch":
        if player_offset is None or player_limit is None:
            raise ValueError("--player-offset and --player-limit are required for player-highest-games-batch")
        catalog = player_service.get_all_players()
        start = max(0, int(player_offset))
        end = start + max(0, int(player_limit))
        batch = catalog[start:end]
        return warm_player_highest_games_batch(player_service, database, batch, log=log)
    if phase == "club-300":
        return warm_player_club_300(player_service, database, log=log)
    if phase == "club-300-batch":
        if club_offset is None or club_limit is None:
            raise ValueError("--club-offset and --club-limit are required for club-300-batch")
        all_clubs = _canonical_clubs(player_service, clubs)
        start = max(0, int(club_offset))
        end = start + max(0, int(club_limit))
        return warm_player_club_300_batch(
            player_service,
            database,
            all_clubs[start:end],
            log=log,
        )
    if phase == "myclub-spieler":
        if not club or not str(club).strip():
            raise ValueError("--club is required for myclub-spieler")
        return warm_player_myclub_spieler(player_service, database, str(club).strip(), log=log)
    if phase == "myclub-spieler-batch":
        if club_offset is None or club_limit is None:
            raise ValueError("--club-offset and --club-limit are required for myclub-spieler-batch")
        all_clubs = _canonical_clubs(player_service, clubs)
        start = max(0, int(club_offset))
        end = start + max(0, int(club_limit))
        return warm_player_myclub_spieler_batch(
            player_service,
            database,
            all_clubs[start:end],
            log=log,
        )
    if phase == "essential":
        return _merge_warm_stats(
            warm_player_search(player_service, database, log=log),
            warm_player_seasons_list(player_service, database, log=log),
            *[
                warm_player_lifetime_season(player_service, database, s, log=log)
                for s in season_list
            ],
            warm_player_lifetime_career(player_service, database, season_list, log=log),
            warm_player_highest_games(player_service, database, log=log),
            *[
                warm_player_highest_games_season(player_service, database, s, log=log)
                for s in season_list
            ],
            warm_all_player_highest_games(player_service, database, log=log),
            warm_player_club_300(player_service, database, log=log),
        )
    raise ValueError(f"Unknown phase: {phase!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Player source id, e.g. db_player_merged_hybrid")
    parser.add_argument(
        "--phase",
        choices=(
            "search",
            "seasons-list",
            "lifetime-season",
            "lifetime-career",
            "highest-games",
            "highest-games-season",
            "player-highest-games",
            "player-highest-games-batch",
            "club-300",
            "club-300-batch",
            "myclub-spieler",
            "myclub-spieler-batch",
            "essential",
        ),
        default="essential",
        help="Warm scope (default: essential = full all-players stack)",
    )
    parser.add_argument(
        "--season",
        help="Required for --phase lifetime-season or highest-games-season",
    )
    parser.add_argument("--player-name", help="Required for --phase player-highest-games")
    parser.add_argument("--player-id", default="", help="Optional for --phase player-highest-games")
    parser.add_argument(
        "--player-offset",
        type=int,
        help="Required for --phase player-highest-games-batch (catalog slice start)",
    )
    parser.add_argument(
        "--player-limit",
        type=int,
        help="Required for --phase player-highest-games-batch (catalog slice length)",
    )
    parser.add_argument("--club", help="Required for --phase myclub-spieler")
    parser.add_argument(
        "--club-offset",
        type=int,
        help="Required for --phase myclub-spieler-batch / club-300-batch (slice start)",
    )
    parser.add_argument(
        "--club-limit",
        type=int,
        help="Required for --phase myclub-spieler-batch / club-300-batch (slice length)",
    )
    parser.add_argument(
        "--clubs-file",
        help="Optional newline-separated club names (same order as shard planner); "
        "defaults to LeagueService clubs for this database",
    )
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="Print JSON catalog {seasons, players, clubs} on stdout and exit",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Invalidate disk cache for this database before warming",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print phase only; no cache writes")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-job log lines")
    args = parser.parse_args()

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")
    os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

    database = args.database.strip()
    log: Callable[[str], None] = (lambda _msg: None) if args.quiet else print

    from app import create_app

    app = create_app()
    with app.app_context():
        from app.services.player_service import PlayerService

        if args.catalog:
            from app.services.league_service import LeagueService

            player_service = PlayerService(database=database)
            print(
                json.dumps(
                    {
                        "seasons": player_service.get_all_seasons(),
                        "players": player_service.get_all_players(),
                        "clubs": LeagueService(database=database).get_available_clubs(),
                    }
                )
            )
            return 0

        if args.dry_run:
            print(
                f"[dry-run] warm_player_cache database={database!r} phase={args.phase!r} "
                f"season={args.season!r} player_name={args.player_name!r} club={args.club!r}"
            )
            return 0

        if args.rebuild:
            from app.cache.league_response_cache import league_cache_invalidate_database

            removed = league_cache_invalidate_database(database)
            log(f"Rebuild: removed {removed} cached file(s) for {database!r}")

        clubs_from_file: List[str] | None = None
        if args.clubs_file:
            club_path = Path(args.clubs_file).expanduser().resolve()
            if not club_path.is_file():
                print(f"clubs-file not found: {club_path}", file=sys.stderr)
                return 1
            clubs_from_file = [
                line.strip()
                for line in club_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        stats = run_player_warm_phase(
            database,
            args.phase,
            season=args.season,
            player_name=args.player_name,
            player_id=args.player_id,
            player_offset=args.player_offset,
            player_limit=args.player_limit,
            club=args.club,
            club_offset=args.club_offset,
            club_limit=args.club_limit,
            clubs=clubs_from_file,
            log=log,
        )
    return 1 if stats.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
