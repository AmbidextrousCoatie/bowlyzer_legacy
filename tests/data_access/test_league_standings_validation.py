import json
from pathlib import Path

import pandas as pd
import pytest

from data_access.league_standings_validation import (
    STATUS_CORRECTED,
    STATUS_GREEN,
    STATUS_PERFECT,
    STATUS_RED,
    STATUS_YELLOW,
    StandingRow,
    StandingsComparison,
    _apply_validation_outcome,
    classify_status,
    compare_standings,
    compare_standings_with_processing,
    comparison_findings,
    compare_league_season_without_reference,
    compute_standings_from_dataframe,
    describe_missing_excel_reference,
    resolve_workbook_path,
    parse_post_2022_tabges_standings,
    parse_pre_2022_tabelle_standings,
    pick_standings_sheet,
    write_comparison_report,
    parse_findings_cell,
)
from data_access.schema import Columns


def _pre_2022_tabelle_df() -> pd.DataFrame:
    rows = [
        [None, None, None, None, None, None, None, None, None, None, None],
        [None, "Neue Tabelle", None, None, None, None, None, None, None, None, None],
        [None, None, "Mannschaft", None, None, None, None, "Pins", "Punkte", "Bonus", "Total"],
        [None, 1, "Team Alpha", None, None, None, None, 1000, 10, 2, 12],
        [None, 2, "Team Beta", None, None, None, None, 900, 8, 1, 9],
    ]
    return pd.DataFrame(rows)


def test_parse_pre_2022_tabelle_standings():
    rows = parse_pre_2022_tabelle_standings(_pre_2022_tabelle_df())
    assert len(rows) == 2
    assert rows[0] == StandingRow(position=1, team="Team Alpha", total_points=12.0, total_pins=1000)
    assert rows[1].team == "Team Beta"


def test_parse_post_2022_tabges_standings():
    rows_data = [
        ["Liga", None, None, None, None, None, None, None, None, None, None, None, None],
        ["Saison", None, None, None, None, None, None, None, None, None, None, None, None],
        ["Gesamttabelle", None, None, None, None, None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None, None, None, None, None, None],
        ["Pl.", "Mannschaften", "Spieltag 1", None, "Spieltag 2", None, None, None, None, None, None, None, None],
        [None, None, "Pins", "Pkt.", "Pins", "Pkt.", None, None, None, None, None, None, None],
        [1, "Team Alpha", 500, 10, 500, 8, None, None, None, None, None, None, None],
        [2, "Team Beta", 400, 6, 450, 7, None, None, None, None, None, None, None],
    ]
    df = pd.DataFrame(rows_data)
    rows = parse_post_2022_tabges_standings(df)
    assert rows[0].team == "Team Alpha"
    assert rows[0].total_points == 18.0
    assert rows[0].total_pins == 1000
    assert rows[1].position == 2


def test_pick_standings_sheet_post_2022_prefers_tabges():
    sheets = ["Spielorte", "Tabelle6", "TabGes6", "Schnitt6", "TabGes4", "Tabelle4"]
    assert pick_standings_sheet(sheets, data_format="data_format_post_2022") == "TabGes6"
    assert pick_standings_sheet(sheets, data_format="data_format_post_2022", max_week=4) == "TabGes4"


def test_parse_post_2022_tabges_uses_gesamt_columns():
    rows_data = [
        ["Liga", None, None, None, None, None, None, None, None, None, None, None],
        ["Saison", None, None, None, None, None, None, None, None, None, None, None],
        ["Gesamttabelle", None, None, None, None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None, None, None, None, None],
        ["Pl.", "Mannschaften", "Spieltag 1", None, "Spieltag 2", None, "Gesamt", None, None, None, None, None],
        [None, None, "Pins", "Pkt.", "Pins", "Pkt.", "Pins", "Pkt.", None, None, None, None],
        [1, "Team Alpha", 100, 10, 200, 20, 300, 30, None, None, None, None],
    ]
    df = pd.DataFrame(rows_data)
    rows = parse_post_2022_tabges_standings(df)
    assert len(rows) == 1
    assert rows[0].total_points == 30.0
    assert rows[0].total_pins == 300


