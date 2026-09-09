import pandas as pd

from app.services.league_service import LeagueService
from data_access.schema import Columns


def test_matchup_nav_unique_round():
    matches = pd.DataFrame(
        {
            Columns.week: [6, 6],
            Columns.round_number: [2, 2],
        }
    )
    assert LeagueService._team_vs_team_matchup_nav(matches) == {"week": 6, "round": 2}


def test_matchup_nav_multiple_rounds_omits_round():
    matches = pd.DataFrame(
        {
            Columns.week: [4, 4],
            Columns.round_number: [1, 2],
        }
    )
    assert LeagueService._team_vs_team_matchup_nav(matches) == {"week": 4}


def test_matchup_nav_uses_latest_week():
    matches = pd.DataFrame(
        {
            Columns.week: [2, 5, 5],
            Columns.round_number: [1, 3, 3],
        }
    )
    assert LeagueService._team_vs_team_matchup_nav(matches) == {"week": 5, "round": 3}
