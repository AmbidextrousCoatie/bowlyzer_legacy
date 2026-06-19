"""Tests for league week schema resolution."""

from data_access.league_week_schema import (
    expected_weeks_for_league,
    expected_weeks_for_league_season,
    schema_rule_summary,
)


def test_pre_2020_default_eight_weeks():
    assert expected_weeks_for_league_season("BL S1 (D)", "09/10", team_count=5) == 8
    assert expected_weeks_for_league_season("BZOL S1", "09/10", team_count=8) == 8


def test_post_2020_default_six_weeks():
    assert expected_weeks_for_league_season("BZOL S1", "24/25", team_count=3) == 6
    assert expected_weeks_for_league_season("BL S1 (D)", "23/24", team_count=5) == 6


def test_bayernliga_always_six():
    assert expected_weeks_for_league_season("BayL", "09/10", team_count=10) == 6
    assert expected_weeks_for_league_season("BayL (D)", "24/25", team_count=12) == 6


def test_config_override():
    assert expected_weeks_for_league_season("LL S", "09/10", team_count=13) == 13


def test_expected_weeks_for_league_without_season_uses_post_default():
    assert expected_weeks_for_league("BZOL S1", 8) == 6
    assert expected_weeks_for_league("BayL", 10) == 6


def test_schema_rule_summary_mentions_config():
    summary = schema_rule_summary()
    assert "bayernliga=6" in summary
    assert "20/21" in summary
