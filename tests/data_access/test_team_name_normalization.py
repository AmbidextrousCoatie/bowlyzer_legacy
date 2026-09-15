"""Team label regex normalization used at Flask runtime (not scripts.data)."""

from __future__ import annotations

from data_access.team_name_normalization import normalize_team_name, reset_team_normalization_stats


def test_normalize_team_name_is_deterministic_with_cache():
    reset_team_normalization_stats()
    first = normalize_team_name("PANthers Pfarrk 2")
    second = normalize_team_name("PANthers Pfarrk 2")
    assert first == second


def test_normalize_team_name_applies_config_regex():
    reset_team_normalization_stats()
    assert normalize_team_name("Lechbowler 1") == "Lechbowler Augsburg 1"
