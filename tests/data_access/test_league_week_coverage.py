import pandas as pd

from data_access.league_week_coverage import (
    WEEK_COVERAGE_CRITICAL,
    compute_league_season_week_coverage,
    discover_league_season_pairs,
)
from data_access.league_week_schema import expected_weeks_for_league_season
from data_access.schema import Columns


def test_expected_weeks_for_league_rules():
    assert expected_weeks_for_league_season("BayL", "24/25", team_count=10) == 6
    assert expected_weeks_for_league_season("BL S1 (D)", "09/10", team_count=5) == 8
    assert expected_weeks_for_league_season("BZOL S1", "24/25", team_count=8) == 6


def test_compute_league_season_week_coverage_missing_matchdays():
    rows = []
    for team in ("Alpha 1", "Beta 1"):
        rows.append(
            {
                Columns.season: "24/25",
                Columns.event: "BayL",
                Columns.event_type: "league",
                Columns.week: 1,
                Columns.team_name: team,
                Columns.computed_data: False,
            }
        )
    rows.append(
        {
            Columns.season: "24/25",
            Columns.event: "BayL",
            Columns.event_type: "league",
            Columns.week: 1,
            Columns.team_name: "Alpha 1",
            Columns.computed_data: True,
        }
    )
    df = pd.DataFrame(rows)
    coverage = compute_league_season_week_coverage(df, league="BayL", season="24/25")
    assert coverage.expected_weeks == 6
    assert coverage.available_weeks == [1]
    assert coverage.missing_weeks == [2, 3, 4, 5, 6]
    assert coverage.status == WEEK_COVERAGE_CRITICAL


def test_discover_league_season_pairs():
    df = pd.DataFrame(
        [
            {Columns.event: "BayL", Columns.season: "24/25", Columns.event_type: "league"},
            {Columns.event: "BayL", Columns.season: "24/25", Columns.event_type: "league"},
            {Columns.event: "LL S", Columns.season: "23/24", Columns.event_type: "league"},
        ]
    )
    assert discover_league_season_pairs(df) == [("BayL", "24/25"), ("LL S", "23/24")]
