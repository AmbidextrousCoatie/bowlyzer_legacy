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
    service._players_registry_lookup = {}
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


def test_get_club_300_games_uses_registry_canonical_name():
    df = pd.DataFrame(
        {
            Columns.season: ["12/13", "13/14"],
            Columns.league_name: ["BayL", "BayL"],
            Columns.player_name: ["Glasl, Hans-Jürgen Jun", "Glasl, Hans Jürgen Jun."],
            Columns.player_id: ["7408", "7408"],
            Columns.score: [300, 300],
            Columns.date: ["2013-01-10", "2014-03-15"],
            Columns.input_data: ["true", "true"],
            Columns.computed_data: ["false", "false"],
        }
    )
    service = _service_with_df(df)
    service._players_registry_lookup = {
        "7408": {"canonical_name": "Glasl jun., Hans-Jürgen", "aliases": ""},
    }
    games = service.get_club_300_games()
    assert len(games) == 2
    assert {g["player_name"] for g in games} == {"Glasl jun., Hans-Jürgen"}


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
        club=None,
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
        club=None,
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
    service.get_club_300_games.assert_called_once_with(club=None)


def test_club_filter_keeps_only_games_for_club():
    """myClub must count games bowled *for* the club, not full alumni careers."""
    df = pd.DataFrame(
        {
            Columns.season: ["24/25", "24/25", "25/26", "25/26"],
            Columns.league_name: ["BayL", "BayL", "BayL", "BayL"],
            Columns.player_name: ["Stemmler", "Stemmler", "Stemmler", "Local"],
            Columns.player_id: ["99", "99", "99", "1"],
            Columns.team_name: [
                "Donaubowler Regensburg 1",
                "Donaubowler Regensburg 1",
                "Rottendorf 1",
                "Donaubowler Regensburg 2",
            ],
            Columns.score: [200, 210, 220, 230],
            Columns.date: ["2024-10-01", "2024-10-08", "2025-10-01", "2025-10-02"],
            Columns.input_data: ["true", "true", "true", "true"],
            Columns.computed_data: ["false", "false", "false", "false"],
        }
    )
    service = _service_with_df(df)
    service._player_catalog_cache = {}
    service._resolve_club_filter_label = lambda club: club  # type: ignore[method-assign]

    filtered = service._filter_df_to_club_games(df, "Donaubowler Regensburg")
    assert len(filtered) == 3
    assert set(filtered[Columns.score].tolist()) == {200, 210, 230}
    assert len(filtered[filtered[Columns.player_id] == "99"]) == 2

    agg = service.get_aggregate_lifetime_stats(season="all", club="Donaubowler Regensburg")
    assert agg is not None
    assert agg["lifetime"]["total_games"] == 3
    games_by_player: dict[str, int] = {}
    for row in agg["player_season_totals"]:
        name = str(row.get("player_name") or "")
        games_by_player[name] = games_by_player.get(name, 0) + int(row.get("games") or 0)
    assert games_by_player["Stemmler"] == 2
    assert games_by_player["Local"] == 1
