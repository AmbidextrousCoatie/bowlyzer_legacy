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


def test_cut_position_differs_by_qualifying_round(svc: TournamentService) -> None:
    df = _load_sued_df()
    season, tournament = "25/26", "Südbayerische Meisterschaft"
    cut_r1 = svc._resolved_cut_position_for_round(df, 1, season, tournament)
    cut_r2 = svc._resolved_cut_position_for_round(df, 2, season, tournament)
    cut_r3 = svc._resolved_cut_position_for_round(df, 3, season, tournament)
    assert cut_r1 == 80
    assert cut_r2 == 40
    assert cut_r3 == 12
    assert cut_r1 != cut_r2 != cut_r3


def test_field_progress_cut_positions_per_round(svc: TournamentService) -> None:
    df = _load_sued_df()
    season, tournament = "25/26", "Südbayerische Meisterschaft"
    fp = svc._compute_field_progress(season, tournament, df=df)
    assert fp["cut_lines_position"] == [80, 40, 12]


def test_cut_line_card_matches_leaderboard_on_cut_player(svc: TournamentService) -> None:
    """Config-only export: card must use cumulative cut rank for the active round, not round 1."""
    csv = Path(__file__).resolve().parents[2] / "database" / "data" / "player_stats_merged_plus_tournaments.csv"
    if not csv.is_file():
        pytest.skip("tournament CSV fixture not present")
    raw = pd.read_csv(csv, sep=";", low_memory=False)
    raw = raw[raw["Event Type"].astype(str).str.lower().eq("tournament")]
    raw = raw[raw["Event Name"].astype(str).eq("Bayerische Meisterschaft - Männer Einzel")]
    raw = raw[raw["Season"].astype(str).str.strip().eq("25/26")]
    season, tournament = "25/26", "Bayerische Meisterschaft - Männer Einzel"
    svc._tournament_df_cache[svc._tournament_cache_key(season, tournament)] = raw

    cards = svc.get_summary_cards(season, tournament, round_number=2, df=raw)
    cut = next(c for c in cards["cards"] if c.get("title") == "Cut Line")
    lb = svc.get_leaderboard_table(season, tournament, round_number=2, df=raw)
    on_cut = [
        row[1]
        for i, row in enumerate(lb.data)
        if (lb.cell_metadata or {}).get(f"{i}:0", {}).get("backgroundColor") == "#ffe8a1"
    ]
    assert on_cut
    assert cut["value"] == on_cut[0]
