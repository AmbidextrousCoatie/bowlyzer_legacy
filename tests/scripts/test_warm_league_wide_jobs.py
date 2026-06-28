"""League-wide warm job plan."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WARM = ROOT / "scripts" / "warm_league_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_league_cache_test", WARM)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


warm = _load()


def test_league_wide_jobs_omits_record_games_alias():
    jobs = warm._league_wide_jobs(object(), "db_real_merged", "BayL")
    endpoints = [job[0] for job in jobs]
    assert "get_record_games" not in endpoints
    assert "get_record_individual_games" in endpoints
    assert len(endpoints) == 6
