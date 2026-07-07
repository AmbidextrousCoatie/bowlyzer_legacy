"""Player merged-hybrid cache invalidation after data publishes."""

from __future__ import annotations

from unittest.mock import patch

from app.cache.player_data_cache import invalidate_player_merged_caches


def test_invalidate_player_merged_caches_clears_adapter_revision_and_disk() -> None:
    with (
        patch("data_access.shared_pandas_store.invalidate_adapter_cache") as mock_adapter,
        patch("app.cache.league_data_revision.invalidate_revision_index") as mock_revision,
        patch("data_access.shared_pandas_store.invalidate_dataframe_cache") as mock_df,
        patch(
            "app.cache.league_response_cache.league_cache_invalidate_database",
            return_value=3,
        ) as mock_disk,
        patch(
            "app.cache.league_response_cache.league_cache_clear_runtime",
            return_value=1,
        ) as mock_runtime,
    ):
        result = invalidate_player_merged_caches()

    mock_adapter.assert_called_once_with("db_player_merged_hybrid")
    mock_revision.assert_called_once_with("db_player_merged_hybrid")
    assert mock_df.call_count == 2
    mock_disk.assert_called_once_with("db_player_merged_hybrid")
    mock_runtime.assert_called_once_with("db_player_merged_hybrid")
    assert result == {"disk_entries_removed": 3, "runtime_entries_removed": 1}


def test_tournament_import_invalidates_player_caches_after_publish() -> None:
    from pathlib import Path

    from database.tournament_import.adapters.base import ImportResult
    from database.tournament_import.config import ImportEntry
    from database.tournament_import.service import TournamentImportService

    entry = ImportEntry(id="x", format="legacy_pdf_erg_2016", source="a.pdf")
    fake_result = ImportResult(
        entry_id="x",
        source=Path("a.pdf"),
        event_names=["Test Event"],
        raw_row_count=1,
        postprocessed_row_count=1,
    )

    service = TournamentImportService()
    with (
        patch.object(service, "_select_entries", return_value=[entry]),
        patch.object(service, "_run_entry", return_value=fake_result),
        patch(
            "database.tournament_import.publish.publish_tournaments_parquet",
            return_value={"rows": 1, "parquet_output": "/tmp/out.parquet"},
        ),
        patch.object(
            service,
            "_invalidate_player_caches",
            return_value={"disk_entries_removed": 2, "runtime_entries_removed": 0},
        ) as mock_invalidate,
    ):
        summary = service.run(entry_ids=["x"], dry_run=False, publish_parquet=True)

    mock_invalidate.assert_called_once()
    assert summary.player_cache_invalidation == {
        "disk_entries_removed": 2,
        "runtime_entries_removed": 0,
    }
