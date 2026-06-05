"""Level-5 BL/BZOL merge helpers."""

from app.utils.league_level5_merge import (
    merge_key_for_league,
    merged_league_label,
    resolve_league_id_for_season,
)


def test_bl_and_bzol_share_merge_key():
    assert merge_key_for_league("BL N1") == merge_key_for_league("BZOL N1")
    assert merge_key_for_league("BL S1 (D)") == merge_key_for_league("BZOL S1 (D)")


def test_unpaired_bl_n4_stays_singleton_label():
    assert merged_league_label(["BL N4"]) == "BL N4"
    assert merge_key_for_league("BL N4") != merge_key_for_league("BZOL N1")


def test_merged_label_joins_both_ids():
    assert merged_league_label(["BZOL N1", "BL N1"]) == "BL N1 / BZOL N1"


def test_resolve_league_id_prefers_bzol_when_both_have_data():
    grouped = {("BL N1", "16/17"): [1], ("BZOL N1", "16/17"): [2]}
    team_counts = {("BL N1", "16/17"): 8, ("BZOL N1", "16/17"): 8}
    assert (
        resolve_league_id_for_season(
            ["BL N1", "BZOL N1"],
            "16/17",
            weeks_by_league_season=grouped,
            team_counts_by_league_season=team_counts,
        )
        == "BZOL N1"
    )


def test_resolve_league_id_uses_bl_for_historical_season():
    grouped = {("BL N1", "15/16"): [1, 2, 3]}
    team_counts = {("BL N1", "15/16"): 8}
    assert (
        resolve_league_id_for_season(
            ["BL N1", "BZOL N1"],
            "15/16",
            weeks_by_league_season=grouped,
            team_counts_by_league_season=team_counts,
        )
        == "BL N1"
    )
