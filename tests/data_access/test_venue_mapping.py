"""Venue alias → canonical mapping (club_mapping counterpart)."""

from __future__ import annotations

import pandas as pd

from data_access.venue_mapping import (
    build_venue_alias_lookup,
    canonicalize_venue_label,
    venue_compact_key,
)


def test_compact_key_folds_hyphens_and_neu_prefix() -> None:
    assert venue_compact_key("Isar-München") == venue_compact_key("Isar München")
    assert venue_compact_key("neu: Rottendorf") == venue_compact_key("Rottendorf")


def test_canonicalize_known_aliases() -> None:
    lookup = build_venue_alias_lookup()
    assert canonicalize_venue_label("Isar München", lookup) == "München Isar Bowling"
    assert canonicalize_venue_label("Dream-Bowl", lookup) == "Unterführing Dreambowl Palace"
    assert canonicalize_venue_label("Regensburg Superbowl", lookup) == "Regensburg Super Bowl"
    assert canonicalize_venue_label("Max Brunnthal", lookup) == "Brunnthal Max Munich"
    assert canonicalize_venue_label("Nürnberg Westbowl", lookup) == "Nürnberg West Bowling"


def test_placeholder_and_unknown_pass_through() -> None:
    lookup = build_venue_alias_lookup()
    assert canonicalize_venue_label("Unknown", lookup) == "Unknown"
    assert canonicalize_venue_label("", lookup) == ""
    assert canonicalize_venue_label("Some New House XYZ", lookup) == "Some New House XYZ"


def test_apply_to_location_series() -> None:
    from data_access.venue_mapping import apply_venue_mapping_to_series

    series = pd.Series(["Isar-München", "Unknown", "City Augsburg"])
    out = apply_venue_mapping_to_series(series)
    assert out.tolist() == ["München Isar Bowling", "Unknown", "Augsburg City Bowling"]
