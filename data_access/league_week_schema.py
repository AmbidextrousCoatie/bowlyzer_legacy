"""Expected league matchdays from season era defaults and optional overrides."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "database" / "config" / "league_week_schema.json"
)

DEFAULT_SEASON_CUTOFF = "20/21"
DEFAULT_PRE_CUTOFF_WEEKS = 8
DEFAULT_POST_CUTOFF_WEEKS = 6
DEFAULT_BAYERNLIGA_IDS = frozenset({"BayL", "BayL (D)"})
DEFAULT_BAYERNLIGA_WEEKS = 6


def _normalize_season(season: str) -> str:
    text = str(season or "").strip()
    if not text:
        return ""
    if "-" in text and "/" not in text:
        return text.replace("-", "/")
    return text


def _normalize_league(league: str) -> str:
    return str(league or "").strip()


@lru_cache(maxsize=1)
def load_league_week_schema() -> dict[str, Any]:
    if not _SCHEMA_PATH.is_file():
        return {}
    try:
        payload = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _override_lookup(schema: dict[str, Any]) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for row in schema.get("overrides") or []:
        if not isinstance(row, dict):
            continue
        league = _normalize_league(row.get("league", ""))
        season = _normalize_season(row.get("season", ""))
        weeks = row.get("expected_weeks")
        if not league or not season or weeks is None:
            continue
        try:
            out[(league, season)] = max(0, int(weeks))
        except (TypeError, ValueError):
            continue
    return out


def schema_rule_summary() -> str:
    schema = load_league_week_schema()
    pre = int(schema.get("pre_cutoff_weeks", DEFAULT_PRE_CUTOFF_WEEKS))
    post = int(schema.get("post_cutoff_weeks", DEFAULT_POST_CUTOFF_WEEKS))
    cutoff = str(schema.get("season_cutoff", DEFAULT_SEASON_CUTOFF))
    bayernliga_weeks = int(schema.get("bayernliga_weeks", DEFAULT_BAYERNLIGA_WEEKS))
    return (
        f"bayernliga={bayernliga_weeks}; before {cutoff}={pre}w; "
        f"from {cutoff}={post}w; overrides in league_week_schema.json"
    )


def expected_weeks_for_league_season(
    league: str,
    season: str,
    *,
    team_count: int = 0,
) -> int:
    """
    Matchdays expected for a league×season.

    Priority:
    1. Explicit override in ``database/config/league_week_schema.json``
    2. Bayernliga ids → fixed week count (default 6)
    3. Season before cutoff → pre_cutoff_weeks (default 8)
    4. Season from cutoff onward → post_cutoff_weeks (default 6)
  """
    _ = team_count  # reserved for future team-count fallbacks in overrides
    schema = load_league_week_schema()
    league_key = _normalize_league(league)
    season_key = _normalize_season(season)

    overrides = _override_lookup(schema)
    if league_key and season_key and (league_key, season_key) in overrides:
        return overrides[(league_key, season_key)]

    bayernliga_ids = frozenset(
        str(item).strip()
        for item in (schema.get("bayernliga_league_ids") or DEFAULT_BAYERNLIGA_IDS)
        if str(item).strip()
    )
    bayernliga_weeks = int(schema.get("bayernliga_weeks", DEFAULT_BAYERNLIGA_WEEKS))
    if league_key in bayernliga_ids:
        return bayernliga_weeks

    cutoff = str(schema.get("season_cutoff", DEFAULT_SEASON_CUTOFF))
    pre_weeks = int(schema.get("pre_cutoff_weeks", DEFAULT_PRE_CUTOFF_WEEKS))
    post_weeks = int(schema.get("post_cutoff_weeks", DEFAULT_POST_CUTOFF_WEEKS))

    if season_key and season_key < cutoff:
        return pre_weeks
    return post_weeks


def expected_weeks_for_league(league: str, team_count: int, *, season: str = "") -> int:
    """Backward-compatible wrapper; pass ``season`` for era-aware expectations."""
    if season:
        return expected_weeks_for_league_season(league, season, team_count=team_count)
    schema = load_league_week_schema()
    bayernliga_ids = frozenset(
        str(item).strip()
        for item in (schema.get("bayernliga_league_ids") or DEFAULT_BAYERNLIGA_IDS)
        if str(item).strip()
    )
    if _normalize_league(league) in bayernliga_ids:
        return int(schema.get("bayernliga_weeks", DEFAULT_BAYERNLIGA_WEEKS))
    return int(schema.get("post_cutoff_weeks", DEFAULT_POST_CUTOFF_WEEKS))
