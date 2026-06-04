"""Tests for persisted league response cache helpers."""

import os
import stat

from app.cache.league_response_cache import (
    compute_data_revision,
    effective_database_id,
    league_cache_put,
    normalize_query_for_key,
)


def test_normalize_query_sorts_and_sets_database():
    q = normalize_query_for_key({"season": "25/26", "league": "A"}, "db_x")
    assert q == {"database": "db_x", "league": "A", "season": "25/26"}


def test_normalize_query_season_dash_to_slash():
    q = normalize_query_for_key({"season": "15-16", "database": "db_x"}, "db_x")
    assert q["season"] == "15/16"


def test_effective_database_falls_back_to_config():
    eff = effective_database_id(None)
    assert isinstance(eff, str) and eff


def test_data_revision_shape():
    rev = compute_data_revision(effective_database_id("nonexistent_source_xyz"))
    assert rev in ("unknown", "missing")


def test_league_cache_put_tolerates_read_only_dir(tmp_path, monkeypatch):
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, stat.S_IREAD | stat.S_IEXEC)
    monkeypatch.setenv("LEAGUE_CACHE_DIR", str(ro))
    monkeypatch.setenv("LEAGUE_CACHE_ENABLED", "1")
    from app.cache import league_response_cache as mod

    mod._LEAGUE_CACHE_DIR = None
    league_cache_put("get_available_seasons", "db_x", {"database": "db_x"}, ["08/09"])
