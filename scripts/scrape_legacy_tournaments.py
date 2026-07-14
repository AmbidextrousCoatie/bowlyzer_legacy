#!/usr/bin/env python3
"""
Download legacy BSKV Meisterschaften result PDFs from sektion-bowling.bowling-bayern.de.

Tournament PDFs are listed on each season's Meisterschaften index. URL layout
varies by era (see ``database/tournament_scrape/urls.py``):

  saison2008-09/meisterschaften/indexm08-09.htm   (standard)
  saison2005-06/meisterschaften/indexm.htm        (plain index, no year suffix)

Discovered files are written flat to ``{work_dir}/tournaments/input/`` for
``scripts/import_tournaments.py``.

Usage:
  uv run python scripts/scrape_legacy_tournaments.py --probe --first-year 2004 --last-year 2017
  uv run python scripts/scrape_legacy_tournaments.py --first-year 2004 --last-year 2017
  uv run python scripts/scrape_legacy_tournaments.py --first-year 2016 --last-year 2018 --tournament sbm,nbm,bm,bm_f
  uv run python scripts/scrape_legacy_tournaments.py --season 2016-17 --dry-run
  uv run python scripts/scrape_legacy_tournaments.py --season 2018-19 --category suedbayerische-herren
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from database.paths import legacy_scrape_dir, tournaments_input_dir
from database.tournament_scrape import load_scrape_config
from database.tournament_scrape.categories import TOURNAMENT_CODES, resolve_category_ids
from database.tournament_scrape.discover import (
    canonical_basename,
    discover_tournament_pdfs,
    select_downloads,
)
from database.tournament_scrape.urls import fetch_tournament_index_html
from scripts.scrape_legacy_liga import (
    REQUEST_INTERVAL_S,
    fetch_bytes,
    normalize_season,
    season_year_range,
)

MIN_RESULT_BYTES = 4_096
MIN_PDF_BYTES = MIN_RESULT_BYTES
LOG_PATH = legacy_scrape_dir() / "tournament_scrape_log.jsonl"


def _append_tournament_log(record: dict) -> None:
    from datetime import UTC, datetime

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def probe_tournaments(
    *,
    first_year: int,
    last_year: int,
    category_ids: list[str] | None,
    interval_s: float,
) -> dict:
    config = load_scrape_config()
    seasons_out: list[dict] = []
    for idx, (folder_slug, liga_slug) in enumerate(season_year_range(first_year, last_year)):
        if idx > 0 and interval_s > 0:
            time.sleep(interval_s)
        row: dict = {
            "season": folder_slug,
            "index_url": "",
            "index_candidates": [],
            "discovered": [],
            "selected": [],
            "error": "",
        }
        try:
            page_url, html, candidates = fetch_tournament_index_html(
                folder_slug, liga_slug, fetch_status=fetch_bytes
            )
            row["index_url"] = page_url
            row["index_candidates"] = candidates
        except (HTTPError, URLError, TimeoutError, OSError, FileNotFoundError) as exc:
            row["error"] = str(exc)
            seasons_out.append(row)
            continue
        discovered = discover_tournament_pdfs(
            html,
            page_url=page_url,
            folder_slug=folder_slug,
            config=config,
            category_ids=category_ids,
        )
        selected = select_downloads(discovered, config)
        row["discovered"] = [item.__dict__ for item in discovered]
        row["selected"] = [item.__dict__ for item in selected]
        seasons_out.append(row)

    with_selected = [row for row in seasons_out if row["selected"]]
    return {
        "seasons_probed": len(seasons_out),
        "seasons_with_results": len(with_selected),
        "selected_files": sum(len(row["selected"]) for row in with_selected),
        "categories": [category.id for category in config.categories],
        "seasons": seasons_out,
    }


def download_season_tournaments(
    season: str,
    *,
    dry_run: bool = False,
    interval_s: float = REQUEST_INTERVAL_S,
    category_ids: list[str] | None = None,
    output_dir: Path | None = None,
) -> dict:
    config = load_scrape_config()
    folder_slug, liga_slug = normalize_season(season)
    dest_dir = (output_dir or tournaments_input_dir()).resolve()
    archive_dir = legacy_scrape_dir() / f"saison{folder_slug}" / "meisterschaften"

    stats: dict = {
        "season": folder_slug,
        "index_url": "",
        "index_candidates": [],
        "output_dir": str(dest_dir),
        "dry_run": dry_run,
        "discovered": 0,
        "selected": 0,
        "skipped_existing": 0,
        "downloaded": 0,
        "failed": 0,
        "files": [],
    }

    try:
        page_url, html, candidates = fetch_tournament_index_html(
            folder_slug, liga_slug, fetch_status=fetch_bytes
        )
    except (HTTPError, URLError, TimeoutError, OSError, FileNotFoundError) as exc:
        stats["error"] = f"index fetch failed: {exc}"
        _append_tournament_log({"event": "tournament_index_failed", "season": folder_slug, "error": str(exc)})
        return stats

    stats["index_url"] = page_url
    stats["index_candidates"] = candidates
    _append_tournament_log(
        {
            "event": "tournament_season_start",
            "season": folder_slug,
            "index_url": page_url,
            "index_candidates": candidates,
            "dry_run": dry_run,
            "categories": category_ids,
        }
    )

    discovered = discover_tournament_pdfs(
        html,
        page_url=page_url,
        folder_slug=folder_slug,
        config=config,
        category_ids=category_ids,
    )
    selected = select_downloads(discovered, config)
    stats["discovered"] = len(discovered)
    stats["selected"] = len(selected)
    stats["files"] = [item.__dict__ for item in selected]

    if dry_run:
        _append_tournament_log({"event": "tournament_dry_run_complete", **stats})
        return stats

    for idx, item in enumerate(selected):
        if idx > 0:
            time.sleep(interval_s)
        filename = canonical_basename(item, folder_slug)
        dest = dest_dir / filename
        archive_path = archive_dir / filename
        if dest.is_file() and dest.stat().st_size >= MIN_RESULT_BYTES:
            stats["skipped_existing"] += 1
            _append_tournament_log(
                {
                    "event": "tournament_skip_exists",
                    "season": folder_slug,
                    "category_id": item.category_id,
                    "basename": filename,
                    "source_basename": item.basename,
                    "dest": str(dest),
                }
            )
            continue
        try:
            code, data = fetch_bytes(item.url)
            if code != 200 or len(data) < MIN_RESULT_BYTES:
                stats["failed"] += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_bytes(data)
            stats["downloaded"] += 1
            _append_tournament_log(
                {
                    "event": "tournament_downloaded",
                    "season": folder_slug,
                    "category_id": item.category_id,
                    "basename": filename,
                    "source_basename": item.basename,
                    "url": item.url,
                    "bytes": len(data),
                    "dest": str(dest),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            stats["failed"] += 1
            _append_tournament_log(
                {
                    "event": "tournament_download_failed",
                    "season": folder_slug,
                    "basename": filename,
                    "source_basename": item.basename,
                    "url": item.url,
                    "error": str(exc),
                }
            )

    _append_tournament_log({"event": "tournament_season_complete", **stats})
    return stats


def download_tournaments_range(
    *,
    first_year: int,
    last_year: int,
    dry_run: bool = False,
    interval_s: float = REQUEST_INTERVAL_S,
    season_interval_s: float | None = None,
    category_ids: list[str] | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Download tournament PDFs for each season from ``first_year-YY`` through ``last_year-YY``."""
    if first_year > last_year:
        raise ValueError(f"--first-year {first_year} must be <= --last-year {last_year}")

    pause_between_seasons = season_interval_s if season_interval_s is not None else interval_s
    seasons_out: list[dict] = []
    totals = {
        "discovered": 0,
        "selected": 0,
        "skipped_existing": 0,
        "downloaded": 0,
        "failed": 0,
    }

    _append_tournament_log(
        {
            "event": "tournament_range_start",
            "first_year": first_year,
            "last_year": last_year,
            "dry_run": dry_run,
            "categories": category_ids,
        }
    )

    for idx, (folder_slug, _liga_slug) in enumerate(season_year_range(first_year, last_year)):
        if idx > 0 and pause_between_seasons > 0:
            time.sleep(pause_between_seasons)
        stats = download_season_tournaments(
            folder_slug,
            dry_run=dry_run,
            interval_s=interval_s,
            category_ids=category_ids,
            output_dir=output_dir,
        )
        seasons_out.append(stats)
        for key in totals:
            totals[key] += int(stats.get(key, 0))

    with_results = [row for row in seasons_out if row.get("selected")]
    report = {
        "first_year": first_year,
        "last_year": last_year,
        "dry_run": dry_run,
        "seasons_attempted": len(seasons_out),
        "seasons_with_results": len(with_results),
        "seasons_failed": sum(1 for row in seasons_out if row.get("error")),
        **totals,
        "output_dir": str((output_dir or tournaments_input_dir()).resolve()),
        "seasons": seasons_out,
    }
    _append_tournament_log({"event": "tournament_range_complete", **report})
    return report


