"""Team API season query normalization (``25-26`` on the wire → ``25/26``)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _service_with_history():
    service = MagicMock()
    service.get_team_history.return_value = {
        "25/26": {"league_name": "LL S (D)", "final_position": 1},
    }
    service.get_special_matches.return_value = {"highest_scores": []}
    service.get_clutch_performance.return_value = {"total_games": 20}
    service.get_consistency_metrics.return_value = {"mean_score": 600}
    service.get_margin_analysis.return_value = {"avg_margin": 12}
    service.get_available_weeks.return_value = [1, 2, 3]
    return service


def test_consistency_metrics_normalizes_hyphen_season(client):
    service = _service_with_history()
    with patch("app.routes.team_routes.get_team_service", return_value=service):
        res = client.get(
            "/team/get_consistency_metrics"
            "?database=db_real_merged"
            "&team_name=BC+EMAX+Unterf%C3%B6hring+1"
            "&season=25-26"
        )

    assert res.status_code == 200
    service.get_consistency_metrics.assert_called_once_with(
        "BC EMAX Unterföhring 1",
        "LL S (D)",
        "25/26",
    )


def test_special_matches_normalizes_hyphen_season(client):
    service = _service_with_history()
    with patch("app.routes.team_routes.get_team_service", return_value=service):
        res = client.get(
            "/team/get_special_matches"
            "?database=db_real_merged"
            "&team_name=BC+EMAX+Unterf%C3%B6hring+1"
            "&season=25-26"
        )

    assert res.status_code == 200
    service.get_special_matches.assert_called_once_with(
        team_name="BC EMAX Unterföhring 1",
        season="25/26",
    )


def test_clutch_analysis_normalizes_hyphen_season(client):
    service = _service_with_history()
    with patch("app.routes.team_routes.get_team_service", return_value=service):
        res = client.get(
            "/team/get_clutch_analysis"
            "?database=db_real_merged"
            "&team_name=BC+EMAX+Unterf%C3%B6hring+1"
            "&season=25-26"
            "&clutch_threshold=10"
        )

    assert res.status_code == 200
    service.get_clutch_performance.assert_called_once_with(
        team_name="BC EMAX Unterföhring 1",
        league_name="LL S (D)",
        season="25/26",
        clutch_threshold=10,
    )


def test_available_weeks_normalizes_hyphen_season(client):
    service = _service_with_history()
    with patch("app.routes.team_routes.get_team_service", return_value=service):
        res = client.get(
            "/team/get_available_weeks"
            "?database=db_real_merged"
            "&team_name=BC+EMAX+Unterf%C3%B6hring+1"
            "&season=25-26"
        )

    assert res.status_code == 200
    service.get_available_weeks.assert_called_once_with(
        team_name="BC EMAX Unterföhring 1",
        season="25/26",
    )


def test_margin_analysis_normalizes_hyphen_season(client):
    service = _service_with_history()
    with patch("app.routes.team_routes.get_team_service", return_value=service):
        res = client.get(
            "/team/get_margin_analysis"
            "?database=db_real_merged"
            "&team_name=BC+EMAX+Unterf%C3%B6hring+1"
            "&season=25-26"
        )

    assert res.status_code == 200
    service.get_margin_analysis.assert_called_once_with(
        "BC EMAX Unterföhring 1",
        "LL S (D)",
        "25/26",
    )
