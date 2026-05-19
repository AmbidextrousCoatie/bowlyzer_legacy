"""Gesamtwertung cut-line row shading vs latest qualifying stage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.tournament_service import TournamentService, _tournament_df_string_series
from data_access.schema import Columns

CSV = Path(__file__).resolve().parents[2] / "database" / "data" / "player_stats_merged_plus_tournaments.csv"


def _load_sued_df() -> pd.DataFrame:
    if not CSV.is_file():
        pytest.skip("tournament CSV fixture not present")
    raw = pd.read_csv(CSV, sep=";", low_memory=False)
    raw = raw[raw["Event Type"].astype(str).str.lower().eq("tournament")]
    raw = raw[raw["Event Name"].astype(str).eq("Südbayerische Meisterschaft")]
    raw = raw[raw["Season"].astype(str).str.strip().eq("25/26")]
    raw[Columns.club] = _tournament_df_string_series(raw[Columns.club])
    raw[Columns.player_name] = _tournament_df_string_series(raw[Columns.player_name])
    raw[Columns.player_id] = _tournament_df_string_series(raw[Columns.player_id])
    return raw


@pytest.fixture
def svc() -> TournamentService:
    return TournamentService()


def test_cut_position_is_on_cut_rank_not_first_outside(svc: TournamentService) -> None:
    df = _load_sued_df()
    cut = svc._resolved_cut_position_for_round(df, 3, "25/26", "Südbayerische Meisterschaft")
    assert cut == 12


def test_gesamt_leaderboard_applies_cut_styles(svc: TournamentService) -> None:
    df = _load_sued_df()
    season, tournament = "25/26", "Südbayerische Meisterschaft"
    svc._tournament_df_cache[svc._tournament_cache_key(season, tournament)] = df

    lb = svc.get_leaderboard_table(season, tournament, round_number=None, df=df)
    assert len(lb.data) > 0
    cm = lb.cell_metadata or {}
    inside = sum(
        1 for v in cm.values() if v.get("backgroundColor") in ("#cfead6", "#e6f4ea")
    )
    on_cut = sum(1 for v in cm.values() if v.get("backgroundColor") == "#ffe8a1")
    assert inside >= 11
    assert on_cut >= 1

    shades = [m.get("cut_shade_rank") for m in (lb.row_metadata or []) if m.get("cut_shade_rank")]
    assert min(shades) == 1
    assert max(shades) <= len(lb.data)


def test_gesamt_cut_rank_uses_total_pins_not_final_round_only(svc: TournamentService) -> None:
    df = _load_sued_df()
    include_club = svc._has_any_club_value(df)
    total_ranks = svc._leaderboard_rank_map_qualifying_total_pins(df, include_club=include_club, through_round=3)
    round3_ranks = svc._leaderboard_rank_map_at_round(df, 3, include_club=include_club)
    assert total_ranks != round3_ranks
