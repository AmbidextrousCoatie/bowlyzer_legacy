"""Game team details matches opponent players by normalized lineup slot."""

from __future__ import annotations

import pandas as pd

from app.services.league_service import LeagueService, _lineup_base, _lineup_slot_lookup
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns


def _service_with_rows(*rows: dict) -> LeagueService:
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(pd.DataFrame(list(rows)))
    service = LeagueService(database=None)
    service.adapter = adapter
    return service


def test_lineup_base_handles_one_and_zero_based_positions():
    assert _lineup_base({0, 1, 2, 3}) == 0
    assert _lineup_base({1, 2, 3, 4}) == 1
    assert _lineup_base({0}) == 0


def test_game_team_details_matches_partial_opponent_lineup():
    common = {
        Columns.season: "11/12",
        Columns.league_name: "BZL S2",
        Columns.week: 2,
        Columns.round_number: 4,
        Columns.computed_data: False,
    }
    rows = [
        {
            **common,
            Columns.team_name: "7 Schwaben Neu-Ulm 1",
            Columns.team_name_opponent: "City-Bowling Augsburg 2",
            Columns.player_name: "Bayer, Uwe",
            Columns.position: 1,
            Columns.score: 149.0,
            Columns.points: 0.0,
        },
        {
            **common,
            Columns.team_name: "7 Schwaben Neu-Ulm 1",
            Columns.team_name_opponent: "City-Bowling Augsburg 2",
            Columns.player_name: "Strahl, Felix",
            Columns.position: 2,
            Columns.score: 179.0,
            Columns.points: 0.0,
        },
        {
            **common,
            Columns.team_name: "City-Bowling Augsburg 2",
            Columns.team_name_opponent: "7 Schwaben Neu-Ulm 1",
            Columns.player_name: "Musiol, Leo",
            Columns.position: 0,
            Columns.score: 106.0,
            Columns.points: 0.0,
        },
        {
            **common,
            Columns.team_name: "7 Schwaben Neu-Ulm 1",
            Columns.team_name_opponent: "City-Bowling Augsburg 2",
            Columns.player_name: "Team Total",
            Columns.position: 0,
            Columns.score: 328.0,
            Columns.points: 2.0,
            Columns.computed_data: True,
        },
        {
            **common,
            Columns.team_name: "City-Bowling Augsburg 2",
            Columns.team_name_opponent: "7 Schwaben Neu-Ulm 1",
            Columns.player_name: "Team Total",
            Columns.position: 0,
            Columns.score: 106.0,
            Columns.points: 0.0,
            Columns.computed_data: True,
        },
    ]
    service = _service_with_rows(*rows)
    table = service.get_game_team_details_data(
        season="11/12",
        league="BZL S2",
        week=2,
        team="7 Schwaben Neu-Ulm 1",
        round_number=4,
    )

    assert table.data
    first_row = table.data[0]
    assert first_row[0] == "Bayer, Uwe"
    assert first_row[4] == 106
    assert first_row[5] == "Musiol, Leo"
    assert table.data[1][5] == ""


def test_lineup_slot_lookup_normalizes_one_based_positions():
    df = pd.DataFrame(
        [
            {Columns.position: 1, Columns.player_name: "A"},
            {Columns.position: 4, Columns.player_name: "D"},
        ]
    )
    lookup = _lineup_slot_lookup(df)
    assert lookup[0][Columns.player_name] == "A"
    assert lookup[3][Columns.player_name] == "D"
