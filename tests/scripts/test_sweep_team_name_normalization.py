"""Sweep redundant literal rules from team_name_normalization.json."""

from __future__ import annotations

from scripts.sweep_team_name_normalization import (
    apply_regex_map,
    merge_literal_runs,
    sweep_map,
)


def test_merge_profishop_mun_literals():
    regex_map = {
        "^ProfiShop\\s+Mün(?:\\s+(\\d+))?$": "Team ProfiShop \\1",
        "^ProfiShop\\ Mün\\ 1$": "Team ProfiShop 1",
        "^ProfiShop\\ Mün\\ 2$": "Team ProfiShop 2",
        "^ProfiShop\\ Mün\\ 3$": "Team ProfiShop 3",
    }
    merged, removed = merge_literal_runs(regex_map, min_run=2)
    assert removed == 3
    assert "^ProfiShop\\ Mün\\ 1$" not in merged
    assert "^ProfiShop\\ Mün\\ (\\d+)$" in merged
    assert apply_regex_map("ProfiShop Mün 2", merged) == "Team ProfiShop 2"


def test_sweep_preserves_normalization():
    before = {
        "^Foo\\ Bar\\ 1$": "Canonical 1",
        "^Foo\\ Bar\\ 2$": "Canonical 2",
        "^Other\\s+Club(?:\\s+(\\d+))?$": "Other Club \\1",
    }
    swept, stats = sweep_map(before, ["Foo Bar 1", "Foo Bar 2", "Other Club 3"])
    assert stats["end"] < stats["start"]
    assert apply_regex_map("Foo Bar 1", before) == apply_regex_map("Foo Bar 1", swept)
