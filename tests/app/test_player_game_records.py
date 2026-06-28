"""Player highest games and Club 300 endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.player_service import PlayerService
from data_access.schema import Columns
from types import SimpleNamespace


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _service_with_df(df: pd.DataFrame) -> PlayerService:
    service = PlayerService.__new__(PlayerService)
    service.database = "test_db"
    service.data_manager = SimpleNamespace(df=df, current_source="test_db")
    return service


def test_get_highest_individual_games_orders_by_score():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26", "24/25"],
            Columns.league_name: ["BayL", "BayL", "BayL"],
            Columns.player_name: ["Alice", "Bob", "Carol"],
            Columns.player_id: ["1", "2", "3"],
            Columns.score: [299, 300, 280],
            Columns.date: ["2025-01-10", "2025-02-01", "2024-11-05"],
            Columns.input_data: ["true", "true", "true"],
            Columns.computed_data: ["false", "false", "false"],
        }
    )
    service = _service_with_df(df)
    games = service.get_highest_individual_games(limit=2)
    assert len(games) == 2
    assert games[0]["score"] == 300
    assert games[0]["player_name"] == "Bob"
    assert games[1]["score"] == 299


def test_get_club_300_games_newest_first():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL"],
            Columns.player_name: ["Alice", "Bob"],
            Columns.player_id: ["1", "2"],
            Columns.score: [300, 300],
            Columns.date: ["2025-01-10", "2025-03-15"],
            Columns.input_data: ["true", "true"],
            Columns.computed_data: ["false", "false"],
        }
    )
    service = _service_with_df(df)
    games = service.get_club_300_games()
    assert len(games) == 2
    assert games[0]["player_name"] == "Bob"
    assert games[1]["player_name"] == "Alice"


def test_get_highest_individual_games_route(client):
    sample = [{"player_name": "Alice", "score": 300, "competition": "BayL"}]

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        service.get_highest_individual_games.return_value = sample
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=None):
            with patch("app.routes.player_routes.league_cache_put"):
                res = client.get(
                    "/player/get_highest_individual_games?database=db_real_merged&limit=5"
                )

    assert res.status_code == 200
    assert res.get_json() == sample
    service.get_highest_individual_games.assert_called_once_with(
        limit=5,
        player_name="",
        player_id="",
        season="all",
    )


def test_get_highest_individual_games_for_player():
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL", "BayL"],
            Columns.player_name: ["Alice", "Alice", "Bob"],
            Columns.player_id: ["1", "1", "2"],
            Columns.score: [250, 290, 300],
            Columns.date: ["2025-01-10", "2025-02-01", "2025-03-01"],
            Columns.input_data: ["true", "true", "true"],
            Columns.computed_data: ["false", "false", "false"],
        }
    )
    service = _service_with_df(df)
    games = service.get_highest_individual_games(limit=5, player_name="Alice", player_id="1")
    assert len(games) == 2
    assert games[0]["score"] == 290
    assert games[0]["player_name"] == "Alice"


def test_get_highest_individual_games_player_route(client):
    sample = [{"player_name": "Alice", "score": 290, "competition": "BayL"}]

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        service.get_highest_individual_games.return_value = sample
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=None):
            with patch("app.routes.player_routes.league_cache_put"):
                res = client.get(
                    "/player/get_highest_individual_games"
                    "?database=db_real_merged"
                    "&limit=10"
                    "&player_name=Alice"
                    "&player_id=1"
                    "&season=all"
                )

    assert res.status_code == 200
    assert res.get_json() == sample
    service.get_highest_individual_games.assert_called_once_with(
        limit=10,
        player_name="Alice",
        player_id="1",
        season="all",
    )


def test_get_club_300_route(client):
    sample = [{"player_name": "Alice", "score": 300, "date": "2025-01-10"}]

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        service.get_club_300_games.return_value = sample
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=None):
            with patch("app.routes.player_routes.league_cache_put"):
                res = client.get("/player/get_club_300?database=db_real_merged")

    assert res.status_code == 200
    assert res.get_json() == sample
    service.get_club_300_games.assert_called_once_with()
