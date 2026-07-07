"""Tournament event name → short abbreviation (mirrors league_mapping.csv for leagues)."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_YEAR_SUFFIX_RE = re.compile(r"\s+20\d{2}\s*$")

# Maps year-stripped labels (and GF/legacy wording variants) to a stable group key.
_GROUP_CANONICAL_ALIASES: Dict[str, str] = {
    "Bayerische Meisterschaft - Männer Einzel": "Bayerische Meisterschaft Einzel",
    "Bayerische Meisterschaft Männer Einzel": "Bayerische Meisterschaft Einzel",
    "Bayerische Meisterschaft - Frauen Einzel": "Bayerische Meisterschaft Einzel Damen",
    "Bayerische Meisterschaft - Damen Einzel": "Bayerische Meisterschaft Einzel Damen",
    "Bayerische Meisterschaft Damen Einzel": "Bayerische Meisterschaft Einzel Damen",
    "Südbayerische Meisterschaft": "Südbayerische Meisterschaft Einzel",
    "Südbayerische Meisterschaft Männer Einzel": "Südbayerische Meisterschaft Einzel",
    "Südbayerische Meisterschaft - Männer Einzel": "Südbayerische Meisterschaft Einzel",
    "Südbayerische Meisterschaft Damen Einzel": "Südbayerische Meisterschaft Einzel Damen",
    "Südbayerische Meisterschaft - Damen Einzel": "Südbayerische Meisterschaft Einzel Damen",
    "Südbayerische Meisterschaft - Frauen Einzel": "Südbayerische Meisterschaft Einzel Damen",
    "Nordbayerische Meisterschaft": "Nordbayrische Meisterschaft Einzel",
    "Nordbayrische Meisterschaft": "Nordbayrische Meisterschaft Einzel",
    "Nordbayerische Meisterschaft Männer Einzel": "Nordbayrische Meisterschaft Einzel",
    "Nordbayerische Meisterschaft - Männer Einzel": "Nordbayrische Meisterschaft Einzel",
    "Nordbayerische Meisterschaft Damen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
    "Nordbayerische Meisterschaft - Damen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
    "Nordbayerische Meisterschaft - Frauen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
}

_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "tournament_mapping.csv"
)


def _split_aliases(raw: str) -> List[str]:
    return [part.strip() for part in str(raw or "").split("|") if part.strip()]


@lru_cache(maxsize=1)
def _load_tournament_mapping_rows() -> List[dict]:
    if not _MAPPING_PATH.is_file():
        return []
    rows: List[dict] = []
    with _MAPPING_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            abbrev = (row.get("id") or "").strip()
            long_name = (row.get("long_name") or "").strip()
            if abbrev and long_name:
                rows.append(row)
    return rows


@lru_cache(maxsize=1)
def get_tournament_abbreviation_lookup() -> Dict[str, str]:
    """
    Event label (``long_name`` or alias) → abbreviation ``id``.

    Canonical source is ``database/relational_csv/tournament_mapping.csv``.
    """
    lookup: Dict[str, str] = {}
    for row in _load_tournament_mapping_rows():
        abbrev = (row.get("id") or "").strip()
        long_name = (row.get("long_name") or "").strip()
        if not abbrev or not long_name:
            continue
        lookup[long_name] = abbrev
        for alias in _split_aliases(row.get("aliases") or ""):
            lookup[alias] = abbrev
    return lookup


def resolve_tournament_abbreviation(event_name: str) -> str:
    """Return abbreviation for a tournament event name, or the input if unmapped."""
    if event_name is None:
        return ""
    key = str(event_name).strip()
    if not key:
        return ""
    lookup = get_tournament_abbreviation_lookup()
    hit = lookup.get(key)
    if hit:
        return hit
    group = normalize_tournament_group_name(key)
    if group != key:
        return lookup.get(group, key)
    return key


@lru_cache(maxsize=1)
def _group_alias_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = dict(_GROUP_CANONICAL_ALIASES)
    for row in _load_tournament_mapping_rows():
        long_name = (row.get("long_name") or "").strip()
        if not long_name:
            continue
        canonical = _GROUP_CANONICAL_ALIASES.get(long_name, long_name)
        lookup[long_name] = canonical
        for alias in _split_aliases(row.get("aliases") or ""):
            lookup[alias] = canonical
    return lookup


def normalize_tournament_group_name(event_name: str) -> str:
    """
    Stable display/group key for a tournament event.

    Strips trailing calendar years (``… 2018``) and maps GF/legacy label variants
    to one canonical name. The raw ``event_name`` in the database is unchanged.
    """
    text = str(event_name or "").strip()
    if not text:
        return ""
    stripped = _YEAR_SUFFIX_RE.sub("", text).strip()
    return _group_alias_lookup().get(stripped, stripped)
