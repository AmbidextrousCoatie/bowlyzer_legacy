"""Shared-workbook tournament source exceptions (database/config/tournament_source_exceptions.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence

from database.paths import REPO_ROOT

DEFAULT_EXCEPTIONS_PATH = REPO_ROOT / "database" / "config" / "tournament_source_exceptions.json"


@dataclass(frozen=True)
class TournamentSourceExceptionTarget:
    category_id: str
    tournament_id: str
    event_name: str
    gender: str
    sheet: str


@dataclass(frozen=True)
class TournamentSourceException:
    id: str
    file_basename: str
    season: str
    calendar_year: int
    format: str
    notes: str
    scrape_filename_pattern: re.Pattern[str]
    targets: tuple[TournamentSourceExceptionTarget, ...]


def _compile_pattern(raw: str) -> re.Pattern[str]:
    return re.compile(raw, re.IGNORECASE)


@lru_cache(maxsize=1)
def load_source_exceptions(path: str | Path | None = None) -> List[TournamentSourceException]:
    config_path = Path(path or DEFAULT_EXCEPTIONS_PATH)
    if not config_path.is_file():
        return []

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    out: List[TournamentSourceException] = []
    for item in raw.get("exceptions") or []:
        targets = tuple(
            TournamentSourceExceptionTarget(
                category_id=str(target["category_id"]),
                tournament_id=str(target["tournament_id"]),
                event_name=str(target["event_name"]),
                gender=str(target.get("gender") or ""),
                sheet=str(target["sheet"]),
            )
            for target in item.get("targets") or []
        )
        if not targets:
            continue
        out.append(
            TournamentSourceException(
                id=str(item["id"]),
                file_basename=str(item["file_basename"]),
                season=str(item["season"]),
                calendar_year=int(item["calendar_year"]),
                format=str(item["format"]),
                notes=str(item.get("notes") or ""),
                scrape_filename_pattern=_compile_pattern(str(item["scrape_filename_pattern"])),
                targets=targets,
            )
        )
    return out


def exception_for_basename(basename: str) -> TournamentSourceException | None:
    name = Path(str(basename or "").strip()).name.lower()
    for item in load_source_exceptions():
        if item.file_basename.lower() == name:
            return item
    return None


def exception_for_scrape_href(href: str) -> TournamentSourceException | None:
    text = str(href or "")
    for item in load_source_exceptions():
        if item.scrape_filename_pattern.search(text):
            return item
    return None


def lookup_exception_target(
    *,
    season: str,
    event_name: str,
) -> tuple[TournamentSourceException, TournamentSourceExceptionTarget] | None:
    season_key = (season or "").strip()
    event_key = (event_name or "").strip()
    if not season_key or not event_key:
        return None
    for item in load_source_exceptions():
        if item.season != season_key:
            continue
        for target in item.targets:
            if target.event_name == event_key:
                return item, target
    return None


def exceptions_as_registry_dicts() -> List[Dict[str, object]]:
    """Flatten exception targets into registry-shaped rows."""
    rows: List[Dict[str, object]] = []
    for item in load_source_exceptions():
        for target in item.targets:
            rows.append(
                {
                    "file_basename": item.file_basename,
                    "file_fingerprint": "",
                    "file_path": item.file_basename,
                    "season": item.season,
                    "calendar_year": item.calendar_year,
                    "category_id": target.category_id,
                    "tournament_id": target.tournament_id,
                    "event_name": target.event_name,
                    "gender": target.gender,
                    "format": item.format,
                    "enabled": True,
                    "notes": item.notes or f"exception {item.id}",
                    "legacy_event_names": (),
                    "source_sheet": target.sheet,
                }
            )
    return rows


def exceptions_for_api() -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for item in load_source_exceptions():
        payload.append(
            {
                "id": item.id,
                "file_basename": item.file_basename,
                "season": item.season,
                "calendar_year": item.calendar_year,
                "format": item.format,
                "notes": item.notes,
                "targets": [
                    {
                        "category_id": target.category_id,
                        "tournament_id": target.tournament_id,
                        "event_name": target.event_name,
                        "gender": target.gender,
                        "sheet": target.sheet,
                    }
                    for target in item.targets
                ],
            }
        )
    return payload
