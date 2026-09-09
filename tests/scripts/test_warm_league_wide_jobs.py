"""League-wide warm job plan."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WARM = ROOT / "scripts" / "warm_league_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_league_cache_test", WARM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


warm = _load()


def test_league_wide_jobs_omits_record_games_alias():
    jobs = warm._league_wide_jobs(object(), "db_real_merged", "BayL")
    endpoints = [job[0] for job in jobs]
    assert "get_record_games" not in endpoints
    assert "get_record_individual_games" in endpoints
    assert len(endpoints) == 6


def test_season_league_jobs_warms_timetable_as_dict():
    class _Table:
        def to_dict(self):
            return {"columns": [], "data": [[1, "TBD", "Brunnthal"]]}

    class _Ls:
        def get_season_timetable(self, *, league, season):
            return _Table()

        def get_league_history_table_data(self, *, league_name, season):
            return _Table()

        def get_team_points_simple(self, *, league_name, season):
            return {}

        def get_team_positions_simple(self, *, league_name, season):
            return {}

        def get_team_averages_simple(self, *, league_name, season):
            return {}

        def get_individual_averages(self, *, league, season, week, team):
            return _Table()

        def get_team_vs_team_comparison_table(self, league, season, _week):
            return _Table()

        def get_available_weeks(self, *, season, league):
            return []

    jobs = warm._season_league_jobs(_Ls(), "db_real_merged", "11/12", "A N1", {})
    endpoint, query, build = jobs[0]
    assert endpoint == "get_season_timetable"
    assert query == {"database": "db_real_merged", "league": "A N1", "season": "11/12"}
    assert build() == {"columns": [], "data": [[1, "TBD", "Brunnthal"]]}
