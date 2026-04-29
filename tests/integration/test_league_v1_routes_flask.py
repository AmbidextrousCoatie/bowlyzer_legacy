from types import SimpleNamespace

import pytest

from app import create_app


class FakeTableData:
    def to_dict(self):
        return {
            "title": "Standings",
            "columns": [
                {
                    "title": "",
                    "columns": [
                        {"title": "Team", "field": "team"},
                        {"title": "Points", "field": "points"},
                    ],
                }
            ],
            "data": [["ABC 1", 42], ["XYZ 1", 39]],
            "config": {},
            "metadata": {},
        }


class FakeWeekTableData:
    def to_dict(self):
        return {
            "title": "Week Standings",
            "columns": [
                {
                    "title": "",
                    "columns": [
                        {"title": "Team", "field": "team"},
                        {"title": "WeekPoints", "field": "week_points"},
                    ],
                }
            ],
            "data": [["ABC 1", 8], ["XYZ 1", 6]],
            "config": {},
            "metadata": {},
        }


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_options_leagues_success(client, monkeypatch):
    fake_service = SimpleNamespace(get_leagues=lambda season=None: ["BAYL", "BZOL"])
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/options/leagues")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["items"][0] == {"value": "BAYL", "label": "BAYL"}
    assert "ETag" in response.headers
    assert payload["meta"]["version"] == "v1"


def test_options_seasons_requires_league(client):
    response = client.get("/api/v1/league/options/seasons")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MISSING_REQUIRED_PARAM"


