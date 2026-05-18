import time
from pathlib import Path

from flask import Blueprint, jsonify, request

from app.cache.league_response_cache import league_cache_put, league_cache_try_get
from app.utils.tournament_benchmark import tournament_benchmark_enabled
from app.config.database_config import database_config
from app.services.tournament_service import TournamentService


bp = Blueprint("tournament", __name__)

# Removed from ``database_config``; old bookmarks still send these IDs.
_LEGACY_SYNTHETIC_TOURNAMENT_IDS = frozenset(
    {"db_tournament_geek_2026", "db_tournament_myth_2024_2026"}
)

_TOURNAMENT_DATABASE_IDS = frozenset(
    {
        *_LEGACY_SYNTHETIC_TOURNAMENT_IDS,
        "db_tournament_sbm_2026_gf",
        "db_tournament_nbm_2026_gf",
        "db_tournament_regions_2026_gf",
    }
)

# Real GF / club tournament CSVs only (never synthetic demo datasets).
# SBM/NBM are single-meet extracts — use only when the regional combined file is absent.
_REGIONAL_TOURNAMENT_SOURCE = "db_tournament_regions_2026_gf"
_SINGLE_MEET_TOURNAMENT_SOURCES = (
    "db_tournament_sbm_2026_gf",
    "db_tournament_nbm_2026_gf",
)


def _normalize_requested_tournament_database(requested: str | None) -> str | None:
    if not requested:
        return None
    if requested in _LEGACY_SYNTHETIC_TOURNAMENT_IDS:
        return _REGIONAL_TOURNAMENT_SOURCE
    if requested in _TOURNAMENT_DATABASE_IDS:
        return requested
    # Global league ?database= (e.g. db_real_merged from sidebar) must not apply here.
    return None


def _resolve_default_tournament_source() -> str:
    """
    Prefer the regional combined (+ manual) merge whenever that CSV exists.

    Previously we fell back to SBM/NBM when ``get_tournaments()`` on the regional
    source was empty (e.g. stub or load glitch). Those extracts only contain one event
    each, so the UI looked like there was a single tournament for the whole season.
    """
    try:
        cfg = database_config.get_source_config(_REGIONAL_TOURNAMENT_SOURCE)
        if cfg and cfg.file_path:
            p = Path(cfg.file_path)
            if p.is_file() and p.stat().st_size > 0:
                TournamentService(database=_REGIONAL_TOURNAMENT_SOURCE)
                return _REGIONAL_TOURNAMENT_SOURCE
    except Exception:
        pass

    for source_id in _SINGLE_MEET_TOURNAMENT_SOURCES:
        try:
            svc = TournamentService(database=source_id)
            if svc.get_tournaments():
                return source_id
        except Exception:
            continue
    return database_config.get_default_source()


def _resolved_tournament_database_id() -> str:
    requested_database = _normalize_requested_tournament_database(
        request.args.get("database")
    )
    if requested_database:
        return requested_database
    return _resolve_default_tournament_source()


def get_tournament_service() -> TournamentService:
    return TournamentService(database=_resolved_tournament_database_id())


def _tournament_json_cache_get(endpoint_key: str):
    return league_cache_try_get(
        endpoint_key,
        _resolved_tournament_database_id(),
        dict(request.args),
    )


def _tournament_json_cache_put(endpoint_key: str, payload) -> None:
    if payload is None:
        return
    league_cache_put(
        endpoint_key,
        _resolved_tournament_database_id(),
        dict(request.args),
        payload,
    )


@bp.route("/tournament/get_available_tournaments")
def get_available_tournaments():
    cached = _tournament_json_cache_get("get_available_tournaments")
    if cached is not None:
        return jsonify(cached)
    season = request.args.get("season")
    payload = get_tournament_service().get_tournaments(season=season)
    _tournament_json_cache_put("get_available_tournaments", payload)
    return jsonify(payload)


@bp.route("/tournament/get_available_seasons")
def get_available_seasons():
    cached = _tournament_json_cache_get("get_available_seasons")
    if cached is not None:
        return jsonify(cached)
    tournament = request.args.get("tournament")
    payload = get_tournament_service().get_seasons(tournament=tournament)
    _tournament_json_cache_put("get_available_seasons", payload)
    return jsonify(payload)


@bp.route("/tournament/get_available_rounds")
def get_available_rounds():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    cached = _tournament_json_cache_get("get_available_rounds")
    if cached is not None:
        return jsonify(cached)
    payload = get_tournament_service().get_rounds(season=season, tournament=tournament)
    _tournament_json_cache_put("get_available_rounds", payload)
    return jsonify(payload)


@bp.route("/tournament/get_available_players")
def get_available_players():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    cached = _tournament_json_cache_get("get_available_players")
    if cached is not None:
        return jsonify(cached)
    payload = get_tournament_service().get_players(
        season=season, tournament=tournament, round_number=round_number
    )
    _tournament_json_cache_put("get_available_players", payload)
    return jsonify(payload)


@bp.route("/tournament/get_summary_cards")
def get_summary_cards():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    top_n = request.args.get("n", default=5, type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_summary_cards(season=season, tournament=tournament, round_number=round_number, top_n=top_n))


@bp.route("/tournament/get_leaderboard")
def get_leaderboard():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_leaderboard_table(season=season, tournament=tournament, round_number=round_number).to_dict())


@bp.route("/tournament/get_round_results")
def get_round_results():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_round_results_table(season=season, tournament=tournament, round_number=round_number).to_dict())


@bp.route("/tournament/get_section")
def get_tournament_section():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    top_n = request.args.get("n", default=5, type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    wall_t0 = time.perf_counter() if tournament_benchmark_enabled() else None
    cached = _tournament_json_cache_get("get_tournament_section")
    if cached is not None:
        if wall_t0 is not None:
            print(
                f"tournament benchmark: get_section DISK CACHE HIT "
                f"({time.perf_counter() - wall_t0:.3f}s)",
                flush=True,
            )
        return jsonify(cached)
    service = get_tournament_service()
    payload = service.get_tournament_section(
        season=season,
        tournament=tournament,
        round_number=round_number,
        top_n=top_n,
    )
    _tournament_json_cache_put("get_tournament_section", payload)
    if wall_t0 is not None:
        print(
            f"tournament benchmark: get_section MISS (computed + cached to disk) "
            f"wall={time.perf_counter() - wall_t0:.3f}s",
            flush=True,
        )
    return jsonify(payload)


@bp.route("/tournament/get_player_section")
def get_player_section():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    player = request.args.get("player")
    if not season or not tournament or not player:
        return jsonify({"error": "season, tournament and player are required"}), 400
    cached = _tournament_json_cache_get("get_player_section")
    if cached is not None:
        return jsonify(cached)
    service = get_tournament_service()
    payload = service.get_player_section(season=season, tournament=tournament, player=player)
    _tournament_json_cache_put("get_player_section", payload)
    return jsonify(payload)
