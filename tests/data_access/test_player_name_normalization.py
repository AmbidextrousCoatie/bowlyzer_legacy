"""Canonical player name parsing (family / given, comma vs last-word rules)."""

from __future__ import annotations

from data_access.player_name_normalization import (
    candidate_canonical_names,
    canonicalize_player_name,
    given_names_substring_equivalent,
    group_canonical_target,
    name_identity_key,
    names_share_identity,
    normalize_particle_name,
    normalize_player_label,
    normalize_player_name_whitespace,
    parse_player_name_parts,
)


def test_whitespace_collapse() -> None:
    assert normalize_player_label("  Feller ,  Christian  ") == "Feller, Christian"
    assert normalize_player_name_whitespace("  Feller ,  Christian  ") == "Feller, Christian"


def test_comma_spacing_variants_share_label() -> None:
    assert normalize_player_label("Mihatsch , Rudolf") == "Mihatsch, Rudolf"
    assert normalize_player_label("Mihatsch, Rudolf") == "Mihatsch, Rudolf"
    assert canonicalize_player_name("Mihatsch , Rudolf") == "Mihatsch, Rudolf"


def test_comma_form_family_first() -> None:
    assert parse_player_name_parts("Feller, Christian") == ("Feller", "Christian")
    assert canonicalize_player_name("Feller, Christian") == "Feller, Christian"
    assert canonicalize_player_name("Hoffman, Hans Peter") == "Hoffman, Hans Peter"
    assert canonicalize_player_name("Behn-Remus, Daniel") == "Behn-Remus, Daniel"


def test_comma_with_extra_whitespace() -> None:
    assert normalize_player_label("Kristof , Robert") == "Kristof, Robert"
    assert canonicalize_player_name("Kristof , Robert") == "Kristof, Robert"


def test_no_comma_last_word_is_family() -> None:
    assert parse_player_name_parts("Christian Feller") == ("Feller", "Christian")
    assert canonicalize_player_name("Christian Feller") == "Feller, Christian"
    assert canonicalize_player_name("Hans Peter Hoffman") == "Hoffman, Hans Peter"
    assert canonicalize_player_name("Daniel Behn-Remus") == "Behn-Remus, Daniel"


def test_single_token_is_family_only() -> None:
    assert canonicalize_player_name("Madonna") == "Madonna"


def test_reversed_spellings_canonicalize_same() -> None:
    assert canonicalize_player_name("Scheigenpflug, Stephan") == "Scheigenpflug, Stephan"
    assert canonicalize_player_name("Stephan Scheigenpflug") == "Scheigenpflug, Stephan"


def test_von_van_particle_identity() -> None:
    assert normalize_particle_name("Alt, Christiane von") == "von Alt, Christiane"
    assert normalize_particle_name("Von Alt, Christiane") == "von Alt, Christiane"
    assert normalize_particle_name("Weverberg, Susanne van") == "van Weverberg, Susanne"
    assert normalize_particle_name("Weverberg Van, Susanne") == "van Weverberg, Susanne"
    assert names_share_identity("Von Alt, Christiane", "Alt, Christiane von")
    assert names_share_identity("Weverberg Van, Susanne", "Weverberg, Susanne van")


def test_generation_suffix_identity() -> None:
    variants = [
        "Glasl jun., Hans-Jürgen",
        "Glasl, Hans-Jürgen",
        "Hans-Jürgen Glasl sen.",
        "Hans-Jürgen Glasl",
    ]
    keys = {name_identity_key(name) for name in variants}
    assert keys == {("glasl", "hans-jürgen")}
    assert name_identity_key(group_canonical_target(variants) or "") == ("glasl", "hans-jürgen")


def test_given_names_substring_equivalent() -> None:
    assert given_names_substring_equivalent("alex", "alexander")
    assert given_names_substring_equivalent("alexander", "alex")
    assert given_names_substring_equivalent("carina", "carina mareen")
    assert given_names_substring_equivalent("carina mareen", "carina")
    assert given_names_substring_equivalent("carina", "carina-maren")
    assert given_names_substring_equivalent("hans", "hans-jürgen")
    assert given_names_substring_equivalent("max", "maximilian")
    assert given_names_substring_equivalent("maximilian", "max")
    assert not given_names_substring_equivalent("ann", "johann")
    assert not given_names_substring_equivalent("bob", "robert")


def test_two_token_reversal_equivalence() -> None:
    variants = ["Köse, Sahin", "Sahin Köse", "Köse Sahin"]
    assert group_canonical_target(variants) == "Köse, Sahin"
    assert candidate_canonical_names("Köse Sahin") == frozenset(
        {"Köse, Sahin", "Sahin, Köse"}
    )
    assert candidate_canonical_names("Sahin Köse") == frozenset(
        {"Köse, Sahin", "Sahin, Köse"}
    )
    assert canonicalize_player_name("Köse Sahin") == "Sahin, Köse"
    assert canonicalize_player_name("Sahin Köse") == "Köse, Sahin"
