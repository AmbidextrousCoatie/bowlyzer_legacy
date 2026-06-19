"""Expected league points pool from scoring schema, team count, and matchdays."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional, Sequence

_SCORING_CSV = (
    Path(__file__).resolve().parents[1] / "database" / "relational_csv" / "scoring_system.csv"
)
_LEAGUE_SEASON_CSV = (
    Path(__file__).resolve().parents[1] / "database" / "relational_csv" / "league_season.csv"
)

DEFAULT_SCORING_2PT = "liga_bayern_2pt"
DEFAULT_SCORING_3PT = "liga_bayern_3pt"
DEFAULT_PLAYERS_PER_TEAM = 4


@dataclass(frozen=True)
class LeaguePointsBudget:
    number_of_teams: int
    games_per_week: int
    reference_weeks: int
    scoring_system_id: str
    players_per_team: int
    points_per_match: float
    weekly_match_points: float
    weekly_placement_points: float
    weekly_total_points: float
    season_total_points: float
    no_show_counts_by_week: Mapping[int, int] = field(default_factory=dict)

    def expected_weekly_points(self, week: int) -> float:
        """Schema weekly pool minus escalating no-show penalty for that matchday."""
        absent = int(self.no_show_counts_by_week.get(int(week), 0))
        return float(self.weekly_total_points) - no_show_weekly_reduction(absent)

    def formula_note(self) -> str:
        if self.weekly_placement_points:
            pairing = (self.number_of_teams + 1) // 2
            game_term = (
                f"({pairing} pair)×{self.games_per_week}×{self.points_per_match:g}pt/game"
            )
        else:
            game_term = (
                f"({self.number_of_teams}/2)×{self.games_per_week}×{self.points_per_match:g}"
            )
        note = (
            f"{game_term}×{self.reference_weeks}w"
            + (
                f" + placement {self.weekly_placement_points:g}/w"
                if self.weekly_placement_points
                else ""
            )
        )
        return note


def no_show_weekly_reduction(no_show_count: int) -> float:
    """
    Escalating weekly pool reduction when teams do not appear.

    1st no-show −1pt, 2nd −2pt, … nth −n pt → total n(n+1)/2 per matchday.
    """
    n = max(0, int(no_show_count))
    return n * (n + 1) / 2


def no_show_expected_pool_gap(team_count: int, no_show_count: int) -> float:
    """Weekly ref-vs-computed pool gap explained by absent teams (1pt each on placement scale)."""
    return float(max(0, int(team_count) - int(no_show_count)))


def apply_no_show_adjustments(
    budget: LeaguePointsBudget,
    no_show_counts_by_week: Mapping[int, int],
) -> LeaguePointsBudget:
    counts = {int(week): int(n) for week, n in no_show_counts_by_week.items() if int(n) > 0}
    if not counts:
        return budget
    season_total = sum(
        budget.weekly_total_points - no_show_weekly_reduction(counts.get(week, 0))
        for week in range(1, budget.reference_weeks + 1)
    )
    return LeaguePointsBudget(
        number_of_teams=budget.number_of_teams,
        games_per_week=budget.games_per_week,
        reference_weeks=budget.reference_weeks,
        scoring_system_id=budget.scoring_system_id,
        players_per_team=budget.players_per_team,
        points_per_match=budget.points_per_match,
        weekly_match_points=budget.weekly_match_points,
        weekly_placement_points=budget.weekly_placement_points,
        weekly_total_points=budget.weekly_total_points,
        season_total_points=season_total,
        no_show_counts_by_week=counts,
    )


@lru_cache(maxsize=1)
def _load_scoring_table() -> dict[str, dict[str, float]]:
    import pandas as pd

    if not _SCORING_CSV.is_file():
        return {}
    df = pd.read_csv(_SCORING_CSV, dtype=str).fillna("")
    out: dict[str, dict[str, float]] = {}
    for row in df.itertuples(index=False):
        out[str(row.id)] = {
            "ind_win": float(row.points_per_individual_match_win),
            "ind_loss": float(row.points_per_individual_match_loss),
            "team_win": float(row.points_per_team_match_win),
            "team_loss": float(row.points_per_team_match_loss),
        }
    return out


def points_per_match(
    scoring_system_id: str,
    *,
    players_per_team: int = DEFAULT_PLAYERS_PER_TEAM,
) -> float:
    """Match pairing awards both sides (individual + team legs), no ties assumed."""
    scoring = _load_scoring_table().get(scoring_system_id)
    if not scoring:
        return 0.0
    individual = players_per_team * (scoring["ind_win"] + scoring["ind_loss"])
    team = scoring["team_win"] + scoring["team_loss"]
    return float(individual + team)


def points_per_game_for_budget(
    scoring_system_id: str,
    *,
    data_format: str = "",
    players_per_team: int = DEFAULT_PLAYERS_PER_TEAM,
) -> float:
    """
    Points pool per scheduled game in the standings total.

    Pre-2022 Excel tables use team-game points only (e.g. 2pt) plus weekly scratch
    placement (1..n). Post-2022 tables sum full match pairings (individual + team).
    """
    scoring = _load_scoring_table().get(scoring_system_id)
    if not scoring:
        return 0.0
    if data_format == "data_format_pre_2022":
        return float(scoring["team_win"] + scoring["team_loss"])
    return points_per_match(scoring_system_id, players_per_team=players_per_team)


def include_placement_for_budget(data_format: str) -> bool:
    """Weekly scratch-ranking bonus (1+2+…+n) is part of pre-2022 standings totals."""
    return data_format == "data_format_pre_2022"


def resolve_games_per_week(
    number_of_teams: int,
    games_per_week: Optional[int],
) -> int:
    if games_per_week is not None and int(games_per_week) > 0:
        return int(games_per_week)
    if number_of_teams > 1:
        return int(number_of_teams) - 1
    return 1


def resolve_scoring_system_id(
    league: str,
    season: str,
    *,
    data_format: str = "",
) -> str:
    """Prefer league_season.csv; 3pt from 25/26 onward in published config."""
    import pandas as pd

    if _LEAGUE_SEASON_CSV.is_file():
        df = pd.read_csv(_LEAGUE_SEASON_CSV, dtype=str).fillna("")
        hit = df[(df["league_id"].astype(str) == str(league)) & (df["season"].astype(str) == str(season))]
        if not hit.empty:
            return str(hit.iloc[0]["scoring_system_id"])

    season_key = str(season or "").strip()
    if season_key >= "25/26":
        return DEFAULT_SCORING_3PT
    if data_format == "data_format_pre_2022":
        return DEFAULT_SCORING_2PT
    return DEFAULT_SCORING_2PT


def weekly_match_points_budget(
    number_of_teams: int,
    games_per_week: int,
    points_per_match_value: float,
    *,
    data_format: str = "",
) -> float:
    if number_of_teams <= 0 or games_per_week <= 0:
        return 0.0
    if data_format == "data_format_pre_2022":
        # Odd-sized leagues schedule a weekly bye (phantom opponent); pairing
        # slots are ceil(n/2), not n/2 of an inflated Spielzettel block count.
        pairing = (number_of_teams + 1) // 2
        return pairing * games_per_week * points_per_match_value
    return (number_of_teams / 2) * games_per_week * points_per_match_value


def phantom_bye_league(
    *,
    standings_team_count: int,
    analysis_team_count: Optional[int],
) -> bool:
    """Spielzettel metadata often counts the bye slot as an extra team."""
    if analysis_team_count is None or standings_team_count <= 0:
        return False
    return int(analysis_team_count) == int(standings_team_count) + 1


def resolve_real_team_count_for_budget(
    *,
    standings_team_count: int,
    analysis_team_count: Optional[int] = None,
) -> int:
    """Standings rows are real teams; analysis may include the phantom bye."""
    standings = max(0, int(standings_team_count))
    if standings > 0:
        return standings
    if analysis_team_count is not None and int(analysis_team_count) > 0:
        return int(analysis_team_count)
    return 0


def resolve_games_per_week_for_budget(
    number_of_teams: int,
    games_per_week: Optional[int],
    *,
    data_format: str = "",
    phantom_bye: bool = False,
) -> int:
    if games_per_week is not None and int(games_per_week) > 0:
        return int(games_per_week)
    team_count = max(0, int(number_of_teams))
    if team_count <= 1:
        return 1
    if data_format == "data_format_pre_2022" and phantom_bye:
        # Each real team plays n games per week, including the default bye win.
        return team_count
    return team_count - 1


def weekly_placement_points_budget(number_of_teams: int) -> float:
    if number_of_teams <= 0:
        return 0.0
    return number_of_teams * (number_of_teams + 1) / 2


def compute_league_points_budget(
    *,
    league: str,
    season: str,
    number_of_teams: int,
    reference_weeks: int,
    games_per_week: Optional[int] = None,
    data_format: str = "",
    players_per_team: int = DEFAULT_PLAYERS_PER_TEAM,
    include_placement: Optional[bool] = None,
    phantom_bye: bool = False,
) -> LeaguePointsBudget:
    team_count = max(0, int(number_of_teams))
    weeks = max(0, int(reference_weeks))
    gpw = resolve_games_per_week_for_budget(
        team_count,
        games_per_week,
        data_format=data_format,
        phantom_bye=phantom_bye,
    )
    scoring_id = resolve_scoring_system_id(league, season, data_format=data_format)
    placement_on = (
        include_placement_for_budget(data_format)
        if include_placement is None
        else bool(include_placement)
    )
    ppm = points_per_game_for_budget(
        scoring_id,
        data_format=data_format,
        players_per_team=players_per_team,
    )
    weekly_match = weekly_match_points_budget(
        team_count,
        gpw,
        ppm,
        data_format=data_format,
    )
    weekly_placement = weekly_placement_points_budget(team_count) if placement_on else 0.0
    weekly_total = weekly_match + weekly_placement
    return LeaguePointsBudget(
        number_of_teams=team_count,
        games_per_week=gpw,
        reference_weeks=weeks,
        scoring_system_id=scoring_id,
        players_per_team=players_per_team,
        points_per_match=ppm,
        weekly_match_points=weekly_match,
        weekly_placement_points=weekly_placement,
        weekly_total_points=weekly_total,
        season_total_points=weekly_total * weeks,
    )


def _totals_close(a: float, b: float, *, tol: float = 0.5) -> bool:
    return abs(float(a) - float(b)) <= tol


def analyze_total_points(
    *,
    reference_total: float,
    computed_total: float,
    budget: LeaguePointsBudget,
    points_mismatches: list[str],
    tol: float = 0.5,
) -> tuple[bool, bool, bool, str]:
    """
    Return (reference_schema_ok, computed_ref_ok, mismatch_explained_by_ref_total, message).

    *reference_schema_ok* — Excel total vs pure scoring-schema budget (ignores no-shows).
    *computed_ref_ok* — merge total vs Excel reference (the coherence check).
    """
    expected = budget.season_total_points
    ref_schema_ok = _totals_close(reference_total, expected, tol=tol)
    comp_ref_ok = _totals_close(computed_total, reference_total, tol=tol)

    ref_gap = reference_total - computed_total
    mismatch_gap = _sum_points_mismatch_delta(points_mismatches)
    explained = (
        bool(points_mismatches)
        and not ref_schema_ok
        and comp_ref_ok
        and _totals_close(ref_gap, mismatch_gap, tol=max(tol, 1.0))
        and _totals_close(reference_total - expected, ref_gap, tol=max(tol, 1.0))
    )

    parts: list[str] = []
    if not ref_schema_ok:
        parts.append(
            f"Excel total {reference_total:g} vs schema expected {expected:g} "
            f"({reference_total - expected:+g}, {budget.formula_note()})"
        )
    if not comp_ref_ok:
        parts.append(
            f"computed total {computed_total:g} vs Excel ref {reference_total:g} "
            f"({computed_total - reference_total:+g})"
        )
    if explained:
        parts.append(
            "per-team point gaps likely reflect wrong Excel standings total, not merge scoring"
        )
    elif points_mismatches and not ref_schema_ok and comp_ref_ok:
        parts.append(
            f"Excel total off by {reference_total - expected:+g}; merge matches Excel ref"
        )

    return ref_schema_ok, comp_ref_ok, explained, "; ".join(parts)


def no_shows_explain_ref_schema_shortfall(
    *,
    reference_total: float,
    schema_total: float,
    no_show_teams_by_week: Mapping[int, Sequence[str]],
    tol: float = 0.5,
) -> bool:
    """Excel season total is below schema only by documented no-show penalties."""
    if not no_show_teams_by_week:
        return False
    reduction = sum(
        no_show_weekly_reduction(len(teams)) for teams in no_show_teams_by_week.values()
    )
    return _totals_close(reference_total, schema_total - reduction, tol=tol)


def detect_no_show_ref_schema_healing(
    *,
    reference_total: float,
    computed_total: float,
    schema_total: float,
    no_show_teams_by_week: Mapping[int, Sequence[str]],
    comp_ref_ok: bool,
    ref_schema_ok: bool,
    teams_match: bool,
    positions_match: bool,
    tol: float = 0.5,
) -> tuple[bool, str]:
    """
    Excel below schema because of no-shows, but merge matches Excel — acceptable.

    ref != schema expected, ref == computed, no-show penalties explain the schema gap.
    """
    if not (teams_match and positions_match and comp_ref_ok and not ref_schema_ok):
        return False, ""
    if not no_shows_explain_ref_schema_shortfall(
        reference_total=reference_total,
        schema_total=schema_total,
        no_show_teams_by_week=no_show_teams_by_week,
        tol=tol,
    ):
        return False, ""

    reduction = sum(
        no_show_weekly_reduction(len(teams)) for teams in no_show_teams_by_week.values()
    )
    week_labels = ", ".join(
        f"W{week}" for week in sorted(no_show_teams_by_week)
    )
    team_labels = ", ".join(
        team
        for week in sorted(no_show_teams_by_week)
        for team in no_show_teams_by_week[week]
    )
    remark = (
        f"no-show {week_labels} ({team_labels}): Excel {reduction:g}pt below schema; "
        f"merge matches Excel ref ({reference_total:g})"
    )
    return True, remark


_POINTS_MISMATCH_RE = re.compile(
    r"^(?P<team>.+?): ref pts (?P<ref>[\d.]+) vs computed (?P<comp>[\d.]+)$",
    re.IGNORECASE,
)


def _parse_points_mismatch_line(line: str) -> tuple[str, float, float] | None:
    match = _POINTS_MISMATCH_RE.match(str(line).strip())
    if not match:
        return None
    return (
        match.group("team").strip(),
        float(match.group("ref")),
        float(match.group("comp")),
    )


def _sum_points_mismatch_delta(points_mismatches: list[str]) -> float:
    total = 0.0
    for line in points_mismatches:
        parsed = _parse_points_mismatch_line(line)
        if not parsed:
            continue
        _team, ref_pts, comp_pts = parsed
        total += ref_pts - comp_pts
    return total


def detect_points_one_off_correction(
    *,
    reference_total: float,
    computed_total: float,
    expected_total: float,
    points_mismatches: list[str],
    teams_match: bool,
    positions_match: bool,
    pins_match: bool,
    reference_total_points_ok: bool,
    computed_total_points_ok: bool,
    tol: float = 0.5,
    max_gap: float = 1.0,
) -> tuple[bool, str]:
    """
    Excel and merge differ by at most one league point, fully accounted for on
    teams, and merge matches the scoring-schema budget (or Excel does while merge
    is 1pt short — accept merge in both cases).
    """
    if not (teams_match and positions_match and pins_match):
        return False, ""
    if not points_mismatches:
        return False, ""

    total_gap = float(reference_total) - float(computed_total)
    if abs(total_gap) <= tol or abs(total_gap) > max_gap + tol:
        return False, ""

    mismatch_gap = _sum_points_mismatch_delta(points_mismatches)
    if not _totals_close(total_gap, mismatch_gap, tol=tol):
        return False, ""

    parsed_lines = [_parse_points_mismatch_line(line) for line in points_mismatches]
    if any(item is None for item in parsed_lines):
        return False, ""

    for _team, ref_pts, comp_pts in parsed_lines:
        if abs(ref_pts - comp_pts) > max_gap + tol:
            return False, ""

    ref_vs_schema = float(reference_total) - float(expected_total)
    comp_vs_schema = float(computed_total) - float(expected_total)
    comp_vs_ref = float(computed_total) - float(reference_total)

    trusted_merge = (
        _totals_close(ref_vs_schema, 0, tol=tol)
        and _totals_close(comp_vs_ref, -total_gap, tol=tol)
    ) or (
        _totals_close(comp_vs_schema, 0, tol=tol)
        and _totals_close(ref_vs_schema, total_gap, tol=tol)
    )
    if not trusted_merge:
        return False, ""

    first_team = parsed_lines[0][0]  # type: ignore[index]
    if _totals_close(comp_vs_schema, 0, tol=tol) and not _totals_close(ref_vs_schema, 0, tol=tol):
        detail = (
            f"Excel standings total {ref_vs_schema:+g}pt vs schema; "
            f"merge matches schema on {first_team}"
        )
    else:
        detail = f"{abs(total_gap):g}pt vs Excel on {first_team}"
    remark = (
        f"accepted computed standings: {detail} "
        f"(Excel total {reference_total:g}, computed {computed_total:g}, "
        f"schema {expected_total:g})"
    )
    return True, remark


def classify_error_categories(comparison: object) -> list[str]:
    """Derive filter tags from a StandingsComparison-like row."""
    categories: list[str] = []
    status = str(getattr(comparison, "status", "") or "")
    if status == "skipped":
        categories.append("skipped")
        return categories
    if status == "perfect":
        categories.append("perfect")
        return categories
    if status == "corrected":
        categories.append("corrected")
        if getattr(comparison, "points_mismatches", None):
            categories.append("points")
        return categories

    if getattr(comparison, "missing_in_computed", None) or getattr(
        comparison, "missing_in_reference", None
    ):
        categories.append("teams")
    if getattr(comparison, "position_mismatches", None):
        categories.append("positions")
    if getattr(comparison, "points_mismatches", None):
        categories.append("points")
    if getattr(comparison, "pins_mismatches", None):
        categories.append("pins")
    if getattr(comparison, "missing_matchdays", None):
        categories.append("weeks")
    if not getattr(comparison, "reference_total_points_ok", True):
        categories.append("total_points_ref")
    if not getattr(comparison, "computed_total_points_ok", True):
        categories.append("total_points_comp")
    if getattr(comparison, "points_mismatch_explained_by_total", False):
        categories.append("points_excel_total")
    if getattr(comparison, "ref_schema_healed_by_no_show", False):
        categories.append("no_show")
    if getattr(comparison, "weekly_points_findings", None):
        categories.append("weekly_points")
    return categories
