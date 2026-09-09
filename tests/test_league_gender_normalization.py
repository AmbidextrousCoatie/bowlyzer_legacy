"""League title → canonical id: long_name match, then gender from Damen/Frauen vs default male."""

from __future__ import annotations

from scripts.data import extract_excel_data as m

m._LEAGUE_MAPPING_CACHE = None


def test_bayernliga_damen_maps_to_female_league():
    assert m.normalize_league_display_to_canonical("Bayernliga - Damen") == "BayL (D)"


def test_bayernliga_herren_maps_to_male_league():
    assert m.normalize_league_display_to_canonical("Bayernliga - Herren") == "BayL"


def test_bayernliga_frauen_maps_to_female_league():
    assert m.normalize_league_display_to_canonical("Bayernliga - Frauen") == "BayL (D)"


def test_bayernliga_without_marker_defaults_male():
    assert m.normalize_league_display_to_canonical("Bayernliga") == "BayL"


def test_bereichsliga_splits_by_gender():
    assert m.normalize_league_display_to_canonical("Bereichsliga Süd 1 - Damen") == "BL S1 (D)"
    assert m.normalize_league_display_to_canonical("Bereichsliga Süd 1 - Herren") == "BL S1"
    assert m.normalize_league_display_to_canonical("Bereichsliga Nord 1 - Damen") == "BL N1 (D)"


def test_gender_scope_from_title():
    assert m._derive_league_gender_scope("Bayernliga - Damen") == "female"
    assert m._derive_league_gender_scope("Bayernliga  -  Frauen") == "female"
    assert m._derive_league_gender_scope("Bayernliga") == "male"
    assert m._derive_league_gender_scope("Bayernliga - Herren") == "male"
    assert m._derive_league_gender_scope("Bezirksliga Nord 4 - Männer") == "male"
    assert m._derive_league_gender_scope("Landesliga Süd (D)") == "female"
    assert m._derive_league_gender_scope("LL S (D)") == "female"


def test_landesliga_sued_frauen_maps_to_female_id():
    """Schlüssel titles use Frauen; must not collapse to male LL S on re-normalize."""
    assert m.normalize_league_display_to_canonical("Landesliga Süd Frauen") == "LL S (D)"
    assert m.normalize_league_display_to_canonical("Landesliga Süd - Frauen") == "LL S (D)"
    # Fallback label from a first pass must stay female on the second pass.
    assert m.normalize_league_display_to_canonical("Landesliga Süd (D)") == "LL S (D)"


def test_landesliga_sued_maenner_maps_to_male_id():
    assert m.normalize_league_display_to_canonical("Landesliga Süd 1 Männer") == "LL S"
    assert m.normalize_league_display_to_canonical("Landesliga Süd") == "LL S"


def test_long_name_match_tolerates_dashes_and_spaces():
    assert m._long_name_matches_title(
        m._normalize_league_match_text("Bereichsliga Süd 1"),
        m._normalize_league_match_text("Bereichsliga  Süd   1  -  Herren"),
    )
