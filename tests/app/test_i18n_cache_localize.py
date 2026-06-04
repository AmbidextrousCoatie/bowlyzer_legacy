"""Warm-cache i18n localization without recomputing payloads."""

from app.cache.i18n_cache_localize import localize_payload_for_language
from app.services.i18n_service import Language


def test_localize_swaps_catalog_strings():
    payload = {
        "title": "Tabelle",
        "columns": [{"title": "Spieler", "field": "name"}],
    }
    en = localize_payload_for_language(payload, Language.GERMAN, Language.ENGLISH)
    assert en["title"] == "Standings"
    assert en["columns"][0]["title"] == "Player"


def test_localize_resolves_title_key():
    payload = {
        "title": "Spieler",
        "title_key": "player",
        "columns": [],
    }
    en = localize_payload_for_language(payload, Language.GERMAN, Language.ENGLISH)
    assert en["title"] == "Player"
    assert en["title_key"] == "player"
