from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from app.config.database_config import database_config
from app.services.tournament_service import TournamentService


bp = Blueprint("tournament", __name__)

# Removed from ``database_config``; old bookmarks still send these IDs.
_LEGACY_SYNTHETIC_TOURNAMENT_IDS = frozenset(
    {"db_tournament_geek_2026", "db_tournament_myth_2024_2026"}
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
        return "db_tournament_regions_2026_gf"
    return requested


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


def get_tournament_service() -> TournamentService:
    requested_database = _normalize_requested_tournament_database(
        request.args.get("database")
    )
    if requested_database:
        # Always honor an explicit source. League-only CSVs have no tournaments;
        # falling back here silently swapped users to synthetic/mythic data.
        return TournamentService(database=requested_database)
    return TournamentService(database=_resolve_default_tournament_source())


@bp.route("/tournament/stats")
def tournament_stats():
    return render_template("tournament/stats.html")


@bp.route("/tournament/get_available_tournaments")
def get_available_tournaments():
    season = request.args.get("season")
    service = get_tournament_service()
    return jsonify(service.get_tournaments(season=season))

@bp.route("/tournament/get_available_seasons")
def get_available_seasons():
    tournament = request.args.get("tournament")
    service = get_tournament_service()
    return jsonify(service.get_seasons(tournament=tournament))


@bp.route("/tournament/get_available_rounds")
def get_available_rounds():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_rounds(season=season, tournament=tournament))

@bp.route("/tournament/get_available_players")
def get_available_players():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    round_number = request.args.get("round", type=int)
    if not season or not tournament:
        return jsonify({"error": "season and tournament are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_players(season=season, tournament=tournament, round_number=round_number))


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
    service = get_tournament_service()
    return jsonify(
        service.get_tournament_section(
            season=season,
            tournament=tournament,
            round_number=round_number,
            top_n=top_n,
        )
    )


@bp.route("/tournament/get_player_section")
def get_player_section():
    season = request.args.get("season")
    tournament = request.args.get("tournament")
    player = request.args.get("player")
    if not season or not tournament or not player:
        return jsonify({"error": "season, tournament and player are required"}), 400
    service = get_tournament_service()
    return jsonify(service.get_player_section(season=season, tournament=tournament, player=player))
