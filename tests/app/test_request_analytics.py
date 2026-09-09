"""Tests for anonymized request analytics helpers."""

from datetime import date

from werkzeug.datastructures import ImmutableMultiDict

from app.analytics.request_log import (
    analytics_log_path,
    build_log_record,
    daily_visitor_id,
    is_logged_api_path,
    normalize_query_params,
    resolve_client_ip,
    truncate_client_ip,
)


def test_truncate_ipv4_to_slash24():
    assert truncate_client_ip("203.0.113.45") == "203.0.113.0"
    assert truncate_client_ip("203.0.113.45") == truncate_client_ip("203.0.113.99")


def test_daily_visitor_id_stable_within_day(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SALT", "test-salt")
    day = date(2026, 6, 3)
    a = daily_visitor_id("203.0.113.45", day=day)
    b = daily_visitor_id("203.0.113.99", day=day)
    c = daily_visitor_id("203.0.113.45", day=day)
    assert a == b
    assert a == c
    assert len(a) == 16


def test_daily_visitor_id_changes_next_day(monkeypatch):
    monkeypatch.setenv("ANALYTICS_SALT", "test-salt")
    d1 = daily_visitor_id("203.0.113.45", day=date(2026, 6, 3))
    d2 = daily_visitor_id("203.0.113.45", day=date(2026, 6, 4))
    assert d1 != d2


def test_resolve_client_ip_prefers_real_ip():
    assert (
        resolve_client_ip("10.0.0.1", "198.51.100.1, 10.0.0.2", "198.51.100.5")
        == "198.51.100.5"
    )


def test_normalize_query_params_sorted():
    q = ImmutableMultiDict([("season", "25/26"), ("database", "db_real_merged")])
    assert normalize_query_params(q) == {
        "database": "db_real_merged",
        "season": "25/26",
    }


def test_is_logged_api_path():
    assert is_logged_api_path("/league/get_available_seasons")
    assert is_logged_api_path("/pipeline/status")
    assert not is_logged_api_path("/liga")
    assert not is_logged_api_path("/assets/app.js")


def test_build_log_record_shape():
    rec = build_log_record(
        method="GET",
        path="/league/get_available_leagues",
        query=ImmutableMultiDict([("season", "25/26")]),
        status_code=200,
        cache_status="HIT",
        visitor_id="abc123",
        duration_ms=12.345,
    )
    assert rec["path"] == "/league/get_available_leagues"
    assert rec["params"]["season"] == "25/26"
    assert rec["cache_status"] == "HIT"
    assert rec["visitor_id"] == "abc123"
    assert rec["duration_ms"] == 12.35
    assert rec["ts"].endswith("Z")


def test_analytics_log_path_override(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "requests.log"
    monkeypatch.setenv("ANALYTICS_REQUEST_LOG", str(target))
    assert analytics_log_path() == target.resolve()


def test_middleware_logs_api_request(tmp_path, monkeypatch):
    monkeypatch.setenv("ANALYTICS_ENABLED", "1")
    monkeypatch.setenv("ANALYTICS_SALT", "test-salt")
    log_file = tmp_path / "requests.log"
    monkeypatch.setenv("ANALYTICS_REQUEST_LOG", str(log_file))

    from app import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get(
        "/league/get_available_seasons?database=db_real_merged",
        headers={"X-Real-IP": "203.0.113.45"},
    )
    assert resp.status_code in (200, 500)
    assert log_file.is_file()
    line = log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert '"path":"/league/get_available_seasons"' in line
    assert '"visitor_id"' in line
    assert "203.0.113.45" not in line
