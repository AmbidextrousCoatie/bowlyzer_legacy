#!/usr/bin/env python3
"""
Download legacy Bayern Liga result workbooks from sektion-bowling.bowling-bayern.de.

Seasons ~2008-09 .. 2018-19 share the liga{yy-yy}.htm hub layout (with minor path variants).
Older seasons need separate handling.

Player registry (Aktive Mitglieder) workbooks live on the season hub ``indexs{yy-yy}.htm``
(not the Liga index). Paths vary (``allgemein/`` vs ``rangliste/``); 2004-05 ships a ``.zip``.

Usage:
  uv run python scripts/scrape_legacy_liga.py --season 2018-19
  uv run python scripts/scrape_legacy_liga.py --season 18-19 --dry-run
  uv run python scripts/scrape_legacy_liga.py --season 2018-19 --fetch-player-registry
  uv run python scripts/scrape_legacy_liga.py --probe-player-registry
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from html.parser import HTMLParser
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
AKTIVE_ASSET_RE = re.compile(
    r"(?:[\w./\\_-]*?)aktive[\w._-]*\.(?:xls|zip)",
    re.IGNORECASE,
)
AKTIVE_LABEL_RE = re.compile(r"aktive\s*mitglieder", re.IGNORECASE)
PROBE_SEASON_FIRST_YEAR = 2004
PROBE_SEASON_LAST_YEAR = 2018


class _HtmlLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href") or ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, "".join(self._text).strip()))
        self._href = None
        self._text = []


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


def season_hub_url(folder_slug: str, liga_slug: str) -> str:
    """Season overview page — hosts the *Aktive Mitglieder* registry link."""
    return f"{BASE_HOST}/saison{folder_slug}/indexs{liga_slug}.htm"


def season_year_range(
    first_year: int = PROBE_SEASON_FIRST_YEAR,
    last_year: int = PROBE_SEASON_LAST_YEAR,
) -> list[tuple[str, str]]:
    seasons: list[tuple[str, str]] = []
    for yyyy in range(first_year, last_year + 1):
        yy2 = f"{(yyyy + 1) % 100:02d}"
        seasons.append((f"{yyyy}-{yy2}", f"{str(yyyy)[2:]}-{yy2}"))
    return seasons


def _normalize_registry_rel_path(rel: str, *, folder_slug: str) -> str:
    cleaned = unquote(rel).replace("\\", "/").strip()
    while cleaned.startswith("../"):
        cleaned = cleaned[3:]
    cleaned = cleaned.lstrip("./")
    if re.match(r"saison\d{4}-\d{2}/", cleaned, re.IGNORECASE):
        return cleaned
    prefix = f"saison{folder_slug}/"
    if cleaned.startswith(prefix):
        return cleaned
    return prefix + cleaned


def discover_player_registry_paths(
    html_text: str,
    *,
    folder_slug: str,
    page_url: str,
) -> list[dict]:
    """
    Find *Aktive Mitglieder* registry assets on a season hub page.

    Returns dicts with ``rel_path``, ``url``, ``label``, ``preferred`` (Endstand pick).
    """
    found: dict[str, dict] = {}

    def add(rel: str, *, label: str = "") -> None:
        if not AKTIVE_ASSET_RE.search(rel):
            return
        abs_url = urljoin(page_url, rel)
        if "/dateien/" in abs_url:
            rel_from_url = abs_url.split("/dateien/", 1)[-1]
            rel_path = _normalize_registry_rel_path(rel_from_url, folder_slug=folder_slug)
        else:
            rel_path = _normalize_registry_rel_path(rel, folder_slug=folder_slug)
        if not rel_path.startswith(f"saison{folder_slug}/"):
            return
        preferred = "endstand" in rel_path.lower()
        entry = {
            "rel_path": rel_path,
            "url": abs_url,
            "label": label.strip(),
            "preferred": preferred,
            "is_zip": rel_path.lower().endswith(".zip"),
        }
        key = rel_path.lower()
        if key not in found or preferred:
            found[key] = entry

    parser = _HtmlLinkParser()
    parser.feed(html_text)
    for href, label in parser.links:
        if AKTIVE_ASSET_RE.search(href) or (
            AKTIVE_LABEL_RE.search(label) and re.search(r"\.(?:xls|zip)\b", href, re.I)
        ):
            add(href, label=label)

    for match in AKTIVE_ASSET_RE.finditer(html_text):
        token = match.group(0)
        if f"saison{folder_slug}/" not in token and "allgemein/" not in token and "rangliste/" not in token:
            continue
        add(token)

    ranked = sorted(
        found.values(),
        key=lambda item: (
            0 if item["preferred"] else 1,
            0 if not item["is_zip"] else 1,
            item["rel_path"],
        ),
    )
    return ranked


def select_player_registry_downloads(entries: list[dict]) -> list[dict]:
    """Prefer Endstand workbook; keep a single primary unless only interim files exist."""
    if not entries:
        return []
    preferred = [entry for entry in entries if entry.get("preferred")]
    if preferred:
        return preferred[:1]
    return entries[:1]


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


def _write_registry_payload(dest: Path, data: bytes) -> Path:
    """
    Write registry bytes to ``dest``; extract ``.xls`` from ``.zip`` when needed.

    Returns the path of the usable workbook (``.xls``).
    """
    if dest.suffix.lower() == ".zip" or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".xls")]
            if not members:
                raise ValueError(f"zip has no .xls member: {dest.name}")
            member = members[0]
            xls_bytes = archive.read(member)
        xls_dest = dest.with_suffix(".xls")
        xls_dest.parent.mkdir(parents=True, exist_ok=True)
        xls_dest.write_bytes(xls_bytes)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return xls_dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


def probe_player_registry(
    *,
    first_year: int = PROBE_SEASON_FIRST_YEAR,
    last_year: int = PROBE_SEASON_LAST_YEAR,
    interval_s: float = REQUEST_INTERVAL_S,
) -> dict:
    """Scan season hubs for *Aktive Mitglieder* links (report-only)."""
    seasons_out: list[dict] = []
    for idx, (folder_slug, liga_slug) in enumerate(season_year_range(first_year, last_year)):
        if idx > 0:
            time.sleep(interval_s)
        hub_url = season_hub_url(folder_slug, liga_slug)
        row: dict = {
            "season": folder_slug,
            "hub_url": hub_url,
            "discovered": [],
            "selected": [],
            "error": "",
        }
        try:
            status, body = fetch_bytes(hub_url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            row["error"] = str(exc)
            seasons_out.append(row)
            continue
        if status != 200 or not body:
            row["error"] = f"HTTP {status}"
            seasons_out.append(row)
            continue
        html = body.decode("iso-8859-1", errors="replace")
        discovered = discover_player_registry_paths(html, folder_slug=folder_slug, page_url=hub_url)
        row["discovered"] = discovered
        row["selected"] = select_player_registry_downloads(discovered)
        if not discovered and AKTIVE_LABEL_RE.search(html):
            row["error"] = "label_present_no_download"
        seasons_out.append(row)

    with_links = [row for row in seasons_out if row["discovered"]]
    return {
        "seasons_probed": len(seasons_out),
        "seasons_with_registry": len(with_links),
        "registry_files_found": sum(len(row["discovered"]) for row in with_links),
        "seasons": seasons_out,
    }


def download_player_registry(
    season: str,
    *,
    dry_run: bool = False,
    interval_s: float = REQUEST_INTERVAL_S,
    download_all: bool = False,
) -> dict:
    """Download *Aktive Mitglieder* workbook(s) for one season."""
    folder_slug, liga_slug = normalize_season(season)
    hub_url = season_hub_url(folder_slug, liga_slug)
    season_dir = SCRAPE_ROOT / f"saison{folder_slug}"

    stats: dict = {
        "season": folder_slug,
        "hub_url": hub_url,
        "dry_run": dry_run,
        "discovered": 0,
        "selected": 0,
        "skipped_existing": 0,
        "downloaded": 0,
        "failed": 0,
        "assets": [],
    }
    _append_log(
        {
            "event": "player_registry_start",
            "season": folder_slug,
            "hub_url": hub_url,
            "dry_run": dry_run,
        }
    )

    status, body = fetch_bytes(hub_url)
    if status != 200 or not body:
        stats["error"] = f"hub fetch failed: HTTP {status}"
        _append_log({"event": "player_registry_hub_failed", "season": folder_slug, "status": status})
        return stats

    html = body.decode("iso-8859-1", errors="replace")
    discovered = discover_player_registry_paths(html, folder_slug=folder_slug, page_url=hub_url)
    targets = discovered if download_all else select_player_registry_downloads(discovered)
    stats["discovered"] = len(discovered)
    stats["selected"] = len(targets)
    stats["assets"] = targets

    if dry_run:
        _append_log({"event": "player_registry_dry_run", "season": folder_slug, **stats})
        return stats

    for idx, asset in enumerate(targets):
        if idx > 0:
            time.sleep(interval_s)
        rel = asset["rel_path"].split(f"saison{folder_slug}/", 1)[-1]
        dest = season_dir / rel
        xls_dest = dest.with_suffix(".xls") if dest.suffix.lower() == ".zip" else dest
        if xls_dest.is_file() and xls_dest.stat().st_size >= MIN_RESULT_BYTES:
            stats["skipped_existing"] += 1
            _append_log(
                {
                    "event": "player_registry_skip_exists",
                    "season": folder_slug,
                    "rel_path": asset["rel_path"],
                    "dest": str(xls_dest),
                }
            )
            continue
        try:
            code, data = fetch_bytes(asset["url"])
            if code != 200 or len(data) < 1024:
                stats["failed"] += 1
                continue
            written = _write_registry_payload(dest, data)
            stats["downloaded"] += 1
            _append_log(
                {
                    "event": "player_registry_downloaded",
                    "season": folder_slug,
                    "rel_path": asset["rel_path"],
                    "url": asset["url"],
                    "bytes": len(data),
                    "dest": str(written),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            stats["failed"] += 1
            _append_log(
                {
                    "event": "player_registry_failed",
                    "season": folder_slug,
                    "rel_path": asset["rel_path"],
                    "error": str(exc),
                }
            )

    _append_log({"event": "player_registry_complete", **stats})
    return stats


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
    parser.add_argument("--season", help="Season e.g. 2018-19 or 18-19")
    parser.add_argument("--dry-run", action="store_true", help="Discover and log only; no downloads")
    parser.add_argument(
        "--fetch-player-registry",
        action="store_true",
        help="Download Aktive Mitglieder registry workbook for --season (from indexs{yy-yy}.htm)",
    )
    parser.add_argument(
        "--player-registry-all",
        action="store_true",
        help="With --fetch-player-registry: download every aktive*.xls (not only Endstand)",
    )
    parser.add_argument(
        "--probe-player-registry",
        action="store_true",
        help=(
            f"Report Aktive Mitglieder links for seasons "
            f"{PROBE_SEASON_FIRST_YEAR}-05 .. {PROBE_SEASON_LAST_YEAR}-19 (no download)"
        ),
    )
    parser.add_argument(
        "--probe-first-year",
        type=int,
        default=PROBE_SEASON_FIRST_YEAR,
        help="First season start year for --probe-player-registry (default 2004)",
    )
    parser.add_argument(
        "--probe-last-year",
        type=int,
        default=PROBE_SEASON_LAST_YEAR,
        help="Last season start year for --probe-player-registry (default 2018)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=REQUEST_INTERVAL_S,
        help=f"Seconds between downloads (default {REQUEST_INTERVAL_S})",
    )
    args = parser.parse_args()

    if args.probe_player_registry:
        report = probe_player_registry(
            first_year=args.probe_first_year,
            last_year=args.probe_last_year,
            interval_s=0.0 if args.dry_run else args.interval,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    if not args.season:
        parser.error("--season is required unless --probe-player-registry is set")

    if args.fetch_player_registry:
        stats = download_player_registry(
            args.season,
            dry_run=args.dry_run,
            interval_s=args.interval,
            download_all=args.player_registry_all,
        )
    else:
        stats = download_season(args.season, dry_run=args.dry_run, interval_s=args.interval)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
