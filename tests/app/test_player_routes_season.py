"""Player API season query normalization."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_lifetime_stats_normalizes_hyphen_season(client):
    sample = {
        "lifetime": {"total_games": 12, "average_score": 180.5},
        "seasons": [{"season": "10/11", "row_type": "season_total", "games": 12}],
    }

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        service.get_lifetime_stats.return_value = sample
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=None):
            with patch("app.routes.player_routes.league_cache_put"):
                res = client.get(
                    "/player/get_lifetime_stats"
                    "?database=db_real_merged"
                    "&player_name=Feller%2C+Christian"
                    "&player_id=16007"
                    "&season=10-11"
                )

    assert res.status_code == 200
    service.get_lifetime_stats.assert_called_once_with(
        "Feller, Christian",
        season="10/11",
        player_id="16007",
    )


def test_get_lifetime_stats_all_players_without_selection(client):
    sample = {
        "scope": "all",
        "lifetime": {"total_games": 100, "average_score": 175.0},
        "seasons": [],
        "player_competitions": [],
        "player_season_totals": [],
        "periods": [],
    }

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        service.get_aggregate_lifetime_stats.return_value = sample
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=None):
            with patch("app.routes.player_routes.league_cache_put"):
                res = client.get("/player/get_lifetime_stats?database=db_real_merged&season=all")

    assert res.status_code == 200
    assert res.headers.get("X-League-Cache") == "MISS"
    service.get_aggregate_lifetime_stats.assert_called_once_with(season="all")
    service.get_lifetime_stats.assert_not_called()


def test_get_lifetime_stats_cache_hit_sets_header(client):
    sample = {"scope": "all", "lifetime": {"total_games": 1}, "seasons": []}

    with patch("app.routes.player_routes.get_player_service") as mock_svc:
        service = MagicMock()
        service.database = "db_real_merged"
        mock_svc.return_value = service

        with patch("app.routes.player_routes.league_cache_try_get", return_value=sample):
            res = client.get("/player/get_lifetime_stats?database=db_real_merged&season=16-17")

    assert res.status_code == 200
    assert res.headers.get("X-League-Cache") == "HIT"
    service.get_aggregate_lifetime_stats.assert_not_called()
