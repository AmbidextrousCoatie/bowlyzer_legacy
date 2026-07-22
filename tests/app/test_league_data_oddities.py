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
                Columns.players_per_team: 4,
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
                Columns.players_per_team: 4,
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
                Columns.players_per_team: 4,
                Columns.input_data: True,
                Columns.computed_data: False,
            },
        ]
    )


def _service_with_df(df: pd.DataFrame) -> LeagueService:
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(df)
    service = LeagueService(database=None)
    service.adapter = adapter
    return service


def test_get_data_oddities_finds_low_score_and_unnumbered_team():
    service = _service_with_df(_sample_df())

    result = service.get_data_oddities(types=["low_score", "unnumbered_team"])
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


def test_get_data_oddities_incomplete_squad_is_info_only():
    rows = []
    common = {
        Columns.season: "11/12",
        Columns.league_name: "BZL S2",
        Columns.week: 2,
        Columns.round_number: 4,
        Columns.match_number: 1,
        Columns.players_per_team: 4,
        Columns.input_data: True,
        Columns.computed_data: False,
    }
    for i, name in enumerate(["A", "B", "C", "D"]):
        rows.append(
            {
                **common,
                Columns.team_name: "Club Full 1",
                Columns.team_name_opponent: "Club Thin 1",
                Columns.player_name: name,
                Columns.position: i,
                Columns.score: 150 + i,
            }
        )
    rows.append(
        {
            **common,
            Columns.team_name: "Club Thin 1",
            Columns.team_name_opponent: "Club Full 1",
            Columns.player_name: "Solo",
            Columns.position: 0,
            Columns.score: 106,
        }
    )
    service = _service_with_df(pd.DataFrame(rows))

    result = service.get_data_oddities(types=["incomplete_squad"])
    assert result["summary"]["by_type"]["incomplete_squad"] == 1
    item = result["oddities"][0]
    assert item["type"] == "incomplete_squad"
    assert item["severity"] == "info"
    assert item["context"]["team"] == "Club Thin 1"
    assert item["context"]["players"] == 1
    assert item["context"]["expected"] == 4
    assert "1/4" in item["message"]


def test_get_data_oddities_over_roster_and_named_missing_side():
    common = {
        Columns.season: "14/15",
        Columns.league_name: "A S1",
        Columns.week: 1,
        Columns.round_number: 2,
        Columns.match_number: 1,
        Columns.players_per_team: 4,
        Columns.input_data: True,
        Columns.computed_data: False,
    }
    rows = [
        {
            **common,
            Columns.team_name: "Crowded 1",
            Columns.team_name_opponent: "Ghost Club 2",
            Columns.player_name: f"P{i}",
            Columns.position: i,
            Columns.score: 100 + i,
        }
        for i in range(6)  # over-roster: 6/4
    ]
    # Normal full match (control) — should not create named_missing
    for i in range(4):
        rows.append(
            {
                **common,
                Columns.round_number: 1,
                Columns.team_name: "Alpha 1",
                Columns.team_name_opponent: "Beta 1",
                Columns.player_name: f"A{i}",
                Columns.position: i,
                Columns.score: 120,
            }
        )
        rows.append(
            {
                **common,
                Columns.round_number: 1,
                Columns.team_name: "Beta 1",
                Columns.team_name_opponent: "Alpha 1",
                Columns.player_name: f"B{i}",
                Columns.position: i,
                Columns.score: 110,
            }
        )

    service = _service_with_df(pd.DataFrame(rows))
    result = service.get_data_oddities(types=["over_roster", "named_missing_side"])

    assert result["summary"]["by_type"]["over_roster"] == 1
    over = next(o for o in result["oddities"] if o["type"] == "over_roster")
    assert over["severity"] == "info"
    assert over["context"]["team"] == "Crowded 1"
    assert over["context"]["players"] == 6
    assert over["context"]["expected"] == 4

    assert result["summary"]["by_type"]["named_missing_side"] == 1
    missing = next(o for o in result["oddities"] if o["type"] == "named_missing_side")
    assert missing["severity"] == "info"
    assert missing["context"]["opponent"] == "Ghost Club 2"
    assert missing["context"]["team"] == "Crowded 1"
