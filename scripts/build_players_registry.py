#!/usr/bin/env python3
"""
Build ``players_registry.parquet`` from scraped *Aktive Mitglieder* workbooks,
then merge normalization JSON updates on top.

By default the published registry is the source of truth: later seasons refresh
DBU canonical names; config changes add aliases and may upgrade canonical only
from trusted sources (``dbu_id``, manual, ``same_person``).

By default rebuilds from Aktive (from ``2008-09`` onward) + configs without merging
the old parquet. Use ``--merge-existing-registry`` or ``--all-aktive-seasons`` only
when you deliberately want legacy behaviour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.aktive_mitglieder_registry import DEFAULT_AKTIVE_MIN_SEASON
from data_access.players_registry import build_and_publish_players_registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Also write players_registry.csv sidecar",
    )
    parser.add_argument(
        "--merge-existing-registry",
        action="store_true",
        help=(
            "Merge into the published parquet instead of rebuilding from "
            "Aktive + configs only (not recommended: keeps stale pre-2008 EDVs)"
        ),
    )
    parser.add_argument(
        "--aktive-min-season",
        metavar="YYYY-YY",
        default=None,
        help=(
            "Only import Aktive Mitglieder from this season onward "
            f'(default: {DEFAULT_AKTIVE_MIN_SEASON})'
        ),
    )
    parser.add_argument(
        "--all-aktive-seasons",
        action="store_true",
        help="Import every Aktive season including 2004–07 (legacy 6-digit EDVs)",
    )
    args = parser.parse_args()

    if args.all_aktive_seasons and args.aktive_min_season:
        parser.error("use only one of --all-aktive-seasons or --aktive-min-season")

    summary = build_and_publish_players_registry(
        write_csv=args.write_csv,
        from_scratch=not args.merge_existing_registry,
        aktive_min_season="" if args.all_aktive_seasons else args.aktive_min_season,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
