"""Special matches (Besondere Momente) use per-match rows only."""

from __future__ import annotations

import pandas as pd

from app.services.team_service import TeamService
from data_access.schema import Columns


def _roster_rows(*entries: dict) -> pd.DataFrame:
    return pd.DataFrame(list(entries))


def _service_with_matches(
    computed: pd.DataFrame,
    roster: pd.DataFrame | None = None,
) -> TeamService:
    svc = object.__new__(TeamService)
    svc.database = "db_test"

    class _FakeAdapter:
        def get_filtered_data(self, filters, columns=None):
            return roster.copy() if roster is not None else pd.DataFrame()

    class _FakeServer:
        data_adapter = _FakeAdapter()

        def get_matches(self, **kwargs):
            return computed

    svc.server = _FakeServer()
    return svc


def test_special_matches_excludes_weekly_totals():
    computed = pd.DataFrame(
        [
            {
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.week: 3,
                Columns.round_number: 0,
                Columns.team_name: "Club 1",
                Columns.score: 5500.0,
                Columns.team_name_opponent: "Club 2",
                "opponent_score": 0.0,
            },
            {
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.week: 3,
                Columns.round_number: 2,
                Columns.team_name: "Club 1",
                Columns.score: 880.0,
                Columns.team_name_opponent: "Club 2",
                "opponent_score": 720.0,
            },
            {
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.week: 4,
                Columns.round_number: 1,
                Columns.team_name: "Club 1",
                Columns.score: 650.0,
                Columns.team_name_opponent: "Club 3",
                "opponent_score": 710.0,
            },
        ]
    )
    roster = _roster_rows(
        *[
            {
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.week: week,
                Columns.round_number: rnd,
                Columns.team_name: team,
                Columns.player_name: f"P{i}",
                Columns.players_per_team: 4,
            }
            for week, rnd, team, n in (
                (3, 2, "Club 1", 4),
                (3, 2, "Club 2", 4),
                (4, 1, "Club 1", 4),
                (4, 1, "Club 3", 4),
            )
            for i in range(n)
        ]
    )

    result = _service_with_matches(computed, roster).get_special_matches(team_name="Club 1")

    assert result["highest_scores"][0]["Score"] == 880.0
    assert result["highest_scores"][0]["Round"] == 2
    assert result["lowest_scores"][0]["Score"] == 650.0
    assert result["biggest_win_margin"][0]["WinMargin"] == 160.0
    assert result["biggest_loss_margin"][0]["WinMargin"] == -60.0


def test_special_matches_excludes_bye_and_partial_lineups():
    computed = pd.DataFrame(
        [
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 2,
                Columns.round_number: 4,
                Columns.team_name: "Club 1",
                Columns.score: 751.0,
                Columns.team_name_opponent: "Club 2",
                "opponent_score": 106.0,
            },
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 3,
                Columns.round_number: 1,
                Columns.team_name: "Club 1",
                Columns.score: 820.0,
                Columns.team_name_opponent: "Club 3",
                "opponent_score": 790.0,
            },
        ]
    )
    roster = _roster_rows(
        *[
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 2,
                Columns.round_number: 4,
                Columns.team_name: "Club 1",
                Columns.player_name: f"A{i}",
                Columns.players_per_team: 4,
            }
            for i in range(4)
        ],
        *[
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 2,
                Columns.round_number: 4,
                Columns.team_name: "Club 2",
                Columns.player_name: "Solo",
                Columns.players_per_team: 4,
            }
        ],
        *[
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 3,
                Columns.round_number: 1,
                Columns.team_name: team,
                Columns.player_name: f"{team}-{i}",
                Columns.players_per_team: 4,
            }
            for team in ("Club 1", "Club 3")
            for i in range(4)
        ],
    )

    result = _service_with_matches(computed, roster).get_special_matches(team_name="Club 1")

    assert result["highest_scores"][0]["Score"] == 820.0
    assert result["biggest_win_margin"][0]["WinMargin"] == 30.0
    assert all(m["Score"] != 751.0 for m in result["highest_scores"])
    assert all(m["WinMargin"] != 645.0 for m in result["biggest_win_margin"])


def test_special_matches_excludes_all_when_roster_unavailable():
    """If roster lookup fails/empty, do not fall back to unfiltered matches."""
    computed = pd.DataFrame(
        [
            {
                Columns.season: "11/12",
                Columns.league_name: "BZL S2",
                Columns.week: 2,
                Columns.round_number: 4,
                Columns.team_name: "Club 1",
                Columns.score: 751.0,
                Columns.team_name_opponent: "Club 2",
                "opponent_score": 106.0,
            },
        ]
    )
    result = _service_with_matches(computed, roster=pd.DataFrame()).get_special_matches(
        team_name="Club 1"
    )
    assert result == {}
