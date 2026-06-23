from flask import Blueprint, jsonify, request
from app.services.player_service import PlayerService
from app.config.database_config import database_config
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


def _aggregate_lifetime_from_season_caches(
    player_service: PlayerService,
    cache_db: str,
    seasons: list[str],
):
    """Assemble career-wide all-players stats from per-season disk cache entries."""
    from app.cache.league_response_cache import league_cache_try_get

    parts = []
    for season in seasons:
        cache_args = {"database": cache_db, "season": season}
        hit = league_cache_try_get("get_lifetime_stats", cache_db, cache_args)
        if hit is None:
            return None
        parts.append(hit)
    return PlayerService.merge_aggregate_lifetime_payloads(parts)


@bp.route('/search')
def search_players():
    search_term = request.args.get('search', '')
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = {"database": cache_db, "search": search_term or ""}
    hit = league_cache_try_get("player_search", cache_db, cache_args)
    if hit is not None:
        return jsonify(hit)
    players = player_service.search_players(search_term)
    payload = json_safe(players)
    league_cache_put("player_search", cache_db, cache_args, payload)
    return jsonify(payload)

@bp.route('/get_available_seasons')
def get_available_seasons():
    player_name = request.args.get('player_name')
    player_id = request.args.get('player_id', '')
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = dict(request.args)
    cache_args["database"] = cache_db
    hit = league_cache_try_get("player_get_available_seasons", cache_db, cache_args)
    if hit is not None:
        return jsonify(hit)
    seasons = player_service.get_player_seasons(player_name or '', player_id=player_id)
    payload = json_safe(seasons)
    league_cache_put("player_get_available_seasons", cache_db, cache_args, payload)
    return jsonify(payload)

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
    season_raw = request.args.get('season', 'all')
    season = normalize_season_query_value(season_raw) if season_raw and str(season_raw).strip().lower() != 'all' else 'all'
    
    player_service = get_player_service()
    cache_db = _player_cache_database(player_service)
    cache_args = dict(request.args)
    cache_args["database"] = cache_db
    hit = league_cache_try_get("get_lifetime_stats", cache_db, cache_args)
    if hit is not None:
        return jsonify(hit)

    if not player_name and not player_id:
        if season == "all":
            merged = _aggregate_lifetime_from_season_caches(
                player_service,
                cache_db,
                player_service.get_all_seasons(),
            )
            if merged is not None:
                payload = json_safe(merged)
                league_cache_put("get_lifetime_stats", cache_db, cache_args, payload)
                return jsonify(payload)
        stats = player_service.get_aggregate_lifetime_stats(season=season)
    else:
        stats = player_service.get_lifetime_stats(player_name or '', season=season, player_id=player_id)
    payload = json_safe(stats)
    league_cache_put("get_lifetime_stats", cache_db, cache_args, payload)
    return jsonify(payload)
