#!/usr/bin/env python3
"""
Publish ``tournaments_postprocessed.parquet`` from GF regional + manual club CSVs.

Minimal entry point for VPS clubmeisterschaft auto-import (no ``scripts.*`` deps).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.competition_schema import apply_tournament_competition_schema_v2
from data_access.parquet_sidecar import publish_dataframe

CSV_SEP = ";"
CSV_READ_KW = {"sep": CSV_SEP, "dtype": str, "low_memory": False}


def merge_tournament_sources(
    input_paths: list[Path],
    out_path: Path,
    *,
    write_csv: bool = False,
    normalize: bool = True,
) -> dict[str, Any]:
    if not input_paths:
        raise FileNotFoundError("No tournament input files found.")

    frames = []
    norm_stats_total: dict[str, Any] = {
        "club_cells_normalized": 0,
        "player_id_rows_changed": 0,
        "registry_rows_changed": 0,
    }
    for path in input_paths:
        frame = pd.read_csv(path, **CSV_READ_KW)
        if normalize and not frame.empty:
            from data_access.tournament_data_normalization import (
                format_tournament_normalization_summary,
                normalize_tournament_dataframe,
            )

            frame, batch_stats = normalize_tournament_dataframe(frame)
            for key in ("club_cells_normalized", "player_id_rows_changed", "registry_rows_changed"):
                norm_stats_total[key] = int(norm_stats_total.get(key, 0)) + int(batch_stats.get(key) or 0)
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.columns.duplicated().any():
        combined = combined.loc[:, ~combined.columns.duplicated()].copy()

    combined = apply_tournament_competition_schema_v2(combined)
    published = publish_dataframe(combined, out_path, write_csv=write_csv, sep=CSV_SEP)

    result = {
        "inputs": [str(p) for p in input_paths],
        "rows": int(len(combined)),
        "output": str(out_path.resolve()),
        "parquet_output": str(published["parquet"]),
        "csv_output": str(published["csv"]) if published.get("csv") else "",
        "normalization": norm_stats_total if normalize else None,
    }
    if normalize:
        from data_access.tournament_data_normalization import format_tournament_normalization_summary

        print(format_tournament_normalization_summary(norm_stats_total))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gf-tournaments", type=Path, required=True)
    parser.add_argument("--manual-tournaments", type=Path, required=True)
    parser.add_argument("--tournaments-out", type=Path, required=True)
    parser.add_argument("--write-csv", action="store_true")
    args = parser.parse_args()

    inputs = [p.resolve() for p in (args.gf_tournaments, args.manual_tournaments) if p.is_file()]
    if not inputs:
        raise FileNotFoundError("No tournament input CSVs found.")

    summary = merge_tournament_sources(
        inputs,
        args.tournaments_out.resolve(),
        write_csv=args.write_csv,
    )
    print(f"Published {summary['rows']} rows -> {summary['parquet_output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
