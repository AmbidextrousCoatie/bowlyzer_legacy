"""Pre-2022 date parsing with season year from folder path."""

from __future__ import annotations

from pathlib import Path

from scripts.data import extract_excel_data as m


def test_infer_season_from_legacy_scrape_folder():
    from database.paths import legacy_scrape_dir

    path = legacy_scrape_dir() / "saison2008-09/nordbereich/LB_LandL_N_D-1.xlsx"
    info = m.infer_season_from_path(path)
    assert info is not None
    assert info["season_short"] == "08/09"
    assert info["year1"] == "2008"
    assert info["year2"] == "2009"


def test_parse_day_month_without_year():
    parsed = m.parse_old_format_date("Spieltag am 14.03.")
    assert parsed is not None
    assert parsed["day"] == 14
    assert parsed["month"] == 3
    assert parsed["year_full"] is None


def test_complete_date_uses_folder_season_rule():
    season = {"season_short": "08/09", "year1": "2008", "year2": "2009"}
    nov = m.complete_old_format_date_info({"day": 15, "month": 11, "year_full": None, "raw": "15.11."}, season)
    assert nov is not None
    assert nov["year_full"] == 2008
    mar = m.complete_old_format_date_info({"day": 14, "month": 3, "year_full": None, "raw": "14.03."}, season)
    assert mar is not None
    assert mar["year_full"] == 2009


def test_parse_weekend_range_date():
    parsed = m.parse_old_format_date("4./5.10.08")
    assert parsed is not None
    assert parsed["day"] == 5
    assert parsed["month"] == 10
    assert parsed["year_full"] == 2008


def test_spielzettel_header_cell_map():
    """Excel D2:F2 league etc. maps to 0-based row/col used in read_pre_2022_metadata_from_spielzettel."""
    import pandas as pd

    df = pd.DataFrame(
        [
            ["", "", "Saison 2008/2009", "", "", ""],
            ["", "", "Liga:", "Bayernliga - Damen", "", ""],
            ["", "", "Datum:", "4./5.10.08", "Spieltag:", 1],
            ["", "", "Anlage:", "Fürth PX-Bowling", "", ""],
        ]
    )
    assert m.get_cells_text(df, 0, 2, 5) == "Saison 2008/2009"
    assert m.get_cells_text(df, 1, 3, 5) == "Bayernliga - Damen"
    assert m.get_cell_value(df, 2, 3) == "4./5.10.08"


def test_combine_season_and_date_month_boundary():
    season = {"season_short": "08/09", "year1": "2008", "year2": "2009"}
    assert m.combine_season_and_date(season, {"day": "01", "month": "9"}) == "2008-09-01"
    assert m.combine_season_and_date(season, {"day": "01", "month": "8"}) == "2009-08-01"
