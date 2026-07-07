"""Club label resolution UI: unresolved tournament clubs vs league registry."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from data_access.clubs_registry import (
    build_alias_to_canonical,
    load_clubs_registry_df,
    propose_club_resolution,
    resolve_club_label,
)
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label
from database.paths import get_work_data_dir, tournaments_postprocessed_csv

CLUB_NAME_CONFLICTS_CSV = "club_name_conflicts.csv"
CLUB_NAME_MAPPING_RESOLVED_CSV = "club_name_mapping_resolved.csv"

CONFLICT_REPORT_FIELDS = [
    "issue_type",
    "source_file",
    "club_label",
    "row_count",
    "proposed_canonical",
    "proposed_rule",
    "peer_labels",
]

RESOLVED_MAPPING_FIELDS = ["unresolved_label", "canonical_name"]


def _load_tournament_dataframe():
    import pandas as pd

    tournament_path = tournaments_postprocessed_csv()
    if not data_file_exists(tournament_path):
        return None
    load_path = resolve_load_path(tournament_path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def load_registry_canonical_names() -> List[str]:
    registry = load_clubs_registry_df()
    if registry is None or registry.empty:
        return []
    names = sorted({str(name).strip() for name in registry["canonical_name"].tolist() if str(name).strip()})
    return names


def load_saved_club_mappings(path: Optional[Path] = None) -> Dict[str, str]:
    """``unresolved_label`` -> ``canonical_name`` from the operator-reviewed file."""
    out_path = path or (get_work_data_dir() / CLUB_NAME_MAPPING_RESOLVED_CSV)
    if not out_path.is_file():
        return {}
    mapping: Dict[str, str] = {}
    with out_path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            label = normalize_unicode_label(record.get("unresolved_label"))
            canonical = normalize_unicode_label(record.get("canonical_name"))
            if label and canonical:
                mapping[label] = canonical
    return mapping


def audit_unresolved_tournament_clubs() -> List[Dict[str, Any]]:
    """Live audit of tournament ``Club`` labels that do not resolve via ``clubs_registry``."""
    import pandas as pd

    df = _load_tournament_dataframe()
    if df is None or df.empty or Columns.club not in df.columns:
        return []

    registry = load_clubs_registry_df()
    if registry is None or registry.empty:
        return []

    alias_lookup = build_alias_to_canonical(registry)
    canonical_names = registry["canonical_name"].astype(str).tolist()
    counts = Counter(
        normalize_unicode_label(value)
        for value in df[Columns.club].fillna("").astype(str)
        if normalize_unicode_label(value)
    )

    rows: List[Dict[str, Any]] = []
    for label, row_count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        resolved, _rule = resolve_club_label(label, alias_lookup, canonical_names)
        if resolved:
            continue
        proposals = propose_club_resolution(label, alias_lookup, canonical_names)
        proposed_canonical = proposals[0][0] if proposals else ""
        proposed_rule = proposals[0][1] if proposals else ""
        rows.append(
            {
                "issue_type": "tournament_club_unknown",
                "source_file": tournaments_postprocessed_csv().name,
                "club_label": label,
                "row_count": int(row_count),
                "proposed_canonical": proposed_canonical or "",
                "proposed_rule": proposed_rule or "",
                "peer_labels": "",
            }
        )
    return rows


def load_club_name_conflicts_report(report_path: Path) -> List[Dict[str, Any]]:
    if not report_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with report_path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            if str(record.get("issue_type") or "").strip() != "tournament_club_unknown":
                continue
            label = normalize_unicode_label(record.get("club_label"))
            if not label:
                continue
            try:
                row_count = int(float(str(record.get("row_count") or "0").strip() or "0"))
            except ValueError:
                row_count = 0
            rows.append(
                {
                    "issue_type": "tournament_club_unknown",
                    "source_file": str(record.get("source_file") or ""),
                    "club_label": label,
                    "row_count": row_count,
                    "proposed_canonical": str(record.get("proposed_canonical") or "").strip(),
                    "proposed_rule": str(record.get("proposed_rule") or "").strip(),
                    "peer_labels": str(record.get("peer_labels") or "").strip(),
                }
            )
    rows.sort(key=lambda row: (-int(row.get("row_count") or 0), str(row.get("club_label") or "")))
    return rows


def build_club_name_validation_rows(
    unresolved_rows: Sequence[Mapping[str, Any]],
    *,
    saved_mappings: Optional[Mapping[str, str]] = None,
    canonical_names: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    registry_names = set(canonical_names or load_registry_canonical_names())
    saved = dict(saved_mappings or {})
    out: List[Dict[str, Any]] = []
    for row in unresolved_rows:
        label = normalize_unicode_label(row.get("club_label"))
        if not label:
            continue
        proposed = str(row.get("proposed_canonical") or "").strip()
        saved_canonical = saved.get(label, "")
        default_canonical = ""
        if saved_canonical and saved_canonical in registry_names:
            default_canonical = saved_canonical
        elif proposed and proposed in registry_names:
            default_canonical = proposed
        out.append(
            {
                "club_label": label,
                "row_count": int(row.get("row_count") or 0),
                "proposed_canonical": proposed,
                "proposed_rule": str(row.get("proposed_rule") or "").strip(),
                "saved_canonical": saved_canonical,
                "default_canonical": default_canonical,
            }
        )
    return out


def write_club_name_mapping_resolved(
    mappings: Sequence[Mapping[str, str]],
    *,
    out_path: Optional[Path] = None,
    merge_existing: bool = True,
) -> Path:
    """
    Persist operator-selected ``unresolved_label`` → ``canonical_name`` pairs.

    When ``merge_existing`` is true, prior saved rows are kept unless overridden.
    """
    target = out_path or (get_work_data_dir() / CLUB_NAME_MAPPING_RESOLVED_CSV)
    target.parent.mkdir(parents=True, exist_ok=True)

    registry_names = set(load_registry_canonical_names())
    merged: Dict[str, str] = load_saved_club_mappings(target) if merge_existing else {}

    for item in mappings:
        label = normalize_unicode_label(item.get("unresolved_label") or item.get("club_label"))
        canonical = normalize_unicode_label(item.get("canonical_name"))
        if not label or not canonical:
            continue
        if registry_names and canonical not in registry_names:
            raise ValueError(f"Unknown registry club: {canonical}")
        merged[label] = canonical

    rows = [
        {"unresolved_label": label, "canonical_name": merged[label]}
        for label in sorted(merged)
    ]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESOLVED_MAPPING_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return target


def write_club_name_conflicts_report(rows: Sequence[Mapping[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONFLICT_REPORT_FIELDS, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CONFLICT_REPORT_FIELDS})


def validation_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    with_proposal = sum(1 for row in rows if str(row.get("proposed_canonical") or "").strip())
    return {
        "unresolved": len(rows),
        "with_proposal": with_proposal,
        "without_proposal": max(0, len(rows) - with_proposal),
    }
