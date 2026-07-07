#!/usr/bin/env python3
"""
Import ``club_name_mapping_resolved.csv`` into ``database/relational_csv/club_mapping.csv``.

Usage:
  uv run python scripts/import_club_mapping_from_resolved.py
  uv run python scripts/import_club_mapping_from_resolved.py path/to/club_name_mapping_resolved.csv --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.club_mapping_import import import_resolved_club_mapping_file
from data_access.club_name_validation import CLUB_NAME_MAPPING_RESOLVED_CSV
from database.paths import get_work_data_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "resolved_csv",
        nargs="?",
        type=Path,
        default=None,
        help=f"Resolved mappings CSV (default: work dir / {CLUB_NAME_MAPPING_RESOLVED_CSV})",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write club_mapping.csv (default: dry-run summary only)",
    )
    args = parser.parse_args()

    resolved_path = args.resolved_csv or (get_work_data_dir() / CLUB_NAME_MAPPING_RESOLVED_CSV)
    if not resolved_path.is_file():
        print(f"Error: resolved mappings not found: {resolved_path}", file=sys.stderr)
        return 2

    if not args.write:
        from data_access.club_name_validation import load_saved_club_mappings

        resolved = load_saved_club_mappings(resolved_path)
        print(f"Dry run: would import {len(resolved)} mapping(s) from {resolved_path}")
        print("Re-run with --write to update database/relational_csv/club_mapping.csv")
        return 0

    summary = import_resolved_club_mapping_file(resolved_path)
    print(
        f"club_mapping.csv: {summary['canonical_count']} canonical club(s), "
        f"{summary['aliases_added']} alias(es) added from {summary['resolved_rows']} resolved row(s)"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