def test_season_standings_maps_rows(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_league_history_table_data=lambda league_name, season: FakeTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/standings?league=BAYL&season=24-25")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0] == {"team": "ABC 1", "points": 42}


def test_season_team_points_maps_chart(client, monkeypatch):
    fake_series = {
        "name": "Points in Season Progress",
        "label_x_axis": "Week",
        "label_y_axis": "Points",
        "length": 3,
        "query_params": {"league": "BAYL", "season": "24-25"},
        "data_accumulated": {"ABC 1": [2, 6, 10]},
        "sorted_by_total": ["ABC 1"],
        "total": {"ABC 1": 10},
        "average": {"ABC 1": 3.33},
        "counts": {"ABC 1": 3},
    }
    fake_service = SimpleNamespace(get_team_points_simple=lambda league_name, season: fake_series)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/team-points?league=BAYL&season=24-25")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["chartType"] == "line"
    assert payload["data"]["xAxis"]["categories"] == [1, 2, 3]
    assert payload["data"]["series"][0]["name"] == "ABC 1"


def test_season_team_points_validates_week(client):
    response = client.get("/api/v1/league/season/team-points?league=BAYL&season=24-25&week=abc")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_PARAM"


def test_season_team_positions_success(client, monkeypatch):
    fake_series = {
        "name": "Positions in Season Progress",
        "label_x_axis": "Week",
        "label_y_axis": "Position",
        "length": 2,
        "query_params": {"league": "BAYL", "season": "24-25"},
        "data_accumulated": {"ABC 1": [1, 2]},
        "sorted_by_total": ["ABC 1"],
        "total": {"ABC 1": 3},
        "average": {"ABC 1": 1.5},
        "counts": {"ABC 1": 2},
    }
    fake_service = SimpleNamespace(get_team_positions_simple=lambda league_name, season: fake_series)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/team-positions?league=BAYL&season=24-25")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["chartType"] == "line"
    assert payload["data"]["yAxis"]["label"] == "Position"


def test_season_team_averages_success(client, monkeypatch):
    fake_series = {
        "name": "Averages in Season Progress",
        "label_x_axis": "Week",
        "label_y_axis": "Average",
        "length": 2,
        "query_params": {"league": "BAYL", "season": "24-25"},
        "data_accumulated": {"ABC 1": [190.5, 192.0]},
        "sorted_by_total": ["ABC 1"],
        "total": {"ABC 1": 382.5},
        "average": {"ABC 1": 191.25},
        "counts": {"ABC 1": 2},
    }
    fake_service = SimpleNamespace(get_team_averages_simple=lambda league_name, season: fake_series)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/team-averages?league=BAYL&season=24-25")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["chartType"] == "line"
    assert payload["data"]["series"][0]["data"] == [190.5, 192.0]


def test_internal_error_is_enveloped(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    fake_service = SimpleNamespace(get_league_history_table_data=boom)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/standings?league=BAYL&season=24-25")
    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["meta"]["version"] == "v1"


def test_matchday_standings_success(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_league_week_table_simple=lambda season, league, week: FakeWeekTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/matchday/standings?league=BAYL&season=24-25&week=3")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0] == {"team": "ABC 1", "week_points": 8}


def test_matchday_standings_not_found(client, monkeypatch):
    fake_service = SimpleNamespace(get_league_week_table_simple=lambda season, league, week: None)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/matchday/standings?league=BAYL&season=24-25&week=3")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND"


def test_matchday_honor_scores_success(client, monkeypatch):
    fake_honor_scores = [{"id": "top_individual", "title": "Top Individual", "value": "290"}]
    fake_service = SimpleNamespace(
        get_honor_scores=lambda **kwargs: fake_honor_scores
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/matchday/honor-scores?league=BAYL&season=24-25&week=3")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["cards"] == fake_honor_scores


def test_matchday_requires_week(client):
    response = client.get("/api/v1/league/matchday/honor-scores?league=BAYL&season=24-25")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MISSING_REQUIRED_PARAM"


def test_team_week_classic_success(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_team_week_details_table_data=lambda league, season, team, week: FakeWeekTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get(
        "/api/v1/league/team-week/classic?league=BAYL&season=24-25&week=3&team=ABC%201"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0] == {"team": "ABC 1", "week_points": 8}


def test_team_week_individual_scores_success(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_team_individual_scores_table=lambda league, season, team, week: FakeWeekTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get(
        "/api/v1/league/team-week/individual-scores?league=BAYL&season=24-25&week=3&team=ABC%201"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][1] == {"team": "XYZ 1", "week_points": 6}


def test_team_week_head_to_head_success(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_team_week_head_to_head_table_data=lambda league, season, team, week, view_mode: FakeWeekTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get(
        "/api/v1/league/team-week/head-to-head?league=BAYL&season=24-25&week=3&team=ABC%201&viewMode=own_team"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0]["team"] == "ABC 1"


def test_team_week_requires_team(client):
    response = client.get("/api/v1/league/team-week/classic?league=BAYL&season=24-25&week=3")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MISSING_REQUIRED_PARAM"


def test_aggregation_averages_history_success(client, monkeypatch):
    fake_series = {
        "name": "League Averages History",
        "label_x_axis": "Season",
        "label_y_axis": "Average",
        "length": 2,
        "query_params": {"league": "BAYL"},
        "data_accumulated": {"League": [190.0, 191.2]},
        "sorted_by_total": ["League"],
        "total": {"League": 381.2},
        "average": {"League": 190.6},
        "counts": {"League": 2},
    }
    fake_service = SimpleNamespace(get_league_averages_history=lambda league, debug=False: fake_series)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/aggregation/averages-history?league=BAYL")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["chartType"] == "line"


def test_aggregation_points_to_win_history_success(client, monkeypatch):
    fake_series = {
        "name": "Points to Win History",
        "label_x_axis": "Season",
        "label_y_axis": "Points",
        "length": 2,
        "query_params": {"league": "BAYL"},
        "data_accumulated": {"Champion Threshold": [60, 63]},
        "sorted_by_total": ["Champion Threshold"],
        "total": {"Champion Threshold": 123},
        "average": {"Champion Threshold": 61.5},
        "counts": {"Champion Threshold": 2},
    }
    fake_service = SimpleNamespace(get_points_to_win_history=lambda league, debug=False: fake_series)
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/aggregation/points-to-win-history?league=BAYL")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["series"][0]["name"] == "Champion Threshold"


def test_aggregation_top_team_performances_success(client, monkeypatch):
    fake_service = SimpleNamespace(get_top_team_performances=lambda league: FakeTableData())
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/aggregation/top-team-performances?league=BAYL")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0]["team"] == "ABC 1"


def test_aggregation_top_individual_performances_success(client, monkeypatch):
    fake_service = SimpleNamespace(get_top_individual_performances=lambda league: FakeTableData())
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/aggregation/top-individual-performances?league=BAYL")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][1]["points"] == 39


def test_aggregation_record_games_success(client, monkeypatch):
    fake_service = SimpleNamespace(get_record_games=lambda league: FakeTableData())
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/aggregation/record-games?league=BAYL")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["meta"]["version"] == "v1"


def test_season_team_vs_team_success(client, monkeypatch):
    fake_service = SimpleNamespace(
        get_team_vs_team_comparison_table=lambda league, season, week: FakeTableData()
    )
    monkeypatch.setattr("app.routes.league_v1_routes.get_league_service", lambda: fake_service)

    response = client.get("/api/v1/league/season/team-vs-team?league=BAYL&season=24-25")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["rows"][0] == {"team": "ABC 1", "points": 42}
