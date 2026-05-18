"""Tests for league data oddities diagnosis."""

import pandas as pd

from app.services.league_service import LeagueService
from data_access.adapters.data_adapter_factory import DataAdapterSelector, DataAdapterFactory
from data_access.schema import Columns


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                Columns.season: "24/25",
                Columns.league_name: "LL N1",
                Columns.week: 3,
                Columns.round_number: 1,
                Columns.match_number: 1,
                Columns.team_name: "Phönix Lauf",
                Columns.team_name_opponent: "BK Test 1",
                Columns.player_name: "Steffen Birkner",
                Columns.position: 1,
                Columns.score: -5,
                Columns.input_data: True,
                Columns.computed_data: False,
            },
            {
                Columns.season: "24/25",
                Columns.league_name: "LL N1",
                Columns.week: 3,
                Columns.round_number: 1,
                Columns.match_number: 1,
                Columns.team_name: "BK Test 1",
                Columns.team_name_opponent: "Phönix Lauf",
                Columns.player_name: "Other Player",
                Columns.position: 1,
                Columns.score: 180,
                Columns.input_data: True,
                Columns.computed_data: False,
            },
            {
                Columns.season: "24/25",
                Columns.league_name: "LL N1",
                Columns.week: 4,
                Columns.round_number: 1,
                Columns.match_number: 2,
                Columns.team_name: "Phönix Lauf",
                Columns.team_name_opponent: "BK Test 2",
                Columns.player_name: "Team Total",
                Columns.position: 0,
                Columns.score: 500,
                Columns.input_data: True,
                Columns.computed_data: False,
            },
        ]
    )


def test_get_data_oddities_finds_low_score_and_unnumbered_team():
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(_sample_df())
    service = LeagueService(database="test")
    service.adapter = adapter

    result = service.get_data_oddities()
    types = {item["type"] for item in result["oddities"]}
    assert "low_score" in types
    assert "unnumbered_team" in types

    low = next(o for o in result["oddities"] if o["type"] == "low_score")
    assert low["context"]["player"] == "Steffen Birkner"
    assert low["context"]["score"] == -5
    assert low["deep_link"]["params"]["week"] == "3"
    assert low["deep_link"]["params"]["team"] == "Phönix Lauf"

    unnumbered = next(o for o in result["oddities"] if o["type"] == "unnumbered_team")
    assert unnumbered["context"]["team"] == "Phönix Lauf"
