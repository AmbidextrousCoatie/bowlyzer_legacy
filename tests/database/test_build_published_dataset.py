"""build_published_dataset path defaults and league input ordering."""

from pathlib import Path

from database.paths import (
    historical_league_results_csv,
    league_results_merged_csv,
    legacy_scrape_league_csv,
    pipeline_gf_league_csv,
    tournaments_postprocessed_csv,
)
from scripts.build_published_dataset import build_league_input_paths


def test_default_paths_under_data_and_work():
    assert league_results_merged_csv().name == "league_results_merged.csv"
    assert tournaments_postprocessed_csv().name == "tournaments_postprocessed.csv"
    assert historical_league_results_csv().name == "historical_league_results.csv"
    assert pipeline_gf_league_csv().name == "latest.csv"
    assert "legacy_out" in str(pipeline_gf_league_csv())
    assert legacy_scrape_league_csv().name == "legacy_scrape_extracted.csv"


def test_build_league_input_paths_order(tmp_path, monkeypatch):
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path))
    hist = tmp_path / "historical.csv"
    scrape = tmp_path / "legacy_scrape_extracted.csv"
    extra = tmp_path / "custom.csv"
    gf = tmp_path / "latest.csv"
    for p in (hist, scrape, extra, gf):
        p.write_text("Season;League\n", encoding="utf-8")
    paths = build_league_input_paths(
        historical=hist,
        gf_league=gf,
        extra_league=[extra],
        with_legacy_scrape=True,
    )
    assert paths == [hist.resolve(), scrape.resolve(), extra.resolve(), gf.resolve()]
