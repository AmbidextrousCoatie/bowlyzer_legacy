"""Tournament season × competition coverage matrix for Diagnose UI."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from app.utils.tournament_utils import (
    _GROUP_CANONICAL_ALIASES,
    _load_tournament_mapping_rows,
    _split_aliases,
    normalize_tournament_group_name,
    resolve_tournament_abbreviation,
)
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from data_access.tournament_data_quality import TOURNAMENT_DATA_QUALITY_CSV
from database.paths import (
    get_data_dir,
    get_work_data_dir,
    gf_tournaments_combined_postprocessed_csv,
    legacy_scrape_dir,
    tournaments_input_dir,
    tournaments_postprocessed_csv,
)

COVERAGE_STATUSES = (
    "not_available",
    "available",
    "published_flaws",
    "published_ok",
)

# Regional SBM/NBM exist for Herren Einzel only — no Damen or Doppel variants.
COVERAGE_EXCLUDED_TOURNAMENT_IDS = frozenset(
    {
        "NBM D",
        "SBM D",
        "NBM M D",
        "SBM M D",
    }
)

SCRAPE_CATEGORY_TO_TOURNAMENT_ID: Dict[str, str] = {
    "suedbayerische-herren": "SBM M",
    "nordbayerische-herren": "NBM M",
    "bayerische-einzel-herren": "BM M",
    "bayerische-einzel-frauen": "BM D",
    "bayerisches-doppel-herren": "BM M D",
    "bayerisches-doppel-frauen": "BM D D",
}

_LEGACY_CSV_RE = re.compile(
    r"tournament_legacy_pdf_(?P<code>[a-z0-9_]+)_(?P<year>\d{4})_postprocessed\.csv$",
    re.IGNORECASE,
)
_LEGACY_CODE_TO_ID = {
    "sbm": "SBM M",
    "nbm": "NBM M",
    "bm": "BM M",
    "bm_f": "BM D",
    "bm_md": "BM M D",
    "bm_dd": "BM D D",
}

_FOLDER_SEASON_RE = re.compile(r"^(\d{4})-(\d{2})$")


def folder_slug_to_app_season(folder_slug: str) -> str:
    match = _FOLDER_SEASON_RE.match(str(folder_slug or "").strip())
    if not match:
        return ""
    return f"{match.group(1)[2:]}/{match.group(2)}"


def app_season_to_calendar_year(season: str) -> int:
    text = str(season or "").strip().replace("-", "/")
    parts = text.split("/")
    if len(parts) != 2 or not parts[1].isdigit():
        return 0
    return 2000 + int(parts[1])


def iter_app_seasons(*, first_season: str = "04/05", last_season: str | None = None) -> List[str]:
    start_yy = int(first_season.split("/")[0])
    if not last_season:
        published_counts, _ = _load_published_events(tournaments_postprocessed_csv())
        if published_counts:
            last_season = max(season for season, _ in published_counts.keys())
        else:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            yy = now.year % 100
            last_season = f"{yy - 1:02d}/{yy:02d}" if now.month < 7 else f"{yy:02d}/{(yy + 1) % 100:02d}"
    end_yy = int(last_season.split("/")[0])
    seasons: List[str] = []
    for yy in range(start_yy, end_yy + 1):
        seasons.append(f"{yy:02d}/{(yy + 1) % 100:02d}")
    return seasons


def _group_to_tournament_id_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for row in _load_tournament_mapping_rows():
        tournament_id = str(row.get("id") or "").strip()
        long_name = str(row.get("long_name") or "").strip()
        if not tournament_id or not long_name:
            continue
        lookup[long_name] = tournament_id
        lookup[normalize_tournament_group_name(long_name)] = tournament_id
        for alias in _split_aliases(row.get("aliases") or ""):
            lookup[alias] = tournament_id
            lookup[normalize_tournament_group_name(alias)] = tournament_id
    for alias, canonical in _GROUP_CANONICAL_ALIASES.items():
        target = lookup.get(canonical) or lookup.get(normalize_tournament_group_name(canonical))
        if target:
            lookup[alias] = target
            lookup[normalize_tournament_group_name(alias)] = target
    return lookup


def tournament_id_for_event(event_name: str) -> str:
    text = str(event_name or "").strip()
    if not text:
        return ""
    known_ids = {str(row.get("id") or "").strip() for row in _load_tournament_mapping_rows()}
    abbrev = resolve_tournament_abbreviation(text)
    if abbrev in known_ids:
        return abbrev
    group = normalize_tournament_group_name(text)
    return _group_to_tournament_id_lookup().get(group, "")


@dataclass
class CoverageCell:
    status: str
    sources: List[str] = field(default_factory=list)
    row_count: int = 0
    validation_status: str = ""
    notes: str = ""
    event_slug: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "sources": list(self.sources),
            "row_count": self.row_count,
            "validation_status": self.validation_status,
            "notes": self.notes,
            "event_slug": self.event_slug,
        }


def _load_registry_pdf_availability(pdf_dir: Path) -> Set[Tuple[str, str]]:
    """``(app_season, tournament_id)`` for PDFs present on disk per source registry."""
    if not pdf_dir.is_dir():
        return set()
    from database.tournament_import.source_registry import load_source_registry

    on_disk = {path.name.lower() for path in pdf_dir.glob("*.pdf")}
    on_disk.update(path.name.lower() for path in pdf_dir.glob("*.xls"))
    on_disk.update(path.name.lower() for path in pdf_dir.glob("*.xlsx"))
    out: Set[Tuple[str, str]] = set()
    for row in load_source_registry():
        if not row.enabled or not row.file_basename:
            continue
        if row.file_basename.lower() not in on_disk:
            continue
        season = str(row.season or "").strip()
        tournament_id = str(row.tournament_id or "").strip()
        if season and tournament_id:
            out.add((season, tournament_id))
    return out


def _load_scrape_downloads(log_path: Path) -> Set[Tuple[str, str]]:
    """``(app_season, tournament_id)`` from scrape log downloads."""
    if not log_path.is_file():
        return set()
    out: Set[Tuple[str, str]] = set()
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event") != "tournament_downloaded":
                continue
            season = folder_slug_to_app_season(str(record.get("season") or ""))
            category_id = str(record.get("category_id") or "")
            tournament_id = SCRAPE_CATEGORY_TO_TOURNAMENT_ID.get(category_id)
            if season and tournament_id:
                out.add((season, tournament_id))
    return out


def _load_postprocessed_csv_availability(data_dir: Path) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    if not data_dir.is_dir():
        return out
    for path in data_dir.glob("tournament_*postprocessed.csv"):
        name = path.name.lower()
        if name == "tournaments_postprocessed.csv":
            continue
        match = _LEGACY_CSV_RE.match(path.name)
        if match:
            code = match.group("code").lower()
            year = int(match.group("year"))
            tournament_id = _LEGACY_CODE_TO_ID.get(code)
            if not tournament_id:
                continue
            season_yy = year - 1
            season = f"{season_yy % 100:02d}/{year % 100:02d}"
            out.add((season, tournament_id))
            continue
        if "clubmeisterschaft_donaubowler" in name:
            out.add(("25/26", "CM DB 26"))
        if "bayerische_meisterschaft_2026" in name:
            out.add(("25/26", "BM M"))
            out.add(("25/26", "BM D"))
        if "nordbayerische_2026" in name:
            out.add(("25/26", "NBM M"))
    return out


def _load_gf_input_availability(
    gf_path: Path,
) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], str]]:
    if not gf_path.is_file():
        return {}, {}
    import pandas as pd

    load_path = resolve_load_path(gf_path)
    if load_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(load_path)
    else:
        df = pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)
    event_col = "Event" if "Event" in df.columns else "Event Name"
    if "Season" not in df.columns or event_col not in df.columns:
        return {}, {}
    counts: Dict[Tuple[str, str], int] = {}
    slugs: Dict[Tuple[str, str], str] = {}
    grouped = df.groupby([df["Season"].astype(str).str.strip(), df[event_col].astype(str).str.strip()])
    for (season, event_name), group in grouped:
        if not season or not event_name:
            continue
        tournament_id = tournament_id_for_event(event_name)
        if not tournament_id:
            continue
        key = (season, tournament_id)
        counts[key] = int(len(group))
        slugs[key] = normalize_tournament_group_name(event_name)
    return counts, slugs


def _load_published_events(
    published_path: Path,
) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], str]]:
    if not data_file_exists(published_path):
        return {}, {}
    import pandas as pd

    load_path = resolve_load_path(published_path)
    if load_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(load_path)
    else:
        df = pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)
    event_col = "Event" if "Event" in df.columns else "Event Name"
    if "Season" not in df.columns or event_col not in df.columns:
        return {}, {}
    counts: Dict[Tuple[str, str], int] = {}
    slugs: Dict[Tuple[str, str], str] = {}
    grouped = df.groupby([df["Season"].astype(str).str.strip(), df[event_col].astype(str).str.strip()])
    for (season, event_name), group in grouped:
        if not season or not event_name:
            continue
        tournament_id = tournament_id_for_event(event_name)
        if not tournament_id:
            continue
        key = (season, tournament_id)
        counts[key] = int(len(group))
        slugs[key] = normalize_tournament_group_name(event_name)
    return counts, slugs


def _load_quality_status(report_path: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if not report_path.is_file():
        return {}
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    with report_path.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle, delimiter=";"):
            season = str(record.get("season") or "").strip()
            event_name = str(record.get("event_name") or "").strip()
            if not season or not event_name:
                continue
            tournament_id = tournament_id_for_event(event_name)
            if not tournament_id:
                continue
            out[(season, tournament_id)] = {
                "status": str(record.get("status") or "").strip(),
                "club_unknown": int(float(record.get("club_unknown") or 0)),
                "missing_player_id": int(float(record.get("missing_player_id") or 0)),
                "same_name_different_ids": int(float(record.get("same_name_different_ids") or 0)),
                "same_id_different_names": int(float(record.get("same_id_different_names") or 0)),
                "findings": str(record.get("findings") or ""),
            }
    return out


def tournament_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in _load_tournament_mapping_rows():
        tournament_id = str(item.get("id") or "").strip()
        long_name = str(item.get("long_name") or "").strip()
        if tournament_id in COVERAGE_EXCLUDED_TOURNAMENT_IDS:
            continue
        if tournament_id and long_name:
            rows.append(
                {
                    "id": tournament_id,
                    "long_name": long_name,
                    "format": str(item.get("format") or "").strip(),
                    "gender_scope": str(item.get("gender_scope") or "").strip(),
                }
            )
    return rows


def build_tournament_coverage_matrix(
    *,
    first_season: str = "04/05",
    last_season: str | None = None,
) -> Dict[str, Any]:
    seasons = iter_app_seasons(first_season=first_season, last_season=last_season)
    tournaments = tournament_rows()
    tournament_ids = [row["id"] for row in tournaments]

    work_dir = get_work_data_dir()
    data_dir = get_data_dir()
    scrape_log = legacy_scrape_dir() / "tournament_scrape_log.jsonl"
    pdf_dir = tournaments_input_dir()

    downloaded_log = _load_scrape_downloads(scrape_log)
    downloaded_registry = _load_registry_pdf_availability(pdf_dir)
    csv_available = _load_postprocessed_csv_availability(data_dir)
    gf_available, gf_slugs = _load_gf_input_availability(gf_tournaments_combined_postprocessed_csv())
    published_counts, published_slugs = _load_published_events(tournaments_postprocessed_csv())
    quality = _load_quality_status(work_dir / TOURNAMENT_DATA_QUALITY_CSV)

    cells: List[Dict[str, Any]] = []
    summary = {status: 0 for status in COVERAGE_STATUSES}

    for tournament in tournaments:
        tournament_id = tournament["id"]
        default_slug = normalize_tournament_group_name(tournament["long_name"])
        for season in seasons:
            key = (season, tournament_id)
            sources: List[str] = []
            cell = CoverageCell(status="not_available", event_slug=default_slug)

            if key in downloaded_log:
                sources.append("scrape_pdf")
            if key in downloaded_registry:
                sources.append("registry_pdf")
            if key in csv_available:
                sources.append("postprocessed_csv")
            if key in gf_available:
                sources.append("gf_input")
                cell.row_count = max(cell.row_count, gf_available[key])
                cell.event_slug = gf_slugs.get(key, default_slug)

            if key in published_counts:
                sources.append("published")
                cell.row_count = published_counts[key]
                cell.event_slug = published_slugs.get(key, "")
                q = quality.get(key)
                if q:
                    cell.validation_status = str(q.get("status") or "")
                    flaws = (
                        cell.validation_status in {"yellow", "red"}
                        or int(q.get("club_unknown") or 0) > 0
                        or int(q.get("missing_player_id") or 0) > 0
                        or int(q.get("same_name_different_ids") or 0) > 0
                        or int(q.get("same_id_different_names") or 0) > 0
                    )
                    cell.status = "published_flaws" if flaws else "published_ok"
                    if q.get("findings"):
                        cell.notes = str(q["findings"])[:240]
                else:
                    cell.status = "published_flaws"
                    cell.notes = "published (no quality report)"
            elif sources:
                cell.status = "available"
            else:
                cell.status = "not_available"

            cell.sources = list(sources)
            summary[cell.status] += 1
            cells.append(
                {
                    "tournament_id": tournament_id,
                    "tournament_name": tournament["long_name"],
                    "season": season,
                    **cell.to_dict(),
                }
            )

    return {
        "seasons": seasons,
        "tournaments": tournaments,
        "cells": cells,
        "summary": summary,
        "sources": {
            "scrape_log": str(scrape_log.resolve()) if scrape_log.is_file() else "",
            "scrape_log_present": scrape_log.is_file(),
            "pdf_dir": str(pdf_dir.resolve()) if pdf_dir.is_dir() else "",
            "gf_input": str(gf_tournaments_combined_postprocessed_csv().resolve()),
            "gf_input_present": gf_tournaments_combined_postprocessed_csv().is_file(),
            "published": str(tournaments_postprocessed_csv().resolve()),
            "published_present": data_file_exists(tournaments_postprocessed_csv()),
            "quality_report": str((work_dir / TOURNAMENT_DATA_QUALITY_CSV).resolve()),
            "quality_report_present": (work_dir / TOURNAMENT_DATA_QUALITY_CSV).is_file(),
            "download_pairs": len(downloaded_log | downloaded_registry),
            "published_pairs": len(published_counts),
        },
    }
