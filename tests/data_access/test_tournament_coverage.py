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


def test_build_tournament_coverage_matrix_includes_scrape_sources() -> None:
    matrix = build_tournament_coverage_matrix(first_season="04/05", last_season="04/05")
    sbm = next(
        cell
        for cell in matrix["cells"]
        if cell["season"] == "04/05" and cell["tournament_id"] == "SBM M"
    )
    if sbm["status"] == "available":
        assert "scrape_pdf" in sbm["sources"] or "registry_pdf" in sbm["sources"]


def test_build_tournament_coverage_matrix_shape() -> None:
    matrix = build_tournament_coverage_matrix(first_season="15/16", last_season="18/19")
    assert matrix["seasons"] == ["15/16", "16/17", "17/18", "18/19"]
    tournament_ids = {row["id"] for row in matrix["tournaments"]}
    assert "NBM D" not in tournament_ids
    assert "SBM D" not in tournament_ids
    assert "NBM M D" not in tournament_ids
    assert "SBM M D" not in tournament_ids
    assert "BM M" in tournament_ids
    assert len(matrix["cells"]) == len(matrix["tournaments"]) * len(matrix["seasons"])
    published_ok = [
        cell
        for cell in matrix["cells"]
        if cell["status"] in {"published_ok", "published_flaws"}
    ]
    assert published_ok, "expected some published cells in 15/16–18/19 window"
