"""Tournament data quality API for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

from app.services.tournament_data_quality_service import (
    get_tournament_data_quality,
    load_tournament_quality_report_csv,
)


def test_load_tournament_quality_report_csv(tmp_path: Path) -> None:
    report = tmp_path / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "23/24;BM 2024;BM M;10;8;0;1;0;0;0;0;0;yellow;missing_club: 1;\n",
        encoding="utf-8",
    )
    rows = load_tournament_quality_report_csv(report)
    assert len(rows) == 1
    assert rows[0]["event_name"] == "BM 2024"
    assert rows[0]["status"] == "yellow"
    assert rows[0]["findings"] == ["missing_club: 1"]


def test_get_tournament_data_quality_from_report(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "23/24;BM 2024;BM M;10;8;0;0;0;0;0;0;0;green;;\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_tournament_data_quality()
    assert payload["source"] == "report"
    assert payload["row_count"] == 1
    assert payload["summary"]["green"] == 1