def test_classify_status():
    assert classify_status(teams_match=True, positions_match=True, points_match=True, pins_match=True) == STATUS_GREEN
    assert classify_status(teams_match=True, positions_match=True, points_match=False, pins_match=True) == STATUS_YELLOW
    assert classify_status(teams_match=False, positions_match=False, points_match=False, pins_match=False) == STATUS_RED


def test_compare_standings_green_yellow_red():
    ref = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    computed_ok = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_ok)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_GREEN

    computed_pts_off = [
        StandingRow(1, "Team Alpha", 11.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_pts_off)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_YELLOW

    computed_wrong_team = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Gamma", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_wrong_team)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_RED


def test_compute_standings_from_dataframe():
    df = pd.DataFrame(
        [
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Alpha",
                "Week": "1",
                "Score": "200",
                "Points": "0",
                "Bonus Points": "0",
                "Input Data": "True",
                "Computed Data": "False",
            },
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Alpha",
                "Week": "1",
                "Score": "0",
                "Points": "1",
                "Bonus Points": "0.5",
                "Input Data": "False",
                "Computed Data": "True",
            },
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Beta",
                "Week": "1",
                "Score": "150",
                "Points": "0",
                "Bonus Points": "0",
                "Input Data": "True",
                "Computed Data": "False",
            },
        ]
    )
    rows = compute_standings_from_dataframe(df, league="A S2", season="19/20")
    assert len(rows) == 2
    assert rows[0].team == "Team Alpha"
    assert rows[0].total_points == 1.5
    assert rows[0].total_pins == 200


def test_team_name_normalization_resolves_profishop_alias():
    reference = [
        StandingRow(1, "Team Alpha", 10.0, 1000),
        StandingRow(5, "Team ProfiShop München 1", 100.0, 2000),
    ]
    computed = [
        StandingRow(1, "Team Alpha", 10.0, 1000),
        StandingRow(5, "Team ProfiShop 1", 100.0, 2000),
    ]
    (
        teams_match,
        _pos,
        _pts,
        _pins,
        missing_in_computed,
        missing_in_reference,
        *_rest,
        snapshots,
    ) = compare_standings_with_processing(
        reference,
        computed,
        season="22/23",
        league="BayL",
    )
    assert snapshots[1].step == "team_name_normalization"
    assert snapshots[1].team_mismatches == 0
    assert teams_match is True
    assert missing_in_computed == []
    assert missing_in_reference == []


@pytest.mark.parametrize(
    ("reference_team", "computed_team"),
    [
        ("BC Merlin München-Land 1", "Merlin München 1"),
        ("SW 77 'Würzburg 1", "SW 77 Würzburg 1"),
        ("1. DBC Bayreuth 1", "DBC Bayreuth 1"),
        ("BC Falken München-Land 1", "Falken München 1"),
        ("BC Merlin München-Land 2", "Merlin München 2"),
    ],
)
def test_team_name_normalization_resolves_configured_aliases(reference_team, computed_team):
    reference = [StandingRow(1, reference_team, 10.0, 1000)]
    computed = [StandingRow(1, computed_team, 10.0, 1000)]
    teams_match, *_rest, snapshots = compare_standings_with_processing(
        reference,
        computed,
        season="09/10",
        league="BZL S1",
    )
    assert snapshots[1].team_mismatches == 0
    assert teams_match is True


