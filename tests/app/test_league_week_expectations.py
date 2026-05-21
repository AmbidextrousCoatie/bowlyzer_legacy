from app.utils.league_week_expectations import (
    expected_weeks_for_league,
    is_bayernliga,
)


def test_is_bayernliga():
    assert is_bayernliga("BayL")
    assert is_bayernliga("BayL (D)")
    assert not is_bayernliga("BZOL S1")


def test_expected_weeks_bayernliga_always_six():
    assert expected_weeks_for_league("BayL", 10) == 6
    assert expected_weeks_for_league("BayL (D)", 12) == 6


def test_expected_weeks_matches_team_count():
    assert expected_weeks_for_league("BZOL S1", 8) == 8
    assert expected_weeks_for_league("A-Klasse Süd 2", 9) == 9


def test_expected_weeks_fallback_when_no_teams():
    assert expected_weeks_for_league("Unknown League", 0) == 6
