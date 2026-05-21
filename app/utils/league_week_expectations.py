"""Expected matchday counts for league week-coverage diagnosis."""

from __future__ import annotations

# Canonical ids from ``league_mapping.csv`` (Bayernliga always 6 weeks).
BAYERNLIGA_LEAGUE_IDS = frozenset({"BayL", "BayL (D)"})


def is_bayernliga(league_name: str) -> bool:
    key = str(league_name or "").strip()
    return key in BAYERNLIGA_LEAGUE_IDS


def expected_weeks_for_league(league_name: str, team_count: int) -> int:
    """
    Matchdays expected for a league/season in diagnosis.

    Rule: one week per team in the league, except Bayernliga (always 6).
    """
    if is_bayernliga(league_name):
        return 6
    if team_count > 0:
        return int(team_count)
    return 6
