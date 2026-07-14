"""Player cache warm shard helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYER_WARM = ROOT / "scripts" / "warm_player_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_player_cache_test", PLAYER_WARM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


player_warm = _load()


def test_build_player_warm_shards_includes_finalize():
    shards = player_warm.build_player_warm_shards(["24/25", "25/26"])
    labels = [s.label for s in shards]
    assert labels == [
        "player:search",
        "player:seasons",
        "player:lifetime:24/25",
        "player:lifetime:25/26",
        "player:lifetime:all",
        "player:highest-games",
        "player:highest-games:24/25",
        "player:highest-games:25/26",
        "player:club-300",
    ]


def test_build_player_warm_shards_adds_batched_highest_games():
    players = [{"id": str(i), "name": f"Player {i}"} for i in range(120)]
    shards = player_warm.build_player_warm_shards(
        ["24/25"],
        players=players,
        players_per_highest_shard=50,
    )
    labels = [s.label for s in shards]
    assert labels.count("player:highest-games-batch:1/3") == 1
    assert labels.count("player:highest-games-batch:2/3") == 1
    assert labels.count("player:highest-games-batch:3/3") == 1
    batch_shard = next(s for s in shards if s.label == "player:highest-games-batch:2/3")
    assert batch_shard.argv == (
        "--phase",
        "player-highest-games-batch",
        "--player-offset",
        "50",
        "--player-limit",
        "50",
    )


def test_merge_aggregate_empty_parts():
    from app.services.player_service import PlayerService

    assert PlayerService.merge_aggregate_lifetime_payloads([]) is None
