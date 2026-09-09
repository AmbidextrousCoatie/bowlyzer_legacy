#!/usr/bin/env python3
"""
Prepare inputs and run a clean full publish from primary league + tournament sources.

League stack (no overlapping seasons between inputs):
  1. legacy scrape CSV       — 08/09 … 18/19
  2. historical Excel CSV    — 19/20 … 24/25  (built from ``--historical-source``)
  3. GF pipeline ``latest``  — current season (default 25/26)

Do **not** pass ``--extra-league`` for the same season that GF already carries; that
was the root cause of inflated match counts / points.

Tournaments: GF combined export + manual/PDF imports (same as ``build_published_dataset``).

Usage:
  uv run python scripts/rebuild_published_from_scratch.py --dry-run
  uv run python scripts/rebuild_published_from_scratch.py --write-csv
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import (
    REPO_WORK_DIR,
    get_published_csv_dir,
    get_work_data_dir,
    gf_tournaments_combined_postprocessed_csv,
    historical_league_results_csv,
    legacy_scrape_league_csv,
    manual_tournament_postprocessed_csv,
    pipeline_gf_league_csv,
    _csv_looks_populated,
)

CSV_SEP = ";"
LEGACY_SCRAPE_SEASONS = {f"{y:02d}/{y+1:02d}" for y in range(8, 19)}  # 08/09 … 18/19
HISTORICAL_EXCEL_SEASONS = {f"{y:02d}/{y+1:02d}" for y in range(19, 25)}  # 19/20 … 24/25


def _read_league_csv(path: Path):
    import pandas as pd

    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, sep=CSV_SEP, dtype=str, keep_default_na=False)


def _league_column(df) -> str:
    if "League" in df.columns:
        return "League"
    if "Event" in df.columns:
        return "Event"
    raise ValueError(f"No League/Event column in {list(df.columns)}")


def prepare_historical_excel_base(
    source: Path,
    out_path: Path,
    *,
    first_season: str = "19/20",
    last_season: str = "24/25",
) -> dict:
    """
    Write flat league CSV containing only Excel-era seasons (default 19/20–24/25).

    Uses ``database/published_csv/league_results_merged.csv`` by default when the
    dedicated work extract is missing or only contains the current season.
    """
    import pandas as pd

    df = _read_league_csv(source)
    league_col = _league_column(df)

    if league_col == "Event":
        df = df.copy()
        if "League" not in df.columns:
            df["League"] = df["Event"]
        drop_cols = [c for c in ("Event", "Event Type", "Club") if c in df.columns]
        df = df.drop(columns=drop_cols, errors="ignore")

    seasons = df["Season"].astype(str).str.strip()
    mask = (seasons >= first_season) & (seasons <= last_season)
    hist = df.loc[mask].copy()
    if hist.empty:
        raise ValueError(
            f"No rows for seasons {first_season}–{last_season} in {source}. "
            "Point --historical-source at a full Excel extract or published CSV."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    hist.to_csv(out_path, sep=CSV_SEP, index=False)
    season_counts = hist["Season"].value_counts().sort_index()
    return {
        "source": str(source.resolve()),
        "output": str(out_path.resolve()),
        "rows": int(len(hist)),
        "seasons": season_counts.to_dict(),
    }


def _check_inputs(
    legacy: Path,
    historical: Path,
    gf_league: Path,
    gf_tournaments: Path,
    manual_tournaments: Path,
) -> list[str]:
    issues: list[str] = []
    if not legacy.is_file():
        issues.append(f"legacy scrape missing: {legacy}")
    if not historical.is_file():
        issues.append(f"historical base missing: {historical}")
    if not gf_league.is_file():
        issues.append(f"GF league missing: {gf_league}")
    if not _csv_looks_populated(gf_tournaments) and not _csv_looks_populated(manual_tournaments):
        issues.append(
            "no populated tournament inputs found "
            f"(GF={gf_tournaments}, manual={manual_tournaments}). "
            f"Copy real CSVs into {get_work_data_dir()} or keep them under {REPO_WORK_DIR}."
        )
    elif not _csv_looks_populated(gf_tournaments):
        print(f"Warning: GF tournaments empty/missing, using manual only: {manual_tournaments}")
    elif not _csv_looks_populated(manual_tournaments):
        print(f"Warning: manual tournaments empty/missing, using GF only: {gf_tournaments}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--historical-source",
        type=Path,
        default=None,
        help=(
            "Full league CSV/Parquet to slice 19/20–24/25 from "
            "(default: database/published_csv/league_results_merged.csv, "
            "else database/work/league/historical_league_results.csv if it spans those seasons)"
        ),
    )
    parser.add_argument(
        "--historical-out",
        type=Path,
        default=None,
        help="Output path for sliced historical CSV (default: work/league/historical_excel_19_24.csv)",
    )
    parser.add_argument(
        "--legacy-scrape",
        type=Path,
        default=None,
        help=f"Legacy scrape CSV (default: {legacy_scrape_league_csv()})",
    )
    parser.add_argument(
        "--gf-league",
        type=Path,
        default=None,
        help=f"GF pipeline league CSV (default: {pipeline_gf_league_csv()})",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Pass --write-csv through to build_published_dataset.py",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare historical slice and print the publish command only",
    )
    parser.add_argument(
        "--skip-female-league-audit",
        action="store_true",
        help="Forward to build_published_dataset.py",
    )
    parser.add_argument(
        "publish_extra_args",
        nargs="*",
        help="Extra args forwarded to build_published_dataset.py (e.g. --force-publish)",
    )
    args = parser.parse_args()

    work_dir = get_work_data_dir()
    historical_out = (args.historical_out or work_dir / "league" / "historical_excel_19_24.csv").resolve()
    legacy = (args.legacy_scrape or legacy_scrape_league_csv()).resolve()
    gf_league = (args.gf_league or pipeline_gf_league_csv()).resolve()
    gf_tournaments = gf_tournaments_combined_postprocessed_csv().resolve()
    manual_tournaments = manual_tournament_postprocessed_csv().resolve()

    historical_source = args.historical_source
    if historical_source is None:
        published = (get_published_csv_dir() / "league_results_merged.csv").resolve()
        work_hist = historical_league_results_csv().resolve()
        if published.is_file():
            historical_source = published
        elif work_hist.is_file():
            historical_source = work_hist
        else:
            print("Error: no --historical-source and no published/work historical file found.", file=sys.stderr)
            return 2
    historical_source = historical_source.resolve()

    print("==> clean rebuild plan")
    print(f"  legacy scrape:     {legacy}")
    print(f"  historical slice:  {historical_out}  <- from {historical_source}")
    print(f"  GF league (last):  {gf_league}")
    print(f"  GF tournaments:    {gf_tournaments}  ({'ok' if _csv_looks_populated(gf_tournaments) else 'EMPTY'})")
    print(
        f"  manual tournaments:{manual_tournaments}  "
        f"({'ok' if _csv_looks_populated(manual_tournaments) else 'EMPTY'})"
    )
    print(f"  seasons:           legacy {min(LEGACY_SCRAPE_SEASONS)}…{max(LEGACY_SCRAPE_SEASONS)}")
    print(f"                     historical {min(HISTORICAL_EXCEL_SEASONS)}…{max(HISTORICAL_EXCEL_SEASONS)}")
    print("                     GF = current season (wins on conflicts)")
    print("  NOTE: do not add --extra-league for the same season GF already contains.")
    print("  Set BOWLYZER_WORK_DATA_DIR if legacy scrape lives outside database/work/")
    print(f"        (e.g. C:\\tmp\\bowlyzer\\data). Current work dir: {work_dir}")

    try:
        hist_summary = prepare_historical_excel_base(historical_source, historical_out)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"==> historical slice: {hist_summary['rows']:,} rows")
    for season, count in sorted(hist_summary["seasons"].items()):
        print(f"    {season}: {count:,}")

    issues = _check_inputs(legacy, historical_out, gf_league, gf_tournaments, manual_tournaments)
    if issues:
        for line in issues:
            print(f"Error: {line}", file=sys.stderr)
        return 2

    publish_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "build_published_dataset.py"),
        "--job",
        "league,tournament",
        "--historical",
        str(historical_out),
        "--gf-league",
        str(gf_league),
        "--gf-tournaments",
        str(gf_tournaments),
        "--manual-tournaments",
        str(manual_tournaments),
    ]
    if args.write_csv:
        publish_cmd.append("--write-csv")
    if args.skip_female_league_audit:
        publish_cmd.append("--skip-female-league-audit")
    publish_cmd.extend(args.publish_extra_args)

    print("==> publish command:")
    print(" ".join(publish_cmd))

    if args.dry_run:
        return 0

    print("==> running publish …")
    completed = subprocess.run(publish_cmd, cwd=str(REPO_ROOT))
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
