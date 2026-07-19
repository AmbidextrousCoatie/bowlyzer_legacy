"""Club name resolution payload for Diagnose Validierung UI."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Mapping, Optional, Sequence

from data_access.club_mapping_import import merge_resolved_mappings_into_club_mapping
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
from data_access.clubs_registry import (
    _club_mapping_path,
    append_aliases_to_clubs_registry,
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

    # Prefer live tournament audit (always current) over a stale offline report.
    live_rows = audit_unresolved_tournament_clubs()
    if live_rows:
        unresolved_rows = live_rows
        source = "live"
    elif report_path.is_file():
        unresolved_rows = load_club_name_conflicts_report(report_path)
        source = "report"
        report_mtime = dt.datetime.fromtimestamp(
            report_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()

    if report_path.is_file() and report_mtime is None:
        report_mtime = dt.datetime.fromtimestamp(
            report_path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()

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

    mapping_path = _club_mapping_path()
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
        "club_mapping": {
            "path": str(mapping_path.resolve()),
            "present": mapping_path.is_file(),
        },
    }


def save_club_name_validation_mappings(
    mappings: Sequence[Mapping[str, str]],
) -> Dict[str, Any]:
    """
    Persist UI selections to the work-dir staging CSV, merge into committed
    ``club_mapping.csv``, and fold aliases into published ``clubs_registry``.
    """
    if not mappings:
        raise ValueError("No mappings to save")

    out_path = write_club_name_mapping_resolved(mappings, merge_existing=True)
    saved = load_saved_club_mappings(out_path)
    club_mapping_summary = merge_resolved_mappings_into_club_mapping(saved)
    registry_summary = append_aliases_to_clubs_registry(saved, write_csv=True)

    mtime = dt.datetime.fromtimestamp(
        out_path.stat().st_mtime,
        tz=dt.timezone.utc,
    ).isoformat()
    return {
        "ok": True,
        "path": str(out_path.resolve()),
        "row_count": len(saved),
        "mtime_utc": mtime,
        "club_mapping": club_mapping_summary,
        "clubs_registry": registry_summary,
    }
