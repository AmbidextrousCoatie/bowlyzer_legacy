"""Tests for process-local pandas adapter cache and metadata indexes."""

import pandas as pd

from data_access.adapters.data_adapter_pandas import DataAdapterPandas
from data_access.schema import Columns
from data_access.shared_pandas_store import build_league_metadata_index, invalidate_adapter_cache


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            Columns.season: ["10/11", "10/11", "11/12"],
            Columns.league_name: ["BayL", "BayL", "KL N1"],
            Columns.week: [1, 2, 1],
            Columns.team_name: ["Team A 1", "Team B 1", "Team C 1"],
            Columns.computed_data: ["False", "False", "False"],
        }
    )


def test_metadata_index_seasons_and_leagues():
    meta = build_league_metadata_index(_sample_df())
    assert meta.seasons_all == ["10/11", "11/12"]
    assert meta.leagues_by_season["10/11"] == ["BayL"]
    assert meta.weeks_by_season_league[("10/11", "BayL")] == [1, 2]
    assert meta.teams_all == ["Team A 1", "Team B 1", "Team C 1"]


def test_adapter_uses_metadata_fast_path():
    invalidate_adapter_cache()
    adapter = DataAdapterPandas(df=_sample_df())
    assert adapter.get_seasons() == ["10/11", "11/12"]
    assert adapter.get_leagues(season="10/11") == ["BayL"]
    assert adapter.get_weeks(season="10/11", league="BayL") == [1, 2]
    assert adapter.get_all_teams() == ["Team A 1", "Team B 1", "Team C 1"]
