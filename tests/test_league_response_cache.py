"""Tests for persisted league response cache helpers."""

import os
import stat

from app.cache.league_response_cache import (
    cache_entry_relative_path,
    compute_data_revision,
    effective_database_id,
    league_cache_put,
    league_cache_try_get,
    normalize_query_for_key,
)


def test_normalize_query_sorts_and_sets_database():
    q = normalize_query_for_key({"season": "25/26", "league": "A"}, "db_x")
    assert q == {"database": "db_x", "league": "A", "season": "25/26"}


def test_normalize_query_season_dash_to_slash():
    q = normalize_query_for_key({"season": "15-16", "database": "db_x"}, "db_x")
    assert q["season"] == "15/16"


def test_normalize_query_ignores_language_param():
    """React buildUrl appends language=; cache keys use i18n_service language instead."""
    q = normalize_query_for_key({"database": "db_x", "language": "de", "season": "22/23"}, "db_x")
    assert q == {"database": "db_x", "season": "22/23"}
    assert "language" not in q


def test_effective_database_falls_back_to_config():
    eff = effective_database_id(None)
    assert isinstance(eff, str) and eff


def test_data_revision_shape():
    rev = compute_data_revision(effective_database_id("nonexistent_source_xyz"))
    assert rev in ("unknown", "missing")


def test_league_cache_put_tolerates_read_only_shipped_dir(tmp_path, monkeypatch):
    shipped = tmp_path / "shipped"
    runtime = tmp_path / "runtime"
    shipped.mkdir()
    runtime.mkdir()
    os.chmod(shipped, stat.S_IREAD | stat.S_IEXEC)
    monkeypatch.setenv("LEAGUE_CACHE_DIR", str(shipped))
    monkeypatch.setenv("LEAGUE_CACHE_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("LEAGUE_CACHE_ENABLED", "1")
    monkeypatch.setenv("LEAGUE_CACHE_GLOBAL_REVISION", "1")

    payload = ["08/09"]
    league_cache_put("get_available_seasons", "db_x", {"database": "db_x"}, payload)

    rel, _ = cache_entry_relative_path("get_available_seasons", "db_x", {"database": "db_x"})
    assert (runtime / rel).is_file()
    assert league_cache_try_get("get_available_seasons", "db_x", {"database": "db_x"}) == payload


def test_runtime_overlay_overrides_shipped(tmp_path, monkeypatch):
    shipped = tmp_path / "shipped"
    runtime = tmp_path / "runtime"
    shipped.mkdir(parents=True)
    runtime.mkdir(parents=True)
    monkeypatch.setenv("LEAGUE_CACHE_DIR", str(shipped))
    monkeypatch.setenv("LEAGUE_CACHE_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("LEAGUE_CACHE_ENABLED", "1")
    monkeypatch.setenv("LEAGUE_CACHE_GLOBAL_REVISION", "1")

    query = {"database": "db_x"}
    rel, _ = cache_entry_relative_path("player_search", "db_x", query)
    (shipped / rel).parent.mkdir(parents=True, exist_ok=True)
    (runtime / rel).parent.mkdir(parents=True, exist_ok=True)
    (shipped / rel).write_text('["shipped"]', encoding="utf-8")
    (runtime / rel).write_text('["runtime"]', encoding="utf-8")

    assert league_cache_try_get("player_search", "db_x", query) == ["runtime"]
