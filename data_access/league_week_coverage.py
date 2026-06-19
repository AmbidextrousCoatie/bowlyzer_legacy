"""Week coverage for a single league×season (same rules as Liga-Wochen diagnosis)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import pandas as pd

from data_access.dtype_normalization import BOOL_FALSE_TOKENS, BOOL_TRUE_TOKENS
from data_access.schema import Columns

from data_access.league_week_schema import expected_weeks_for_league_season

WEEK_COVERAGE_OK = "ok"
WEEK_COVERAGE_WARN = "warn"
WEEK_COVERAGE_BAD = "bad"
WEEK_COVERAGE_CRITICAL = "critical"
WEEK_COVERAGE_EMPTY = ""


@dataclass(frozen=True)
class LeagueSeasonWeekCoverage:
    league: str
    season: str
    team_count: int
    expected_weeks: int
    available_weeks: List[int]
    missing_weeks: List[int]
    status: str

    @property
    def is_complete(self) -> bool:
        return not self.missing_weeks and self.expected_weeks > 0


def _computed_data_mask(series: pd.Series, *, want_true: bool) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    tokens = BOOL_TRUE_TOKENS if want_true else BOOL_FALSE_TOKENS
    return normalized.isin(tokens)


def _season_label_variants(season: str) -> set[str]:
    text = str(season or "").strip()
    if not text:
        return set()
    variants = {text}
    if "/" in text:
        variants.add(text.replace("/", "-"))
    if "-" in text:
        variants.add(text.replace("-", "/"))
    return variants


def _week_coverage_status(expected_count: int, missing_weeks: Sequence[int]) -> str:
    if expected_count <= 0:
        return WEEK_COVERAGE_EMPTY
    if not missing_weeks:
        return WEEK_COVERAGE_OK
    available_count = expected_count - len(missing_weeks)
    coverage_ratio = available_count / expected_count
    if coverage_ratio >= 0.67:
        return WEEK_COVERAGE_WARN
    if coverage_ratio >= 0.34:
        return WEEK_COVERAGE_BAD
    return WEEK_COVERAGE_CRITICAL


def compute_league_season_week_coverage(
    df: pd.DataFrame,
    *,
    league: str,
    season: str,
) -> LeagueSeasonWeekCoverage:
    """Mirror ``LeagueService.get_league_week_matrix`` for one league×season cell."""
    league_col = Columns.event if Columns.event in df.columns else "League"
    empty = LeagueSeasonWeekCoverage(
        league=league,
        season=season,
        team_count=0,
        expected_weeks=0,
        available_weeks=[],
        missing_weeks=[],
        status=WEEK_COVERAGE_EMPTY,
    )
    if df.empty or league_col not in df.columns or Columns.season not in df.columns:
        return empty

    season_variants = _season_label_variants(season)
    mask = df[league_col].astype(str) == str(league)
    mask &= df[Columns.season].astype(str).isin(season_variants)
    if Columns.event_type in df.columns:
        mask &= df[Columns.event_type].fillna("league").astype(str).str.lower().eq("league")
    sub = df.loc[mask]
    if sub.empty:
        return empty

    computed_mask = _computed_data_mask(sub[Columns.computed_data], want_true=True)
    raw_mask = _computed_data_mask(sub[Columns.computed_data], want_true=False)

    week_series = pd.to_numeric(sub.loc[computed_mask, Columns.week], errors="coerce")
    available_weeks = sorted({int(w) for w in week_series.dropna().tolist() if int(w) > 0})

    team_count = int(sub.loc[raw_mask, Columns.team_name].nunique()) if raw_mask.any() else 0
    if team_count == 0 and not available_weeks:
        return empty

    expected_count = expected_weeks_for_league_season(league, season, team_count=team_count)
    expected_set = set(range(1, expected_count + 1))
    missing_weeks = sorted(expected_set - set(available_weeks))
    status = _week_coverage_status(expected_count, missing_weeks)

    return LeagueSeasonWeekCoverage(
        league=league,
        season=season,
        team_count=team_count,
        expected_weeks=expected_count,
        available_weeks=available_weeks,
        missing_weeks=missing_weeks,
        status=status,
    )


def discover_league_season_pairs(df: pd.DataFrame) -> List[tuple[str, str]]:
    league_col = Columns.event if Columns.event in df.columns else "League"
    if df.empty or league_col not in df.columns or Columns.season not in df.columns:
        return []
    if Columns.event_type in df.columns:
        sub = df[df[Columns.event_type].fillna("league").astype(str).str.lower().eq("league")]
    else:
        sub = df
    pairs = (
        sub[[league_col, Columns.season]]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    return sorted({(str(league).strip(), str(season).strip()) for league, season in pairs})
