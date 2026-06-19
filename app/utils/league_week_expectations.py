"""Expected matchday counts for league week-coverage diagnosis."""

from __future__ import annotations

from data_access.league_week_schema import (
    DEFAULT_BAYERNLIGA_IDS,
    expected_weeks_for_league,
    expected_weeks_for_league_season,
    schema_rule_summary,
)

BAYERNLIGA_LEAGUE_IDS = DEFAULT_BAYERNLIGA_IDS


def is_bayernliga(league_name: str) -> bool:
    key = str(league_name or "").strip()
    return key in BAYERNLIGA_LEAGUE_IDS


__all__ = [
    "BAYERNLIGA_LEAGUE_IDS",
    "expected_weeks_for_league",
    "expected_weeks_for_league_season",
    "is_bayernliga",
    "schema_rule_summary",
]
