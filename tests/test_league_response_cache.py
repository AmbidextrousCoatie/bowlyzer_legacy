"""Tests for persisted league response cache helpers."""

from app.cache.league_response_cache import (
    compute_data_revision,
    effective_database_id,
    normalize_query_for_key,
)


def test_normalize_query_sorts_and_sets_database():
    q = normalize_query_for_key({"season": "25/26", "league": "A"}, "db_x")
    assert q == {"database": "db_x", "league": "A", "season": "25/26"}


def test_effective_database_falls_back_to_config():
    eff = effective_database_id(None)
    assert isinstance(eff, str) and eff


def test_data_revision_shape():
    rev = compute_data_revision(effective_database_id("nonexistent_source_xyz"))
    assert rev in ("unknown", "missing")
