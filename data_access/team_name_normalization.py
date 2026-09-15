"""Runtime team-label regex map from ``database/config/team_name_normalization.json``.

Kept in ``data_access`` so Flask/Docker can canonicalize club/team labels without
importing ``scripts.data`` (ETL is not copied into the production image).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "database" / "config" / "team_name_normalization.json"
)

_TEAM_NAME_NORMALIZATION_CACHE: Dict[str, str] | None = None
_TEAM_NAME_REGEX_RULES_CACHE: List[Tuple[str, re.Pattern[str], str]] | None = None
_TEAM_NORMALIZATION_STATS: Dict[str, object] | None = None


def normalize_optional_text(value):
    """Normalize metadata text value (empty / NaN → None)."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _load_team_name_regex_map() -> Dict[str, str]:
    global _TEAM_NAME_NORMALIZATION_CACHE
    if _TEAM_NAME_NORMALIZATION_CACHE is not None:
        return _TEAM_NAME_NORMALIZATION_CACHE

    if not DEFAULT_CONFIG_PATH.is_file():
        _TEAM_NAME_NORMALIZATION_CACHE = {}
        return _TEAM_NAME_NORMALIZATION_CACHE

    try:
        payload = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
        mapping_raw = payload.get("team_name_regex_map", {}) if isinstance(payload, dict) else {}
        normalized = {}
        for source, target in mapping_raw.items():
            src_key = normalize_optional_text(source)
            tgt_val = normalize_optional_text(target)
            if src_key and tgt_val:
                normalized[src_key] = tgt_val
        _TEAM_NAME_NORMALIZATION_CACHE = normalized
    except Exception as exc:
        print(f"Warning: failed to load team name regex map: {exc}")
        _TEAM_NAME_NORMALIZATION_CACHE = {}

    return _TEAM_NAME_NORMALIZATION_CACHE


def _load_team_name_regex_rules() -> List[Tuple[str, re.Pattern[str], str]]:
    """Compiled (pattern_str, regex, replacement) in map order — built once per process."""
    global _TEAM_NAME_REGEX_RULES_CACHE
    if _TEAM_NAME_REGEX_RULES_CACHE is not None:
        return _TEAM_NAME_REGEX_RULES_CACHE

    rules: List[Tuple[str, re.Pattern[str], str]] = []
    for pattern, replacement in _load_team_name_regex_map().items():
        try:
            rules.append((pattern, re.compile(pattern), replacement))
        except re.error as exc:
            print(f"Warning: skip invalid team name regex {pattern!r}: {exc}")
    _TEAM_NAME_REGEX_RULES_CACHE = rules
    return _TEAM_NAME_REGEX_RULES_CACHE


def reset_team_normalization_stats():
    global _TEAM_NORMALIZATION_STATS
    _TEAM_NORMALIZATION_STATS = {
        # Distinct input strings that matched a regex rule (memoized; not row count).
        "regex_distinct_strings": 0,
        "regex_total": 0,
        "regex_by_source": {},
        # Rows in Team/Opponent columns where regex normalization changed the cell.
        "regex_cells_changed": 0,
    }
    _normalize_team_name_text.cache_clear()


def _bump_team_normalization_stat(kind: str, source_key: str):
    global _TEAM_NORMALIZATION_STATS
    if _TEAM_NORMALIZATION_STATS is None:
        reset_team_normalization_stats()
    if kind == "regex":
        _TEAM_NORMALIZATION_STATS["regex_total"] += 1
        _TEAM_NORMALIZATION_STATS["regex_distinct_strings"] += 1
        by_source = _TEAM_NORMALIZATION_STATS["regex_by_source"]
        by_source[source_key] = by_source.get(source_key, 0) + 1
    elif kind == "regex_cells":
        _TEAM_NORMALIZATION_STATS["regex_cells_changed"] += int(source_key)


def print_team_normalization_summary():
    stats = _TEAM_NORMALIZATION_STATS or {}
    distinct = int(stats.get("regex_distinct_strings", stats.get("regex_total", 0)))
    cells = int(stats.get("regex_cells_changed", 0))
    print("\nTeam Name Normalization Summary:")
    print(f"  regex: {cells:,} cells updated in Team/Opponent columns")
    print(f"  regex: {distinct:,} distinct team strings rewritten (cached; not row count)")
    if distinct:
        print("  regex rules hit (by distinct string, not by cell):")
        for source, count in sorted(
            (stats.get("regex_by_source") or {}).items(), key=lambda item: (-item[1], item[0])
        ):
            print(f"    - {source}: {count}")


@lru_cache(maxsize=131072)
def _normalize_team_name_text(text: str) -> str:
    """Apply regex map to already-normalized whitespace text (memoized)."""
    for pattern, compiled, replacement in _load_team_name_regex_rules():
        updated = compiled.sub(replacement, text, count=1)
        if updated != text:
            updated = re.sub(r"\s+", " ", updated).strip()
            _bump_team_normalization_stat("regex", pattern)
            return updated
    return text


def normalize_team_name(value):
    text = normalize_optional_text(value)
    if not text:
        return value
    return _normalize_team_name_text(text)
