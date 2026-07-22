"""Cross-club rankings for the club page empty state."""

from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.club_rankings_service import ClubRankingsService
from data_access.schema import Columns


def _league_row(**overrides):
    base = {
        Columns.season: "2023/2024",
        Columns.player_name: "Alpha, A",
        Columns.player_id: "A",
        Columns.club: "Club A",
        Columns.team_name: "Club A 1",
        Columns.score: 200.0,
        Columns.input_data: "TRUE",
        Columns.computed_data: "FALSE",
        Columns.event_type: "league",
        Columns.league_name: "BayL",
        Columns.week: "1",
        Columns.round_number: "1",
        Columns.points: 1.0,
    }
    base.update(overrides)
    return base


def _service_with_player_rows(rows: list) -> ClubRankingsService:
    svc = object.__new__(ClubRankingsService)
    svc.league_database = "test_db"
    svc._tournament_database = None
    svc._league_service = MagicMock()
    svc._league_service.get_available_clubs.return_value = ["Club A", "Club B"]
    svc._league_service.resolve_club_name.side_effect = lambda name, _clubs: str(name or "").strip()
    svc._league_service._split_club_and_team_number.side_effect = lambda team: (
        str(team).rsplit(" ", 1)[0] if str(team).rsplit(" ", 1)[-1].isdigit() else str(team),
        str(team).rsplit(" ", 1)[-1] if str(team).rsplit(" ", 1)[-1].isdigit() else "",
    )
    svc._league_service.adapter.get_filtered_data.side_effect = _adapter_side_effect(rows)
    return svc


def _adapter_side_effect(all_rows: list):
    df = pd.DataFrame(all_rows)

    def _get_filtered_data(filters=None, columns=None):
        work = df.copy()
        filters = filters or {}
        if Columns.computed_data in filters:
            want_true = filters[Columns.computed_data]["value"] is True
            mask = work[Columns.computed_data].astype(str).str.upper().eq("TRUE" if want_true else "FALSE")
            work = work.loc[mask]
        if columns:
            keep = [c for c in columns if c in work.columns]
            work = work[keep]
        return work

    return _get_filtered_data


@patch("app.services.player_service.PlayerService")
def test_club_rankings_pinfall_and_members(mock_player_service):
    rows = [
        _league_row(**{Columns.club: "Club A", Columns.player_id: "A1", Columns.score: 200}),
        _league_row(**{Columns.club: "Club A", Columns.player_id: "A2", Columns.score: 180}),
        _league_row(**{Columns.club: "Club B", Columns.player_id: "B1", Columns.score: 210}),
        _league_row(**{Columns.club: "Club B", Columns.player_id: "B1", Columns.score: 210}),
        _league_row(**{Columns.club: "Club B", Columns.player_id: "B1", Columns.score: 210}),
    ]
    mock_player_service.return_value.data_manager.df = pd.DataFrame(rows)

    svc = _service_with_player_rows(rows)
    with patch.object(svc, "_tournament_wins", return_value=[]):
        result = svc.get_club_rankings(top_n=3)

    assert result["highest_total_pinfall"][0]["club"] == "Club B"
    assert result["highest_total_pinfall"][0]["value"] == 630
    assert result["most_members"][0]["club"] == "Club A"
    assert result["most_members"][0]["value"] == 2
    assert "most_games" not in result


@patch("app.services.player_service.PlayerService")
def test_club_rankings_team_averages(mock_player_service):
    rows = [
        _league_row(
            **{
                Columns.team_name: "Club A 1",
                Columns.player_name: "P1",
                Columns.score: 240,
                Columns.week: "1",
                Columns.round_number: "1",
            }
        ),
        _league_row(
            **{
                Columns.team_name: "Club A 1",
                Columns.player_name: "P2",
                Columns.score: 260,
                Columns.week: "1",
                Columns.round_number: "1",
            }
        ),
        _league_row(
            **{
                Columns.team_name: "Club A 1",
                Columns.player_name: "P1",
                Columns.score: 200,
                Columns.week: "1",
                Columns.round_number: "2",
            }
        ),
        _league_row(
            **{
                Columns.team_name: "Club A 1",
                Columns.player_name: "P2",
                Columns.score: 200,
                Columns.week: "1",
                Columns.round_number: "2",
            }
        ),
        _league_row(
            **{
                Columns.team_name: "Club B 1",
                Columns.player_name: "Q1",
                Columns.score: 280,
                Columns.week: "2",
                Columns.round_number: "1",
            }
        ),
        _league_row(
            **{
                Columns.team_name: "Club B 1",
                Columns.player_name: "Q2",
                Columns.score: 280,
                Columns.week: "2",
                Columns.round_number: "1",
            }
        ),
    ]
    mock_player_service.return_value.data_manager.df = pd.DataFrame([])

    svc = _service_with_player_rows(rows)
    with patch.object(svc, "_tournament_wins", return_value=[]), patch.object(
        svc, "_league_wins", return_value=[]
    ):
        result = svc.get_club_rankings(top_n=2)

    assert result["highest_team_game_average"][0]["club"] == "Club B"
    assert result["highest_team_game_average"][0]["value"] == 280.0
    assert result["highest_team_game_average"][0]["match_total"] == 560
    assert result["highest_weekly_team_average"][0]["club"] == "Club B"
    assert result["highest_weekly_team_average"][0]["value"] == 280.0


@patch("app.services.player_service.PlayerService")
def test_club_rankings_league_wins(mock_player_service):
    rows = [
        _league_row(
            **{
                Columns.season: "23/24",
                Columns.league_name: "BayL",
                Columns.team_name: "Club A 1",
                Columns.points: 30,
            }
        ),
        _league_row(
            **{
                Columns.season: "23/24",
                Columns.league_name: "BayL",
                Columns.team_name: "Club B 1",
                Columns.points: 20,
            }
        ),
        _league_row(
            **{
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.team_name: "Club B 1",
                Columns.points: 35,
            }
        ),
        _league_row(
            **{
                Columns.season: "24/25",
                Columns.league_name: "BayL",
                Columns.team_name: "Club A 1",
                Columns.points: 25,
            }
        ),
    ]
    mock_player_service.return_value.data_manager.df = pd.DataFrame([])

    svc = _service_with_player_rows(rows)
    with patch.object(svc, "_tournament_wins", return_value=[]):
        result = svc.get_club_rankings(top_n=3)

    by_club = {entry["club"]: entry["value"] for entry in result["most_league_wins"]}
    assert by_club["Club A"] == 1
    assert by_club["Club B"] == 1


def test_get_club_rankings_route():
    from app import create_app

    payload = {
        "top_n": 5,
        "highest_total_pinfall": [{"club": "Club A", "value": 10}],
        "most_members": [],
        "highest_weekly_team_average": [],
        "highest_team_game_average": [],
        "most_tournament_wins": [],
        "most_league_wins": [],
    }
    with patch(
        "app.services.club_rankings_service.ClubRankingsService.get_club_rankings",
        return_value=payload,
    ):
        with patch("app.routes.league_routes._league_json_cache_get", return_value=None):
            with patch("app.routes.league_routes._league_json_cache_put"):
                app = create_app()
                client = app.test_client()
                res = client.get("/league/get_club_rankings?database=db_real_merged")
    assert res.status_code == 200
    data = res.get_json()
    assert data["highest_total_pinfall"][0]["club"] == "Club A"
