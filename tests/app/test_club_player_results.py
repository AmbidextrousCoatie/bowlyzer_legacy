"""Club player results table aggregates per-player club tenure stats."""

from unittest.mock import MagicMock

import pandas as pd

from app.services.club_player_results_service import ClubPlayerResultsService
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


def _service_with_df(rows: list) -> ClubPlayerResultsService:
    svc = object.__new__(ClubPlayerResultsService)
    svc.league_database = "test_db"
    svc.player_database = "test_player"
    svc._league_service = MagicMock()
    svc._league_service.get_available_clubs.return_value = ["Test Club"]
    svc._league_service.resolve_club_name.side_effect = lambda name, _clubs: name
    svc._player_service = MagicMock()
    svc._player_service.data_manager.df = pd.DataFrame(rows)
    svc._league_games = None
    return svc


def test_club_player_results_one_row_per_player():
    rows = []
    for season, score in (("2022/2023", 180), ("2023/2024", 220)):
        for _ in range(4):
            rows.append(
                _league_row(
                    **{
                        Columns.season: season,
                        Columns.player_name: "Alpha, A",
                        Columns.player_id: "A",
                        Columns.score: score,
                    }
                )
            )
    for _ in range(6):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2023/2024",
                    Columns.player_name: "Beta, B",
                    Columns.player_id: "B",
                    Columns.score: 210,
                }
            )
        )

    payload = _service_with_df(rows).get_club_player_results_table("Test Club")
    table = payload["table"]
    assert payload["club"] == "Test Club"
    assert len(table["data"]) == 2

    by_name = {row["player_name"]: row for row in table["data"]}
    assert by_name["Beta, B"]["rank"] == 1
    assert by_name["Beta, B"]["average"] == 210.0
    assert by_name["Beta, B"]["games"] == 6
    assert by_name["Beta, B"]["membership_seasons"] == 1
    assert by_name["Alpha, A"]["membership_seasons"] == 2
    assert by_name["Alpha, A"]["best_season"] == "2023/2024"
    assert by_name["Alpha, A"]["best_season_average"] == 220.0
    assert by_name["Alpha, A"]["club_active"] is True
    assert by_name["Beta, B"]["club_active"] is True

    meta = table["row_metadata"]
    assert len(meta) == 2
    assert all(entry["rowAccentColor"] == "#8CBF8A" for entry in meta)
    assert table["metadata"]["latest_season"] == "2023/2024"

    groups = [g["title_key"] for g in table["columns"]]
    assert groups == [
        "ui.team.club_player_group",
        "ui.team.club_alltime_group",
        "ui.team.club_best_season_group",
        "ui.team.club_membership_group",
    ]


def test_club_player_results_inactive_alumni_accent():
    rows = []
    for _ in range(4):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2022/2023",
                    Columns.player_name: "Alumni, A",
                    Columns.player_id: "AL",
                    Columns.score: 190,
                }
            )
        )
    for _ in range(4):
        rows.append(
            _league_row(
                **{
                    Columns.season: "2023/2024",
                    Columns.player_name: "Current, C",
                    Columns.player_id: "CU",
                    Columns.score: 200,
                }
            )
        )

    payload = _service_with_df(rows).get_club_player_results_table("Test Club")
    table = payload["table"]
    by_name = {row["player_name"]: row for row in table["data"]}
    assert by_name["Current, C"]["club_active"] is True
    assert by_name["Alumni, A"]["club_active"] is False

    meta_by_name = {
        table["data"][i]["player_name"]: table["row_metadata"][i]["rowAccentColor"]
        for i in range(len(table["data"]))
    }
    assert meta_by_name["Current, C"] == "#8CBF8A"
    assert meta_by_name["Alumni, A"] == "#E86E56"


def test_get_club_player_results_route_returns_table():
    from app import create_app

    app = create_app()
    client = app.test_client()
    response = client.get(
        "/league/get_club_player_results",
        query_string={"database": "db_real_merged", "club": "Donaubowler Regensburg"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "table" in data
    assert "columns" in data["table"]
    assert "data" in data["table"]
