"""League standings validation payload for Diagnose UI."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from data_access.league_standings_validation import (
    LEAGUE_STANDINGS_VALIDATION_CSV,
    StandingsComparison,
    audit_league_standings,
    comparison_findings,
    findings_from_row_parts,
    parse_findings_cell,
)
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from database.paths import analysis_log_path, get_work_data_dir, league_results_merged_csv


def _parse_int_list(raw: str) -> List[int]:
    if not raw or not str(raw).strip():
        return []
    out: List[int] = []
    for part in str(raw).replace("|", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(float(part)))
        except ValueError:
            continue
    return out


def _parse_pipe_list(raw: str) -> List[str]:
    if not raw or not str(raw).strip():
        return []
    return [part for part in str(raw).split("|") if part]


def _comparison_to_row(item: StandingsComparison) -> Dict[str, Any]:
    row = asdict(item)
    row["available_weeks"] = list(item.available_weeks)
    row["missing_matchdays"] = list(item.missing_matchdays)
    row["findings"] = comparison_findings(item)
    return row


def _attach_findings(row: Dict[str, Any]) -> Dict[str, Any]:
    parsed = parse_findings_cell(str(row.get("findings") or ""))
    if parsed:
        row["findings"] = parsed
    else:
        row["findings"] = findings_from_row_parts(
            missing_in_computed=row.get("missing_in_computed") or [],
            missing_in_reference=row.get("missing_in_reference") or [],
            position_mismatches=row.get("position_mismatches") or [],
            points_mismatches=row.get("points_mismatches") or [],
            pins_mismatches=row.get("pins_mismatches") or [],
        )
    if not row.get("error_categories"):
        row["error_categories"] = classify_error_categories_from_row(row)
    weekly = row.get("weekly_points_findings") or []
    if weekly:
        findings = list(row.get("findings") or [])
        for line in weekly:
            if line not in findings:
                findings.append(line)
        row["findings"] = findings
    return row


def classify_error_categories_from_row(row: Dict[str, Any]) -> List[str]:
    """Rebuild tags from CSV columns when error_categories absent."""

    class _Row:
        pass

    item = _Row()
    for key, value in row.items():
        setattr(item, key, value)
    from data_access.league_points_budget import classify_error_categories

    return classify_error_categories(item)


def _row_from_csv_record(record: Dict[str, str]) -> Dict[str, Any]:
    def _bool_cell(key: str) -> bool:
        return str(record.get(key, "")).strip() in {"1", "true", "True"}

    ref_week = record.get("reference_week", "").strip()
    return {
        "season": record.get("season", ""),
        "league": record.get("league", ""),
        "status": record.get("status", ""),
        "reference_source": record.get("reference_source", ""),
        "reference_sheet": record.get("reference_sheet", ""),
        "reference_week": int(float(ref_week)) if ref_week else None,
        "data_format": record.get("data_format", ""),
        "reference_team_count": int(record.get("reference_team_count") or 0),
        "computed_team_count": int(record.get("computed_team_count") or 0),
        "teams_match": _bool_cell("teams_match"),
        "positions_match": _bool_cell("positions_match"),
        "points_match": _bool_cell("points_match"),
        "pins_match": _bool_cell("pins_match"),
        "missing_in_computed": _parse_pipe_list(record.get("missing_in_computed", "")),
        "missing_in_reference": _parse_pipe_list(record.get("missing_in_reference", "")),
        "position_mismatches": _parse_pipe_list(record.get("position_mismatches", "")),
        "points_mismatches": _parse_pipe_list(record.get("points_mismatches", "")),
        "pins_mismatches": _parse_pipe_list(record.get("pins_mismatches", "")),
        "findings": parse_findings_cell(record.get("findings", "")),
        "expected_weeks": int(record.get("expected_weeks") or 0),
        "available_weeks": _parse_int_list(record.get("available_weeks", "")),
        "missing_matchdays": _parse_int_list(record.get("missing_matchdays", "")),
        "week_coverage_status": record.get("week_coverage_status", ""),
        "notes": record.get("notes", ""),
        "status_raw": record.get("status_raw", ""),
        "team_mismatches_raw": int(record.get("team_mismatches_raw") or 0),
        "team_mismatches_after_team_name": int(
            record.get("team_mismatches_after_team_name") or 0
        ),
        "team_mismatches_final": int(record.get("team_mismatches_final") or 0),
        "team_resolution_step": record.get("team_resolution_step", ""),
        "total_points_reference": float(record.get("total_points_reference") or 0),
        "total_points_computed": float(record.get("total_points_computed") or 0),
        "total_points_expected": float(record.get("total_points_expected") or 0),
        "reference_total_points_ok": _bool_cell("reference_total_points_ok"),
        "computed_total_points_ok": _bool_cell("computed_total_points_ok"),
        "points_mismatch_explained_by_total": _bool_cell(
            "points_mismatch_explained_by_total"
        ),
        "points_auto_corrected": _bool_cell("points_auto_corrected"),
        "correction_remark": record.get("correction_remark", ""),
        "weekly_points_findings": _parse_pipe_list(record.get("weekly_points_findings", "")),
        "error_categories": [
            part for part in str(record.get("error_categories") or "").split(",") if part
        ],
    }


def load_validation_report_csv(report_path: Path) -> List[Dict[str, Any]]:
    if not report_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with report_path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            if not record.get("league"):
                continue
            rows.append(_attach_findings(_row_from_csv_record(record)))
    return rows


def _load_league_dataframe():
    import pandas as pd

    league_path = league_results_merged_csv()
    if not data_file_exists(league_path):
        return None
    load_path = resolve_load_path(league_path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def _run_live_audit(
    *,
    season: Optional[str],
    league: Optional[str],
) -> List[Dict[str, Any]]:
    log_path = analysis_log_path()
    if not log_path.is_file():
        return []
    league_df = _load_league_dataframe()
    if league_df is None or league_df.empty:
        return []
    seasons = [season] if season else None
    leagues = [league] if league else None
    comparisons = audit_league_standings(
        league_df,
        analysis_log_path=log_path,
        leagues=leagues,
        seasons=seasons,
    )
    return [_comparison_to_row(item) for item in comparisons]


def _filter_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    season: Optional[str],
    league: Optional[str],
) -> List[Dict[str, Any]]:
    out = list(rows)
    if season:
        out = [row for row in out if str(row.get("season") or "") == season]
    if league:
        out = [row for row in out if str(row.get("league") or "") == league]
    return out


def _summary_from_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        key: 0
        for key in (
            "perfect",
            "corrected",
            "green",
            "yellow",
            "red",
            "skipped",
            "week_incomplete",
        )
    }
    for row in rows:
        status = str(row.get("status") or "")
        if status in counts:
            counts[status] += 1
        elif status == "green":
            counts["green"] += 1
        if row.get("missing_matchdays"):
            counts["week_incomplete"] += 1
    counts["green"] = (
        counts["green"] + counts["perfect"] + counts["corrected"]
    )
    return counts


def get_league_standings_validation(
    *,
    season: Optional[str] = None,
    league: Optional[str] = None,
) -> Dict[str, Any]:
    """Report rows from work-dir CSV, or live audit when CSV is absent."""
    work_dir = get_work_data_dir()
    report_path = work_dir / LEAGUE_STANDINGS_VALIDATION_CSV
    source = "absent"
    report_mtime: Optional[str] = None
    rows: List[Dict[str, Any]] = []

    if report_path.is_file():
        rows = load_validation_report_csv(report_path)
        source = "report"
        report_mtime = dt.datetime.fromtimestamp(
            report_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()
    else:
        live_rows = _run_live_audit(season=season, league=league)
        if live_rows:
            rows = live_rows
            source = "live"

    rows = _filter_rows(rows, season=season, league=league)
    summary = _summary_from_rows(rows)

    return {
        "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "source": source,
        "report_present": report_path.is_file(),
        "report_mtime_utc": report_mtime,
        "row_count": len(rows),
        "summary": summary,
        "rows": rows,
        "filters": {"season": season, "league": league},
    }
