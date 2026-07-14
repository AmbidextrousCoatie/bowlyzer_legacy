"""Tournament data quality payload for Diagnose UI."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from data_access.tournament_data_quality import (
    TOURNAMENT_DATA_QUALITY_CSV,
    audit_tournament_data_quality,
    comparison_summary_from_dicts,
    parse_findings_cell,
)
from database.paths import get_work_data_dir, tournaments_input_dir, tournaments_postprocessed_csv


def _row_from_csv_record(record: Dict[str, str]) -> Dict[str, Any]:
    def _int_cell(key: str) -> int:
        raw = str(record.get(key, "")).strip()
        if not raw:
            return 0
        try:
            return int(float(raw))
        except ValueError:
            return 0

    return {
        "season": record.get("season", ""),
        "event_name": record.get("event_name", ""),
        "tournament_group": record.get("tournament_group", ""),
        "row_count": _int_cell("row_count"),
        "player_count": _int_cell("player_count"),
        "missing_player_id": _int_cell("missing_player_id"),
        "missing_club": _int_cell("missing_club"),
        "club_unknown": _int_cell("club_unknown"),
        "club_resolved": _int_cell("club_resolved"),
        "club_names_normalized": _int_cell("club_names_normalized"),
        "player_id_remap_rows": _int_cell("player_id_remap_rows"),
        "registry_rows_changed": _int_cell("registry_rows_changed"),
        "same_name_different_ids": _int_cell("same_name_different_ids"),
        "same_id_different_names": _int_cell("same_id_different_names"),
        "status": record.get("status", ""),
        "findings": parse_findings_cell(record.get("findings", "")),
        "notes": record.get("notes", ""),
    }


def load_tournament_quality_report_csv(report_path: Path) -> List[Dict[str, Any]]:
    if not report_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with report_path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            if not record.get("event_name"):
                continue
            rows.append(_row_from_csv_record(record))
    return rows


def _load_tournament_dataframe():
    import pandas as pd

    tournament_path = tournaments_postprocessed_csv()
    if not data_file_exists(tournament_path):
        return None
    load_path = resolve_load_path(tournament_path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def _run_live_audit(*, season: Optional[str], event: Optional[str]) -> List[Dict[str, Any]]:
    df = _load_tournament_dataframe()
    if df is None or df.empty:
        return []
    seasons = [season] if season else None
    events = [event] if event else None
    from dataclasses import asdict

    rows = audit_tournament_data_quality(df, seasons=seasons, events=events)
    return [asdict(item) for item in rows]


def _attach_source_pdf(row: Dict[str, Any]) -> Dict[str, Any]:
    from database.tournament_import.source_registry import lookup_source_by_season_event

    season = str(row.get("season") or "").strip()
    event_name = str(row.get("event_name") or "").strip()
    source = lookup_source_by_season_event(season, event_name)
    if source is None:
        row["source_pdf"] = None
        row["source_pdf_basename"] = None
        row["source_sheet"] = None
        row["source_format"] = None
        return row
    basename = source.file_basename or Path(source.file_path).name
    row["source_pdf_basename"] = basename or None
    row["source_pdf"] = basename or None
    row["source_sheet"] = source.source_sheet or None
    row["source_format"] = source.format or None
    return row


def resolve_tournament_source_pdf_path(basename: str) -> Path | None:
    """Resolve a tournament source file (PDF or legacy XLS) under the input directory."""
    name = Path(str(basename or "").strip()).name
    suffix = name.lower()
    if not (suffix.endswith(".pdf") or suffix.endswith(".xls") or suffix.endswith(".xlsx")):
        return None
    candidate = tournaments_input_dir() / name
    if candidate.is_file():
        return candidate
    return None


def _source_file_mimetype(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".xls":
        return "application/vnd.ms-excel"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


def _filter_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    season: Optional[str],
    event: Optional[str],
) -> List[Dict[str, Any]]:
    out = list(rows)
    if season:
        out = [row for row in out if str(row.get("season") or "") == season]
    if event:
        out = [row for row in out if str(row.get("event_name") or "") == event]
    return out


def get_tournament_data_quality(
    *,
    season: Optional[str] = None,
    event: Optional[str] = None,
) -> Dict[str, Any]:
    """Report rows from work-dir CSV, or live audit when CSV is absent."""
    work_dir = get_work_data_dir()
    report_path = work_dir / TOURNAMENT_DATA_QUALITY_CSV
    source = "absent"
    report_mtime: Optional[str] = None
    rows: List[Dict[str, Any]] = []

    if report_path.is_file():
        rows = load_tournament_quality_report_csv(report_path)
        source = "report"
        report_mtime = dt.datetime.fromtimestamp(
            report_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()
    else:
        live_rows = _run_live_audit(season=season, event=event)
        if live_rows:
            rows = live_rows
            source = "live"

    rows = _filter_rows(rows, season=season, event=event)
    rows = [_attach_source_pdf(dict(row)) for row in rows]
    summary = comparison_summary_from_dicts(rows)

    pdf_dir = tournaments_input_dir()
    from database.tournament_import.source_exceptions import exceptions_for_api

    return {
        "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "source": source,
        "report_present": report_path.is_file(),
        "report_mtime_utc": report_mtime,
        "row_count": len(rows),
        "summary": summary,
        "rows": rows,
        "filters": {"season": season, "event": event},
        "source_pdf_dir": str(pdf_dir.resolve()) if pdf_dir.is_dir() else "",
        "source_exceptions": exceptions_for_api(),
    }
