#!/usr/bin/env python3
"""Audit tournament player/club data quality (one row per season × event)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import get_work_data_dir, tournaments_postprocessed_csv
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from data_access.tournament_data_quality import (
    TOURNAMENT_DATA_QUALITY_CSV,
    audit_tournament_data_quality,
    format_quality_report,
    write_quality_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tournament_data",
        nargs="?",
        type=Path,
        help="Tournament CSV or Parquet (default: published tournaments_postprocessed)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"Output CSV (default: work dir / {TOURNAMENT_DATA_QUALITY_CSV})",
    )
    parser.add_argument("--season", action="append", default=[], help="Limit to season (repeatable)")
    parser.add_argument("--event", action="append", default=[], help="Limit to event name (repeatable)")
    parser.add_argument(
        "--fail-on-red",
        action="store_true",
        help="Exit 1 when any event is red",
    )
    return parser.parse_args()


def _load_tournament_data(path: Path):
    import pandas as pd

    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def main() -> int:
    args = _parse_args()
    tournament_path = args.tournament_data or tournaments_postprocessed_csv()
    if not data_file_exists(tournament_path):
        print(f"Error: tournament data not found: {tournament_path}", file=sys.stderr)
        return 2

    report_path = args.report or (get_work_data_dir() / TOURNAMENT_DATA_QUALITY_CSV)
    df = _load_tournament_data(tournament_path)
    rows = audit_tournament_data_quality(
        df,
        seasons=args.season or None,
        events=args.event or None,
    )
    write_quality_report(rows, report_path)
    print(format_quality_report(rows, data_path=Path(tournament_path)))
    print(f"Report: {report_path.resolve()}")

    if args.fail_on_red and any(item.status == "red" for item in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
