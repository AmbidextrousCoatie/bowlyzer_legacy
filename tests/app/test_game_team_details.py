"""Game team details densifies sparse Position values to API slots 0..ppt-1."""

from __future__ import annotations

import pandas as pd

from app.services.league_service import (
    LeagueService,
    _canonical_lineup_slots,
    _densify_position_map,
)
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns


def _service_with_rows(*rows: dict) -> LeagueService:
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=None)
    adapter.set_dataframe(pd.DataFrame(list(rows)))
    service = LeagueService(database=None)
    service.adapter = adapter
    return service


def test_densify_position_map_maps_sparse_to_contiguous():
    assert _densify_position_map([2, 4, 5, 6]) == {2: 0, 4: 1, 5: 2, 6: 3}
    assert _densify_position_map([1, 2, 3, 4]) == {1: 0, 2: 1, 3: 2, 4: 3}


def test_canonical_slots_densify_when_outside_expected_range():
    df = pd.DataFrame(
        [
            {Columns.position: 2, Columns.player_name: "A", Columns.score: 100},
            {Columns.position: 4, Columns.player_name: "B", Columns.score: 110},
            {Columns.position: 5, Columns.player_name: "C", Columns.score: 120},
            {Columns.position: 6, Columns.player_name: "D", Columns.score: 130},
        ]
    )
    slots = _canonical_lineup_slots(df, expected=4)
    assert set(slots) == {0, 1, 2, 3}
    assert slots[0][Columns.player_name] == "A"
    assert slots[3][Columns.player_name] == "D"


def test_canonical_slots_keep_vacant_lanes_inside_expected_range():
    """Post-2022: positions 0..3 with a hole keep the hole (H2H lane)."""
    df = pd.DataFrame(
        [
            {Columns.position: 0, Columns.player_name: "A", Columns.score: 100},
            {Columns.position: 1, Columns.player_name: "B", Columns.score: 110},
            {Columns.position: 3, Columns.player_name: "D", Columns.score: 130},
        ]
    )
    slots = _canonical_lineup_slots(df, expected=4)
    assert set(slots) == {0, 1, 3}
    assert 2 not in slots


def test_game_team_details_densifies_sparse_home_vs_partial_away():
    common = {
        Columns.season: "11/12",
        Columns.league_name: "BZL S2",
        Columns.week: 2,
        Columns.round_number: 4,
        Columns.players_per_team: 4,
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
            Columns.team_name: "7 Schwaben Neu-Ulm 1",
            Columns.team_name_opponent: "City-Bowling Augsburg 2",
            Columns.player_name: "Baumann, Timo",
            Columns.position: 3,
            Columns.score: 201.0,
            Columns.points: 0.0,
        },
        {
            **common,
            Columns.team_name: "7 Schwaben Neu-Ulm 1",
            Columns.team_name_opponent: "City-Bowling Augsburg 2",
            Columns.player_name: "Niesner, Christian",
            Columns.position: 4,
            Columns.score: 222.0,
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
            Columns.score: 751.0,
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

    # 4 player slots + team total + points sum row
    assert len(table.data) == 6
    assert table.data[0][0] == "Bayer, Uwe"
    assert table.data[0][4] == 106
    assert table.data[0][5] == "Musiol, Leo"
    assert table.data[1][0] == "Strahl, Felix"
    assert table.data[1][5] == ""
    assert table.data[3][0] == "Niesner, Christian"
    assert table.data[4][1] == 751  # team pins total
