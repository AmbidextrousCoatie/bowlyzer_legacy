#!/usr/bin/env python3
"""Validate merged league standings against Excel reference tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import analysis_log_path, get_work_data_dir
from data_access.league_standings_validation import (
    LEAGUE_STANDINGS_VALIDATION_CSV,
    audit_league_standings,
    format_comparison_report,
    write_comparison_report,
)
from data_access.parquet_sidecar import data_file_exists, resolve_load_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "league_data",
        nargs="?",
        type=Path,
        help="Merged league CSV or Parquet (default: work dir league_results_merged)",
    )
    parser.add_argument(
        "--analysis-log",
        type=Path,
        default=None,
        help="extract_excel_analysis_log.json (default: work dir)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"Output CSV (default: work dir / {LEAGUE_STANDINGS_VALIDATION_CSV})",
    )
    parser.add_argument("--league", action="append", default=[], help="Limit to league id (repeatable)")
    parser.add_argument("--season", action="append", default=[], help="Limit to season label (repeatable)")
    parser.add_argument("--limit", type=int, default=None, help="Max league×season comparisons")
    parser.add_argument(
        "--fail-on-red",
        action="store_true",
        help="Exit 1 when any comparison is red",
    )
    return parser.parse_args()


def _load_league_data(path: Path):
    import pandas as pd

    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def main() -> int:
    args = _parse_args()
    work_dir = get_work_data_dir()
    league_path = args.league_data
    if league_path is None:
        from database.paths import league_results_merged_csv

        league_path = league_results_merged_csv()
    if not data_file_exists(league_path):
        print(f"Error: league data not found: {league_path}", file=sys.stderr)
        return 2

    analysis_log = args.analysis_log or analysis_log_path()
    if not analysis_log.is_file():
        print(f"Error: analysis log not found: {analysis_log}", file=sys.stderr)
        return 2

    report_path = args.report or (work_dir / LEAGUE_STANDINGS_VALIDATION_CSV)
    df = _load_league_data(league_path)
    comparisons = audit_league_standings(
        df,
        analysis_log_path=analysis_log,
        leagues=args.league or None,
        seasons=args.season or None,
        limit=args.limit,
    )
    write_comparison_report(comparisons, report_path)
    print(format_comparison_report(comparisons, data_path=Path(league_path)))
    print(f"Report: {report_path.resolve()}")

    if args.fail_on_red and any(item.status == "red" for item in comparisons):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
