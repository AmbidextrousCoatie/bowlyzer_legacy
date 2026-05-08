from flask import Blueprint, jsonify, render_template, request

from app.config.database_config import database_config
from app.services.tournament_service import TournamentService


bp = Blueprint("tournament", __name__)


def _resolve_default_tournament_source() -> str:
    """
    Prefer the combined tournament dataset source.
    Falls back to any tournament-capable source, then global default.
    """
    preferred_source = "db_tournament_regions_2026_gf"
    try:
        preferred_service = TournamentService(database=preferred_source)
        if preferred_service.get_tournaments():
            return preferred_source
    except Exception:
        pass

    for source_id in [s for s in database_config.get_available_sources() if s.startswith("db_tournament_")]:
        try:
            svc = TournamentService(database=source_id)
            if svc.get_tournaments():
                return source_id
        except Exception:
            continue
    return database_config.get_default_source()


def get_tournament_service() -> TournamentService:
    requested_database = request.args.get("database")
    if requested_database:
        requested_service = TournamentService(database=requested_database)
        # If caller passes a DB without tournament rows, transparently fall back.
        if requested_service.get_tournaments():
            return requested_service
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
