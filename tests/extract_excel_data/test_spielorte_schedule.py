"""Post-2022 Spielorte schedule + Erfassung header date/venue extraction."""

from __future__ import annotations

import pandas as pd

from scripts.data.extract_excel_data import (
    combine_season_and_date,
    extract_date_info,
    extract_erfassung_header_fields,
    extract_team_info,
    normalize_extracted_dataframe,
    parse_spielorte_schedule,
)


SEASON_22 = {"season_short": "22/23", "year1": "2022", "year2": "2023"}
SEASON_24 = {"season_short": "24/25", "year1": "2024", "year2": "2025"}


def test_parse_spielorte_schedule_with_year() -> None:
    df = pd.DataFrame(
        [
            [1, "14./15.01.2023", "Regensburg Superbowl"],
            [2, "28./29.01.2023", "Schweinfurt Extreme Bowling"],
            [None, None, None],
            ["Saison:", None, "2022 / 2023"],
        ]
    )
    schedule = parse_spielorte_schedule(df, SEASON_22)
    assert schedule[1]["date"] == "2023-01-15"
    assert schedule[1]["location"] == "Regensburg Superbowl"
    assert schedule[2]["date"] == "2023-01-29"
    assert 3 not in schedule


def test_parse_spielorte_schedule_without_year_uses_season() -> None:
    df = pd.DataFrame(
        [
            [1, "12.10./13.10.", "Unterföhring Dreambowl Palace", None, "Bamberg Bowlinghaus"],
            [2, "01.02./02.02.", "Regensburg Super Bowl", None, "Bayreuth Blu Bowl"],
        ]
    )
    schedule = parse_spielorte_schedule(df, SEASON_24)
    assert schedule[1]["date"] == "2024-10-13"
    assert schedule[1]["location"] == "Unterföhring Dreambowl Palace"
    assert schedule[2]["date"] == "2025-02-02"
    # Column 4 catalog must not become the venue.
    assert "Bamberg" not in (schedule[1]["location"] or "")


def test_extract_date_info_does_not_invent_october_fourth() -> None:
    df = pd.DataFrame([[None, None, None], [None, None, None]])
    assert extract_date_info(df, SEASON_22) is None
    assert combine_season_and_date(SEASON_22, None) == ""


def test_erfassung_header_reads_ort_and_datum_labels() -> None:
    df = pd.DataFrame(
        [
            ["Team-Nr.", None, "Liga:", None, "Bayernliga Männer", None, None, "Datum:", None, "14./15.01.2023"],
            [1, None, "Ort:", None, "Regensburg Superbowl", None, None, "Spieltag:", 1, None],
        ]
    )
    header = extract_erfassung_header_fields(df)
    assert header["location"] == "Regensburg Superbowl"
    assert header["week"] == 1
    parsed = extract_date_info(df, SEASON_22)
    assert parsed is not None
    assert combine_season_and_date(SEASON_22, parsed) == "2023-01-15"


def test_extract_team_info_uses_ort_label_not_offset_cell() -> None:
    rows = [
        ["Team-Nr.", None, "Liga:", None, "Bayernliga Männer"],
        [1, None, "Ort:", None, "Regensburg Superbowl"],
        ["Raubritter Hallstadt 1", None, None, None, None],
    ]
    df = pd.DataFrame(rows).reindex(range(30))
    info = extract_team_info(df)
    assert info["location"] == "Regensburg Superbowl"


def test_normalize_extracted_dataframe_maps_location() -> None:
    df = pd.DataFrame(
        {
            "Team": ["Isar München 1"],
            "Opponent": ["Isar München 2"],
            "League": ["BayL"],
            "Location": ["Isar-München"],
        }
    )
    out = normalize_extracted_dataframe(df)
    assert out["Location"].iloc[0] == "München Isar Bowling"