def test_compare_standings_with_processing_team_number_resolves_unnumbered():
    reference = [
        StandingRow(1, "BSC Kirchenlamitz", 10.0, 1000),
        StandingRow(2, "Noris 81 Nürnberg", 9.0, 900),
        StandingRow(3, "Strikers Lauf", 8.0, 800),
    ]
    computed = [
        StandingRow(1, "BSC Kirchenlamitz 1", 10.0, 1000),
        StandingRow(2, "Noris 81 Nürnberg 1", 9.0, 900),
        StandingRow(3, "Strikers Lauf 1", 8.0, 800),
    ]
    (
        teams_match,
        _pos,
        _pts,
        _pins,
        missing_in_computed,
        missing_in_reference,
        *_rest,
        snapshots,
    ) = compare_standings_with_processing(
        reference,
        computed,
        season="08/09",
        league="A N1",
    )
    assert snapshots[0].team_mismatches == 6
    assert snapshots[1].team_mismatches == 6
    assert snapshots[2].team_mismatches == 0
    assert teams_match is True
    assert missing_in_computed == []
    assert missing_in_reference == []


def test_describe_missing_excel_reference_not_in_log(tmp_path: Path) -> None:
    log_path = tmp_path / "extract_excel_analysis_log.json"
    log_path.write_text(json.dumps({"files": {}}), encoding="utf-8")
    note = describe_missing_excel_reference(
        log_path,
        league="BayL",
        season="08/09",
    )
    assert "No Excel workbook indexed" in note


def test_resolve_workbook_path_remaps_legacy_scrape_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    work_scrape = tmp_path / "work" / "legacy_scrape"
    workbook = work_scrape / "saison2008-09" / "bayernliga" / "LB_BAY-L_H-1.xlsx"
    workbook.parent.mkdir(parents=True)
    workbook.write_bytes(b"x")
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))

    stale = (
        tmp_path
        / "old_repo"
        / "database"
        / "data"
        / "legacy_scrape"
        / "saison2008-09"
        / "bayernliga"
        / "LB_BAY-L_H-1.xlsx"
    )
    resolved = resolve_workbook_path(stale)
    assert resolved == workbook.resolve()


