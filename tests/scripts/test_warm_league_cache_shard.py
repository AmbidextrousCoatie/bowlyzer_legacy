"""Shard helpers for warm_league_cache."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WARM = ROOT / "scripts" / "warm_league_cache.py"


def _load_warm():
    spec = importlib.util.spec_from_file_location("warm_league_cache_test", WARM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


warm = _load_warm()


def test_slice_club_names_offset_limit():
    clubs = ["A", "B", "C", "D", "E"]
    assert warm.slice_club_names(clubs, offset=1, limit=2) == ["B", "C"]
    assert warm.slice_club_names(clubs, offset=10) == []


def test_club_shard_ranges():
    assert warm.club_shard_ranges(0, 40) == []
    assert warm.club_shard_ranges(95, 40) == [(0, 40), (40, 40), (80, 15)]


def test_build_warm_shards_season_meta_clubs():
    catalog = {
        "seasons": ["24/25", "25/26"],
        "leagues": ["BayL", "LL S"],
        "clubs": [f"C{i}" for i in range(5)],
    }
    shards = warm.build_warm_shards(
        catalog,
        warm_clubs=True,
        skip_seasons=False,
        skip_meta=False,
        skip_clubs=False,
        meta_per_league=True,
        clubs_per_shard=2,
    )
    labels = [s.label for s in shards]
    assert labels == [
        "season:24/25",
        "season:25/26",
        "meta:BayL",
        "meta:LL S",
        "clubs:1/3",
        "clubs:2/3",
        "clubs:3/3",
    ]
    by_label = {s.label: s for s in shards}
    assert by_label["clubs:1/3"].extra_argv == ()
    assert by_label["clubs:2/3"].extra_argv == ("--skip-club-shared",)


def test_collect_global_page_jobs_endpoints():
    class _FakeLs:
        def get_league_week_matrix(self):
            return {"seasons": [], "rows": []}

        def get_latest_events(self, limit: int = 5):
            return [{"Season": "25/26", "limit": limit}]

    jobs = warm.collect_global_page_jobs(_FakeLs(), "db_real_merged")
    endpoints = [j[0] for j in jobs]
    assert endpoints == [
        "get_week_matrix",
        "home_stats",
        "get_club_rankings",
        "get_latest_events",
        "get_latest_events",
    ]
    assert jobs[0][1] == {"database": "db_real_merged"}
    assert jobs[2][1] == {"database": "db_real_merged"}
    assert jobs[3][1]["limit"] == "8"
    assert jobs[4][1]["limit"] == "10"


def test_build_warm_shards_meta_monolith():
    catalog = {"seasons": ["25/26"], "leagues": ["BayL"], "clubs": []}
    shards = warm.build_warm_shards(
        catalog,
        warm_clubs=False,
        skip_seasons=True,
        skip_meta=False,
        skip_clubs=True,
        meta_per_league=False,
        clubs_per_shard=40,
    )
    assert [s.label for s in shards] == ["meta:all-leagues"]
    assert shards[0].argv == ["--phase", "league-wide"]
