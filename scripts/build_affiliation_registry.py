#!/usr/bin/env python3
"""Build affiliation index + Verein registry from *Aktive Mitglieder* workbooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.affiliation_registry import (
    build_and_publish_affiliation_registry,
    format_affiliation_build_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-csv", action="store_true", help="Also write CSV sidecars")
    parser.add_argument(
        "--aktive-min-season",
        metavar="YYYY-YY",
        default="",
        help=(
            "Optional floor (folder slug YYYY-YY). Default: all seasons "
            "(required for pre-08/09 tournament club resolution)."
        ),
    )
    args = parser.parse_args()

    summary = build_and_publish_affiliation_registry(
        write_csv=args.write_csv,
        min_season=args.aktive_min_season,
    )
    print(format_affiliation_build_summary(summary))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
