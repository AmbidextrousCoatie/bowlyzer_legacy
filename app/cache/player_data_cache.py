"""Invalidate player merged-hybrid caches after tournament or league data publishes."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from app.config.database_config import TOURNAMENTS_POSTPROCESSED_CSV

PLAYER_MERGED_DATABASE = "db_player_merged_hybrid"


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
    from data_access.shared_pandas_store import invalidate_adapter_cache, invalidate_dataframe_cache

    invalidate_adapter_cache(database_id)
    invalidate_revision_index(database_id)

    tournaments_path = Path(TOURNAMENTS_POSTPROCESSED_CSV)
    invalidate_dataframe_cache(tournaments_path)
    invalidate_dataframe_cache(tournaments_path.with_suffix(".parquet"))

    disk_removed = league_cache_invalidate_database(database_id)
    runtime_removed = league_cache_clear_runtime(database_id)
    return {
        "disk_entries_removed": disk_removed,
        "runtime_entries_removed": runtime_removed,
    }
