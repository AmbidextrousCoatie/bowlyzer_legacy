from flask import Blueprint, jsonify, request
from app.services.player_service import PlayerService
from app.config.database_config import database_config
from app.utils.json_safe import json_safe

bp = Blueprint('player', __name__, url_prefix='/player')

def get_player_service():
    """Helper function to get PlayerService with database parameter"""
    requested = request.args.get('database')
    has_combined = database_config.validate_source('db_player_combined_gf')
    has_merged_hybrid = database_config.validate_source('db_player_merged_hybrid')
    merged_like_sources = {'db_real_historical_league', 'db_real_merged'}
    if requested:
        # Player stats source should follow the selected league scope:
        # - merged/historical -> merged hybrid (multi-season + tournaments)
        # - pipeline GF -> GF-combined player source
        if requested in merged_like_sources and has_merged_hybrid:
            database = 'db_player_merged_hybrid'
        elif requested == 'db_real_pipeline_gf' and has_combined:
            database = 'db_player_combined_gf'
        else:
            database = requested
    elif has_merged_hybrid:
        database = 'db_player_merged_hybrid'
    elif has_combined:
        database = 'db_player_combined_gf'
    else:
        database = database_config.get_default_source()
    return PlayerService(database=database)

@bp.route('/search')
def search_players():
    search_term = request.args.get('search', '')
    player_service = get_player_service()
    players = player_service.search_players(search_term)
    return jsonify(json_safe(players))

@bp.route('/get_available_seasons')
def get_available_seasons():
    player_name = request.args.get('player_name')
    player_id = request.args.get('player_id', '')
    if not player_name and not player_id:
        return jsonify([])
    player_service = get_player_service()
    seasons = player_service.get_player_seasons(player_name or '', player_id=player_id)
    return jsonify(json_safe(seasons))

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
    season = request.args.get('season', 'all')
    
    if not player_name and not player_id:
        return jsonify({'error': 'Player name is required'}), 400
    
    print(f"Player Route: Get Lifetime Stats - Received request with: player_name={player_name}")
    
    player_service = get_player_service()
    stats = player_service.get_lifetime_stats(player_name or '', season=season, player_id=player_id)  # Supports optional season scope
    
    return jsonify(json_safe(stats))
