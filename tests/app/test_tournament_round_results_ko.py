"""KO-Finale round results: unplayed games show blank cells when absent from import."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.tournament_service import TournamentService, _tournament_df_string_series
from data_access.schema import Columns

CSV = Path(__file__).resolve().parents[2] / "database" / "data" / "player_stats_merged_plus_tournaments.csv"
TOURNAMENT = "Bayerische Meisterschaft - Frauen Einzel"
SEASON = "25/26"
KO_ROUND = 3


def _load_frauen_df() -> pd.DataFrame:
    if not CSV.is_file():
        pytest.skip("tournament CSV fixture not present")
    raw = pd.read_csv(CSV, sep=";", low_memory=False)
    raw = raw[raw["Event Type"].astype(str).str.lower().eq("tournament")]
    raw = raw[raw["Event Name"].astype(str).eq(TOURNAMENT)]
    raw = raw[raw["Season"].astype(str).str.strip().eq(SEASON)]
    return pd.DataFrame(
        {
            Columns.season: raw["Season"],
            Columns.event_name: raw["Event Name"],
            Columns.round_number: pd.to_numeric(raw["Round Number"], errors="coerce"),
            Columns.round_name: _tournament_df_string_series(raw["Round Name"]),
            Columns.game_number: pd.to_numeric(raw["Game Number"], errors="coerce"),
            Columns.player_name: _tournament_df_string_series(raw["Player"]),
            Columns.player_id: _tournament_df_string_series(raw["Player ID"]),
            Columns.club: _tournament_df_string_series(raw["Club"]),
            Columns.score: pd.to_numeric(raw["Score"], errors="coerce"),
            Columns.handicap: pd.to_numeric(raw.get("Handicap", 0), errors="coerce").fillna(0),
        }
    )


def _game_field_indices(table) -> list[int]:
    flat: list[tuple[str, int]] = []

    def walk(groups, offset: int = 0) -> int:
        idx = offset
        for grp in groups:
            for col in grp.columns or []:
                field = str(col.field or "")
                flat.append((field, idx))
                idx += 1
        return idx

    walk(table.columns)
    return [i for field, i in flat if field.startswith("game_")]


@pytest.fixture
def svc() -> TournamentService:
    return TournamentService()


def test_ko_round_results_blank_for_unplayed_games(svc: TournamentService) -> None:
    df = _load_frauen_df()
    svc._tournament_df_cache[svc._tournament_cache_key(SEASON, TOURNAMENT)] = df

    table = svc.get_round_results_table(SEASON, TOURNAMENT, KO_ROUND, df=df)
    assert table.data
    game_idx = _game_field_indices(table)
    assert game_idx

    blank_cells = sum(1 for row in table.data for i in game_idx if row[i] == "")
    assert blank_cells > 0

    for row in table.data:
        for i in game_idx:
            if row[i] == "":
                continue
            assert row[i] != 0 or row[i] == "", "game columns should be blank or positive pins"
