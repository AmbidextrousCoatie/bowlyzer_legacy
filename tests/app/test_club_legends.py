"""Club legends aggregates top player metrics per club."""

from unittest.mock import MagicMock

import pandas as pd

from app.services.club_legends_service import ClubLegendsService
from data_access.schema import Columns


def _league_row(**overrides):
    base = {
        Columns.season: "2023/2024",
        Columns.player_name: "Alpha, A",
        Columns.player_id: "A",
        Columns.club: "Test Club",
        Columns.score: 200.0,
        Columns.input_data: "TRUE",
        Columns.computed_data: "FALSE",
        Columns.event_type: "league",
    }
    base.update(overrides)
    return base


def _service_with_df(rows: list) -> ClubLegendsService:
    svc = object.__new__(ClubLegendsService)
    svc.league_database = "test_db"
    svc.player_database = "test_player"
    svc._league_service = MagicMock()
    svc._league_service.get_available_clubs.return_value = ["Test Club"]
    svc._league_service.resolve_club_name.side_effect = lambda name, _clubs: name
    svc._player_service = MagicMock()
    svc._player_service.data_manager.df = pd.DataFrame(rows)
    svc._league_games = None
    return svc


def test_club_legends_ranks_seasons_games_and_averages():
    rows = []
    for season in ("2021/2022", "2022/2023", "2023/2024"):
        for _ in range(10):
            rows.append(
                _league_row(
                    **{
                        Columns.season: season,
                        Columns.player_name: "Alpha, A",
                        Columns.player_id: "A",
                        Columns.score: 180,
                    }
                )
            )
    for _ in range(15):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2023/2024",
                    Columns.player_name: "Beta, B",
                    Columns.player_id: "B",
                    Columns.score: 220,
                }
            )
        )
    rows.append(
        _league_row(
            **{
                Columns.player_name: "Other",
                Columns.player_id: "X",
                Columns.club: "Other Club",
                Columns.score: 250,
            }
        )
    )

    result = _service_with_df(rows).get_club_legends("Test Club")

    assert result["club"] == "Test Club"
    assert result["most_seasons"][0]["player_name"] == "Alpha, A"
    assert result["most_seasons"][0]["value"] == 3
    assert result["most_games"][0]["player_name"] == "Alpha, A"
    assert result["most_games"][0]["value"] == 30
    assert result["highest_average"][0]["player_name"] == "Beta, B"
    assert result["highest_average"][0]["games"] == 15
    assert result["best_seasons"][0]["player_name"] == "Beta, B"
    assert result["best_seasons"][0]["season"] == "2023/2024"


def test_club_legends_ranks_teams_and_leagues():
    rows = []
    for team_name in ("Test Club 1", "Test Club 2", "Test Club 3"):
        rows.append(
            _league_row(
                **{
                    Columns.team_name: team_name,
                    Columns.league_name: "KL",
                    Columns.player_name: "Rover, R",
                    Columns.player_id: "R",
                    Columns.score: 190,
                }
            )
        )
    for league in ("KL", "BL", "BZOL"):
        rows.append(
            _league_row(
                **{
                    Columns.team_name: "Test Club 1",
                    Columns.league_name: league,
                    Columns.player_name: "Wide, W",
                    Columns.player_id: "W",
                    Columns.score: 185,
                }
            )
        )
    rows.append(
        _league_row(
            **{
                Columns.team_name: "Test Club 1",
                Columns.league_name: "KL",
                Columns.player_name: "Single, S",
                Columns.player_id: "S",
                Columns.score: 200,
            }
        )
    )

    result = _service_with_df(rows).get_club_legends("Test Club")

    assert result["most_teams_represented"][0]["player_name"] == "Rover, R"
    assert result["most_teams_represented"][0]["value"] == 3
    assert result["most_teams_represented"][0]["teams"] == ["1", "2", "3"]
    assert result["most_leagues_seen"][0]["player_name"] == "Wide, W"
    assert result["most_leagues_seen"][0]["value"] == 3
    assert set(result["most_leagues_seen"][0]["leagues"]) == {"BL", "BZOL", "KL"}
    assert "Single, S" not in [e["player_name"] for e in result["most_teams_represented"]]
    assert "Single, S" not in [e["player_name"] for e in result["most_leagues_seen"]]


def test_club_legends_uses_registry_canonical_name(monkeypatch):
    """Same player_id with seasonal spelling variants → one canonical label."""
    rows = []
    for season, name, score in (
        ("12/13", "Glasl, Hans-Jürgen Jun", 220),
        ("13/14", "Glasl, Hans Jürgen Jun.", 219),
        ("14/15", "Glasl Jun., Hans-Jürgen", 218),
    ):
        for _ in range(8):
            rows.append(
                _league_row(
                    **{
                        Columns.season: season,
                        Columns.player_name: name,
                        Columns.player_id: "7408",
                        Columns.score: score,
                    }
                )
            )

    monkeypatch.setattr(
        "data_access.players_registry.load_players_registry_df",
        lambda: pd.DataFrame(
            [
                {
                    "player_id": "7408",
                    "canonical_name": "Glasl, Hans-Jürgen",
                    "aliases": "",
                    "source": "test",
                    "player_id_legacy": "",
                    "player_id_pass": "",
                }
            ]
        ),
    )

    result = _service_with_df(rows).get_club_legends("Test Club")
    names = [e["player_name"] for e in result["best_seasons"]]
    assert names
    assert set(names) == {"Glasl, Hans-Jürgen"}


def test_club_legends_filters_to_selected_season():
    rows = []
    for _ in range(15):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2022/2023",
                    Columns.player_name: "Alpha, A",
                    Columns.player_id: "A",
                    Columns.score: 250,
                }
            )
        )
    for _ in range(15):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2023/2024",
                    Columns.player_name: "Beta, B",
                    Columns.player_id: "B",
                    Columns.score: 180,
                }
            )
        )

    result = _service_with_df(rows).get_club_legends("Test Club", season="2023/2024")

    assert result["most_seasons"] == []
    assert result["best_seasons"] == []
    games_names = [e["player_name"] for e in result["most_games"]]
    assert games_names[0] == "Beta, B"
    assert "Alpha, A" not in games_names
    assert result["most_games"][0]["value"] == 15
    avg_names = [e["player_name"] for e in result["highest_average"]]
    assert avg_names[0] == "Beta, B"
    assert "Alpha, A" not in avg_names


def test_club_legends_season_all_keeps_alltime():
    rows = []
    for season in ("2022/2023", "2023/2024"):
        for _ in range(8):
            rows.append(
                _league_row(
                    **{
                        Columns.season: season,
                        Columns.player_name: "Alpha, A",
                        Columns.player_id: "A",
                        Columns.score: 180,
                    }
                )
            )

    result = _service_with_df(rows).get_club_legends("Test Club", season="all")
    assert result["most_seasons"][0]["value"] == 2
    assert result["most_games"][0]["value"] == 16


def test_get_club_legends_route_returns_json():
    from app import create_app

    app = create_app()
    client = app.test_client()
    response = client.get(
        "/league/get_club_legends",
        query_string={"database": "db_real_merged", "club": "Donaubowler Regensburg"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "most_seasons" in data
    assert "most_games" in data
    assert "highest_average" in data
    assert "best_seasons" in data
    assert "most_teams_represented" in data
    assert "most_leagues_seen" in data
