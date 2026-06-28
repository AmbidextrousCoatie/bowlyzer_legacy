"""LeagueService warm-slice memoization."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from app.services.league_service import LeagueService
from data_access.schema import Columns


class _CountingAdapter:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.calls = 0

    def get_filtered_data(self, filters=None, columns=None):
        self.calls += 1
        work = self.df
        if filters:
            for col, spec in filters.items():
                if col not in work.columns:
                    continue
                value = spec.get("value")
                if col == Columns.computed_data:
                    want = "true" if bool(value) else "false"
                    work = work.loc[work[col].astype(str).str.lower().eq(want)]
                elif spec.get("operator") == "eq":
                    work = work.loc[work[col].astype(str).str.strip().eq(str(value).strip())]
        if columns:
            keep = [c for c in columns if c in work.columns]
            work = work[keep]
        return work.copy()


def _service(adapter: _CountingAdapter) -> LeagueService:
    service = LeagueService.__new__(LeagueService)
    service.database = "test_db"
    service.adapter = adapter
    service.stats_service = SimpleNamespace()
    service._warm_slice_cache = None
    return service


def test_season_league_dataframe_cached_during_warm():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL"],
            Columns.computed_data: ["false", "true"],
            Columns.team_name: ["A", "A"],
            Columns.week: [1, 1],
            Columns.score: [200, 10],
            Columns.points: [2, 1],
        }
    )
    adapter = _CountingAdapter(df)
    service = _service(adapter)
    service.warm_slice_cache_begin()

    a = service._season_league_dataframe("BayL", "25/26", computed_data=False)
    b = service._season_league_dataframe("BayL", "25/26", computed_data=False)
    c = service._season_league_dataframe("BayL", "25/26", computed_data=True)

    service.warm_slice_cache_end()

    assert adapter.calls == 2
    assert len(a) == 1
    assert len(b) == 1
    assert len(c) == 1


def test_team_points_simple_uses_warm_cache():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL", "BayL"],
            Columns.computed_data: ["false", "false", "true"],
            Columns.team_name: ["A", "A", "A"],
            Columns.week: [1, 2, 1],
            Columns.score: [200, 210, 0],
            Columns.points: [2, 2, 1],
        }
    )
    adapter = _CountingAdapter(df)
    service = _service(adapter)
    service.warm_slice_cache_begin()

    service.get_team_points_simple("BayL", "25/26")
    service.get_team_averages_simple("BayL", "25/26")
    service.get_team_positions_simple("BayL", "25/26")

    service.warm_slice_cache_end()

    assert adapter.calls == 2
