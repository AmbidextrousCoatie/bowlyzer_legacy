"""Tests for league week matrix (Liga-Wochen) payload."""

import pandas as pd

from app.services.league_service import LeagueService
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns


def _week_matrix_df() -> pd.DataFrame:
    rows = []
    teams = ["Alpha 1", "Beta 1", "Gamma 1"]
    for team in teams:
        rows.append(
            {
                Columns.season: "24/25",
                Columns.league_name: "BZOL S1",
                Columns.week: 1,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )
    for week in (1, 2, 3):
        rows.append(
            {
                Columns.season: "24/25",
                Columns.league_name: "BZOL S1",
                Columns.week: week,
                Columns.team_name: "Alpha 1",
                Columns.computed_data: True,
            }
        )
        rows.append(
            {
                Columns.season: "24/25",
                Columns.league_name: "BZOL S1",
                Columns.week: week,
                Columns.team_name: "Beta 1",
                Columns.computed_data: True,
            }
        )
    rows.append(
        {
            Columns.season: "23/24",
            Columns.league_name: "BayL",
            Columns.week: 1,
            Columns.team_name: "Club A 1",
            Columns.computed_data: True,
        }
    )
    for team in ("Club A 1", "Club B 1"):
        rows.append(
            {
                Columns.season: "23/24",
                Columns.league_name: "BayL",
                Columns.week: 2,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )
    return pd.DataFrame(rows)


def test_get_league_week_matrix_team_counts_and_missing_weeks():
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(_week_matrix_df())
    service = LeagueService(database=None)
    service.adapter = adapter

    result = service.get_league_week_matrix()

    assert result["seasons"] == ["23/24", "24/25"]

    south_l5 = next(row for row in result["rows"] if "BZOL S1" in row["league"])
    assert south_l5["league"] == "BL S1 / BZOL S1"
    cell = south_l5["seasons"]["24/25"]
    assert cell["league_id"] == "BZOL S1"
    assert cell["team_count"] == 3
    assert cell["expected_weeks"] == 3
    assert cell["missing_weeks"] == []
    assert cell["label"] == "✓"
    assert cell["status"] == "ok"

    bayl = next(row for row in result["rows"] if row["league"] == "BayL")
    bayl_cell = bayl["seasons"]["23/24"]
    assert bayl_cell["team_count"] == 2
    assert bayl_cell["expected_weeks"] == 6
    assert bayl_cell["missing_weeks"] == [2, 3, 4, 5, 6]


def test_bl_bzol_merge_avoids_cross_era_false_positives():
    rows = []
    for week in (1, 2, 3):
        rows.append(
            {
                Columns.season: "15/16",
                Columns.league_name: "BL N1",
                Columns.week: week,
                Columns.team_name: "Team A 1",
                Columns.computed_data: True,
            }
        )
    for team in ("Team A 1", "Team B 1", "Team C 1"):
        rows.append(
            {
                Columns.season: "15/16",
                Columns.league_name: "BL N1",
                Columns.week: 1,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )
    for week in (1, 2, 3, 4):
        rows.append(
            {
                Columns.season: "24/25",
                Columns.league_name: "BZOL N1",
                Columns.week: week,
                Columns.team_name: "Team X 1",
                Columns.computed_data: True,
            }
        )
    for team in ("Team X 1", "Team Y 1", "Team Z 1", "Team W 1"):
        rows.append(
            {
                Columns.season: "24/25",
                Columns.league_name: "BZOL N1",
                Columns.week: 1,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )

    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(pd.DataFrame(rows))
    service = LeagueService(database=None)
    service.adapter = adapter

    result = service.get_league_week_matrix()
    merged = next(row for row in result["rows"] if row["league"] == "BL N1 / BZOL N1")

    old_season = merged["seasons"]["15/16"]
    assert old_season["label"] == "✓"
    assert old_season["league_id"] == "BL N1"

    new_season = merged["seasons"]["24/25"]
    assert new_season["label"] == "✓"
    assert new_season["league_id"] == "BZOL N1"

    # No phantom missing-week row for the other short id in the same season.
    league_labels = {row["league"] for row in result["rows"]}
    assert "BL N1" not in league_labels
    assert "BZOL N1" not in league_labels
