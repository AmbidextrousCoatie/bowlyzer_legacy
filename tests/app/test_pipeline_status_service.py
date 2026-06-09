"""Pipeline status snapshot for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

from app.services.pipeline_status_service import get_pipeline_status


def test_pipeline_status_includes_published_league(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    league_csv = data_dir / "league_results_merged.csv"
    league_csv.write_text("Season;Player\n24/25;A\n", encoding="utf-8")

    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))

    status = get_pipeline_status()
    league = next(a for a in status["published_artifacts"] if a["id"] == "league_merged")
    assert league["exists"] is True
    assert league["status"] in {"ok", "warn"}
    assert status["paths"]["published_data_dir"] == str(data_dir.resolve())
