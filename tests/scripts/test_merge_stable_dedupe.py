"""Merge dedupe must collapse same game across sources with different match numbers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.merge_league_sources import DEFAULT_KEYS, merge_sources


def _row(
    *,
    season: str = "25/26",
    league: str = "BayL",
    week: str = "6",
    round_number: str = "1",
    match_number: str,
    team: str = "BC Bamberger Bowlinghaus 1",
    opponent: str = "BC Comet Nürnberg 1",
    position: str = "2",
    player: str,
    player_id: str = "16251",
    score: str = "150",
) -> dict:
    return {
        "Season": season,
        "Week": week,
        "Date": "2026-01-01",
        "League": league,
        "Team": team,
        "Opponent": opponent,
        "Position": position,
        "Player": player,
        "Player ID": player_id,
        "Round Number": round_number,
        "Match Number": match_number,
        "Score": score,
        "Points": "0",
    }


def test_merge_collapses_same_game_with_different_match_numbers(tmp_path: Path) -> None:
    low = tmp_path / "excel.csv"
    high = tmp_path / "gf.csv"
    out = tmp_path / "merged.csv"

    pd.DataFrame(
        [
            _row(match_number="1", player="Nickoleit, Thomas"),
            _row(match_number="0", player="Nikoleit Thomas"),
        ]
    ).to_csv(low, sep=";", index=False)
    pd.DataFrame([_row(match_number="3", player="Nikoleit Thomas")]).to_csv(high, sep=";", index=False)

    merge_sources([low, high], out, key_names=list(DEFAULT_KEYS), write_csv=True)

    merged = pd.read_csv(out, sep=";", dtype=str).fillna("")
    player_rows = merged[
        (merged["Player ID"] == "16251") & (merged["Position"] == "2")
    ]
    assert len(player_rows) == 1
    assert player_rows.iloc[0]["Score"] == "150"
