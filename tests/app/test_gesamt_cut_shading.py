"""Gesamtwertung cut-line row shading vs latest qualifying stage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.i18n_service import i18n_service
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


def test_gesamt_cut_shade_rank_matches_net_sort_rank(svc: TournamentService) -> None:
    """Handicap Gesamtwertung: row cut colors follow net sort (#), not qual scratch pins."""
    csv = Path(__file__).resolve().parents[2] / "database" / "data" / "tournament_manual_postprocessed.csv"
    if not csv.is_file():
        pytest.skip("tournament_manual_postprocessed.csv not present")
    raw = pd.read_csv(csv, sep=";", low_memory=False)
    raw = raw[raw["Event Type"].astype(str).str.lower().eq("tournament")]
    raw = raw[raw["Event Name"].astype(str).eq("Clubmeisterschaft Donaubowler 2026")]
    if raw.empty:
        pytest.skip("Clubmeisterschaft Donaubowler 2026 not in fixture")
    season, tournament = "25/26", "Clubmeisterschaft Donaubowler 2026"
    svc._tournament_df_cache[svc._tournament_cache_key(season, tournament)] = raw

    lb = svc.get_leaderboard_table(season, tournament, round_number=None, df=raw)
    assert lb.metadata and lb.metadata.get("leaderboard_mode") == "scratch_net_handicap"
    assert lb.default_sort and lb.default_sort.get("field") == "total_net"

    for i, row in enumerate(lb.data):
        meta = (lb.row_metadata or [])[i] if i < len(lb.row_metadata or []) else {}
        assert meta.get("cut_shade_rank") == row[0], (
            f"row {i}: cut_shade_rank {meta.get('cut_shade_rank')} != displayed rank {row[0]}"
        )

    group_titles = [g.title for g in lb.columns]
    assert len(group_titles) == 3
    net_idx = group_titles.index(i18n_service.get_text("ui.tournament.lb_group_net"))
    assert i18n_service.get_text("ui.tournament.lb_group_net") == "mit Handicap"
    scratch_idx = group_titles.index(i18n_service.get_text("ui.tournament.lb_group_scratch"))
    spieler_idx = group_titles.index(i18n_service.get_text("ui.tournament.lb_group_players"))
    assert spieler_idx < net_idx < scratch_idx
    assert lb.columns[net_idx].highlight_header_only is True
    assert lb.columns[net_idx].highlighted is not True
    assert lb.columns[scratch_idx].highlight_header_only is not True
    assert lb.columns[scratch_idx].style is None
    assert lb.columns[net_idx].title_key == "ui.tournament.lb_group_net"
    rank_col = next(c for g in lb.columns for c in g.columns if c.field == "rank")
    assert rank_col.width == "44px"
    player_col = next(c for g in lb.columns for c in g.columns if c.field == "player")
    assert player_col.width == "110px"
    assert player_col.title_key == "player"
    hcp_col = next(c for g in lb.columns for c in g.columns if c.field == "handicap_display")
    assert hcp_col.width == "55px"
    first_round_col = next(c for g in lb.columns for c in g.columns if c.field.startswith("round_"))
    assert first_round_col.width == "80px"
    avg_net_col = next(c for g in lb.columns for c in g.columns if c.field == "avg_net")
    assert avg_net_col.title_key == "table.header.average"
    assert avg_net_col.width == "60px"

    flat_fields = [col.field for g in lb.columns for col in g.columns]
    first_round_field = next(f for f in flat_fields if f.startswith("round_"))
    assert flat_fields.index("total_net") < flat_fields.index(first_round_field)


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


def test_cut_line_card_matches_average_rank_for_active_round(svc: TournamentService) -> None:
    """Cut-line card uses cumulative average rank for the active round."""
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
    cut_pos = svc._resolved_cut_position_for_round(raw, 2, season, tournament)
    assert cut_pos is not None
    ranked = svc._avg_net_standings_from_gesamt_pivot(
        raw, through_round=2, include_club=svc._has_any_club_value(raw)
    )
    expected = str(ranked.loc[ranked["rank"].eq(int(cut_pos)), Columns.player_name].iloc[0])
    assert cut["value"] == expected
