from collections.abc import Callable
from typing import Any

from flask import Blueprint, jsonify, request
from app.services.player_service import PlayerService
from app.cache.league_response_cache import league_cache_put, league_cache_try_get
from app.utils.json_safe import json_safe
from app.utils.league_player_sources import resolve_player_database_id
from app.utils.season_query import normalize_season_query_value

bp = Blueprint('player', __name__, url_prefix='/player')

def get_player_service():
    """Helper function to get PlayerService with database parameter"""
    return PlayerService(database=resolve_player_database_id(request.args.get("database")))


def _player_cache_database(player_service: PlayerService) -> str:
    return str(player_service.database or request.args.get("database") or "")


def _jsonify_player_cached(
    endpoint: str,
    cache_db: str,
    cache_args: dict[str, Any],
    compute: Callable[[], Any],
):
    """Return JSON; set X-League-Cache: HIT|MISS for debugging."""
    hit = league_cache_try_get(endpoint, cache_db, cache_args)
    if hit is not None:
        resp = jsonify(hit)
        resp.headers["X-League-Cache"] = "HIT"
        return resp
    payload = json_safe(compute())
    league_cache_put(endpoint, cache_db, cache_args, payload)
    resp = jsonify(payload)
    resp.headers["X-League-Cache"] = "MISS"
    return resp


@bp.route('/search')
def search_players():
    search_term = request.args.get('search', '')
    club = (request.args.get("club") or "").strip() or None
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = {"database": cache_db, "search": search_term or "", "club": club or ""}
    return _jsonify_player_cached(
        "player_search",
        cache_db,
        cache_args,
        lambda: player_service.search_players(search_term, club=club),
    )

@bp.route('/get_available_seasons')
def get_available_seasons():
    player_name = request.args.get('player_name')
    player_id = request.args.get('player_id', '')
    club = (request.args.get("club") or "").strip() or None
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = dict(request.args)
    cache_args["database"] = cache_db
    return _jsonify_player_cached(
        "player_get_available_seasons",
        cache_db,
        cache_args,
        lambda: player_service.get_player_seasons(
            player_name or '',
            player_id=player_id,
            club=club,
        ),
    )

@bp.route('/get-stats')
def get_stats():
    player_id = request.args.get('player_id')
    player_service = get_player_service()
    stats = player_service.get_personal_stats(player_id)
    return jsonify(stats)

@bp.route('/get_lifetime_stats')
def get_lifetime_stats():
   
    player_name = request.args.get('player_name')
    player_id = request.args.get('player_id', '')
    club = (request.args.get("club") or "").strip() or None
    season_raw = request.args.get('season', 'all')
    season = normalize_season_query_value(season_raw) if season_raw and str(season_raw).strip().lower() != 'all' else 'all'
    
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = dict(request.args)
    cache_args["database"] = cache_db

    def _compute():
        if not player_name and not player_id:
            return player_service.get_aggregate_lifetime_stats(season=season, club=club)
        return player_service.get_lifetime_stats(player_name or '', season=season, player_id=player_id)

    return _jsonify_player_cached("get_lifetime_stats", cache_db, cache_args, _compute)


@bp.route('/get_highest_individual_games')
def get_highest_individual_games():
    limit_raw = request.args.get('limit', '10')
    try:
        limit = max(1, min(100, int(limit_raw)))
    except (TypeError, ValueError):
        limit = 10

    player_name = request.args.get('player_name') or ''
    player_id = request.args.get('player_id', '')
    club = (request.args.get("club") or "").strip() or None
    season_raw = request.args.get('season', 'all')
    season = (
        normalize_season_query_value(season_raw)
        if season_raw and str(season_raw).strip().lower() != 'all'
        else 'all'
    )

    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = dict(request.args)
    cache_args["database"] = cache_db
    cache_args["limit"] = str(limit)

    return _jsonify_player_cached(
        "get_highest_individual_games",
        cache_db,
        cache_args,
        lambda: player_service.get_highest_individual_games(
            limit=limit,
            player_name=player_name,
            player_id=player_id,
            season=season,
            club=club,
        ),
    )


@bp.route('/get_club_300')
def get_club_300():
    club = (request.args.get("club") or "").strip() or None
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = {"database": cache_db, "club": club or ""}
    return _jsonify_player_cached(
        "get_club_300",
        cache_db,
        cache_args,
        lambda: player_service.get_club_300_games(club=club),
    )
