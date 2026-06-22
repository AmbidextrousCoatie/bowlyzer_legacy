"""Tournament event name → short abbreviation (mirrors league_mapping.csv for leagues)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

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
    return get_tournament_abbreviation_lookup().get(key, key)
