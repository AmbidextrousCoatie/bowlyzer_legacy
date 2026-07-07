"""Tournament abbreviation lookup from tournament_mapping.csv."""

from app.utils.tournament_utils import (
    get_tournament_abbreviation_lookup,
    normalize_tournament_group_name,
    resolve_tournament_abbreviation,
)


def test_normalize_tournament_group_name_strips_year():
    assert (
        normalize_tournament_group_name("Bayerische Meisterschaft Einzel 2018")
        == "Bayerische Meisterschaft Einzel"
    )
    assert (
        normalize_tournament_group_name("Südbayerische Meisterschaft Einzel 2017")
        == "Südbayerische Meisterschaft Einzel"
    )
    assert (
        normalize_tournament_group_name("Nordbayrische Meisterschaft 2019")
        == "Nordbayrische Meisterschaft Einzel"
    )


def test_normalize_tournament_group_name_gf_aliases():
    assert (
        normalize_tournament_group_name("Bayerische Meisterschaft - Männer Einzel")
        == "Bayerische Meisterschaft Einzel"
    )
    assert (
        normalize_tournament_group_name("Südbayerische Meisterschaft")
        == "Südbayerische Meisterschaft Einzel"
    )
    assert (
        normalize_tournament_group_name("Nordbayerische Meisterschaft")
        == "Nordbayrische Meisterschaft Einzel"
    )


def test_resolve_tournament_abbreviation_long_names():
    assert resolve_tournament_abbreviation("Nordbayerische Meisterschaft") == "NBM M"
    assert resolve_tournament_abbreviation("Bayerische Meisterschaft - Männer Einzel") == "BM M"
    assert resolve_tournament_abbreviation("Bayerische Meisterschaft Männer Doppel") == "BM M D"
    assert resolve_tournament_abbreviation("Südbayerische Meisterschaft Damen Einzel") == "SBM D"


def test_resolve_tournament_abbreviation_alias():
    assert resolve_tournament_abbreviation("Südbayerische Meisterschaft - Frauen Einzel") == "SBM D"


def test_resolve_tournament_abbreviation_unknown_passthrough():
    assert resolve_tournament_abbreviation("Mystery Open 2026") == "Mystery Open 2026"


def test_lookup_is_non_empty():
    assert len(get_tournament_abbreviation_lookup()) >= 5
