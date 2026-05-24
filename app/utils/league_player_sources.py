"""Map league UI database ids to player-stats backing sources."""

from __future__ import annotations

from app.config.database_config import database_config

_MERGED_LIKE_LEAGUE_SOURCES = frozenset({"db_real_historical_league", "db_real_merged"})


def resolve_player_database_id(requested: str | None = None) -> str:
    """
    Player pages use a different CSV when the league scope is merged or pipeline GF.
    Mirrors ``get_player_service()`` in ``app.routes.player_routes``.
    """
    has_combined = database_config.validate_source("db_player_combined_gf")
    has_merged_hybrid = database_config.validate_source("db_player_merged_hybrid")

    if requested:
        if requested in _MERGED_LIKE_LEAGUE_SOURCES and has_merged_hybrid:
            return "db_player_merged_hybrid"
        if requested == "db_real_pipeline_gf" and has_combined:
            return "db_player_combined_gf"
        return requested
    if has_merged_hybrid:
        return "db_player_merged_hybrid"
    if has_combined:
        return "db_player_combined_gf"
    return database_config.get_default_source()
