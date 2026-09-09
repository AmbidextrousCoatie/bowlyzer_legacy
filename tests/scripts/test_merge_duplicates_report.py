"""Duplicate-key report must stay correct when vectorized (no per-row CSV writes)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.merge_league_sources import _write_duplicates_report


def test_write_duplicates_report_counts_and_files(tmp_path: Path) -> None:
    combined = pd.DataFrame(
        [
            {
                "__k_league": "bayl",
                "__k_season": "24/25",
                "__k_week": "1",
                "__k_team": "a 1",
                "__k_player": "alice",
                "__source_idx": "0",
                "Score": "100",
                "Team": "A 1",
            },
            {
                "__k_league": "bayl",
                "__k_season": "24/25",
                "__k_week": "1",
                "__k_team": "a 1",
                "__k_player": "alice",
                "__source_idx": "1",
                "Score": "100",
                "Team": "A 1",
            },
            {
                "__k_league": "bayl",
                "__k_season": "24/25",
                "__k_week": "1",
                "__k_team": "b 1",
                "__k_player": "bob",
                "__source_idx": "0",
                "Score": "110",
                "Team": "B 1",
            },
            {
                "__k_league": "bayl",
                "__k_season": "24/25",
                "__k_week": "1",
                "__k_team": "b 1",
                "__k_player": "bob",
                "__source_idx": "1",
                "Score": "120",
                "Team": "B 1",
            },
            {
                "__k_league": "ll s",
                "__k_season": "24/25",
                "__k_week": "1",
                "__k_team": "c 1",
                "__k_player": "cara",
                "__source_idx": "0",
                "Score": "200",
                "Team": "C 1",
            },
        ]
    )
    dedupe_cols = ["__k_league", "__k_season", "__k_week", "__k_team", "__k_player"]
    out = tmp_path / "dups.csv"
    non_exact = tmp_path / "dups_non_exact.csv"

    stats = _write_duplicates_report(
        combined=combined,
        dedupe_cols=dedupe_cols,
        out_path=out,
        non_exact_out_path=non_exact,
        sep=";",
    )

    assert stats["duplicate_groups"] == 2
    assert stats["duplicate_rows"] == 4
    assert stats["exact_groups_business"] == 1
    assert stats["non_exact_groups_business"] == 1
    assert stats["rows_in_exact_groups_business"] == 2
    assert stats["rows_in_non_exact_groups_business"] == 2

    full = pd.read_csv(out, sep=";", dtype=str).fillna("")
    assert len(full) == 4
    conflict = pd.read_csv(non_exact, sep=";", dtype=str).fillna("")
    assert len(conflict) == 2
    assert set(conflict["Score"]) == {"110", "120"}
