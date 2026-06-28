"""Shard orchestrator forwards script-specific CLI flags."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARD = ROOT / "scripts" / "warm_cache_shard.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_cache_shard_test", SHARD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


shard = _load()


def test_child_extra_league_includes_languages_and_sequential():
    extra = shard._child_extra_for_script(
        shard.LEAGUE_WARM_SCRIPT,
        languages="de,en",
        quiet_children=True,
        standings_no_division_grid=False,
        verbose=False,
        dry_run=False,
        club_workers=0,
    )
    assert "--languages" in extra
    assert "--sequential" in extra
    assert "--no-progress" in extra
    assert "--quiet" in extra


def test_child_extra_player_omits_league_only_flags():
    extra = shard._child_extra_for_script(
        shard.PLAYER_WARM_SCRIPT,
        languages="de,en",
        quiet_children=True,
        standings_no_division_grid=True,
        verbose=True,
        dry_run=True,
        club_workers=8,
    )
    assert extra == ["--quiet", "--dry-run"]
    assert "--languages" not in extra
    assert "--sequential" not in extra
    assert "--no-progress" not in extra


def test_child_extra_tournament_minimal():
    extra = shard._child_extra_for_script(
        shard.TOURNAMENT_WARM_SCRIPT,
        languages="de,en",
        quiet_children=True,
        standings_no_division_grid=True,
        verbose=True,
        dry_run=False,
        club_workers=4,
    )
    assert extra == []
