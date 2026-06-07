#!/usr/bin/env python3
"""
Warm persisted tournament API disk caches (Turnier page).

Targets ``db_tournament_regions_2026_gf`` (``tournaments_postprocessed.parquet`` on the VPS).

Usage:
  uv run python scripts/warm_tournament_cache.py
  uv run python scripts/warm_tournament_cache.py --rebuild
  uv run python scripts/warm_tournament_cache.py --database db_tournament_regions_2026_gf --dry-run

Environment: same as warm_league_cache.py (LEAGUE_CACHE_DIR, …).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_TOURNAMENT_DATABASE = "db_tournament_regions_2026_gf"


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


def warm_tournament_caches(
    database: str = DEFAULT_TOURNAMENT_DATABASE,
    *,
    rebuild: bool = False,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> Dict[str, int]:
    from app.cache.league_data_revision import ensure_revision_index, revision_index_summary
    from app.cache.league_response_cache import is_league_cache_enabled, league_cache_invalidate_database
    from app.services.i18n_service import Language, i18n_service
    from app.services.tournament_service import TournamentService
    from app.utils.json_safe import json_safe
    from data_access.shared_pandas_store import get_shared_pandas_adapter

    stats = {"built": 0, "hit": 0, "skip_empty": 0, "errors": 0, "jobs": 0}
    if not is_league_cache_enabled():
        log("Tournament cache warmup skipped: LEAGUE_CACHE_ENABLED is off.")
        return stats

    if rebuild and not dry_run:
        n = league_cache_invalidate_database(database)
        log(f"Rebuild: removed {n} cached file(s) under database={database!r}")

    log(f"Tournament cache warmup: loading {database!r} …")
    if not dry_run:
        get_shared_pandas_adapter(database)
        log(f"  [revision] {revision_index_summary(database)}")
        ensure_revision_index(database)

    service = TournamentService(database=database)
    seasons = service.get_seasons()
    log(f"Tournament cache warmup: {len(seasons)} season(s)")

    dbq = {"database": database}
    langs = (Language.GERMAN, Language.ENGLISH)

    def _tally(status: str) -> None:
        stats["jobs"] += 1
        if status == "built":
            stats["built"] += 1
        elif status == "hit":
            stats["hit"] += 1
        elif status == "skip-empty":
            stats["skip_empty"] += 1

    def _run_job(endpoint: str, query: Dict[str, str], build: Callable[[], Any], label: str) -> None:
        if dry_run:
            stats["jobs"] += 1
            log(f"  [dry-run] {label}")
            return
        for lang in langs:
            i18n_service.set_language(lang)
            try:
                status = _warm_one(endpoint, database, query, build)
                _tally(status)
                log(f"  [{lang.value}] {label} -> {status}")
            except Exception as exc:
                stats["errors"] += 1
                log(f"  [{lang.value}] {label} ERROR: {exc}")

    _run_job(
        "get_available_seasons",
        dict(dbq),
        lambda: json_safe(service.get_seasons()),
        "get_available_seasons",
    )

    for season in seasons:
        tour_query = {**dbq, "season": season}
        tournaments = service.get_tournaments(season=season)
        _run_job(
            "get_available_tournaments",
            tour_query,
            lambda s=season: json_safe(service.get_tournaments(season=s)),
            f"get_available_tournaments season={season!r}",
        )

        for tournament in tournaments:
            base = {**dbq, "season": season, "tournament": tournament}

            def _rounds_build(s: str = season, t: str = tournament) -> Any:
                return json_safe(service.get_rounds(s, t))

            _run_job(
                "get_available_rounds",
                dict(base),
                _rounds_build,
                f"get_available_rounds season={season!r} tournament={tournament!r}",
            )

            def _format_build(s: str = season, t: str = tournament) -> Any:
                return json_safe(service.get_tournament_format_info(s, t))

            _run_job(
                "get_tournament_format",
                dict(base),
                _format_build,
                f"get_tournament_format season={season!r} tournament={tournament!r}",
            )

            rounds = service.get_rounds(season, tournament)
            round_nums: List[str] = [""]
            for row in rounds:
                if not isinstance(row, dict):
                    continue
                rn = row.get("round_number")
                if rn is None or str(rn).strip() == "":
                    continue
                try:
                    round_nums.append(str(int(rn)))
                except (TypeError, ValueError):
                    round_nums.append(str(rn).strip())
            round_nums = list(dict.fromkeys(round_nums))

            for round_str in round_nums:
                q = dict(base)
                label_round = "all"
                if round_str:
                    q["round"] = round_str
                    label_round = round_str

                def _players_build(
                    s: str = season,
                    t: str = tournament,
                    r: str = round_str,
                ) -> Any:
                    rn = int(r) if r and str(r).isdigit() else None
                    return json_safe(service.get_players(s, t, round_number=rn))

                _run_job(
                    "get_available_players",
                    q,
                    _players_build,
                    f"get_available_players season={season!r} tournament={tournament!r} round={label_round!r}",
                )

                section_q = {**q, "n": "5"}

                def _section_build(
                    s: str = season,
                    t: str = tournament,
                    r: str = round_str,
                ) -> Any:
                    rn = int(r) if r and str(r).isdigit() else None
                    return json_safe(
                        service.get_tournament_section(s, t, round_number=rn, top_n=5)
                    )

                _run_job(
                    "get_tournament_section",
                    section_q,
                    _section_build,
                    f"get_tournament_section season={season!r} tournament={tournament!r} round={label_round!r}",
                )

    log(
        "Tournament cache warmup done: "
        f"jobs={stats['jobs']} built={stats['built']} hit={stats['hit']} "
        f"skip_empty={stats['skip_empty']} errors={stats['errors']}"
    )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default=DEFAULT_TOURNAMENT_DATABASE,
        help=f"Tournament source id (default: {DEFAULT_TOURNAMENT_DATABASE})",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete cached files for this database before warming",
    )
    parser.add_argument("--dry-run", action="store_true", help="List work only; no cache writes")
    args = parser.parse_args()

    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")
    os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")

    from app import create_app

    app = create_app()
    with app.app_context():
        stats = warm_tournament_caches(
            args.database.strip(),
            rebuild=args.rebuild,
            dry_run=args.dry_run,
        )
    return 1 if stats.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
