"""Pre-2022 weekly scratch placement bonus (1..N for N real teams)."""

from extract_excel_data import (
    _is_phantom_pre_2022_team_name,
    _pre_2022_placement_team_count,
    _pre_2022_weekly_placement_bonuses,
)


def test_phantom_team_names():
    assert _is_phantom_pre_2022_team_name("0") is True
    assert _is_phantom_pre_2022_team_name("bye") is True
    assert _is_phantom_pre_2022_team_name("Bad-Tölz 2") is False


def test_five_team_league_ignores_phantom_bye_in_metadata():
    pins = {
        "Bad-Tölz 2": 900,
        "Werdenfels 1": 850,
        "Olching 07 3": 800,
        "EPA München 3": 750,
        "HighRoller Rosenheim 4": 700,
    }
    assert _pre_2022_placement_team_count(pins, 6) == 5
    bonuses = _pre_2022_weekly_placement_bonuses(pins, 6)
    assert bonuses == {
        "Bad-Tölz 2": 5.0,
        "Werdenfels 1": 4.0,
        "Olching 07 3": 3.0,
        "EPA München 3": 2.0,
        "HighRoller Rosenheim 4": 1.0,
    }
    assert sum(bonuses.values()) == 15.0


def test_even_eight_team_league_unchanged():
    pins = {f"Team {index}": 1000 - index * 10 for index in range(8)}
    assert _pre_2022_placement_team_count(pins, 8) == 8
    bonuses = _pre_2022_weekly_placement_bonuses(pins, 8)
    assert bonuses["Team 0"] == 8.0
    assert bonuses["Team 7"] == 1.0
    assert sum(bonuses.values()) == 36.0


def test_phantom_team_block_excluded_from_ranking():
    pins = {
        "0": 0,
        "Alpha": 500,
        "Beta": 400,
        "Gamma": 300,
        "Delta": 200,
        "Epsilon": 100,
    }
    bonuses = _pre_2022_weekly_placement_bonuses(pins, 6)
    assert "0" not in bonuses
    assert bonuses["Alpha"] == 5.0
    assert sum(bonuses.values()) == 15.0


def test_no_show_team_gets_zero_bonus_while_league_keeps_full_scale():
    pins = {
        "Pfaffenhofen 1": 3256,
        "EPA 2": 3402,
        "Highroller 1": 2961,
        "EPA 3": 2827,
        "Olching 07 1": 2792,
        "Lauterach 1": 0,
    }
    bonuses = _pre_2022_weekly_placement_bonuses(pins, 6)
    assert bonuses["EPA 2"] == 6.0
    assert bonuses["Pfaffenhofen 1"] == 5.0
    assert bonuses["Highroller 1"] == 4.0
    assert bonuses["EPA 3"] == 3.0
    assert bonuses["Olching 07 1"] == 2.0
    assert bonuses["Lauterach 1"] == 0.0
    assert sum(bonuses.values()) == 20.0