def main() -> None:
    config = load_scrape_config()
    parser = argparse.ArgumentParser(description="Scrape legacy BSKV Meisterschaften result PDFs.")
    parser.add_argument("--season", help="Season e.g. 2018-19 or 18-19")
    parser.add_argument("--dry-run", action="store_true", help="Discover and log only; no downloads")
    parser.add_argument(
        "--tournament",
        action="append",
        dest="tournaments",
        metavar="CODE",
        help=f"Shorthand tournament code (repeatable or comma-separated): {', '.join(TOURNAMENT_CODES)}",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        metavar="ID",
        help=f"Tournament category id (repeatable). Known: {', '.join(c.id for c in config.categories)}",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Report discovered PDFs for a year range (no download)",
    )
    parser.add_argument(
        "--first-year",
        type=int,
        default=None,
        help="First season start year (e.g. 2004 for season 2004-05 / BM 2005)",
    )
    parser.add_argument(
        "--last-year",
        type=int,
        default=None,
        help="Last season start year (e.g. 2017 for season 2017-18 / BM 2018)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output directory (default: work_dir/tournaments/input)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=REQUEST_INTERVAL_S,
        help=f"Seconds between PDF downloads (default {REQUEST_INTERVAL_S})",
    )
    parser.add_argument(
        "--season-interval",
        type=float,
        default=None,
        help="Seconds between seasons in a year-range run (default: same as --interval)",
    )
    args = parser.parse_args()

    try:
        category_ids = resolve_category_ids(
            tournaments=args.tournaments,
            category_ids=args.categories,
        )
    except ValueError as exc:
        parser.error(str(exc))

    probe_first_year = args.first_year if args.first_year is not None else 2016
    probe_last_year = args.last_year if args.last_year is not None else 2019

    if args.probe:
        report = probe_tournaments(
            first_year=probe_first_year,
            last_year=probe_last_year,
            category_ids=category_ids,
            interval_s=0.0 if args.dry_run else args.interval,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if args.season:
        stats = download_season_tournaments(
            args.season,
            dry_run=args.dry_run,
            interval_s=args.interval,
            category_ids=category_ids,
            output_dir=args.output_dir,
        )
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    if args.first_year is None or args.last_year is None:
        parser.error("Specify --season, --probe, or both --first-year and --last-year")

    report = download_tournaments_range(
        first_year=args.first_year,
        last_year=args.last_year,
        dry_run=args.dry_run,
        interval_s=args.interval,
        season_interval_s=args.season_interval,
        category_ids=category_ids,
        output_dir=args.output_dir,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
