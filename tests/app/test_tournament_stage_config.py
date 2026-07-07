"""Tournament stage definitions for regional 3-tier events."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.tournament_service import TournamentService, _tournament_df_string_series
from app.utils.tournament_stage_config import (
    load_tournament_stage_definitions,
    stage_cut_rank_for_round,
)
from data_access.schema import Columns

DEFS = Path(__file__).resolve().parents[2] / "database" / "data" / "tournament_stage_definitions.json"
PARQUET = Path(__file__).resolve().parents[2] / "database" / "data" / "tournaments_postprocessed.parquet"


def test_stage_definitions_file_non_empty() -> None:
    if not DEFS.is_file():
        pytest.skip("tournament_stage_definitions.json not present")
    assert len(load_tournament_stage_definitions()) >= 10


def test_legacy_sbm_2018_stage_cuts() -> None:
    if not DEFS.is_file():
        pytest.skip("tournament_stage_definitions.json not present")
    season, event = "17/18", "Südbayerische Meisterschaft Einzel 2018"
    assert stage_cut_rank_for_round(season, event, 1) == 79
    assert stage_cut_rank_for_round(season, event, 2) == 40
    assert stage_cut_rank_for_round(season, event, 3) is None


def test_gf_sbm_2026_official_cuts() -> None:
    if not DEFS.is_file():
        pytest.skip("tournament_stage_definitions.json not present")
    season, event = "25/26", "Südbayerische Meisterschaft"
    assert stage_cut_rank_for_round(season, event, 1) == 80
    assert stage_cut_rank_for_round(season, event, 2) == 40
    assert stage_cut_rank_for_round(season, event, 3) is None


def test_legacy_field_progress_cut_positions(svc: TournamentService) -> None:
    if not PARQUET.is_file():
        pytest.skip("tournaments_postprocessed.parquet not present")
    raw = pd.read_parquet(PARQUET)
    raw = raw[raw["Event Type"].astype(str).str.lower().eq("tournament")]
    from data_access.competition_schema import competition_event_column

    event_col = competition_event_column(raw)
    season = "17/18"
    for tournament in ("Bayerische Meisterschaft Einzel 2018", "Bayerische Meisterschaft Einzel"):
        sub = raw[
            (raw["Season"].astype(str).str.strip() == season)
            & (raw[event_col].astype(str) == "Bayerische Meisterschaft Einzel 2018")
        ]
        if sub.empty:
            pytest.skip("legacy BM 2018 not in parquet")
        sub = sub.copy()
        if Columns.club in sub.columns:
            sub[Columns.club] = _tournament_df_string_series(sub[Columns.club])
        svc._tournament_df_cache[svc._tournament_cache_key(season, tournament)] = sub
        svc._field_progress_cache.clear()

        fp = svc._compute_field_progress(season, tournament, df=sub)
        assert fp["cut_lines_position"] == [40, 20], tournament
        assert len(fp["tournament_leader_avg_series"]) == 18, tournament
        assert fp["cut_lines_avg"], tournament


@pytest.fixture
def svc() -> TournamentService:
    return TournamentService(database="db_tournament_regions_2026_gf")


def test_final_round_leaderboard_marks_players_inside_cut(svc: TournamentService) -> None:
    if not PARQUET.is_file():
        pytest.skip("tournaments_postprocessed.parquet not present")
    season, tournament = "18/19", "Südbayerische Meisterschaft Einzel 2019"
    df = svc._get_tournament_df(season=season, tournament=tournament)
    if df.empty:
        pytest.skip("SBM 2019 not in parquet")
    lb = svc.get_leaderboard_table(season, tournament, round_number=3, df=df)
    assert lb.data
    styled = sum(1 for meta in (lb.cell_metadata or {}).values() if meta.get("backgroundColor"))
    assert styled >= len(lb.data)


def test_player_section_includes_field_progress(svc: TournamentService) -> None:
    if not PARQUET.is_file():
        pytest.skip("tournaments_postprocessed.parquet not present")
    season, tournament = "18/19", "Südbayerische Meisterschaft Einzel"
    df = svc._get_tournament_df(season=season, tournament=tournament)
    if df.empty:
        pytest.skip("SBM 18/19 not in parquet")
    players = df[Columns.player_name].astype(str).str.strip().unique().tolist()
    if not players:
        pytest.skip("no players")
    payload = svc.get_player_section(season, tournament, players[0])
    fp = payload.get("field_progress") or {}
    assert fp.get("tournament_leader_avg_series")
    assert fp.get("cut_lines_position")
