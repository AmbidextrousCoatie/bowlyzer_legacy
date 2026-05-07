#!/usr/bin/env python3
"""
Analyze persistent extractor analysis log for week coverage.

Outputs:
1) available_weeks_by_league_season.csv
2) missing_weeks_by_league_season.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd


def parse_weeks(raw_value) -> Set[int]:
    """Parse comma-separated week values into int set."""
    if raw_value is None:
        return set()
    weeks = set()
    for token in str(raw_value).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
            if value > 0:
                weeks.add(value)
        except ValueError:
            continue
    return weeks


def load_analysis_rows(log_path: Path) -> List[dict]:
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    files_map = payload.get("files", {})
    rows: List[dict] = []
    for file_entry in files_map.values():
        analysis_result = file_entry.get("analysis_result") or {}
        if isinstance(analysis_result, dict):
            rows.append(analysis_result)
    return rows


def build_tables(rows: List[dict]) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], List[str]]:
    grouped: Dict[Tuple[str, str], Dict[str, object]] = {}

    for row in rows:
        league = str(row.get("league") or "").strip()
        season = str(row.get("season") or "").strip()
        if not league or not season:
            continue

        key = (season, league)
        if key not in grouped:
            grouped[key] = {
                "available_weeks": set(),
                "week_count_hints": [],
                "files": set(),
            }

        grouped[key]["available_weeks"].update(parse_weeks(row.get("available_weeks")))

        number_of_weeks = row.get("number_of_weeks")
        try:
            if number_of_weeks is not None and str(number_of_weeks).strip() != "":
                num = int(number_of_weeks)
                if num > 0:
                    grouped[key]["week_count_hints"].append(num)
        except (ValueError, TypeError):
            pass

        grouped[key]["files"].add(str(row.get("file") or ""))

    seasons = sorted({season for season, _ in grouped.keys()})
    leagues = sorted({league for _, league in grouped.keys()})

    available_records: List[dict] = []
    missing_records: List[dict] = []

    for (season, league), info in sorted(grouped.items()):
        available_weeks = sorted(info["available_weeks"])
        week_count_hints = info["week_count_hints"]
        expected_weeks_count = max(week_count_hints) if week_count_hints else 6
        expected_weeks = set(range(1, expected_weeks_count + 1))
        missing_weeks = sorted(expected_weeks - set(available_weeks))

        available_records.append(
            {
                "season": season,
                "league": league,
                "expected_weeks_count": expected_weeks_count,
                "available_weeks": ",".join(str(w) for w in available_weeks),
                "available_week_count": len(available_weeks),
                "file_count": len(info["files"]),
            }
        )
        missing_records.append(
            {
                "season": season,
                "league": league,
                "expected_weeks_count": expected_weeks_count,
                "missing_weeks": ",".join(str(w) for w in missing_weeks),
                "missing_week_count": len(missing_weeks),
            }
        )

    available_df = pd.DataFrame(available_records)
    missing_df = pd.DataFrame(missing_records)
    return available_df, missing_df, seasons, leagues


def main():
    parser = argparse.ArgumentParser(description="Analyze missing league weeks from extract analysis log.")
    parser.add_argument(
        "--log",
        default="database/data/extract_excel_analysis_log.json",
        help="Path to extract analysis log JSON.",
    )
    parser.add_argument(
        "--outdir",
        default="database/data",
        help="Directory to write output CSV tables.",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.is_file():
        raise FileNotFoundError(f"Analysis log not found: {log_path}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = load_analysis_rows(log_path)
    available_df, missing_df, seasons, leagues = build_tables(rows)

    available_out = outdir / "available_weeks_by_league_season.csv"
    missing_out = outdir / "missing_weeks_by_league_season.csv"
    available_df.to_csv(available_out, index=False, sep=";")
    missing_df.to_csv(missing_out, index=False, sep=";")

    # Alternative matrix output: rows=league, cols=season, cell=weeks string
    available_matrix_df = (
        available_df.pivot(index="league", columns="season", values="available_weeks")
        .fillna("")
        .sort_index(axis=0)
        .sort_index(axis=1)
    )
    missing_matrix_df = (
        missing_df.pivot(index="league", columns="season", values="missing_weeks")
        .fillna("")
        .sort_index(axis=0)
        .sort_index(axis=1)
    )

    available_matrix_out = outdir / "available_weeks_matrix.csv"
    missing_matrix_out = outdir / "missing_weeks_matrix.csv"
    available_matrix_df.to_csv(available_matrix_out, sep=";")
    missing_matrix_df.to_csv(missing_matrix_out, sep=";")

    # Combined matrix:
    # [league] + ["Available league weeks"] + [available season columns]
    #        + ["Missing league weeks"] + [missing season columns]
    available_cols = list(available_matrix_df.columns)
    missing_cols = list(missing_matrix_df.columns)
    all_leagues = sorted(set(available_matrix_df.index).union(set(missing_matrix_df.index)))

    available_section = available_matrix_df.reindex(index=all_leagues, columns=available_cols, fill_value="")
    missing_section = missing_matrix_df.reindex(index=all_leagues, columns=missing_cols, fill_value="")

    combined_df = pd.DataFrame(index=all_leagues)
    combined_df["Available league weeks"] = ""
    for col in available_cols:
        combined_df[str(col)] = available_section[col]
    combined_df["Missing league weeks"] = ""
    for col in missing_cols:
        out_col = str(col)
        if out_col in combined_df.columns:
            out_col = f"{out_col}_missing"
        combined_df[out_col] = missing_section[col]

    combined_out = outdir / "league_weeks_combined_matrix.csv"
    combined_df.to_csv(combined_out, sep=";", index_label="league")

    print(f"Unique seasons ({len(seasons)}): {', '.join(seasons)}")
    print(f"Unique leagues ({len(leagues)}): {', '.join(leagues)}")
    print(f"Available weeks table: {available_out}")
    print(f"Missing weeks table: {missing_out}")
    print(f"Available weeks matrix (league x season): {available_matrix_out}")
    print(f"Missing weeks matrix (league x season): {missing_matrix_out}")
    print(f"Combined matrix (available + missing): {combined_out}")


if __name__ == "__main__":
    main()
