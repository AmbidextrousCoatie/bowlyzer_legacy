from app.utils.league_week_expectations import (
    expected_weeks_for_league,
    expected_weeks_for_league_season,
    is_bayernliga,
)


def test_is_bayernliga():
    assert is_bayernliga("BayL")
    assert is_bayernliga("BayL (D)")
    assert not is_bayernliga("BZOL S1")


def test_expected_weeks_bayernliga_always_six():
    assert expected_weeks_for_league_season("BayL", "24/25", team_count=10) == 6
    assert expected_weeks_for_league_season("BayL (D)", "09/10", team_count=12) == 6


def test_expected_weeks_era_defaults():
    assert expected_weeks_for_league_season("BZOL S1", "09/10", team_count=8) == 8
    assert expected_weeks_for_league_season("BZOL S1", "24/25", team_count=8) == 6
    assert expected_weeks_for_league_season("BL S1 (D)", "09/10", team_count=5) == 8


def test_expected_weeks_fallback_when_no_season():
    assert expected_weeks_for_league("Unknown League", 0) == 6
    assert expected_weeks_for_league("BayL", 10) == 6
