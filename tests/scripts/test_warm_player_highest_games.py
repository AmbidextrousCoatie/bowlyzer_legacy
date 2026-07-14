"""Per-player highest-games cache warm helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PLAYER_WARM = ROOT / "scripts" / "warm_player_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_player_highest_games_test", PLAYER_WARM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


player_warm = _load()


def test_warm_player_highest_games_uses_season_all_in_cache_key(monkeypatch):
    calls: list[dict] = []

    def fake_warm_one(endpoint, database, query, build):
        calls.append({"endpoint": endpoint, "query": dict(query)})
        build()
        return "built"

    monkeypatch.setattr(player_warm, "_warm_one", fake_warm_one)

    service = MagicMock()
    service.get_highest_individual_games.return_value = [{"score": 300}]

    stats = player_warm.warm_player_highest_games(
        service,
        "db_player_merged_hybrid",
        log=lambda _msg: None,
    )

    assert stats["built"] == 1
    assert calls[0]["query"] == {
        "database": "db_player_merged_hybrid",
        "limit": "10",
        "season": "all",
    }


def test_warm_player_highest_games_season_uses_season_in_cache_key(monkeypatch):
    calls: list[dict] = []

    def fake_warm_one(endpoint, database, query, build):
        calls.append({"endpoint": endpoint, "query": dict(query)})
        build()
        return "built"

    monkeypatch.setattr(player_warm, "_warm_one", fake_warm_one)

    service = MagicMock()
    service.get_highest_individual_games.return_value = [{"score": 290}]

    stats = player_warm.warm_player_highest_games_season(
        service,
        "db_player_merged_hybrid",
        "16/17",
        log=lambda _msg: None,
    )

    assert stats["built"] == 1
    assert calls[0]["query"] == {
        "database": "db_player_merged_hybrid",
        "limit": "10",
        "season": "16/17",
    }
    service.get_highest_individual_games.assert_called_once_with(limit=10, season="16/17")


def test_warm_player_highest_games_for_player_warms_career_only_by_default(monkeypatch):
    calls: list[dict] = []

    def fake_warm_one(endpoint, database, query, build):
        calls.append({"endpoint": endpoint, "query": dict(query)})
        build()
        return "built"

    monkeypatch.setattr(player_warm, "_warm_one", fake_warm_one)

    service = MagicMock()
    service.get_player_seasons.return_value = ["24/25", "25/26"]
    service.get_highest_individual_games.return_value = [{"score": 290}]

    stats = player_warm.warm_player_highest_games_for_player(
        service,
        "db_player_merged_hybrid",
        "Alice",
        "1",
        log=lambda _msg: None,
    )

    assert stats["built"] == 1
    assert calls[0]["query"]["season"] == "all"
    service.get_player_seasons.assert_not_called()


def test_warm_player_highest_games_for_player_can_include_seasons(monkeypatch):
    calls: list[dict] = []

    def fake_warm_one(endpoint, database, query, build):
        calls.append({"endpoint": endpoint, "query": dict(query)})
        build()
        return "built"

    monkeypatch.setattr(player_warm, "_warm_one", fake_warm_one)

    service = MagicMock()
    service.get_player_seasons.return_value = ["24/25", "25/26"]
    service.get_highest_individual_games.return_value = [{"score": 290}]

    stats = player_warm.warm_player_highest_games_for_player(
        service,
        "db_player_merged_hybrid",
        "Alice",
        "1",
        include_player_seasons=True,
        log=lambda _msg: None,
    )

    assert stats["built"] == 3
    seasons = [call["query"]["season"] for call in calls]
    assert seasons == ["all", "24/25", "25/26"]
