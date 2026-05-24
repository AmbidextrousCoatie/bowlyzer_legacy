"""League tier levels from league_mapping.csv."""

from app.utils.league_utils import get_league_level


def test_bereichsliga_and_bzol_share_level():
    assert get_league_level("BL N1") == 5
    assert get_league_level("BZOL N1") == 5


def test_unknown_league_defaults_high():
    assert get_league_level("Not A Real League") == 99
