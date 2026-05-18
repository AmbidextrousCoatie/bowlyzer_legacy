"""Incremental field-progress must match legacy snapshot standings."""

from __future__ import annotations

import pandas as pd

from app.services.tournament_service import (
    Columns,
    TournamentService,
    _field_progress_delta_games,
    _field_progress_prepare_game_pins,
    _field_progress_snapshot_from_cumulative,
    _progress_game_slots,
    _progress_snapshot_rows,
    _with_progress_pins,
)
from collections import defaultdict


def _mini_tournament_df() -> pd.DataFrame:
  return pd.DataFrame(
      {
          Columns.player_name: [
              "Alice",
              "Alice",
              "Bob",
              "Bob",
              "Carol",
              "Carol",
              "Dave",
              "Dave",
          ],
          Columns.round_number: [1, 1, 1, 1, 1, 1, 1, 1],
          Columns.game_number: [0, 1, 0, 1, 0, 1, 0, 1],
          Columns.score: [200, 210, 190, 195, 180, 185, 170, 175],
          Columns.handicap: [10, 10, 20, 20, 5, 5, 15, 15],
          Columns.round_name: ["Qual"] * 8,
      }
  )


def test_incremental_snapshots_match_legacy():
    df = _with_progress_pins(_mini_tournament_df(), use_net=True)
    round_lengths = [(1, "Qual", 2)]
    game_slots = _progress_game_slots(round_lengths, 2)
    per_game_pins = _field_progress_prepare_game_pins(df)
    cum_pins: dict[str, float] = defaultdict(float)
    cum_games: dict[str, int] = defaultdict(int)
    prev = None
    for rn, g in game_slots:
        for rno, gg in _field_progress_delta_games(prev, (rn, g), round_lengths):
            for player, pins in per_game_pins.get((rno, gg), {}).items():
                cum_pins[player] += pins
                cum_games[player] += 1
        prev = (rn, g)
        legacy = _progress_snapshot_rows(df, round_lengths, rn, g)
        fast = _field_progress_snapshot_from_cumulative(cum_pins, cum_games)
        assert legacy == fast, f"mismatch at round={rn} game={g}"


def test_ko_bye_player_excluded_from_pins():
    df = pd.DataFrame(
        {
            Columns.player_name: ["Alice", "bye"],
            Columns.round_number: [1, 1],
            Columns.game_number: [0, 0],
            Columns.score: [200, 0],
            Columns.round_name: ["Q", "Q"],
        }
    )
    df = _with_progress_pins(df, use_net=False)
    pins = _field_progress_prepare_game_pins(df)
    assert "bye" not in pins.get((1, 0), {})
