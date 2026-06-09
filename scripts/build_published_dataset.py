#!/usr/bin/env python3
"""
Build published Bowl-A-Lyzer datasets (Parquet by default) from historical Excel extract,
GF pipeline, and tournaments.

By default **does not** include legacy web-scrape data. Add ``--with-legacy-scrape`` or
``--extra-league PATH`` (repeatable) to merge more sources (later inputs win on duplicates;
GF pipeline is always last among the built-in sources).

Outputs (under ``BOWLYZER_DATA_DIR`` / ``database/data`` by default):
  - ``league_results_merged.csv``  — historical + GF pipeline league (deduped)
  - ``tournaments_postprocessed.csv`` — GF regional tournaments + manual imports

Intermediate / duplicate reports go to ``BOWLYZER_WORK_DATA_DIR`` (e.g. ``C:\\tmp\\bowlyzer\\data``).

Usage:
  uv run python scripts/build_published_dataset.py
  uv run python scripts/build_published_dataset.py --dry-run
  uv run python scripts/build_published_dataset.py --with-player-hybrid
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import (
    get_data_dir,
    get_work_data_dir,
    gf_tournaments_combined_postprocessed_csv,
    historical_league_results_csv,
    league_results_merged_csv,
    legacy_scrape_league_csv,
    manual_tournament_postprocessed_csv,
    pipeline_gf_league_csv,
    player_stats_merged_hybrid_csv,
    tournaments_postprocessed_csv,
)
from scripts.audit_female_league_split import audit_league_csv, format_issue_report
from scripts.audit_player_id_names import audit_player_id_names, format_summary, write_conflict_report
from scripts.merge_league_sources import CSV_SEP, DEFAULT_KEYS, merge_sources

PLAYER_ID_NAME_CONFLICTS_CSV = "player_id_name_conflicts.csv"

CSV_READ_KW = {"sep": CSV_SEP, "dtype": str, "low_memory": False}


def _existing(paths: List[Path]) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        if p.is_file():
            out.append(p.resolve())
        else:
            print(f"  skip (missing): {p}")
    return out


def _dedupe_paths(paths: List[Path]) -> List[Path]:
    seen: set[Path] = set()
    out: List[Path] = []
    for p in paths:
        resolved = p.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def build_league_input_paths(
    *,
    historical: Path,
    gf_league: Path,
    extra_league: List[Path],
    with_legacy_scrape: bool,
) -> List[Path]:
    """
    Ordered league merge inputs (low -> high priority on duplicate keys).

    Built-in order: historical, optional extras / legacy scrape, GF pipeline (wins).
    """
    ordered: List[Path] = [historical]
    if with_legacy_scrape:
        ordered.append(legacy_scrape_league_csv())
    ordered.extend(extra_league)
    ordered.append(gf_league)
    return _dedupe_paths(ordered)


def merge_tournament_sources(
    input_paths: List[Path],
    out_path: Path,
    *,
    write_csv: bool = False,
) -> Dict[str, Any]:
    """Concatenate tournament postprocessed CSVs (union of columns)."""
    if not input_paths:
        raise FileNotFoundError("No tournament input files found.")

    frames = [pd.read_csv(p, **CSV_READ_KW) for p in input_paths]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.columns.duplicated().any():
        combined = combined.loc[:, ~combined.columns.duplicated()].copy()

    from data_access.parquet_sidecar import publish_dataframe

    published = publish_dataframe(combined, out_path, write_csv=write_csv, sep=CSV_SEP)

    return {
        "inputs": [str(p) for p in input_paths],
        "rows": int(len(combined)),
        "output": str(out_path.resolve()),
        "parquet_output": str(published["parquet"]),
        "csv_output": str(published["csv"]) if published.get("csv") else "",
    }


def build_player_hybrid(
    league_csv: Path,
    tournament_csv: Path,
    out_path: Path,
    *,
    write_csv: bool = False,
) -> Dict[str, Any]:
    """League rows + tournament rows in one file (legacy Spieler source)."""
    import csv

    from data_access.dtype_normalization import dataframe_to_str_dict_records
    from data_access.parquet_sidecar import data_file_exists, publish_dataframe
    from data_access.shared_pandas_store import get_dataframe

    league_rows = dataframe_to_str_dict_records(get_dataframe(league_csv))

    tournament_rows: List[Dict[str, str]] = []
    if data_file_exists(tournament_csv):
        tournament_rows = dataframe_to_str_dict_records(get_dataframe(tournament_csv))

    headers = sorted({k for r in (league_rows + tournament_rows) for k in r.keys()})
    if not headers:
        from database.conversion.bowlingbayern_legacy_core import OUTPUT_HEADERS

        headers = list(OUTPUT_HEADERS)

    out_rows: List[Dict[str, str]] = []
    for row in league_rows:
        merged = {h: str(row.get(h, "")) for h in headers}
        if not str(merged.get("Event Type", "")).strip():
            merged["Event Type"] = "league"
        if not str(merged.get("Event Name", "")).strip():
            merged["Event Name"] = str(merged.get("League", "")).strip()
        if not str(merged.get("Club", "")).strip():
            merged["Club"] = str(merged.get("Team", "")).strip()
        out_rows.append(merged)

    for row in tournament_rows:
        merged = {h: str(row.get(h, "")) for h in headers}
        merged["Input Data"] = "True"
        merged["Computed Data"] = "False"
        out_rows.append(merged)

    hybrid_df = pd.DataFrame(out_rows)
    from data_access.player_id_name_normalization import (
        apply_player_id_name_normalization,
        format_normalization_summary as format_player_id_normalization_summary,
    )
    from data_access.player_name_normalization_config import (
        apply_player_name_normalization,
        format_normalization_summary as format_player_name_normalization_summary,
    )

    hybrid_df, player_id_stats = apply_player_id_name_normalization(hybrid_df)
    if player_id_stats:
        print(format_player_id_normalization_summary(player_id_stats))
    hybrid_df, player_name_stats = apply_player_name_normalization(hybrid_df)
    if player_name_stats:
        print(format_player_name_normalization_summary(player_name_stats))

    published = publish_dataframe(hybrid_df, out_path, write_csv=write_csv, sep=CSV_SEP)
    if write_csv:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=CSV_SEP, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(out_rows)

    return {
        "league_rows": len(league_rows),
        "tournament_rows": len(tournament_rows),
        "output_rows": len(out_rows),
        "output": str(out_path.resolve()),
        "parquet_output": str(published["parquet"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--historical",
        type=Path,
        default=None,
        help=f"Historical league CSV (default: {historical_league_results_csv()})",
    )
    parser.add_argument(
        "--gf-league",
        type=Path,
        default=None,
        help=f"GF pipeline league CSV (default: {pipeline_gf_league_csv()})",
    )
    parser.add_argument(
        "--gf-tournaments",
        type=Path,
        default=None,
        help=f"GF combined tournaments CSV (default: {gf_tournaments_combined_postprocessed_csv()})",
    )
    parser.add_argument(
        "--manual-tournaments",
        type=Path,
        default=None,
        help=f"Manual tournament CSV (default: {manual_tournament_postprocessed_csv()})",
    )
    parser.add_argument(
        "--league-out",
        type=Path,
        default=None,
        help=f"Merged league output (default: {league_results_merged_csv()})",
    )
    parser.add_argument(
        "--tournaments-out",
        type=Path,
        default=None,
        help=f"Merged tournaments output (default: {tournaments_postprocessed_csv()})",
    )
    parser.add_argument(
        "--with-player-hybrid",
        action="store_true",
        help="Also write player_stats_merged_plus_tournaments.csv (league copy + tournaments).",
    )
    parser.add_argument(
        "--league-only",
        action="store_true",
        help="Only merge league sources; skip tournaments.",
    )
    parser.add_argument(
        "--tournaments-only",
        action="store_true",
        help="Only merge tournament sources; skip league.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved paths and exit without writing.",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Also write large CSV exports alongside Parquet (default: Parquet only).",
    )
    parser.add_argument(
        "--extra-league",
        type=Path,
        action="append",
        default=[],
        metavar="CSV",
        help=(
            "Additional league CSV to merge (repeatable). Inserted after historical and "
            "before GF; later files win on duplicate keys."
        ),
    )
    parser.add_argument(
        "--with-legacy-scrape",
        action="store_true",
        help=(
            "Include legacy_scrape_extracted.csv from the work dir "
            f"(default path: {legacy_scrape_league_csv()})."
        ),
    )
    parser.add_argument(
        "--skip-female-league-audit",
        action="store_true",
        help="Do not fail when legacy/extra league CSVs collapse Damen into male league ids.",
    )
    parser.add_argument(
        "--skip-player-id-name-audit",
        action="store_true",
        help="Skip player name / Player ID conflict report (player_id_name_conflicts.csv).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars during team-name normalization (merge step)",
    )
    args = parser.parse_args()

    historical = (args.historical or historical_league_results_csv()).resolve()
    gf_league = (args.gf_league or pipeline_gf_league_csv()).resolve()
    gf_tournaments = (args.gf_tournaments or gf_tournaments_combined_postprocessed_csv()).resolve()
    manual_tournaments = (args.manual_tournaments or manual_tournament_postprocessed_csv()).resolve()
    league_out = (args.league_out or league_results_merged_csv()).resolve()
    tournaments_out = (args.tournaments_out or tournaments_postprocessed_csv()).resolve()

    print(f"Data dir (published outputs): {get_data_dir()}")
    print(f"Work dir (inputs + reports):  {get_work_data_dir()}")
    print()
    league_input_candidates = build_league_input_paths(
        historical=historical,
        gf_league=gf_league,
        extra_league=list(args.extra_league),
        with_legacy_scrape=args.with_legacy_scrape,
    )
    print("League merge (low -> high priority on duplicate keys; GF pipeline last):")
    for idx, path in enumerate(league_input_candidates):
        print(f"  [{idx}] {path}")
    league_inputs = _existing(league_input_candidates)
    print(f"  output:         {league_out}")
    print()
    print("Tournament merge:")
    print(f"  gf tournaments: {gf_tournaments}")
    print(f"  manual:         {manual_tournaments}")
    tournament_inputs = _existing([gf_tournaments, manual_tournaments])
    print(f"  output:         {tournaments_out}")
    if args.with_player_hybrid:
        print()
        print("Player hybrid:")
        print(f"  output:         {player_stats_merged_hybrid_csv().resolve()}")

    if args.dry_run:
        return 0

    summary: Dict[str, Any] = {"paths": {"data_dir": str(get_data_dir()), "work_dir": str(get_work_data_dir())}}
    player_id_audit_paths: List[Path] = []

    if not args.skip_female_league_audit:
        audit_paths = [
            p
            for p in league_inputs
            if p.name == legacy_scrape_league_csv().name or p in list(args.extra_league)
        ]
        for audit_path in audit_paths:
            issues = audit_league_csv(audit_path, sep=CSV_SEP)
            if issues:
                print(format_issue_report(issues, csv_path=audit_path), file=sys.stderr)
                print(
                    "Error: female league rows appear merged into male ids (e.g. BayL + BayL (D)). "
                    "Re-run legacy scrape extract/process, or pass --skip-female-league-audit to override.",
                    file=sys.stderr,
                )
                return 2

    if not args.tournaments_only:
        if len(league_inputs) < 2:
            print(
                "Error: need at least two league input files after resolving paths. "
                "Provide historical + GF and/or --extra-league / --with-legacy-scrape.",
                file=sys.stderr,
            )
            return 2
        print("==> merging league sources …")
        summary["league"] = merge_sources(
            input_paths=league_inputs,
            out_path=league_out,
            key_names=list(DEFAULT_KEYS),
            write_csv=args.write_csv,
            show_progress=not args.no_progress,
        )
        player_id_audit_paths.append(league_out)

    if not args.league_only:
        if not tournament_inputs:
            print("Error: no tournament input files found.", file=sys.stderr)
            return 2
        print("==> merging tournament sources …")
        summary["tournaments"] = merge_tournament_sources(
            tournament_inputs,
            tournaments_out,
            write_csv=args.write_csv,
        )

    if args.with_player_hybrid:
        from data_access.parquet_sidecar import data_file_exists

        if not data_file_exists(league_out):
            print("Error: league output missing; cannot build player hybrid.", file=sys.stderr)
            return 2
        print("==> building player hybrid (optional) …")
        hybrid_out = player_stats_merged_hybrid_csv().resolve()
        summary["player_hybrid"] = build_player_hybrid(
            league_out,
            tournaments_out,
            hybrid_out,
            write_csv=args.write_csv,
        )
        player_id_audit_paths.append(hybrid_out)

    if not args.skip_player_id_name_audit and player_id_audit_paths:
        from data_access.parquet_sidecar import data_file_exists, resolve_load_path

        report_path = get_work_data_dir() / PLAYER_ID_NAME_CONFLICTS_CSV
        all_conflicts = []
        for audit_target in player_id_audit_paths:
            if not data_file_exists(audit_target):
                continue
            load_path = resolve_load_path(audit_target)
            conflicts = audit_player_id_names(
                load_path,
                sep=CSV_SEP,
                source_file=audit_target.name,
            )
            all_conflicts.extend(conflicts)
            print(format_summary(conflicts, data_path=load_path, report_path=report_path))
        if all_conflicts:
            write_conflict_report(all_conflicts, report_path)
            summary["player_id_name_audit"] = {
                "report": str(report_path.resolve()),
                "detail_rows": len(all_conflicts),
            }
        else:
            write_conflict_report([], report_path)
            summary["player_id_name_audit"] = {
                "report": str(report_path.resolve()),
                "detail_rows": 0,
            }
            print(f"Player ID/name audit: no conflicts; empty report at {report_path}")

    print()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
