"""Tournament coverage matrix."""

from __future__ import annotations

from pathlib import Path

from data_access.tournament_coverage import (
    app_season_to_calendar_year,
    build_tournament_coverage_matrix,
    folder_slug_to_app_season,
)


def test_folder_slug_to_app_season() -> None:
    assert folder_slug_to_app_season("2015-16") == "15/16"
    assert folder_slug_to_app_season("2008-09") == "08/09"


def test_app_season_to_calendar_year() -> None:
    assert app_season_to_calendar_year("15/16") == 2016
    assert app_season_to_calendar_year("25/26") == 2026


def test_build_tournament_coverage_matrix_shape() -> None:
    matrix = build_tournament_coverage_matrix(first_season="15/16", last_season="18/19")
    assert matrix["seasons"] == ["15/16", "16/17", "17/18", "18/19"]
    assert len(matrix["tournaments"]) >= 5
    assert len(matrix["cells"]) == len(matrix["tournaments"]) * len(matrix["seasons"])
    published_ok = [
        cell
        for cell in matrix["cells"]
        if cell["status"] in {"published_ok", "published_flaws"}
    ]
    assert published_ok, "expected some published cells in 15/16–18/19 window"