def test_describe_missing_excel_reference_ineligible_workbook(tmp_path: Path) -> None:
    log_path = tmp_path / "extract_excel_analysis_log.json"
    workbook = tmp_path / "BayL_08_09.xlsx"
    workbook.write_bytes(b"x")
    log_path.write_text(
        json.dumps(
            {
                "files": {
                    str(workbook): {
                        "analysis_result": {
                            "file": str(workbook),
                            "league": "BayL",
                            "season": "08/09",
                            "data_format": "data_format_pre_2022",
                            "eligible_for_processing": False,
                            "issues": "Missing Tabelle sheet",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    note = describe_missing_excel_reference(log_path, league="BayL", season="08/09")
    assert "not eligible" in note
    assert "Missing Tabelle sheet" in note


def test_compare_league_season_without_reference_uses_descriptive_note(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "extract_excel_analysis_log.json"
    log_path.write_text(json.dumps({"files": {}}), encoding="utf-8")
    df = pd.DataFrame(
        [
            {
                Columns.season: "08/09",
                Columns.event: "BayL",
                Columns.event_type: "league",
                Columns.week: 1,
                Columns.team_name: "Team A 1",
                Columns.computed_data: True,
            }
        ]
    )
    comparison = compare_league_season_without_reference(
        df,
        league="BayL",
        season="08/09",
        analysis_log_path=log_path,
    )
    assert comparison.status in {"skipped", "yellow"}
    assert "No Excel workbook indexed" in comparison.notes


def test_comparison_findings_includes_all_mismatch_types():
    item = StandingsComparison(
        season="23/24",
        league="LL N1",
        status=STATUS_RED,
        missing_in_computed=["SW 77 Würzburg"],
        position_mismatches=["Castra Regina Regensburg 1: ref pos 4 vs computed 5"],
        points_mismatches=["Castra Regina Regensburg 1: ref pts 82.0 vs computed 81.0"],
        pins_mismatches=["Castra Regina Regensburg 1: ref pins 23370 vs computed 23149"],
    )
    findings = comparison_findings(item)
    assert findings[0] == "SW 77 Würzburg"
    assert findings[1].startswith("pos: ")
    assert findings[2].startswith("pts: ")
    assert findings[3].startswith("pins: ")


def test_write_comparison_report_includes_findings_column(tmp_path):
    item = StandingsComparison(
        season="23/24",
        league="KL N2",
        status=STATUS_YELLOW,
        points_mismatches=["RW Lichtenhof Stein 8: ref pts 117.5 vs computed 95.5"],
    )
    report = tmp_path / "league_standings_validation.csv"
    write_comparison_report([item], report)
    import csv

    with report.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter=";"))
    assert row["findings"] == (
        "pts: RW Lichtenhof Stein 8: ref pts 117.5 vs computed 95.5"
    )


def test_incomplete_weeks_downgrade_green_to_yellow():
    rows = []
    for team in ("Alpha 1", "Beta 1"):
        rows.append(
            {
                Columns.season: "24/25",
                Columns.event: "BayL",
                Columns.event_type: "league",
                Columns.week: 1,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )
    rows.append(
        {
            Columns.season: "24/25",
            Columns.event: "BayL",
            Columns.event_type: "league",
            Columns.week: 1,
            Columns.team_name: "Alpha 1",
            Columns.computed_data: True,
        }
    )
    df = pd.DataFrame(rows)
    comparison = compare_league_season_without_reference(df, league="BayL", season="24/25")
    assert comparison.status == STATUS_YELLOW
    assert comparison.missing_matchdays == [2, 3, 4, 5, 6]
    assert "incomplete season" in comparison.notes


def test_apply_validation_outcome_marks_excel_high_total_as_corrected():
    comparison = StandingsComparison(
        season="08/09",
        league="A N2",
        status=STATUS_YELLOW,
        teams_match=True,
        positions_match=True,
        points_match=False,
        pins_match=True,
        points_mismatches=["OK Bowlers Bindlach 2: ref pts 99.0 vs computed 98.0"],
        total_points_reference=737.0,
        total_points_computed=736.0,
        total_points_expected=736.0,
        reference_total_points_ok=False,
        computed_total_points_ok=True,
        points_mismatch_explained_by_total=True,
    )
    outcome = _apply_validation_outcome(comparison)
    assert outcome.status == STATUS_CORRECTED
    assert outcome.points_auto_corrected is True


def test_apply_validation_outcome_marks_one_off_points_as_corrected():
    comparison = StandingsComparison(
        season="09/10",
        league="A N2",
        status=STATUS_YELLOW,
        teams_match=True,
        positions_match=True,
        points_match=False,
        pins_match=True,
        points_mismatches=["SG Rottendorf 4: ref pts 146.0 vs computed 145.0"],
        total_points_reference=736.0,
        total_points_computed=735.0,
        total_points_expected=736.0,
        reference_total_points_ok=True,
        computed_total_points_ok=False,
    )
    outcome = _apply_validation_outcome(comparison)
    assert outcome.status == STATUS_CORRECTED
    assert outcome.points_auto_corrected is True
    assert "accepted computed" in outcome.correction_remark
    assert "corrected" in outcome.error_categories
    findings = comparison_findings(outcome)
    assert findings[0].startswith("corrected: ")


def test_apply_validation_outcome_promotes_full_match_to_perfect():
    comparison = StandingsComparison(
        season="24/25",
        league="BayL",
        status=STATUS_GREEN,
        teams_match=True,
        positions_match=True,
        points_match=True,
        pins_match=True,
        total_points_reference=1080.0,
        total_points_computed=1080.0,
        total_points_expected=1080.0,
        reference_total_points_ok=True,
        computed_total_points_ok=True,
    )
    outcome = _apply_validation_outcome(comparison)
    assert outcome.status == STATUS_PERFECT
    assert outcome.error_categories == ["perfect"]
