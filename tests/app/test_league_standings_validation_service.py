"""League standings validation API for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

from app.services.league_standings_validation_service import (
    get_league_standings_validation,
    load_validation_report_csv,
)


def test_load_validation_report_csv_parses_lists(tmp_path: Path) -> None:
    report = tmp_path / "league_standings_validation.csv"
    report.write_text(
        "season;league;status;reference_week;expected_weeks;available_weeks;"
        "missing_matchdays;week_coverage_status;notes;missing_in_computed\n"
        "24/25;BayL;red;4;6;1,2,3,4;5,6;warn;incomplete season;;\n",
        encoding="utf-8",
    )
    rows = load_validation_report_csv(report)
    assert len(rows) == 1
    row = rows[0]
    assert row["season"] == "24/25"
    assert row["league"] == "BayL"
    assert row["status"] == "red"
    assert row["reference_week"] == 4
    assert row["available_weeks"] == [1, 2, 3, 4]
    assert row["missing_matchdays"] == [5, 6]
    assert row["week_coverage_status"] == "warn"


def test_get_league_standings_validation_from_report(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "league_standings_validation.csv"
    report.write_text(
        "season;league;status;reference_team_count;computed_team_count;expected_weeks;"
        "available_weeks;missing_matchdays;week_coverage_status;notes\n"
        "24/25;BayL;green;10;10;6;1,2,3,4,5,6;;ok;match\n"
        "24/25;BL;yellow;8;8;8;1,2,3,4;5,6,7,8;warn;weeks\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_league_standings_validation()
    assert payload["source"] == "report"
    assert payload["row_count"] == 2
    assert payload["summary"]["green"] == 1
    assert payload["summary"]["yellow"] == 1
    assert payload["summary"]["week_incomplete"] == 1

    filtered = get_league_standings_validation(season="24/25", league="BayL")
    assert filtered["row_count"] == 1
    assert filtered["rows"][0]["league"] == "BayL"


def test_get_league_standings_validation_builds_findings_from_legacy_columns(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "league_standings_validation.csv"
    report.write_text(
        "season;league;status;missing_in_computed;position_mismatches;points_mismatches;"
        "pins_mismatches;expected_weeks;available_weeks;missing_matchdays;week_coverage_status;notes\n"
        "23/24;LL N1;red;SW 77 Würzburg;Castra Regina Regensburg 1: ref pos 4 vs computed 5;"
        "Castra Regina Regensburg 1: ref pts 82.0 vs computed 81.0;"
        "Castra Regina Regensburg 1: ref pins 23370 vs computed 23149;"
        "6;1,2,3,4,5,6;;ok;\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_league_standings_validation(season="23/24", league="LL N1")
    findings = payload["rows"][0]["findings"]
    assert findings[0] == "SW 77 Würzburg"
    assert any(line.startswith("pos: ") for line in findings)
    assert any(line.startswith("pts: ") for line in findings)
    assert any(line.startswith("pins: ") for line in findings)


def test_get_league_standings_validation_absent_when_no_report(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_league_standings_validation()
    assert payload["source"] == "absent"
    assert payload["rows"] == []
