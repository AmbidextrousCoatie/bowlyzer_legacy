#!/usr/bin/env python3
"""Summarize weeks and teams per league/season in a legacy scrape extract CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import legacy_scrape_dir

DEFAULT_CSV = legacy_scrape_dir() / "legacy_scrape_extracted.csv"
ALT_CSV = legacy_scrape_dir() / "legacy_scrap_extracxted.csv"


def resolve_csv(path: str | None) -> Path:
    if path:
        return Path(path)
    if DEFAULT_CSV.is_file():
        return DEFAULT_CSV
    if ALT_CSV.is_file():
        return ALT_CSV
    raise FileNotFoundError(f"No CSV at {DEFAULT_CSV} or {ALT_CSV}")


def _sorted_team_names(series: pd.Series) -> list[str]:
    names = sorted({str(x).strip() for x in series if str(x).strip()}, key=str.casefold)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="Path to legacy scrape extract CSV")
    parser.add_argument("--export", default=None, help="Optional path to write summary CSV")
    parser.add_argument(
        "--high-teams-threshold",
        type=int,
        default=10,
        help="Print all team names when a league/season has more than this many teams (default: 12).",
    )
    args = parser.parse_args()

    csv_path = resolve_csv(args.csv)
    df = pd.read_csv(
        csv_path,
        sep=";",
        dtype=str,
        usecols=["Season", "League", "Week", "Team", "Position", "Player"],
    )
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str).str.strip()

    team_rows = df[(df["Position"] == "0") & (df["Player"].str.lower() == "team total")]

    high_threshold = max(1, int(args.high_teams_threshold))

    summary = (
        team_rows.groupby(["Season", "League"], dropna=False)
        .agg(
            weeks=("Week", lambda s: sorted({x for x in s if x}, key=lambda w: int(w) if w.isdigit() else w)),
            teams=("Team", "nunique"),
            team_names=("Team", _sorted_team_names),
        )
        .reset_index()
    )
    summary["week_count"] = summary["weeks"].apply(len)
    summary["weeks_list"] = summary["weeks"].apply(lambda ws: ",".join(ws))

    def flag_row(row: pd.Series) -> str:
        notes: list[str] = []
        if row["week_count"] < 6:
            notes.append("LOW_WEEKS")
        if row["teams"] < 5:
            notes.append("LOW_TEAMS")
        if row["teams"] > high_threshold:
            notes.append("HIGH_TEAMS")
        return " ".join(notes)

    summary["note"] = summary.apply(flag_row, axis=1)
    out = summary[["Season", "League", "week_count", "teams", "weeks_list", "note"]].sort_values(
        ["Season", "League"]
    )

    print(f"File: {csv_path}")
    print(f"Rows (all): {len(df):,}  |  team-total rows: {len(team_rows):,}")
    print(f"League × season combos: {len(out)}  |  flagged: {(out['note'] != '').sum()}\n")

    high_team_rows = summary[summary["teams"] > high_threshold].sort_values(["Season", "League"])
    if not high_team_rows.empty:
        print(f"--- High team count (>{high_threshold}) — all detected teams ---")
        for row in high_team_rows.itertuples(index=False):
            names = list(row.team_names) if isinstance(row.team_names, list) else []
            print(f"\n{row.Season} | {row.League} | {row.teams} teams | {row.note or 'HIGH_TEAMS'}")
            for index, name in enumerate(names, start=1):
                print(f"  {index:2}. {name}")
        print()

    for season, grp in out.groupby("Season", sort=True):
        print(f"--- {season} ({len(grp)} leagues) ---")
        display = grp[["League", "week_count", "teams", "note"]].copy()
        display.columns = ["League", "Wks", "Teams", "Note"]
        print(display.to_string(index=False))
        print()

    print("--- Season rollup ---")
    rollup = (
        out.groupby("Season")
        .agg(
            leagues=("League", "count"),
            min_weeks=("week_count", "min"),
            max_weeks=("week_count", "max"),
            avg_teams=("teams", "mean"),
        )
        .reset_index()
    )
    print(rollup.to_string(index=False))

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(export_path, sep=";", index=False)
        print(f"\nWrote {export_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
