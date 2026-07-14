"""Invalidate player and tournament caches after tournament data publishes."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from app.config.database_config import TOURNAMENTS_POSTPROCESSED_CSV

PLAYER_MERGED_DATABASE = "db_player_merged_hybrid"
TOURNAMENT_PUBLISHED_DATABASE = "db_tournament_regions_2026_gf"


def _invalidate_tournament_dataframe_caches() -> None:
    from data_access.shared_pandas_store import invalidate_dataframe_cache

    tournaments_path = Path(TOURNAMENTS_POSTPROCESSED_CSV)
    invalidate_dataframe_cache(tournaments_path)
    invalidate_dataframe_cache(tournaments_path.with_suffix(".parquet"))


def invalidate_tournament_published_caches(
    database_id: str = TOURNAMENT_PUBLISHED_DATABASE,
) -> Dict[str, int]:
    """
    Drop adapter/revision/disk JSON caches for the published tournament Parquet DB.

    The Turnier UI reads ``db_tournament_regions_2026_gf`` →
    ``tournaments_postprocessed.parquet``.
    """
    from app.cache.league_data_revision import invalidate_revision_index
    from app.cache.league_response_cache import (
        league_cache_clear_runtime,
        league_cache_invalidate_database,
    )
    from data_access.shared_pandas_store import invalidate_adapter_cache

    invalidate_adapter_cache(database_id)
    invalidate_revision_index(database_id)
    _invalidate_tournament_dataframe_caches()

    disk_removed = league_cache_invalidate_database(database_id)
    runtime_removed = league_cache_clear_runtime(database_id)
    return {
        "disk_entries_removed": disk_removed,
        "runtime_entries_removed": runtime_removed,
    }


def invalidate_player_merged_caches(database_id: str = PLAYER_MERGED_DATABASE) -> Dict[str, int]:
    """
    Drop in-process adapters, revision index, and on-disk league response caches
    for the Spieler database (league + tournaments_postprocessed merge).
    """
    from app.cache.league_data_revision import invalidate_revision_index
    from app.cache.league_response_cache import (
        league_cache_clear_runtime,
        league_cache_invalidate_database,
    )
    from data_access.shared_pandas_store import invalidate_adapter_cache

    invalidate_adapter_cache(database_id)
    invalidate_revision_index(database_id)
    _invalidate_tournament_dataframe_caches()

    disk_removed = league_cache_invalidate_database(database_id)
    runtime_removed = league_cache_clear_runtime(database_id)
    return {
        "disk_entries_removed": disk_removed,
        "runtime_entries_removed": runtime_removed,
    }


def invalidate_after_tournament_publish() -> Dict[str, int]:
    """Invalidate both published tournament APIs and the Spieler hybrid merge."""
    tournament = invalidate_tournament_published_caches()
    player = invalidate_player_merged_caches()
    return {
        "tournament_disk_entries_removed": int(tournament.get("disk_entries_removed") or 0),
        "tournament_runtime_entries_removed": int(tournament.get("runtime_entries_removed") or 0),
        "player_disk_entries_removed": int(player.get("disk_entries_removed") or 0),
        "player_runtime_entries_removed": int(player.get("runtime_entries_removed") or 0),
    }
