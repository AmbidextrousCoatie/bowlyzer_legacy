"""Tests for tournament affiliation gap audit dedupe."""

from __future__ import annotations

from scripts.audit_tournament_club_gaps import dedupe_gap_rows


def test_dedupe_gap_rows_collapses_per_game_noise() -> None:
    rows = [
        {"player_id": "7245", "season": "05/06", "raw_club": "Berchtesgaden", "reason": "no_index_or_verein"},
        {"player_id": "7245", "season": "05/06", "raw_club": "Berchtesgaden", "reason": "no_index_or_verein"},
        {"player_id": "7245", "season": "05/06", "raw_club": "Berchtesgaden", "reason": "no_index_or_verein"},
        {"player_id": "100", "season": "25/26", "raw_club": "", "reason": "no_index_or_verein"},
        {
            "player_id": "100",
            "season": "25/26",
            "raw_club": "BV 68 Regensburg",
            "reason": "verein_no_extrapolation_match",
            "verein": "BV 68 Regensburg",
        },
    ]
    out = dedupe_gap_rows(rows)
    assert len(out) == 3
    by_key = {(r["player_id"], r["season"], r["reason"]): r for r in out}
    assert by_key[("7245", "05/06", "no_index_or_verein")]["game_rows"] == 3
    assert by_key[("100", "25/26", "no_index_or_verein")]["game_rows"] == 1
    assert by_key[("100", "25/26", "verein_no_extrapolation_match")]["verein"] == "BV 68 Regensburg"
