"""Merge operator-reviewed club mappings into ``club_mapping.csv``."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Mapping, Set

from data_access.club_name_validation import load_saved_club_mappings
from data_access.clubs_registry import _club_mapping_path, load_club_mapping_rows
from data_access.text_norm import normalize_unicode_label


def _join_aliases(aliases: Set[str]) -> str:
    return "|".join(sorted(alias for alias in aliases if alias))


def merge_resolved_mappings_into_club_mapping(
    resolved: Mapping[str, str],
    *,
    club_mapping_path: Path | None = None,
) -> Dict[str, object]:
    """
    Add ``unresolved_label`` values as aliases for each ``canonical_name``.

    Existing ``club_mapping.csv`` rows are preserved; aliases are unioned per canonical.
    """
    path = club_mapping_path or _club_mapping_path()
    buckets: Dict[str, Set[str]] = {}

    for row in load_club_mapping_rows():
        canonical = str(row["canonical_name"]).strip()
        if not canonical:
            continue
        bucket = buckets.setdefault(canonical, set())
        bucket.update(str(alias).strip() for alias in row.get("aliases") or [] if str(alias).strip())

    added = 0
    for raw_label, raw_canonical in resolved.items():
        label = normalize_unicode_label(raw_label)
        canonical = normalize_unicode_label(raw_canonical)
        if not label or not canonical:
            continue
        bucket = buckets.setdefault(canonical, set())
        if label not in bucket and label != canonical:
            bucket.add(label)
            added += 1

    rows: List[dict] = []
    for canonical in sorted(buckets):
        aliases = buckets[canonical]
        aliases.discard(canonical)
        rows.append(
            {
                "canonical_name": canonical,
                "aliases": _join_aliases(aliases),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["canonical_name", "aliases"])
        writer.writeheader()
        writer.writerows(rows)

    if hasattr(load_club_mapping_rows, "cache_clear"):
        load_club_mapping_rows.cache_clear()

    return {
        "path": str(path.resolve()),
        "canonical_count": len(rows),
        "aliases_added": added,
        "resolved_rows": len(resolved),
    }


def import_resolved_club_mapping_file(
    resolved_path: Path,
    *,
    club_mapping_path: Path | None = None,
) -> Dict[str, object]:
    resolved = load_saved_club_mappings(resolved_path)
    if not resolved:
        raise ValueError(f"No mappings in {resolved_path}")
    summary = merge_resolved_mappings_into_club_mapping(
        resolved,
        club_mapping_path=club_mapping_path,
    )
    summary["source"] = str(resolved_path.resolve())
    return summary
