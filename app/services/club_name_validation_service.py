"""Club name resolution payload for Diagnose Validierung UI."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from data_access.club_name_validation import (
    CLUB_NAME_CONFLICTS_CSV,
    CLUB_NAME_MAPPING_RESOLVED_CSV,
    audit_unresolved_tournament_clubs,
    build_club_name_validation_rows,
    load_club_name_conflicts_report,
    load_registry_canonical_names,
    load_saved_club_mappings,
    validation_summary,
    write_club_name_mapping_resolved,
)
from database.paths import get_work_data_dir


def get_club_name_validation() -> Dict[str, Any]:
    """Unresolved tournament club labels + registry options for the mapping UI."""
    work_dir = get_work_data_dir()
    report_path = work_dir / CLUB_NAME_CONFLICTS_CSV
    resolved_path = work_dir / CLUB_NAME_MAPPING_RESOLVED_CSV
    source = "absent"
    report_mtime: Optional[str] = None
    unresolved_rows: List[Dict[str, Any]] = []

    if report_path.is_file():
        unresolved_rows = load_club_name_conflicts_report(report_path)
        source = "report"
        report_mtime = dt.datetime.fromtimestamp(
            report_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()
    else:
        live_rows = audit_unresolved_tournament_clubs()
        if live_rows:
            unresolved_rows = live_rows
            source = "live"

    canonical_names = load_registry_canonical_names()
    saved_mappings = load_saved_club_mappings(resolved_path)
    rows = build_club_name_validation_rows(
        unresolved_rows,
        saved_mappings=saved_mappings,
        canonical_names=canonical_names,
    )
    summary = validation_summary(rows)

    resolved_mtime: Optional[str] = None
    if resolved_path.is_file():
        resolved_mtime = dt.datetime.fromtimestamp(
            resolved_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()

    return {
        "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "source": source,
        "report_present": report_path.is_file(),
        "report_mtime_utc": report_mtime,
        "row_count": len(rows),
        "summary": summary,
        "canonical_names": canonical_names,
        "rows": rows,
        "saved_mapping": {
            "present": resolved_path.is_file(),
            "path": str(resolved_path.resolve()),
            "mtime_utc": resolved_mtime,
            "row_count": len(saved_mappings),
        },
    }


def save_club_name_validation_mappings(
    mappings: Sequence[Mapping[str, str]],
) -> Dict[str, Any]:
    """Persist UI selections to ``club_name_mapping_resolved.csv`` in the work dir."""
    if not mappings:
        raise ValueError("No mappings to save")
    out_path = write_club_name_mapping_resolved(mappings, merge_existing=True)
    saved = load_saved_club_mappings(out_path)
    mtime = dt.datetime.fromtimestamp(
        out_path.stat().st_mtime,
        tz=dt.timezone.utc,
    ).isoformat()
    return {
        "ok": True,
        "path": str(out_path.resolve()),
        "row_count": len(saved),
        "mtime_utc": mtime,
    }
