"""Competition rank cache for all-players lifetime stats."""

from __future__ import annotations

import pandas as pd

from app.services.player_service import PlayerService, _CompetitionRankTable
from data_access.schema import Columns


from types import SimpleNamespace


def _service_with_df(df: pd.DataFrame) -> PlayerService:
    service = PlayerService.__new__(PlayerService)
    service.database = "test_db"
    service.data_manager = SimpleNamespace(df=df, current_source="test_db")
    return service


def test_league_competition_rank_table_matches_lookup():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26", "25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL", "BayL", "BayL"],
            Columns.player_name: ["Alice", "Alice", "Bob", "Bob"],
            Columns.player_id: ["1", "1", "2", "2"],
            Columns.score: [200, 220, 180, 190],
            Columns.input_data: ["true", "true", "true", "true"],
            Columns.computed_data: ["false", "false", "false", "false"],
        }
    )
    service = _service_with_df(df)
    table = service._league_competition_rank_table("25/26", "BayL")
    assert table.competitors == 2
    rank_alice, _ = service._lookup_competition_rank(
        table, "Alice", "1", normalize_player_id=service._normalize_player_id
    )
    rank_bob, _ = service._lookup_competition_rank(
        table, "Bob", "2", normalize_player_id=service._normalize_player_id
    )
    assert rank_alice == 1
    assert rank_bob == 2


def test_build_competition_rank_cache_deduplicates():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL"],
            Columns.player_name: ["Alice", "Bob"],
            Columns.player_id: ["1", "2"],
            Columns.score: [200, 180],
            Columns.input_data: ["true", "true"],
            Columns.computed_data: ["false", "false"],
        }
    )
    service = _service_with_df(df)
    cache = service._build_competition_rank_cache(df, comp_group_col=Columns.league_name)
    assert len(cache) == 1
    table = next(iter(cache.values()))
    assert isinstance(table, _CompetitionRankTable)
    assert table.competitors == 2
