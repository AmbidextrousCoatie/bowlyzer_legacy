#!/usr/bin/env python3
"""
Download legacy Bayern Liga result workbooks from sektion-bowling.bowling-bayern.de.

Seasons ~2008-09 .. 2018-19 share the liga{yy-yy}.htm hub layout (with minor path variants).
Older seasons need separate handling.

Usage:
  uv run python scripts/scrape_legacy_liga.py --season 2018-19
  uv run python scripts/scrape_legacy_liga.py --season 18-19 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin
from urllib.request import Request, urlopen

BASE_HOST = "http://sektion-bowling.bowling-bayern.de/dateien"
USER_AGENT = "Bowl-A-Lyzer/1.0 (legacy-liga-scrape)"
REQUEST_INTERVAL_S = 2.5
MIN_RESULT_BYTES = 8_192

import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from database.paths import legacy_scrape_dir

SCRAPE_ROOT = legacy_scrape_dir()
LOG_PATH = SCRAPE_ROOT / "scrape_log.jsonl"

# LB_* result sheets under regional auswertungen folders (2018+) or direct folders (2009-era).
RESULT_PATH_RE = re.compile(
    r"(?:auswertungen_)?(?:bayernliga|nordbereich|suedbereich)/LB_[^\s\"'<>]+\.xls",
    re.IGNORECASE,
)
WEEK_FROM_NAME_RE = re.compile(r"-(\d+)(?:-\d+)?\.xls$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _append_log(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", _now_iso())
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_season(season: str) -> tuple[str, str]:
    """
    Return (folder_slug, liga_slug) e.g. ('2018-19', '18-19').
    Accepts '2018-19' or '18-19'.
    """
    raw = season.strip()
    m4 = re.fullmatch(r"(\d{4})-(\d{2})", raw)
    if m4:
        yyyy, yy2 = m4.group(1), m4.group(2)
        folder = f"{yyyy}-{yy2}"
        liga = f"{yyyy[2:]}-{yy2}"
        return folder, liga
    m2 = re.fullmatch(r"(\d{2})-(\d{2})", raw)
    if m2:
        yy1, yy2 = m2.group(1), m2.group(2)
        folder = f"20{yy1}-{yy2}"
        liga = f"{yy1}-{yy2}"
        return folder, liga
    raise ValueError(f"Invalid season {season!r}; use e.g. 2018-19 or 18-19")


def liga_index_url(folder_slug: str, liga_slug: str) -> str:
    return f"{BASE_HOST}/saison{folder_slug}/liga/liga{liga_slug}.htm"


def discover_result_paths(html_text: str) -> list[str]:
    found: set[str] = set()
    for match in RESULT_PATH_RE.finditer(html_text):
        rel = unquote(match.group(0)).replace("\\", "/")
        if "ligaplanung" in rel.lower() or "ligaeinteilung" in rel.lower():
            continue
        found.add(rel)
    return sorted(found)


def league_key_for_path(rel_path: str) -> str:
    directory, filename = rel_path.rsplit("/", 1)
    stem = WEEK_FROM_NAME_RE.sub("", filename)
    return f"{directory}/{stem}"


def week_for_path(rel_path: str) -> int | None:
    filename = rel_path.rsplit("/", 1)[-1]
    m = WEEK_FROM_NAME_RE.search(filename)
    return int(m.group(1)) if m else None


def summarize_weeks(paths: list[str]) -> dict[str, dict]:
    by_league: dict[str, set[int]] = defaultdict(set)
    for rel in paths:
        wk = week_for_path(rel)
        if wk is not None:
            by_league[league_key_for_path(rel)].add(wk)
    out: dict[str, dict] = {}
    for key in sorted(by_league):
        weeks = sorted(by_league[key])
        out[key] = {
            "weeks_found": weeks,
            "week_count": len(weeks),
            "week_min": weeks[0],
            "week_max": weeks[-1],
        }
    return out


def fetch_bytes(url: str, timeout: float = 60.0) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def download_season(
    season: str,
    *,
    dry_run: bool = False,
    interval_s: float = REQUEST_INTERVAL_S,
) -> dict:
    folder_slug, liga_slug = normalize_season(season)
    index_url = liga_index_url(folder_slug, liga_slug)
    season_dir = SCRAPE_ROOT / f"saison{folder_slug}"

    stats = {
        "season": folder_slug,
        "liga_slug": liga_slug,
        "index_url": index_url,
        "dry_run": dry_run,
        "discovered": 0,
        "skipped_existing": 0,
        "downloaded": 0,
        "failed": 0,
        "league_keys": 0,
    }

    _append_log({"event": "season_start", "season": folder_slug, "index_url": index_url, "dry_run": dry_run})

    status, body = fetch_bytes(index_url)
    if status != 200 or not body:
        stats["error"] = f"index fetch failed: HTTP {status}"
        _append_log({"event": "index_failed", "season": folder_slug, "url": index_url, "status": status})
        return stats

    html = body.decode("iso-8859-1", errors="replace")
    rel_paths = discover_result_paths(html)
    stats["discovered"] = len(rel_paths)
    week_summary = summarize_weeks(rel_paths)
    stats["league_keys"] = len(week_summary)

    _append_log(
        {
            "event": "discovered",
            "season": folder_slug,
            "file_count": len(rel_paths),
            "league_keys": len(week_summary),
            "weeks_by_league": week_summary,
        }
    )

    pending = []
    for rel in rel_paths:
        dest = season_dir / Path(rel)
        if dest.is_file() and dest.stat().st_size >= MIN_RESULT_BYTES:
            stats["skipped_existing"] += 1
            _append_log(
                {
                    "event": "skip_exists",
                    "season": folder_slug,
                    "rel_path": rel,
                    "dest": str(dest.relative_to(_REPO_ROOT)),
                    "bytes": dest.stat().st_size,
                }
            )
            continue
        pending.append((rel, dest))

    if dry_run:
        stats["pending_downloads"] = len(pending)
        _append_log({"event": "dry_run_complete", "season": folder_slug, **stats})
        return stats

    for i, (rel, dest) in enumerate(pending):
        if i > 0:
            time.sleep(interval_s)
        url = urljoin(index_url, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            code, data = fetch_bytes(url)
            if code != 200 or len(data) < MIN_RESULT_BYTES:
                stats["failed"] += 1
                _append_log(
                    {
                        "event": "download_failed",
                        "season": folder_slug,
                        "rel_path": rel,
                        "url": url,
                        "status": code,
                        "bytes": len(data),
                    }
                )
                continue
            dest.write_bytes(data)
            stats["downloaded"] += 1
            _append_log(
                {
                    "event": "downloaded",
                    "season": folder_slug,
                    "rel_path": rel,
                    "url": url,
                    "status": code,
                    "bytes": len(data),
                    "dest": str(dest.relative_to(_REPO_ROOT)),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            stats["failed"] += 1
            _append_log(
                {
                    "event": "download_failed",
                    "season": folder_slug,
                    "rel_path": rel,
                    "url": url,
                    "error": str(exc),
                }
            )

    _append_log({"event": "season_complete", **stats})
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape legacy Liga LB_*.xls result files.")
    parser.add_argument("--season", required=True, help="Season e.g. 2018-19 or 18-19")
    parser.add_argument("--dry-run", action="store_true", help="Discover and log only; no downloads")
    parser.add_argument(
        "--interval",
        type=float,
        default=REQUEST_INTERVAL_S,
        help=f"Seconds between downloads (default {REQUEST_INTERVAL_S})",
    )
    args = parser.parse_args()
    stats = download_season(args.season, dry_run=args.dry_run, interval_s=args.interval)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
