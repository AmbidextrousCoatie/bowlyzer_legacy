#!/usr/bin/env python3
"""Build ``clubs_registry.parquet`` from published league merge output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.clubs_registry import build_and_publish_clubs_registry, format_registry_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "league_data",
        nargs="?",
        type=Path,
        help="League CSV/Parquet (default: published league_results_merged)",
    )
    parser.add_argument("--write-csv", action="store_true", help="Also write clubs_registry.csv")
    args = parser.parse_args()

    league_df = None
    if args.league_data is not None:
        from data_access.parquet_sidecar import resolve_load_path

        load_path = resolve_load_path(args.league_data.resolve())
        if load_path.suffix.lower() == ".parquet":
            import pandas as pd

            league_df = pd.read_parquet(load_path)
        else:
            import pandas as pd

            league_df = pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)

    summary = build_and_publish_clubs_registry(league_df, write_csv=args.write_csv)
    print(format_registry_summary(summary))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
