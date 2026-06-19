"""Tests for per-matchday league points pool analysis."""

import pandas as pd

from data_access.league_points_budget import compute_league_points_budget
from data_access.league_weekly_points_analysis import (
    analyze_weekly_points_divergence,
    compute_weekly_points_pool_from_dataframe,
    format_no_show_findings,
    no_show_teams_by_week_from_reference,
    no_shows_by_week_from_reference,
    parse_pre_2022_tabelle_weekly_points_pool,
    parse_tabges_weekly_team_points,
    weekly_pool_from_team_points,
)
from data_access.schema import Columns


def _tabges_df() -> pd.DataFrame:
    rows_data = [
        ["Pl.", "Mannschaften", "Spieltag 1", None, "Spieltag 2", None, "Gesamt", None],
        [None, None, "Pins", "Pkt.", "Pins", "Pkt.", "Pins", "Pkt."],
        [1, "Team Alpha", 100, 20, 110, 22, 210, 42],
        [2, "Team Beta", 90, 18, 95, 19, 185, 37],
    ]
    return pd.DataFrame(rows_data)


def test_parse_tabges_weekly_team_points():
    weekly = parse_tabges_weekly_team_points(_tabges_df())
    assert weekly[1]["Team Alpha"] == 20.0
    assert weekly[2]["Team Beta"] == 19.0
    pool = weekly_pool_from_team_points(weekly)
    assert pool[1] == 38.0
    assert pool[2] == 41.0


def test_compute_weekly_points_pool_from_dataframe():
    df = pd.DataFrame(
        [
            {
                Columns.season: "10/11",
                Columns.event: "A S1",
                Columns.event_type: "league",
                Columns.week: "1",
                Columns.team_name: "Team Alpha",
                Columns.points: "10",
                Columns.bonus_points: "5",
                Columns.computed_data: "True",
            },
            {
                Columns.season: "10/11",
                Columns.event: "A S1",
                Columns.event_type: "league",
                Columns.week: "1",
                Columns.team_name: "Team Beta",
                Columns.points: "8",
                Columns.bonus_points: "4",
                Columns.computed_data: "True",
            },
            {
                Columns.season: "10/11",
                Columns.event: "A S1",
                Columns.event_type: "league",
                Columns.week: "2",
                Columns.team_name: "Team Alpha",
                Columns.points: "12",
                Columns.bonus_points: "0",
                Columns.computed_data: "True",
            },
        ]
    )
    pools = compute_weekly_points_pool_from_dataframe(
        df,
        league="A S1",
        season="10/11",
        max_week=2,
    )
    assert pools[1] == 27.0
    assert pools[2] == 12.0


def test_analyze_weekly_points_divergence_lists_off_weeks():
    budget = compute_league_points_budget(
        league="A S1",
        season="10/11",
        number_of_teams=5,
        reference_weeks=2,
        games_per_week=5,
        data_format="data_format_pre_2022",
        phantom_bye=True,
    )
    lines = analyze_weekly_points_divergence(
        reference_weekly={1: 38.0, 2: 41.0},
        computed_weekly={1: 50.0, 2: 41.0},
        budget=budget,
        reference_total_ok=False,
        computed_total_ok=False,
    )
    assert len(lines) >= 1
    assert lines[0].startswith("pts-week: W1")
    assert "comp-ref" in lines[0]


def test_parse_pre_2022_tabelle_weekly_points_pool():
    rows = [
        [None] * 15,
        [None] * 15,
        [None] * 15,
        [None, "5", "Spieltag"] + [None] * 12,
        [None] * 15,
        [None] * 15,
        [None, None, "Mannschaft", None, None, "Vortag", None, None, None, None, None, "Spieltag"] + [None] * 4,
        [None] * 11 + ["Pins", "Punkte", "Bonus", "Total"],
        [None, 1, "Pfaffenhofen 1"] + [None] * 8 + [3290, 8, 6, 14],
        [None, 2, "EPA 2"] + [None] * 8 + [3402, 8, 5, 13],
        [None, 6, "Lauterach 1"] + [None] * 8 + [0, 0, 0, 0],
    ]
    df = pd.DataFrame(rows)
    assert parse_pre_2022_tabelle_weekly_points_pool(df) == {5: 27.0}


def test_analyze_weekly_points_uses_no_show_adjusted_expected():
    from data_access.league_points_budget import apply_no_show_adjustments

    budget = apply_no_show_adjustments(
        compute_league_points_budget(
            league="BL S1 (D)",
            season="10/11",
            number_of_teams=6,
            reference_weeks=8,
            games_per_week=5,
            data_format="data_format_pre_2022",
        ),
        {5: 1},
    )
    lines = analyze_weekly_points_divergence(
        reference_weekly={5: 50.0},
        computed_weekly={5: 50.0},
        budget=budget,
        reference_total_ok=True,
        computed_total_ok=True,
        has_points_mismatches=False,
        include_when_totals_ok=True,
    )
    assert lines == []


def test_no_shows_by_week_from_reference():
    weekly = {
        4: {"A": 12.0, "B": 10.0},
        5: {"A": 14.0, "B": 13.0, "Lauterach 1": 0.0},
    }
    assert no_shows_by_week_from_reference(weekly) == {5: 1}
    assert no_show_teams_by_week_from_reference(weekly) == {5: ["Lauterach 1"]}
    assert format_no_show_findings({5: ["SG Rottendorf 5"]}) == ["no-show W5: SG Rottendorf 5"]


def test_analyze_weekly_points_skips_when_totals_ok():
    budget = compute_league_points_budget(
        league="BayL",
        season="24/25",
        number_of_teams=10,
        reference_weeks=1,
        games_per_week=9,
        data_format="data_format_post_2022",
    )
    expected = budget.weekly_total_points
    lines = analyze_weekly_points_divergence(
        reference_weekly={1: expected},
        computed_weekly={1: expected},
        budget=budget,
        reference_total_ok=True,
        computed_total_ok=True,
    )
    assert lines == []
