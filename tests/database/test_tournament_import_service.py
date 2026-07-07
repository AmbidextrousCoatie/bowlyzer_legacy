from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import import TournamentImportService, load_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "database" / "config" / "tournament_imports.json"
PDF_2019 = Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2019_akt_sb_he_erg.pdf")


def test_load_tournament_import_config() -> None:
    config = load_config(CONFIG)
    assert config.schema_version == 1
    assert "legacy_pdf_erg_2016" in config.formats
    assert any(entry.id == "sbm-2019-herren" for entry in config.imports)


@pytest.mark.skipif(not PDF_2019.is_file(), reason="sample PDF not on disk")
def test_tournament_import_service_dry_run_single_entry() -> None:
    service = TournamentImportService(config_path=CONFIG)
    summary = service.run(
        entry_ids=["sbm-2019-herren"],
        dry_run=True,
        publish_parquet=False,
        rebuild_player_hybrid=False,
    )
    assert len(summary.results) == 1
    result = summary.results[0]
    assert result.entry_id == "sbm-2019-herren"
    assert result.postprocessed_row_count > 0
    assert "Südbayerische Meisterschaft Einzel 2019" in result.event_names
    assert summary.published_parquet is None
