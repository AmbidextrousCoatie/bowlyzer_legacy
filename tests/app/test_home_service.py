"""Tests for landing-page aggregate stats."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.home_service import (
    _unique_season_event_combos,
    _unique_seasons,
    get_home_stats,
)
from data_access.schema import Columns


def test_unique_seasons_union() -> None:
    league_df = pd.DataFrame({Columns.season: ["24/25", "25/26", "25/26"]})
    tournament_df = pd.DataFrame({Columns.season: ["05/06", "24/25"]})
    assert _unique_seasons(league_df, tournament_df) == 3


def test_unique_season_event_combos() -> None:
    frame = pd.DataFrame(
        {
            Columns.season: ["24/25", "24/25", "25/26"],
            Columns.event: ["BayL", "OBL", "BayL"],
        }
    )
    assert _unique_season_event_combos(frame, Columns.event) == 3


def test_get_home_stats_shape() -> None:
    stats = get_home_stats("db_real_merged")
    assert stats["league_seasons"] > 0
    assert stats["tournaments"] > 0
    assert stats["years"] > 0
    assert stats["tournaments"] <= stats["league_seasons"] + stats["tournaments"]
    assert "leagues" not in stats
    assert "seasons" not in stats
