"""Merge Bereichsliga (BL) and Bezirksoberliga (BZOL) for level-5 diagnosis.

From 2016/17 the tier was renamed; historical data uses BL ids, newer data BZOL.
Week-coverage diagnosis treats them as one logical league per division/suffix.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

_LEVEL5_PREFIX = re.compile(r"^(BL|BZOL)\s+", re.IGNORECASE)
_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "league_mapping.csv"
)


@lru_cache(maxsize=1)
def get_level5_merge_registry() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Return ``(league_id -> merge_key, merge_key -> member ids)``.

    Only level-5 BL/BZOL ids with the same division, gender scope, and numeric
    suffix (e.g. ``N1``, ``S2 (D)``) share a merge key. Unpaired ids keep a
    singleton group keyed by the league id itself.
    """
    league_to_key: Dict[str, str] = {}
    key_to_members: Dict[str, List[str]] = {}

    if not _MAPPING_PATH.is_file():
        return league_to_key, key_to_members

    with _MAPPING_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            league_id = (row.get("id") or "").strip()
            if not league_id:
                continue
            try:
                level = int(str(row.get("level") or "").strip())
            except (TypeError, ValueError):
                continue
            if level != 5:
                continue

            suffix = _level5_suffix(league_id)
            if suffix is None:
                league_to_key[league_id] = league_id
                key_to_members.setdefault(league_id, []).append(league_id)
                continue

            division = (row.get("division") or "").strip().lower()
            gender = (row.get("gender_scope") or "").strip().lower()
            merge_key = f"L5|{division}|{gender}|{suffix}"
            league_to_key[league_id] = merge_key
            key_to_members.setdefault(merge_key, []).append(league_id)

    for members in key_to_members.values():
        members.sort()
    return league_to_key, key_to_members


def _level5_suffix(league_id: str) -> Optional[str]:
    text = str(league_id or "").strip()
    match = _LEVEL5_PREFIX.match(text)
    if not match:
        return None
    return text[match.end() :].strip()


def merge_key_for_league(league_id: str) -> str:
    league_to_key, _ = get_level5_merge_registry()
    key = str(league_id or "").strip()
    return league_to_key.get(key, key)


def merged_league_label(member_ids: Sequence[str]) -> str:
    """Combined first-column label, e.g. ``BL N1 / BZOL N1``."""
    ids = sorted({str(lid).strip() for lid in member_ids if str(lid).strip()})
    if not ids:
        return ""
    if len(ids) == 1:
        return ids[0]
    return " / ".join(ids)


def resolve_league_id_for_season(
    member_ids: Sequence[str],
    season: str,
    *,
    weeks_by_league_season: Mapping[Tuple[str, str], Sequence[int]],
    team_counts_by_league_season: Mapping[Tuple[str, str], int],
) -> str:
    """Pick the short id to use for deep links in a merged row cell."""
    members = sorted({str(lid).strip() for lid in member_ids if str(lid).strip()})
    if not members:
        return ""
    if len(members) == 1:
        return members[0]

    with_data = [
        lid
        for lid in members
        if weeks_by_league_season.get((lid, season)) or team_counts_by_league_season.get((lid, season), 0) > 0
    ]
    if with_data:
        bzol = [lid for lid in with_data if lid.upper().startswith("BZOL")]
        return bzol[0] if bzol else with_data[0]
    return members[0]
