"""Compare published league standings with reference tables from Excel workbooks."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from data_access.league_points_budget import (
    analyze_total_points,
    classify_error_categories,
    compute_league_points_budget,
    detect_no_show_ref_schema_healing,
    detect_points_one_off_correction,
    phantom_bye_league,
    resolve_real_team_count_for_budget,
)
from data_access.league_week_schema import expected_weeks_for_league_season
from data_access.league_weekly_points_analysis import (
    analyze_weekly_points_divergence,
    compute_weekly_points_pool_from_dataframe,
    format_no_show_findings,
    no_show_teams_by_week_from_reference,
    parse_reference_weekly_points_pool,
    weekly_pool_from_team_points,
)
from data_access.league_week_coverage import (
    LeagueSeasonWeekCoverage,
    WEEK_COVERAGE_OK,
    compute_league_season_week_coverage,
    discover_league_season_pairs,
)
from data_access.schema import Columns
from data_access.score_utils import league_points_cell, sum_scores_float
from database.paths import legacy_scrape_dir

STATUS_GREEN = "green"
STATUS_PERFECT = "perfect"
STATUS_CORRECTED = "corrected"
STATUS_YELLOW = "yellow"
STATUS_RED = "red"
STATUS_SKIPPED = "skipped"

GREEN_STATUSES = frozenset({STATUS_GREEN, STATUS_PERFECT, STATUS_CORRECTED})

LEAGUE_STANDINGS_VALIDATION_CSV = "league_standings_validation.csv"
FINDINGS_DELIMITER = "||"

_TABGES_RE = re.compile(r"^TabGes(\d+)$", re.IGNORECASE)
_TABELLE_WEEK_RE = re.compile(r"^Tabelle(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class StandingRow:
    position: int
    team: str
    total_points: float
    total_pins: int


@dataclass
class StandingsComparison:
    season: str
    league: str
    status: str
    reference_source: str = ""
    reference_sheet: str = ""
    reference_week: Optional[int] = None
    data_format: str = ""
    computed_team_count: int = 0
    reference_team_count: int = 0
    teams_match: bool = False
    positions_match: bool = False
    points_match: bool = False
    pins_match: bool = False
    missing_in_computed: List[str] = field(default_factory=list)
    missing_in_reference: List[str] = field(default_factory=list)
    position_mismatches: List[str] = field(default_factory=list)
    points_mismatches: List[str] = field(default_factory=list)
    pins_mismatches: List[str] = field(default_factory=list)
    notes: str = ""
    expected_weeks: int = 0
    available_weeks: List[int] = field(default_factory=list)
    missing_matchdays: List[int] = field(default_factory=list)
    week_coverage_status: str = ""
    # Processing pipeline (mirrors merge_league_sources: regex → team number).
    status_raw: str = ""
    team_mismatches_raw: int = 0
    team_mismatches_after_team_name: int = 0
    team_mismatches_final: int = 0
    team_resolution_step: str = ""
    total_points_reference: float = 0.0
    total_points_computed: float = 0.0
    total_points_expected: float = 0.0
    reference_total_points_ok: bool = True
    computed_total_points_ok: bool = True
    points_mismatch_explained_by_total: bool = False
    points_auto_corrected: bool = False
    correction_remark: str = ""
    no_show_findings: List[str] = field(default_factory=list)
    ref_schema_healed_by_no_show: bool = False
    no_show_remark: str = ""
    weekly_points_findings: List[str] = field(default_factory=list)
    error_categories: List[str] = field(default_factory=list)

    def summary_line(self) -> str:
        week_hint = ""
        if self.missing_matchdays:
            week_hint = (
                f", weeks {len(self.available_weeks)}/{self.expected_weeks}"
                f" (missing {','.join(str(w) for w in self.missing_matchdays)})"
            )
        return (
            f"{self.season} | {self.league}: {self.status} "
            f"(ref={self.reference_team_count}, computed={self.computed_team_count}{week_hint})"
            + (f" — {self.notes}" if self.notes else "")
        )


def _parse_numeric(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, np.integer)):
        return float(int(value))
    if isinstance(value, float):
        if np.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text or text.lower() in {"nan", "-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cell_equals(value: Any, label: str) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return str(value).strip().lower() == label.strip().lower()


def _cell_contains(value: Any, needle: str) -> bool:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return needle.lower() in str(value).strip().lower()


def _normalize_team_key(name: str) -> str:
    try:
        from extract_excel_data import normalize_team_name

        return str(normalize_team_name(name) or "").strip().casefold()
    except Exception:
        return str(name or "").strip().casefold()


def _normalize_league_id(raw: Any) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        from extract_excel_data import normalize_league_display_to_canonical

        mapped = normalize_league_display_to_canonical(text)
        return mapped or text
    except Exception:
        return text


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


def _points_close(a: float, b: float, *, tol: float = 0.05) -> bool:
    return abs(float(a) - float(b)) <= tol


def _pins_close(a: int, b: int) -> bool:
    return int(a) == int(b)


def _legacy_scrape_relative_path(path: Path) -> Optional[Path]:
    """Path under ``legacy_scrape/`` (e.g. ``saison2008-09/bayernliga/foo.xlsx``)."""
    parts = path.parts
    for idx, part in enumerate(parts):
        if part.casefold() == "legacy_scrape" and idx + 1 < len(parts):
            return Path(*parts[idx + 1 :])
    return None


def resolve_workbook_path(logged_path: Path | str) -> Optional[Path]:
    """Resolve an analysis-log workbook path, including stale absolute prefixes."""
    logged = Path(logged_path)
    candidates: List[Path] = [logged]
    suffix = _legacy_scrape_relative_path(logged)
    if suffix is not None:
        candidates.append(legacy_scrape_dir() / suffix)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
        stem = candidate.with_suffix("")
        for alt_suffix in (".xlsx", ".xls", ".XLSX", ".XLS"):
            alt = stem.with_suffix(alt_suffix)
            if alt.is_file():
                return alt
    return None


def parse_pre_2022_tabelle_standings(df: pd.DataFrame) -> List[StandingRow]:
    """Parse cumulative *Neue Tabelle* block from a pre-2022 ``Tabelle`` sheet."""
    start_row: Optional[int] = None
    for row_idx in range(len(df)):
        for col_idx in range(min(4, df.shape[1])):
            if _cell_contains(df.iat[row_idx, col_idx], "neue tabelle"):
                start_row = row_idx
                break
        if start_row is not None:
            break
    if start_row is None:
        return []

    header_row = start_row + 1
    if header_row >= len(df):
        return []

    pins_col = points_col = None
    for col_idx in range(df.shape[1]):
        cell = df.iat[header_row, col_idx]
        if _cell_equals(cell, "Pins"):
            pins_col = col_idx
        elif _cell_equals(cell, "Total"):
            points_col = col_idx
        elif points_col is None and _cell_equals(cell, "Punkte"):
            points_col = col_idx

    rows: List[StandingRow] = []
    for row_idx in range(header_row + 1, len(df)):
        position = _parse_numeric(df.iat[row_idx, 1])
        team_raw = df.iat[row_idx, 2]
        if position is None:
            continue
        team = str(team_raw).strip() if team_raw is not None and not pd.isna(team_raw) else ""
        if not team or team == "0":
            break
        pins_val = _parse_numeric(df.iat[row_idx, pins_col]) if pins_col is not None else None
        points_val = _parse_numeric(df.iat[row_idx, points_col]) if points_col is not None else None
        if pins_val is None and points_val is None:
            continue
        rows.append(
            StandingRow(
                position=int(position),
                team=team,
                total_points=float(points_val or 0.0),
                total_pins=int(pins_val or 0),
            )
        )
    return rows


def parse_post_2022_tabges_standings(df: pd.DataFrame) -> List[StandingRow]:
    """Parse season cumulative standings from ``TabGes{N}`` sheet."""
    header_idx: Optional[int] = None
    scan_rows = min(12, len(df))
    for row_idx in range(scan_rows):
        if _cell_equals(df.iat[row_idx, 0], "Pl.") and _cell_contains(df.iat[row_idx, 1], "Mannschaft"):
            header_idx = row_idx
            break
    if header_idx is None:
        return []

    label_row = header_idx + 1
    if label_row >= len(df):
        return []

    gesamt_pins_col: Optional[int] = None
    gesamt_pkt_col: Optional[int] = None
    for col_idx in range(2, df.shape[1]):
        if _cell_contains(df.iat[header_idx, col_idx], "gesamt"):
            for sub_col in range(col_idx, min(col_idx + 4, df.shape[1])):
                label = df.iat[label_row, sub_col]
                if gesamt_pins_col is None and _cell_equals(label, "Pins"):
                    gesamt_pins_col = sub_col
                elif gesamt_pkt_col is None and (
                    _cell_equals(label, "Pkt.") or _cell_equals(label, "Pkt")
                ):
                    gesamt_pkt_col = sub_col
            break

    use_gesamt_totals = gesamt_pins_col is not None and gesamt_pkt_col is not None
    pins_cols: List[int] = []
    pkt_cols: List[int] = []
    if not use_gesamt_totals:
        for col_idx in range(2, df.shape[1]):
            label = df.iat[label_row, col_idx]
            if _cell_equals(label, "Pins"):
                pins_cols.append(col_idx)
            elif _cell_equals(label, "Pkt.") or _cell_equals(label, "Pkt"):
                pkt_cols.append(col_idx)

    rows: List[StandingRow] = []
    for row_idx in range(label_row + 1, len(df)):
        position = _parse_numeric(df.iat[row_idx, 0])
        team_raw = df.iat[row_idx, 1]
        if position is None:
            continue
        team = str(team_raw).strip() if team_raw is not None and not pd.isna(team_raw) else ""
        if not team:
            break
        if use_gesamt_totals:
            total_points = float(_parse_numeric(df.iat[row_idx, gesamt_pkt_col]) or 0.0)
            total_pins = int(_parse_numeric(df.iat[row_idx, gesamt_pins_col]) or 0.0)
        else:
            total_points = sum(_parse_numeric(df.iat[row_idx, col]) or 0.0 for col in pkt_cols)
            total_pins = int(sum(_parse_numeric(df.iat[row_idx, col]) or 0.0 for col in pins_cols))
        rows.append(
            StandingRow(
                position=int(position),
                team=team,
                total_points=float(total_points),
                total_pins=total_pins,
            )
        )
    return rows


def _week_numbered_sheets(
    sheet_names: Sequence[str],
    pattern: re.Pattern[str],
) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for name in sheet_names:
        match = pattern.match(name)
        if match:
            out.append((int(match.group(1)), name))
    return out


def standings_sheet_candidates(
    sheet_names: Sequence[str],
    *,
    data_format: str,
    max_week: Optional[int] = None,
) -> List[str]:
    """Ordered sheet names to try (TabGes before Tabelle per week, highest week first)."""
    names = list(sheet_names)
    if data_format == "data_format_pre_2022":
        return ["Tabelle"] if "Tabelle" in names else []

    tabges = _week_numbered_sheets(names, _TABGES_RE)
    tabelle = _week_numbered_sheets(names, _TABELLE_WEEK_RE)
    weeks = sorted({week for week, _ in tabges + tabelle}, reverse=True)
    if max_week is not None:
        weeks = [week for week in weeks if week <= int(max_week)]

    candidates: List[str] = []
    tabges_by_week = dict(tabges)
    tabelle_by_week = dict(tabelle)
    for week in weeks:
        if week in tabges_by_week:
            candidates.append(tabges_by_week[week])
        if week in tabelle_by_week:
            candidates.append(tabelle_by_week[week])
    return candidates


def pick_standings_sheet(
    sheet_names: Sequence[str],
    *,
    data_format: str,
    max_week: Optional[int] = None,
) -> Optional[str]:
    candidates = standings_sheet_candidates(
        sheet_names,
        data_format=data_format,
        max_week=max_week,
    )
    return candidates[0] if candidates else None


def parse_standings_sheet(df: pd.DataFrame, *, data_format: str, sheet_name: str) -> List[StandingRow]:
    if data_format == "data_format_pre_2022" or sheet_name == "Tabelle":
        rows = parse_pre_2022_tabelle_standings(df)
        if rows:
            return rows
    if _TABGES_RE.match(sheet_name or ""):
        return parse_post_2022_tabges_standings(df)
    return []


def parse_standings_from_workbook(
    workbook_path: Path,
    *,
    data_format: str,
    sheet_name: Optional[str] = None,
    max_week: Optional[int] = None,
) -> Tuple[List[StandingRow], str]:
    from extract_excel_data import get_sheet_names_safely, read_excel_safely

    path = Path(workbook_path)
    sheet_names = get_sheet_names_safely(path)
    if sheet_name:
        candidates = [sheet_name]
    else:
        candidates = standings_sheet_candidates(
            sheet_names,
            data_format=data_format,
            max_week=max_week,
        )
    if not candidates:
        return [], ""

    for chosen in candidates:
        df = read_excel_safely(path, sheet_name=chosen, header=None)
        rows = parse_standings_sheet(df, data_format=data_format, sheet_name=chosen)
        if rows:
            return rows, chosen
    return [], candidates[0]


@dataclass(frozen=True)
class ExcelReferenceTarget:
    league: str
    season: str
    file_path: Path
    data_format: str
    week: Optional[int]
    number_of_teams: Optional[int] = None
    games_per_week: Optional[int] = None


def _int_from_analysis_row(row: Mapping[str, Any], key: str) -> Optional[int]:
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(float(str(raw).strip()))
        return value if value > 0 else None
    except ValueError:
        return None


def _week_from_analysis_row(row: Mapping[str, Any]) -> Optional[int]:
    raw = row.get("available_weeks") or row.get("debug_week_raw")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if "," in text:
        values: List[int] = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(int(float(part)))
            except ValueError:
                continue
        return max(values) if values else None
    try:
        return int(float(text))
    except ValueError:
        return None


def _week_from_sheet_name(sheet_name: str) -> Optional[int]:
    match = _TABGES_RE.match(sheet_name or "") or _TABELLE_WEEK_RE.match(sheet_name or "")
    if not match:
        return None
    return int(match.group(1))


def discover_excel_reference_targets(analysis_log_path: Path) -> List[ExcelReferenceTarget]:
    """Pick the last-week workbook per league×season from the Excel analysis log."""
    from extract_excel_data import load_analysis_log

    payload = load_analysis_log(analysis_log_path)
    files = payload.get("files") or {}
    grouped: Dict[Tuple[str, str], ExcelReferenceTarget] = {}

    for file_path, entry in files.items():
        row = entry.get("analysis_result") if isinstance(entry, dict) else None
        if not isinstance(row, dict):
            continue
        if not row.get("eligible_for_processing"):
            continue
        data_format = str(row.get("data_format") or "")
        if data_format not in {"data_format_pre_2022", "data_format_post_2022"}:
            continue
        league = _normalize_league_id(row.get("league"))
        season = str(row.get("season") or "").strip()
        if not league or not season:
            continue
        resolved = resolve_workbook_path(str(row.get("file") or file_path))
        if resolved is None:
            continue
        week = _week_from_analysis_row(row)
        key = (league, season)
        current = grouped.get(key)
        candidate = ExcelReferenceTarget(
            league=league,
            season=season,
            file_path=resolved,
            data_format=data_format,
            week=week,
            number_of_teams=_int_from_analysis_row(row, "number_of_teams"),
            games_per_week=_int_from_analysis_row(row, "games_per_week"),
        )
        if current is None:
            grouped[key] = candidate
            continue
        if data_format == "data_format_post_2022" and current.data_format == "data_format_pre_2022":
            grouped[key] = candidate
            continue
        if data_format == "data_format_pre_2022" and current.data_format == "data_format_post_2022":
            continue
        cur_week = current.week or -1
        cand_week = week or -1
        if cand_week > cur_week:
            grouped[key] = candidate
        elif cand_week == cur_week and str(resolved) > str(current.file_path):
            grouped[key] = candidate

    return sorted(grouped.values(), key=lambda item: (item.season, item.league))


def collect_pre_2022_reference_weekly_pools(
    analysis_log_path: Path,
    *,
    league: str,
    season: str,
    max_week: Optional[int] = None,
) -> Dict[int, float]:
    """Weekly league points pools from per-matchday pre-2022 ``Tabelle`` workbooks."""
    return weekly_pool_from_team_points(
        collect_pre_2022_reference_weekly_team_points(
            analysis_log_path,
            league=league,
            season=season,
            max_week=max_week,
        )
    )


def collect_pre_2022_reference_weekly_team_points(
    analysis_log_path: Path,
    *,
    league: str,
    season: str,
    max_week: Optional[int] = None,
) -> Dict[int, Dict[str, float]]:
    """Per-team Spieltag totals from per-matchday pre-2022 ``Tabelle`` workbooks."""
    from extract_excel_data import get_sheet_names_safely, read_excel_safely
    from data_access.league_weekly_points_analysis import parse_pre_2022_tabelle_weekly_team_points

    if not analysis_log_path.is_file():
        return {}

    season_variants = _season_label_variants(season)
    weekly_teams: Dict[int, Dict[str, float]] = {}

    for file_path, row in _iter_analysis_rows(analysis_log_path):
        if str(row.get("data_format") or "") != "data_format_pre_2022":
            continue
        if _normalize_league_id(row.get("league")) != league:
            continue
        if str(row.get("season") or "").strip() not in season_variants:
            continue
        if not row.get("eligible_for_processing"):
            continue
        resolved = resolve_workbook_path(str(row.get("file") or file_path))
        if resolved is None:
            continue
        if "Tabelle" not in get_sheet_names_safely(resolved):
            continue
        df = read_excel_safely(resolved, sheet_name="Tabelle", header=None)
        week_number, team_points = parse_pre_2022_tabelle_weekly_team_points(df)
        if week_number <= 0 or not team_points:
            continue
        if max_week is not None and int(week_number) > int(max_week):
            continue
        weekly_teams[int(week_number)] = {str(team): float(pts) for team, pts in team_points.items()}
    return weekly_teams


def _iter_analysis_rows(analysis_log_path: Path) -> Iterable[Tuple[str, Dict[str, Any]]]:
    from extract_excel_data import load_analysis_log

    payload = load_analysis_log(analysis_log_path)
    files = payload.get("files") or {}
    for file_path, entry in files.items():
        row = entry.get("analysis_result") if isinstance(entry, dict) else None
        if isinstance(row, dict):
            yield str(file_path), row


def describe_missing_excel_reference(
    analysis_log_path: Path,
    *,
    league: str,
    season: str,
) -> str:
    """Explain why no eligible Excel workbook was picked for standings validation."""
    if not analysis_log_path.is_file():
        return (
            "No analysis log on disk (extract_excel_analysis_log.json); "
            "standings validation needs indexed Excel workbooks"
        )

    season_variants = _season_label_variants(season)
    ineligible_issues: List[str] = []
    missing_on_disk: List[str] = []
    indexed_but_unreadable = 0
    unsupported_format = 0

    for _file_path, row in _iter_analysis_rows(analysis_log_path):
        row_league = _normalize_league_id(row.get("league"))
        row_season = str(row.get("season") or "").strip()
        if row_league != league or row_season not in season_variants:
            continue
        data_format = str(row.get("data_format") or "")
        if data_format not in {"data_format_pre_2022", "data_format_post_2022"}:
            unsupported_format += 1
            continue
        resolved = resolve_workbook_path(str(row.get("file") or _file_path))
        if resolved is None:
            indexed_but_unreadable += 1
            missing_on_disk.append(Path(str(row.get("file") or _file_path)).name)
            continue
        if not row.get("eligible_for_processing"):
            issue = str(row.get("issues") or "").strip()
            ineligible_issues.append(issue or resolved.name)

    if ineligible_issues:
        hint = ineligible_issues[0]
        if len(ineligible_issues) > 1:
            hint = f"{hint} (+{len(ineligible_issues) - 1} more)"
        return f"Excel workbook indexed but not eligible for processing: {hint}"
    if indexed_but_unreadable:
        hint = missing_on_disk[0]
        if len(missing_on_disk) > 1:
            hint = f"{hint} (+{len(missing_on_disk) - 1} more)"
        return (
            f"Excel workbook indexed in analysis log but not readable on disk ({hint}); "
            f"expected under {legacy_scrape_dir()} or the original scan path"
        )
    if unsupported_format:
        return (
            "Excel workbook indexed but data_format not supported for standings tables "
            "(expected pre/post-2022 league format)"
        )
    return (
        "No Excel workbook indexed for this league×season in extract_excel_analysis_log.json "
        "(merge may use another source, e.g. legacy scrape CSV without per-file analysis)"
    )


def _is_input_row(row: pd.Series) -> bool:
    value = str(row.get(Columns.input_data, "")).strip().lower()
    return value in {"true", "1", "yes"}


def compute_standings_from_dataframe(
    df: pd.DataFrame,
    *,
    league: str,
    season: str,
    max_week: Optional[int] = None,
) -> List[StandingRow]:
    """Aggregate season standings from flat league rows (mirrors merge output)."""
    if df.empty:
        return []

    league_col = Columns.event if Columns.event in df.columns else "League"
    season_col = Columns.season
    team_col = Columns.team_name
    if league_col not in df.columns or season_col not in df.columns or team_col not in df.columns:
        return []

    season_variants = _season_label_variants(season)
    mask = df[league_col].astype(str) == str(league)
    mask &= df[season_col].astype(str).isin(season_variants)
    if Columns.event_type in df.columns:
        mask &= df[Columns.event_type].fillna("league").astype(str).str.lower().eq("league")
    if max_week is not None:
        week_nums = pd.to_numeric(df[Columns.week], errors="coerce")
        mask &= week_nums <= int(max_week)
    sub = df.loc[mask]
    if sub.empty:
        return []

    totals: Dict[str, Tuple[float, int]] = {}
    for team, group in sub.groupby(team_col, sort=False):
        team_name = str(team).strip()
        if not team_name or team_name in {"0", "Team Total"}:
            continue
        input_rows = group[group.apply(_is_input_row, axis=1)]
        pins = int(sum_scores_float(input_rows[Columns.score] if not input_rows.empty else group.iloc[0:0][Columns.score]))
        points = sum(float(league_points_cell(row)) for _, row in group.iterrows())
        totals[team_name] = (float(points), pins)

    ranked = sorted(totals.items(), key=lambda item: (-item[1][0], -item[1][1], item[0].casefold()))
    return [
        StandingRow(position=idx, team=team, total_points=pts, total_pins=pins)
        for idx, (team, (pts, pins)) in enumerate(ranked, start=1)
    ]


def _team_mismatch_count(
    missing_in_computed: Sequence[str],
    missing_in_reference: Sequence[str],
) -> int:
    return len(missing_in_computed) + len(missing_in_reference)


@dataclass(frozen=True)
class StandingsProcessingSnapshot:
    step: str
    team_mismatches: int
    teams_match: bool
    positions_match: bool
    points_match: bool
    pins_match: bool
    status: str
    missing_in_computed: Tuple[str, ...]
    missing_in_reference: Tuple[str, ...]
    position_mismatches: Tuple[str, ...]
    points_mismatches: Tuple[str, ...]
    pins_mismatches: Tuple[str, ...]


_TEAM_NUMBER_OVERRIDE_MAP: Optional[Dict[Tuple[str, str, str, str], str]] = None


def _load_team_number_override_map() -> Dict[Tuple[str, str, str, str], str]:
    global _TEAM_NUMBER_OVERRIDE_MAP
    if _TEAM_NUMBER_OVERRIDE_MAP is not None:
        return _TEAM_NUMBER_OVERRIDE_MAP
    from extract_excel_data import load_team_number_overrides, normalize_optional_text

    override_map: Dict[Tuple[str, str, str, str], str] = {}
    overrides_df = load_team_number_overrides()
    if not overrides_df.empty:
        for row in overrides_df.itertuples(index=False):
            club = normalize_optional_text(getattr(row, "club", ""))
            season = normalize_optional_text(getattr(row, "season", ""))
            from_num = normalize_optional_text(getattr(row, "from_team_number", ""))
            to_num = normalize_optional_text(getattr(row, "to_team_number", ""))
            league = normalize_optional_text(getattr(row, "league", ""))
            if not club or not season or to_num is None:
                continue
            override_map[(club, season, league or "", from_num or "")] = str(to_num)
    _TEAM_NUMBER_OVERRIDE_MAP = override_map
    return override_map


def _apply_team_name_normalization(team: str) -> str:
    """Single-pass team name normalization (same as merge ``normalize_extracted_dataframe``)."""
    from extract_excel_data import normalize_team_name

    return str(normalize_team_name(team) or "").strip()


def _canonical_team_standings_key(name: str) -> str:
    """
    Stable comparison key after team-name normalization rules.

    Rules exist for these aliases (Merlin München-Land, SW 77 'Würzburg, etc.);
    the key must use post-normalization forms only — not the raw Excel spelling.
    """
    once = _apply_team_name_normalization(name)
    if not once:
        return ""
    twice = _apply_team_name_normalization(once)
    variants = list(dict.fromkeys(item for item in (once, twice) if item))
    return min(variants, key=lambda item: item.casefold()).casefold()


def _apply_team_name_regex(team: str) -> str:
    """Backward-compatible alias for normalization helper."""
    return _apply_team_name_normalization(team)


def _apply_team_number(
    team: str,
    *,
    season: str,
    league: str,
    override_map: Mapping[Tuple[str, str, str, str], str],
) -> str:
    from extract_excel_data import _split_team_base_and_number, normalize_optional_text

    team_raw = normalize_optional_text(team)
    if not team_raw:
        return team_raw
    base, num = _split_team_base_and_number(team_raw)
    if not base:
        return team_raw
    current_num = num or ""
    override_target = (
        override_map.get((base, season, league, current_num))
        or override_map.get((base, season, "", current_num))
    )
    if override_target is not None:
        target_num = str(override_target).strip()
        return f"{base} {target_num}".strip() if target_num else base
    if current_num:
        return team_raw
    return f"{base} 1"


def _transform_standings(
    rows: Sequence[StandingRow],
    *,
    season: str,
    league: str,
    apply_normalization: bool,
    apply_team_number: bool,
    override_map: Mapping[Tuple[str, str, str, str], str],
) -> List[StandingRow]:
    out: List[StandingRow] = []
    for row in rows:
        team = row.team
        if apply_normalization:
            team = _apply_team_name_normalization(team)
        if apply_team_number:
            team = _apply_team_number(
                team,
                season=season,
                league=league,
                override_map=override_map,
            )
        out.append(
            StandingRow(
                position=row.position,
                team=team,
                total_points=row.total_points,
                total_pins=row.total_pins,
            )
        )
    return out


def _resolved_by_step(snapshots: Sequence[StandingsProcessingSnapshot]) -> str:
    if not snapshots or snapshots[0].team_mismatches == 0:
        return ""
    resolved = ""
    for idx in range(1, len(snapshots)):
        prev = snapshots[idx - 1]
        cur = snapshots[idx]
        if cur.team_mismatches < prev.team_mismatches:
            resolved = cur.step
            if cur.team_mismatches == 0:
                return cur.step
    return resolved


def compare_standings_with_processing(
    reference: Sequence[StandingRow],
    computed: Sequence[StandingRow],
    *,
    season: str,
    league: str,
) -> Tuple[
    bool,
    bool,
    bool,
    bool,
    List[str],
    List[str],
    List[str],
    List[str],
    List[str],
    List[StandingsProcessingSnapshot],
]:
    """Compare standings through merge-aligned processing steps; return final + snapshots."""
    override_map = _load_team_number_override_map()
    step_configs = (
        ("raw", False, False, False, None),
        ("team_name_normalization", True, False, False, _canonical_team_standings_key),
        ("team_number", True, False, True, _canonical_team_standings_key),
    )
    snapshots: List[StandingsProcessingSnapshot] = []
    final: Optional[
        Tuple[bool, bool, bool, bool, List[str], List[str], List[str], List[str], List[str]]
    ] = None

    for step, ref_norm, comp_norm, apply_team_number, key_fn in step_configs:
        ref = _transform_standings(
            reference,
            season=season,
            league=league,
            apply_normalization=ref_norm,
            apply_team_number=apply_team_number,
            override_map=override_map,
        )
        comp = _transform_standings(
            computed,
            season=season,
            league=league,
            apply_normalization=comp_norm,
            apply_team_number=apply_team_number,
            override_map=override_map,
        )
        (
            teams_match,
            positions_match,
            points_match,
            pins_match,
            missing_in_computed,
            missing_in_reference,
            position_mismatches,
            points_mismatches,
            pins_mismatches,
        ) = compare_standings(
            ref,
            comp,
            normalize_team_keys=step != "raw",
            key_fn=key_fn,
        )
        status = classify_status(
            teams_match=teams_match,
            positions_match=positions_match,
            points_match=points_match,
            pins_match=pins_match,
        )
        snapshots.append(
            StandingsProcessingSnapshot(
                step=step,
                team_mismatches=_team_mismatch_count(missing_in_computed, missing_in_reference),
                teams_match=teams_match,
                positions_match=positions_match,
                points_match=points_match,
                pins_match=pins_match,
                status=status,
                missing_in_computed=tuple(missing_in_computed),
                missing_in_reference=tuple(missing_in_reference),
                position_mismatches=tuple(position_mismatches),
                points_mismatches=tuple(points_mismatches),
                pins_mismatches=tuple(pins_mismatches),
            )
        )
        final = (
            teams_match,
            positions_match,
            points_match,
            pins_match,
            missing_in_computed,
            missing_in_reference,
            position_mismatches,
            points_mismatches,
            pins_mismatches,
        )

    assert final is not None
    return (*final, snapshots)


def compare_standings(
    reference: Sequence[StandingRow],
    computed: Sequence[StandingRow],
    *,
    normalize_team_keys: bool = True,
    key_fn: Optional[Any] = None,
) -> Tuple[bool, bool, bool, bool, List[str], List[str], List[str], List[str], List[str]]:
    if key_fn is not None:
        match_key = key_fn
    elif normalize_team_keys:
        match_key = _normalize_team_key
    else:
        match_key = lambda name: str(name or "").strip().casefold()
    ref_by_team = {match_key(row.team): row for row in reference}
    comp_by_team = {match_key(row.team): row for row in computed}

    ref_teams = set(ref_by_team)
    comp_teams = set(comp_by_team)
    missing_in_computed = sorted(
        row.team for key, row in ref_by_team.items() if key not in comp_teams
    )
    missing_in_reference = sorted(
        row.team for key, row in comp_by_team.items() if key not in ref_teams
    )
    teams_match = ref_teams == comp_teams and not missing_in_computed and not missing_in_reference

    position_mismatches: List[str] = []
    points_mismatches: List[str] = []
    pins_mismatches: List[str] = []

    positions_match = teams_match
    points_match = teams_match
    pins_match = teams_match

    if teams_match:
        for key, ref_row in ref_by_team.items():
            comp_row = comp_by_team[key]
            if ref_row.position != comp_row.position:
                positions_match = False
                position_mismatches.append(
                    f"{ref_row.team}: ref pos {ref_row.position} vs computed {comp_row.position}"
                )
            if not _points_close(ref_row.total_points, comp_row.total_points):
                points_match = False
                points_mismatches.append(
                    f"{ref_row.team}: ref pts {ref_row.total_points} vs computed {comp_row.total_points}"
                )
            if not _pins_close(ref_row.total_pins, comp_row.total_pins):
                pins_match = False
                pins_mismatches.append(
                    f"{ref_row.team}: ref pins {ref_row.total_pins} vs computed {comp_row.total_pins}"
                )

    return (
        teams_match,
        positions_match,
        points_match,
        pins_match,
        missing_in_computed,
        missing_in_reference,
        position_mismatches,
        points_mismatches,
        pins_mismatches,
    )


def classify_status(
    *,
    teams_match: bool,
    positions_match: bool,
    points_match: bool,
    pins_match: bool,
) -> str:
    if teams_match and positions_match and points_match and pins_match:
        return STATUS_GREEN
    if teams_match and positions_match:
        return STATUS_YELLOW
    return STATUS_RED


def _week_coverage_note(coverage: LeagueSeasonWeekCoverage) -> str:
    if not coverage.missing_weeks:
        return ""
    available = ",".join(str(w) for w in coverage.available_weeks) or "—"
    missing = ",".join(str(w) for w in coverage.missing_weeks)
    return (
        f"incomplete season: {len(coverage.available_weeks)}/{coverage.expected_weeks} matchdays "
        f"(available {available}; missing {missing})"
    )


def _append_note(existing: str, extra: str) -> str:
    if not extra:
        return existing
    if not existing:
        return extra
    if extra in existing:
        return existing
    return f"{existing}; {extra}"


def _apply_week_coverage(
    comparison: StandingsComparison,
    coverage: LeagueSeasonWeekCoverage,
) -> StandingsComparison:
    comparison.expected_weeks = coverage.expected_weeks
    comparison.available_weeks = list(coverage.available_weeks)
    comparison.missing_matchdays = list(coverage.missing_weeks)
    comparison.week_coverage_status = coverage.status

    week_note = _week_coverage_note(coverage)
    if week_note:
        comparison.notes = _append_note(comparison.notes, week_note)
        if comparison.status == STATUS_GREEN:
            comparison.status = STATUS_YELLOW
        elif comparison.status == STATUS_SKIPPED and coverage.missing_weeks:
            comparison.status = STATUS_YELLOW

    if (
        coverage.missing_weeks
        and comparison.reference_week is not None
        and comparison.expected_weeks > 0
        and comparison.reference_week < comparison.expected_weeks
    ):
        comparison.notes = _append_note(
            comparison.notes,
            f"Excel reference through week {comparison.reference_week} only "
            f"(expected {comparison.expected_weeks} matchdays)",
        )

    return comparison


def _with_week_coverage(df: pd.DataFrame, comparison: StandingsComparison) -> StandingsComparison:
    coverage = compute_league_season_week_coverage(
        df,
        league=comparison.league,
        season=comparison.season,
    )
    return _apply_week_coverage(comparison, coverage)


def _apply_total_points_validation(
    comparison: StandingsComparison,
    *,
    reference: Sequence[StandingRow],
    computed: Sequence[StandingRow],
    target: ExcelReferenceTarget,
    league_df: pd.DataFrame,
    reference_sheet: str = "",
    analysis_log_path: Optional[Path] = None,
) -> StandingsComparison:
    ref_total = sum(row.total_points for row in reference)
    comp_total = sum(row.total_points for row in computed)
    standings_teams = max(len(reference), len(computed))
    team_count = resolve_real_team_count_for_budget(
        standings_team_count=standings_teams,
        analysis_team_count=target.number_of_teams,
    )
    bye_phantom = phantom_bye_league(
        standings_team_count=standings_teams,
        analysis_team_count=target.number_of_teams,
    )
    schema_weeks = expected_weeks_for_league_season(
        target.league,
        target.season,
        team_count=team_count,
    )
    ref_weeks = target.week or schema_weeks
    budget = compute_league_points_budget(
        league=target.league,
        season=target.season,
        number_of_teams=team_count,
        reference_weeks=ref_weeks,
        games_per_week=target.games_per_week,
        data_format=target.data_format,
        phantom_bye=bye_phantom,
    )
    ref_weekly: Dict[int, float] = {}
    weekly_team_points: Dict[int, Dict[str, float]] = {}
    if target.data_format == "data_format_pre_2022" and analysis_log_path is not None:
        weekly_team_points = collect_pre_2022_reference_weekly_team_points(
            analysis_log_path,
            league=target.league,
            season=target.season,
            max_week=ref_weeks,
        )
        ref_weekly = weekly_pool_from_team_points(weekly_team_points)
    if not ref_weekly:
        ref_weekly = parse_reference_weekly_points_pool(
            target.file_path,
            sheet_name=reference_sheet,
            ref_week=ref_weeks,
        )
    no_show_teams: Dict[int, List[str]] = {}
    if target.data_format == "data_format_pre_2022" and weekly_team_points:
        no_show_teams = no_show_teams_by_week_from_reference(weekly_team_points)
        comparison.no_show_findings = format_no_show_findings(no_show_teams)
    ref_schema_ok, comp_ref_ok, explained, message = analyze_total_points(
        reference_total=ref_total,
        computed_total=comp_total,
        budget=budget,
        points_mismatches=comparison.points_mismatches,
    )
    comparison.total_points_reference = ref_total
    comparison.total_points_computed = comp_total
    comparison.total_points_expected = budget.season_total_points
    comparison.reference_total_points_ok = ref_schema_ok
    comparison.computed_total_points_ok = comp_ref_ok
    comp_weekly = compute_weekly_points_pool_from_dataframe(
        league_df,
        league=target.league,
        season=target.season,
        max_week=ref_weeks,
    )
    comparison.weekly_points_findings = analyze_weekly_points_divergence(
        reference_weekly=ref_weekly,
        computed_weekly=comp_weekly,
        budget=budget,
        no_show_teams_by_week=no_show_teams,
        reference_total_ok=ref_schema_ok,
        computed_total_ok=comp_ref_ok,
        has_points_mismatches=bool(comparison.points_mismatches),
    )
    healed, no_show_remark = detect_no_show_ref_schema_healing(
        reference_total=ref_total,
        computed_total=comp_total,
        schema_total=budget.season_total_points,
        no_show_teams_by_week=no_show_teams,
        comp_ref_ok=comp_ref_ok,
        ref_schema_ok=ref_schema_ok,
        teams_match=comparison.teams_match,
        positions_match=comparison.positions_match,
    )
    if healed:
        comparison.ref_schema_healed_by_no_show = True
        comparison.no_show_remark = no_show_remark
    comparison.points_mismatch_explained_by_total = explained
    if message:
        comparison.notes = _append_note(comparison.notes, message)
    for finding in comparison.no_show_findings:
        comparison.notes = _append_note(comparison.notes, finding)
    if no_show_remark:
        comparison.notes = _append_note(comparison.notes, no_show_remark)
    if comparison.teams_match and comparison.positions_match:
        if not comp_ref_ok:
            comparison.status = STATUS_RED
        elif not ref_schema_ok:
            comparison.status = STATUS_YELLOW
        elif explained:
            comparison.status = STATUS_YELLOW
    comparison.error_categories = classify_error_categories(comparison)
    return comparison


def _apply_validation_outcome(comparison: StandingsComparison) -> StandingsComparison:
    """Promote clean matches to perfect; accept consistent 1pt Excel drift as corrected."""
    if comparison.status == STATUS_SKIPPED:
        comparison.error_categories = classify_error_categories(comparison)
        return comparison
    if comparison.missing_matchdays:
        comparison.error_categories = classify_error_categories(comparison)
        return comparison

    corrected, remark = detect_points_one_off_correction(
        reference_total=comparison.total_points_reference,
        computed_total=comparison.total_points_computed,
        expected_total=comparison.total_points_expected,
        points_mismatches=comparison.points_mismatches,
        teams_match=comparison.teams_match,
        positions_match=comparison.positions_match,
        pins_match=comparison.pins_match,
        reference_total_points_ok=comparison.reference_total_points_ok,
        computed_total_points_ok=comparison.computed_total_points_ok,
    )
    if corrected:
        comparison.points_auto_corrected = True
        comparison.correction_remark = remark
        comparison.status = STATUS_CORRECTED
        comparison.notes = _append_note(comparison.notes, remark)
        comparison.error_categories = classify_error_categories(comparison)
        return comparison

    if (
        comparison.ref_schema_healed_by_no_show
        and comparison.teams_match
        and comparison.positions_match
        and comparison.pins_match
        and comparison.computed_total_points_ok
    ):
        comparison.status = STATUS_CORRECTED
        comparison.error_categories = classify_error_categories(comparison)
        return comparison

    if (
        comparison.teams_match
        and comparison.positions_match
        and comparison.points_match
        and comparison.pins_match
        and comparison.reference_total_points_ok
        and comparison.computed_total_points_ok
        and comparison.status in {STATUS_GREEN, STATUS_YELLOW}
    ):
        comparison.status = STATUS_PERFECT

    comparison.error_categories = classify_error_categories(comparison)
    return comparison


def compare_league_season_without_reference(
    df: pd.DataFrame,
    *,
    league: str,
    season: str,
    analysis_log_path: Optional[Path] = None,
) -> StandingsComparison:
    if analysis_log_path is not None:
        notes = describe_missing_excel_reference(
            analysis_log_path,
            league=league,
            season=season,
        )
    else:
        notes = (
            "No Excel workbook indexed for this league×season "
            "(merge may use another source, e.g. legacy scrape CSV)"
        )
    comparison = StandingsComparison(
        season=season,
        league=league,
        status=STATUS_SKIPPED,
        notes=notes,
        error_categories=["skipped"],
    )
    return _with_week_coverage(df, comparison)


def compare_league_season(
    df: pd.DataFrame,
    target: ExcelReferenceTarget,
    *,
    analysis_log_path: Optional[Path] = None,
) -> StandingsComparison:
    reference, sheet_name = parse_standings_from_workbook(
        target.file_path,
        data_format=target.data_format,
        max_week=target.week,
    )
    reference_week = target.week or _week_from_sheet_name(sheet_name)
    computed = compute_standings_from_dataframe(
        df,
        league=target.league,
        season=target.season,
        max_week=reference_week,
    )
    if not reference:
        return _with_week_coverage(
            df,
            StandingsComparison(
                season=target.season,
                league=target.league,
                status=STATUS_SKIPPED,
                reference_source=str(target.file_path),
                reference_sheet=sheet_name,
                reference_week=reference_week,
                data_format=target.data_format,
                computed_team_count=len(computed),
                notes="no reference standings parsed"
                + (f" (tried through week {reference_week})" if reference_week else ""),
            ),
        )
    if not computed:
        return _with_week_coverage(
            df,
            StandingsComparison(
                season=target.season,
                league=target.league,
                status=STATUS_RED,
                reference_source=str(target.file_path),
                reference_sheet=sheet_name,
                reference_week=reference_week,
                data_format=target.data_format,
                reference_team_count=len(reference),
                notes="no computed standings for league season",
            ),
        )

    (
        teams_match,
        positions_match,
        points_match,
        pins_match,
        missing_in_computed,
        missing_in_reference,
        position_mismatches,
        points_mismatches,
        pins_mismatches,
        snapshots,
    ) = compare_standings_with_processing(
        reference,
        computed,
        season=target.season,
        league=target.league,
    )

    status = classify_status(
        teams_match=teams_match,
        positions_match=positions_match,
        points_match=points_match,
        pins_match=pins_match,
    )
    comparison = StandingsComparison(
        season=target.season,
        league=target.league,
        status=status,
        reference_source=str(target.file_path),
        reference_sheet=sheet_name,
        reference_week=reference_week,
        data_format=target.data_format,
        computed_team_count=len(computed),
        reference_team_count=len(reference),
        teams_match=teams_match,
        positions_match=positions_match,
        points_match=points_match,
        pins_match=pins_match,
        missing_in_computed=missing_in_computed,
        missing_in_reference=missing_in_reference,
        position_mismatches=position_mismatches,
        points_mismatches=points_mismatches,
        pins_mismatches=pins_mismatches,
        status_raw=snapshots[0].status if snapshots else "",
        team_mismatches_raw=snapshots[0].team_mismatches if snapshots else 0,
        team_mismatches_after_team_name=(
            snapshots[1].team_mismatches if len(snapshots) > 1 else 0
        ),
        team_mismatches_final=snapshots[-1].team_mismatches if snapshots else 0,
        team_resolution_step=_resolved_by_step(snapshots),
    )
    comparison = _apply_total_points_validation(
        comparison,
        reference=reference,
        computed=computed,
        target=target,
        league_df=df,
        reference_sheet=sheet_name,
        analysis_log_path=analysis_log_path,
    )
    comparison = _with_week_coverage(df, comparison)
    return _apply_validation_outcome(comparison)


def audit_league_standings(
    league_df: pd.DataFrame,
    *,
    analysis_log_path: Path,
    leagues: Optional[Sequence[str]] = None,
    seasons: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    excel_only: bool = False,
) -> List[StandingsComparison]:
    excel_targets = discover_excel_reference_targets(analysis_log_path)
    excel_by_key = {(target.league, target.season): target for target in excel_targets}

    if excel_only:
        pair_keys = list(excel_by_key.keys())
    else:
        pair_keys = sorted(set(discover_league_season_pairs(league_df)) | set(excel_by_key.keys()))

    if leagues:
        league_set = {str(item) for item in leagues}
        pair_keys = [key for key in pair_keys if key[0] in league_set]
    if seasons:
        season_set: set[str] = set()
        for season in seasons:
            season_set |= _season_label_variants(str(season))
        pair_keys = [key for key in pair_keys if key[1] in season_set]
    if limit is not None:
        pair_keys = pair_keys[: max(0, int(limit))]

    comparisons: List[StandingsComparison] = []
    for league, season in pair_keys:
        target = excel_by_key.get((league, season))
        if target is not None:
            comparisons.append(
                compare_league_season(
                    league_df,
                    target,
                    analysis_log_path=analysis_log_path,
                )
            )
        else:
            comparisons.append(
                compare_league_season_without_reference(
                    league_df,
                    league=league,
                    season=season,
                    analysis_log_path=analysis_log_path,
                )
            )
    return comparisons


def comparison_findings(item: StandingsComparison) -> List[str]:
    """Human-readable mismatch lines (same shape as CLI detail bullets)."""
    lines: List[str] = []
    if item.points_auto_corrected and item.correction_remark:
        lines.append(f"corrected: {item.correction_remark}")
    lines.extend(item.no_show_findings)
    if item.ref_schema_healed_by_no_show and item.no_show_remark:
        lines.append(item.no_show_remark)
    if item.points_mismatch_explained_by_total:
        lines.append(
            "pts-total: Excel standings aggregate likely wrong "
            f"(ref {item.total_points_reference:g} vs schema {item.total_points_expected:g}, "
            f"computed {item.total_points_computed:g} matches Excel ref)"
        )
    elif not item.reference_total_points_ok or not item.computed_total_points_ok:
        lines.append(
            "pts-total: "
            f"ref {item.total_points_reference:g} / schema {item.total_points_expected:g} / "
            f"computed {item.total_points_computed:g}"
        )
    lines.extend(item.weekly_points_findings)
    lines.extend(item.missing_in_computed)
    lines.extend(item.missing_in_reference)
    lines.extend(f"pos: {line}" for line in item.position_mismatches)
    lines.extend(f"pts: {line}" for line in item.points_mismatches)
    lines.extend(f"pins: {line}" for line in item.pins_mismatches)
    return lines


def parse_findings_cell(raw: str) -> List[str]:
    if not raw or not str(raw).strip():
        return []
    return [part for part in str(raw).split(FINDINGS_DELIMITER) if part]


def findings_from_row_parts(
    *,
    missing_in_computed: Sequence[str],
    missing_in_reference: Sequence[str],
    position_mismatches: Sequence[str],
    points_mismatches: Sequence[str],
    pins_mismatches: Sequence[str],
) -> List[str]:
    """Rebuild findings from structured CSV columns (older reports)."""
    lines: List[str] = []
    lines.extend(missing_in_computed)
    lines.extend(missing_in_reference)
    lines.extend(f"pos: {line}" for line in position_mismatches)
    lines.extend(f"pts: {line}" for line in points_mismatches)
    lines.extend(f"pins: {line}" for line in pins_mismatches)
    return lines


def summarize_comparisons(comparisons: Sequence[StandingsComparison]) -> Dict[str, int]:
    counts = {
        STATUS_PERFECT: 0,
        STATUS_CORRECTED: 0,
        STATUS_GREEN: 0,
        STATUS_YELLOW: 0,
        STATUS_RED: 0,
        STATUS_SKIPPED: 0,
    }
    week_issues = 0
    for item in comparisons:
        counts[item.status] = counts.get(item.status, 0) + 1
        if item.missing_matchdays:
            week_issues += 1
    counts["week_incomplete"] = week_issues
    counts["green"] = (
        counts.get(STATUS_GREEN, 0)
        + counts.get(STATUS_PERFECT, 0)
        + counts.get(STATUS_CORRECTED, 0)
    )
    return counts


def format_comparison_report(
    comparisons: Sequence[StandingsComparison],
    *,
    data_path: Optional[Path] = None,
) -> str:
    lines = ["League standings validation"]
    if data_path is not None:
        lines.append(f"Data: {data_path}")
    counts = summarize_comparisons(comparisons)
    lines.append(
        "Summary: "
        + ", ".join(
            f"{key}={counts.get(key, 0)}"
            for key in (
                STATUS_PERFECT,
                STATUS_CORRECTED,
                STATUS_YELLOW,
                STATUS_RED,
                STATUS_SKIPPED,
                "week_incomplete",
            )
        )
    )
    for item in comparisons:
        show = (
            item.status not in {STATUS_GREEN, STATUS_PERFECT}
            or item.ref_schema_healed_by_no_show
            or item.missing_matchdays
            or item.week_coverage_status not in ("", WEEK_COVERAGE_OK)
        )
        if not show:
            continue
        lines.append(item.summary_line())
        for detail in comparison_findings(item):
            lines.append(f"  - {detail}")
    return "\n".join(lines)


def write_comparison_report(
    comparisons: Sequence[StandingsComparison],
    report_path: Path,
) -> None:
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "season",
        "league",
        "status",
        "reference_source",
        "reference_sheet",
        "reference_week",
        "data_format",
        "reference_team_count",
        "computed_team_count",
        "teams_match",
        "positions_match",
        "points_match",
        "pins_match",
        "missing_in_computed",
        "missing_in_reference",
        "position_mismatches",
        "points_mismatches",
        "pins_mismatches",
        "findings",
        "expected_weeks",
        "available_weeks",
        "missing_matchdays",
        "week_coverage_status",
        "notes",
        "status_raw",
        "team_mismatches_raw",
        "team_mismatches_after_team_name",
        "team_mismatches_final",
        "team_resolution_step",
        "total_points_reference",
        "total_points_computed",
        "total_points_expected",
        "reference_total_points_ok",
        "computed_total_points_ok",
        "points_mismatch_explained_by_total",
        "points_auto_corrected",
        "correction_remark",
        "weekly_points_findings",
        "error_categories",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in comparisons:
            findings = comparison_findings(item)
            writer.writerow(
                {
                    "season": item.season,
                    "league": item.league,
                    "status": item.status,
                    "reference_source": item.reference_source,
                    "reference_sheet": item.reference_sheet,
                    "reference_week": item.reference_week if item.reference_week is not None else "",
                    "data_format": item.data_format,
                    "reference_team_count": item.reference_team_count,
                    "computed_team_count": item.computed_team_count,
                    "teams_match": int(item.teams_match),
                    "positions_match": int(item.positions_match),
                    "points_match": int(item.points_match),
                    "pins_match": int(item.pins_match),
                    "missing_in_computed": "|".join(item.missing_in_computed),
                    "missing_in_reference": "|".join(item.missing_in_reference),
                    "position_mismatches": "|".join(item.position_mismatches),
                    "points_mismatches": "|".join(item.points_mismatches),
                    "pins_mismatches": "|".join(item.pins_mismatches),
                    "findings": FINDINGS_DELIMITER.join(findings),
                    "expected_weeks": item.expected_weeks,
                    "available_weeks": ",".join(str(w) for w in item.available_weeks),
                    "missing_matchdays": ",".join(str(w) for w in item.missing_matchdays),
                    "week_coverage_status": item.week_coverage_status,
                    "notes": item.notes,
                    "status_raw": item.status_raw,
                    "team_mismatches_raw": item.team_mismatches_raw,
                    "team_mismatches_after_team_name": item.team_mismatches_after_team_name,
                    "team_mismatches_final": item.team_mismatches_final,
                    "team_resolution_step": item.team_resolution_step,
                    "total_points_reference": item.total_points_reference,
                    "total_points_computed": item.total_points_computed,
                    "total_points_expected": item.total_points_expected,
                    "reference_total_points_ok": int(item.reference_total_points_ok),
                    "computed_total_points_ok": int(item.computed_total_points_ok),
                    "points_mismatch_explained_by_total": int(
                        item.points_mismatch_explained_by_total
                    ),
                    "points_auto_corrected": int(item.points_auto_corrected),
                    "correction_remark": item.correction_remark,
                    "weekly_points_findings": "|".join(item.weekly_points_findings),
                    "error_categories": ",".join(item.error_categories),
                }
            )


def comparison_summary_for_manifest(comparisons: Sequence[StandingsComparison]) -> Dict[str, Any]:
    counts = summarize_comparisons(comparisons)
    evaluated = [item for item in comparisons if item.status != STATUS_SKIPPED]
    overall = STATUS_PERFECT
    if any(item.status == STATUS_RED for item in evaluated):
        overall = STATUS_RED
    elif any(item.status == STATUS_YELLOW for item in evaluated):
        overall = STATUS_YELLOW
    elif not evaluated:
        overall = STATUS_SKIPPED
    elif any(item.status == STATUS_CORRECTED for item in evaluated):
        overall = STATUS_CORRECTED
    return {
        "status": overall,
        "counts": counts,
        "evaluated": len(evaluated),
        "skipped": counts.get(STATUS_SKIPPED, 0),
        "week_incomplete": counts.get("week_incomplete", 0),
    }
