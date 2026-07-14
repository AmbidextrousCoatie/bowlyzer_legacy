#!/usr/bin/env python3
"""Run configured tournament imports (database/config/tournament_imports.json)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.paths import tournaments_input_dir
from database.tournament_import import TournamentImportService
from database.tournament_scrape.categories import TOURNAMENT_CODES, resolve_category_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import tournaments from configured sources.")
    parser.add_argument(
        "--config",
        default=str(ROOT / "database" / "config" / "tournament_imports.json"),
        help="Path to tournament_imports.json",
    )
    parser.add_argument(
        "--id",
        action="append",
        dest="entry_ids",
        metavar="IMPORT_ID",
        help="Run only the given import id(s) from tournament_imports.json. Repeatable.",
    )
    parser.add_argument(
        "--tournament",
        action="append",
        dest="tournaments",
        metavar="CODE",
        help=f"Legacy PDF shorthand (repeatable or comma-separated): {', '.join(TOURNAMENT_CODES)}",
    )
    parser.add_argument(
        "--first-year",
        type=int,
        default=None,
        help="First season start year (e.g. 2016 for season 2016-17 / BM 2017 PDFs)",
    )
    parser.add_argument(
        "--last-year",
        type=int,
        default=None,
        help="Last season start year (e.g. 2018 for season 2018-19 / BM 2019 PDFs)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Directory with scraped legacy PDFs (default: work_dir/tournaments/input)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only; do not write CSV or merge.",
    )
    parser.add_argument(
        "--no-publish-parquet",
        action="store_true",
        help="Skip publishing tournaments_postprocessed.parquet (app reads Parquet, not manual CSV alone).",
    )
    parser.add_argument(
        "--no-rebuild-player-hybrid",
        action="store_true",
        help="Skip rebuilding player_stats_merged_plus_tournaments.csv",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        resolve_category_ids(tournaments=args.tournaments)
    except ValueError as exc:
        build_parser().error(str(exc))

    legacy_mode = (
        args.tournaments is not None or args.first_year is not None or args.last_year is not None
    )
    if legacy_mode and args.entry_ids:
        build_parser().error("Use either --id or (--tournament with --first-year/--last-year), not both")
    if legacy_mode and (args.tournaments is None or args.first_year is None or args.last_year is None):
        build_parser().error("Legacy import requires --tournament, --first-year, and --last-year")

    service = TournamentImportService(config_path=args.config)
    summary = service.run(
        entry_ids=args.entry_ids,
        tournaments=args.tournaments,
        first_year=args.first_year,
        last_year=args.last_year,
        input_dir=args.input_dir or tournaments_input_dir(),
        dry_run=args.dry_run,
        publish_parquet=not args.no_publish_parquet,
        rebuild_player_hybrid=not args.no_rebuild_player_hybrid,
    )

    if summary.missing_legacy_pdfs:
        print("Missing PDFs (not imported):")
        for item in summary.missing_legacy_pdfs:
            print(f"  - {item}")

    if not summary.results:
        print("No imports ran (none enabled, no matching --id, or no PDFs found).")
        return

    for result in summary.results:
        print(
            f"[{result.entry_id}] {result.source.name}: "
            f"{result.postprocessed_row_count} rows, events={result.event_names}"
        )
        for warning in result.warnings:
            print(f"  - {warning}")

    if summary.published_parquet:
        pub = summary.published_parquet
        print(
            f"Published tournaments parquet: {pub.get('rows')} rows -> {pub.get('parquet_output')}"
        )
    if summary.tournament_cache_invalidation:
        inv = summary.tournament_cache_invalidation
        print(
            "Invalidated tournament caches (db_tournament_regions_2026_gf / parquet): "
            f"{inv.get('disk_entries_removed', 0)} disk entries, "
            f"{inv.get('runtime_entries_removed', 0)} runtime overlay entries"
        )
        print(
            "Re-warm optional: uv run python scripts/warm_tournament_cache.py "
            "--database db_tournament_regions_2026_gf"
        )
    if summary.player_cache_invalidation:
        inv = summary.player_cache_invalidation
        print(
            "Invalidated player caches: "
            f"{inv.get('disk_entries_removed', 0)} disk entries, "
            f"{inv.get('runtime_entries_removed', 0)} runtime overlay entries"
        )
        print(
            "Re-warm optional: uv run python scripts/warm_player_cache.py "
            "--database db_player_merged_hybrid --phase essential"
        )
    if summary.rebuilt_player_hybrid:
        print("Rebuilt player hybrid: database/data/player_stats_merged_plus_tournaments.csv")


if __name__ == "__main__":
    main()
