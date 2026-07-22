"""Per-matchday league points pool (ref vs merge vs schema budget)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence

import pandas as pd

from data_access.league_points_budget import LeaguePointsBudget
from data_access.schema import Columns
from data_access.score_utils import league_points_cell

_SPIELTAG_RE = re.compile(r"spieltag\s*(\d+)", re.IGNORECASE)
_TABGES_SHEET_RE = re.compile(r"^TabGes(\d+)$", re.IGNORECASE)
_POINTS_TOL = 0.05


def _parse_numeric(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", ".")
    if not text or text.lower() in {"nan", "-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cell_equals(value, label: str) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() == label.strip().lower()


def _cell_contains(value, needle: str) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return needle.lower() in str(value).strip().lower()


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


def parse_tabges_weekly_team_points(df: pd.DataFrame) -> Dict[int, Dict[str, float]]:
    """
    Extract per-Spieltag points per team from a TabGes sheet.

    Returns ``{week: {team: points_earned_that_week}}``.
    """
    header_idx: Optional[int] = None
    scan_rows = min(12, len(df))
    for row_idx in range(scan_rows):
        if _cell_equals(df.iat[row_idx, 0], "Pl.") and _cell_contains(df.iat[row_idx, 1], "Mannschaft"):
            header_idx = row_idx
            break
    if header_idx is None:
        return {}

    label_row = header_idx + 1
    if label_row >= len(df):
        return {}

    week_pkt_cols: Dict[int, int] = {}
    col_idx = 2
    while col_idx < df.shape[1]:
        header_cell = str(df.iat[header_idx, col_idx] or "")
        if _cell_contains(header_cell, "gesamt"):
            break
        match = _SPIELTAG_RE.search(header_cell)
        if match:
            week_num = int(match.group(1))
            pkt_col = None
            for sub_col in range(col_idx, min(col_idx + 4, df.shape[1])):
                label = df.iat[label_row, sub_col]
                if _cell_equals(label, "Pkt.") or _cell_equals(label, "Pkt"):
                    pkt_col = sub_col
                    break
            if pkt_col is not None:
                week_pkt_cols[week_num] = pkt_col
            col_idx += 2
            continue
        col_idx += 1

    if not week_pkt_cols:
        return {}

    out: Dict[int, Dict[str, float]] = {week: {} for week in week_pkt_cols}
    for row_idx in range(label_row + 1, len(df)):
        position = _parse_numeric(df.iat[row_idx, 0])
        team_raw = df.iat[row_idx, 1]
        if position is None:
            continue
        team = str(team_raw).strip() if team_raw is not None and not pd.isna(team_raw) else ""
        if not team:
            break
        for week_num, pkt_col in week_pkt_cols.items():
            pts = _parse_numeric(df.iat[row_idx, pkt_col])
            if pts is not None:
                out[week_num][team] = float(pts)
    return out


def weekly_pool_from_team_points(weekly_teams: Mapping[int, Mapping[str, float]]) -> Dict[int, float]:
    return {
        week: float(sum(team_pts.values()))
        for week, team_pts in weekly_teams.items()
    }


def parse_pre_2022_tabelle_weekly_team_points(
    df: pd.DataFrame,
) -> tuple[int, Dict[str, float]]:
    """
    Parse per-team Spieltag points from a pre-2022 ``Tabelle`` sheet.

    Returns ``(week_number, {team: points_earned_that_week})`` using the
    Spieltag *Total* column (Punkte + Bonus). Empty dict when not parseable.
    """
    week_number: Optional[int] = None
    for row_idx in range(min(10, len(df))):
        for col_idx in range(min(4, df.shape[1])):
            if not _cell_contains(df.iat[row_idx, col_idx], "spieltag"):
                continue
            week_raw = _parse_numeric(df.iat[row_idx, col_idx - 1] if col_idx > 0 else None)
            if week_raw is not None and int(week_raw) > 0:
                week_number = int(week_raw)
                break
        if week_number is not None:
            break
    if week_number is None:
        return 0, {}

    header_row: Optional[int] = None
    for row_idx in range(len(df)):
        if _cell_equals(df.iat[row_idx, 2], "Mannschaft") or _cell_contains(
            df.iat[row_idx, 2], "mannschaft"
        ):
            if any(
                _cell_contains(df.iat[row_idx, col_idx], "spieltag")
                for col_idx in range(df.shape[1])
            ):
                header_row = row_idx
                break
    if header_row is None:
        return week_number, {}

    label_row = header_row + 1
    if label_row >= len(df):
        return week_number, {}

    spieltag_col: Optional[int] = None
    for col_idx in range(df.shape[1]):
        if _cell_contains(df.iat[header_row, col_idx], "spieltag"):
            spieltag_col = col_idx
            break
    if spieltag_col is None:
        return week_number, {}

    total_col: Optional[int] = None
    for col_idx in range(spieltag_col, min(spieltag_col + 6, df.shape[1])):
        if _cell_equals(df.iat[label_row, col_idx], "Total"):
            total_col = col_idx
            break
    if total_col is None:
        return week_number, {}

    team_points: Dict[str, float] = {}
    for row_idx in range(label_row + 1, len(df)):
        if _cell_contains(df.iat[row_idx, 1], "neue tabelle"):
            break
        position = _parse_numeric(df.iat[row_idx, 1])
        team_raw = df.iat[row_idx, 2]
        if position is None:
            continue
        team = str(team_raw).strip() if team_raw is not None and not pd.isna(team_raw) else ""
        if not team or team == "0":
            break
        week_pts = _parse_numeric(df.iat[row_idx, total_col])
        if week_pts is not None:
            team_points[team] = float(week_pts)
    return week_number, team_points


def parse_pre_2022_tabelle_weekly_points_pool(df: pd.DataFrame) -> Dict[int, float]:
    week_number, team_points = parse_pre_2022_tabelle_weekly_team_points(df)
    if week_number <= 0 or not team_points:
        return {}
    return {week_number: float(sum(team_points.values()))}


def no_show_teams_by_week_from_reference(
    weekly_team_points: Mapping[int, Mapping[str, float]],
) -> Dict[int, List[str]]:
    """Teams with zero Spieltag total (did not appear — no placement point)."""
    out: Dict[int, List[str]] = {}
    for week, teams in weekly_team_points.items():
        absent = [str(team) for team, pts in teams.items() if float(pts) <= 0]
        if absent:
            out[int(week)] = sorted(absent)
    return out


def no_shows_by_week_from_reference(
    weekly_team_points: Mapping[int, Mapping[str, float]],
) -> Dict[int, int]:
    """Count of no-show teams per week."""
    return {
        week: len(teams)
        for week, teams in no_show_teams_by_week_from_reference(weekly_team_points).items()
    }


def format_no_show_findings(
    no_show_teams_by_week: Mapping[int, Sequence[str]],
) -> List[str]:
    lines: List[str] = []
    for week in sorted(no_show_teams_by_week):
        for team in no_show_teams_by_week[week]:
            lines.append(f"no-show W{week}: {team}")
    return lines


def parse_reference_weekly_points_pool(
    workbook_path: Path,
    *,
    sheet_name: str,
    ref_week: Optional[int] = None,
) -> Dict[int, float]:
    """League points pool per week from Excel TabGes (falls back to TabGes{N} sheets)."""
    from scripts.data.extract_excel_data import get_sheet_names_safely, read_excel_safely

    path = Path(workbook_path)
    if not path.is_file():
        return {}

    chosen = sheet_name or ""
    if _TABGES_SHEET_RE.match(chosen):
        df = read_excel_safely(path, sheet_name=chosen, header=None)
        return weekly_pool_from_team_points(parse_tabges_weekly_team_points(df))

    if chosen.lower() == "tabelle" or (not chosen and "Tabelle" in get_sheet_names_safely(path)):
        tabelle_name = chosen if chosen else "Tabelle"
        df = read_excel_safely(path, sheet_name=tabelle_name, header=None)
        pool = parse_pre_2022_tabelle_weekly_points_pool(df)
        if pool:
            return pool

    sheet_names = get_sheet_names_safely(path)
    tabges_sheets = []
    for name in sheet_names:
        match = _TABGES_SHEET_RE.match(name or "")
        if match:
            tabges_sheets.append((int(match.group(1)), name))
    if not tabges_sheets:
        return {}

    if ref_week is not None:
        tabges_sheets = [(week, name) for week, name in tabges_sheets if week <= int(ref_week)]
    if not tabges_sheets:
        return {}

    best_week, best_name = max(tabges_sheets, key=lambda item: item[0])
    df = read_excel_safely(path, sheet_name=best_name, header=None)
    weekly_teams = parse_tabges_weekly_team_points(df)
    if ref_week is not None:
        weekly_teams = {
            week: teams for week, teams in weekly_teams.items() if week <= int(ref_week)
        }
    return weekly_pool_from_team_points(weekly_teams)


def compute_weekly_points_pool_from_dataframe(
    df: pd.DataFrame,
    *,
    league: str,
    season: str,
    max_week: Optional[int] = None,
) -> Dict[int, float]:
    """Sum merge league points awarded per matchday."""
    if df.empty:
        return {}

    league_col = Columns.event if Columns.event in df.columns else "League"
    if league_col not in df.columns or Columns.season not in df.columns:
        return {}

    season_variants = _season_label_variants(season)
    mask = df[league_col].astype(str) == str(league)
    mask &= df[Columns.season].astype(str).isin(season_variants)
    if Columns.event_type in df.columns:
        mask &= df[Columns.event_type].fillna("league").astype(str).str.lower().eq("league")
    if max_week is not None:
        week_nums = pd.to_numeric(df[Columns.week], errors="coerce")
        mask &= week_nums <= int(max_week)
    sub = df.loc[mask]
    if sub.empty or Columns.week not in sub.columns:
        return {}

    pools: Dict[int, float] = {}
    for week_raw, group in sub.groupby(Columns.week, sort=False):
        week = int(pd.to_numeric(week_raw, errors="coerce") or 0)
        if week <= 0:
            continue
        pools[week] = float(sum(league_points_cell(row) for _, row in group.iterrows()))
    return pools


def _close(a: float, b: float, *, tol: float = _POINTS_TOL) -> bool:
    return abs(float(a) - float(b)) <= tol


def analyze_weekly_points_divergence(
    *,
    reference_weekly: Mapping[int, float],
    computed_weekly: Mapping[int, float],
    budget: LeaguePointsBudget,
    include_when_totals_ok: bool = False,
    reference_total_ok: bool = True,
    computed_total_ok: bool = True,
    has_points_mismatches: bool = False,
    no_show_teams_by_week: Optional[Mapping[int, Sequence[str]]] = None,
) -> list[str]:
    """
    List matchdays where the league points pool differs (ref/computed/schema).

  *expected* is the pure scoring-schema weekly budget (ignores no-shows).
  Primary merge issue: ``comp-ref`` (computed vs Excel reference).
    """
    if not include_when_totals_ok:
        if reference_total_ok and computed_total_ok and not has_points_mismatches:
            return []

    if budget.weekly_total_points <= 0:
        return []

    weeks = sorted(set(reference_weekly) | set(computed_weekly))
    if budget.reference_weeks > 0:
        weeks = [week for week in weeks if week <= budget.reference_weeks]
    if not weeks:
        return []

    no_show_by_week = no_show_teams_by_week or {}
    lines: list[str] = []
    for week in weeks:
        expected_weekly = float(budget.weekly_total_points)
        if expected_weekly <= 0:
            continue
        ref = float(reference_weekly.get(week, 0.0))
        comp = float(computed_weekly.get(week, 0.0))
        has_ref = week in reference_weekly
        has_comp = week in computed_weekly
        ref_part = f"{ref:g}" if has_ref else "—"
        comp_part = f"{comp:g}" if has_comp else "—"

        comp_ref_mismatch = has_ref and has_comp and not _close(ref, comp)
        ref_schema_mismatch = has_ref and not _close(ref, expected_weekly)
        comp_schema_mismatch = has_comp and not _close(comp, expected_weekly)
        if not (comp_ref_mismatch or ref_schema_mismatch or comp_schema_mismatch):
            continue

        delta_parts: list[str] = []
        if comp_ref_mismatch:
            delta_parts.append(f"comp-ref {comp - ref:+g}")
        if ref_schema_mismatch:
            delta_parts.append(f"ref-schema {ref - expected_weekly:+g}")
        if comp_schema_mismatch:
            delta_parts.append(f"comp-schema {comp - expected_weekly:+g}")
        if int(week) in no_show_by_week and ref_schema_mismatch:
            absent = ", ".join(no_show_by_week[int(week)])
            delta_parts.append(f"no-show ({absent})")

        delta_note = f" ({'; '.join(delta_parts)})" if delta_parts else ""
        lines.append(
            f"pts-week: W{week} pool ref {ref_part} / computed {comp_part} / "
            f"schema {expected_weekly:g}{delta_note}"
        )
    return lines
