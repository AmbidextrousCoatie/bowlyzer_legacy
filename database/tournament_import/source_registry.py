"""File-based tournament source metadata (database/config/tournament_source_registry.csv)."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from database.paths import REPO_ROOT

DEFAULT_REGISTRY_PATH = REPO_ROOT / "database" / "config" / "tournament_source_registry.csv"

# Scrape category id → import metadata (tournament_mapping.csv ids + canonical labels).
CATEGORY_IMPORT_META: Dict[str, Dict[str, str]] = {
    "suedbayerische-herren": {
        "tournament_code": "sbm",
        "tournament_id": "SBM M",
        "event_name": "Südbayerische Meisterschaft",
        "gender": "male",
    },
    "nordbayerische-herren": {
        "tournament_code": "nbm",
        "tournament_id": "NBM M",
        "event_name": "Nordbayerische Meisterschaft",
        "gender": "male",
    },
    "bayerische-einzel-herren": {
        "tournament_code": "bm",
        "tournament_id": "BM M",
        "event_name_template": "Bayerische Meisterschaft Einzel {calendar_year}",
        "gender": "male",
    },
    "bayerische-einzel-frauen": {
        "tournament_code": "bm_f",
        "tournament_id": "BM D",
        "event_name_template": "Bayerische Meisterschaft Einzel Damen {calendar_year}",
        "gender": "female",
    },
    "bayerisches-doppel-herren": {
        "tournament_code": "bm_md",
        "tournament_id": "BM M D",
        "event_name_template": "Bayerische Meisterschaft Männer Doppel {calendar_year}",
        "gender": "male",
    },
    "bayerisches-doppel-frauen": {
        "tournament_code": "bm_dd",
        "tournament_id": "BM D D",
        "event_name_template": "Bayerische Meisterschaft Damen Doppel {calendar_year}",
        "gender": "female",
    },
    "bayerische-mixed": {
        "tournament_code": "bm_x",
        "tournament_id": "BM X",
        "event_name_template": "Bayerische Meisterschaft Mixed {calendar_year}",
        "gender": "mixed",
    },
}


@dataclass(frozen=True)
class TournamentSourceRow:
    file_basename: str
    file_fingerprint: str
    file_path: str
    season: str
    calendar_year: int
    category_id: str
    tournament_id: str
    event_name: str
    gender: str
    format: str
    enabled: bool
    notes: str = ""
    legacy_event_names: tuple[str, ...] = ()
    source_sheet: str = ""

    @property
    def tournament_code(self) -> str:
        meta = CATEGORY_IMPORT_META.get(self.category_id) or {}
        return str(meta.get("tournament_code") or "")


def compute_file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def season_label(season_start_year: int) -> str:
    return f"{season_start_year % 100:02d}/{(season_start_year + 1) % 100:02d}"


def event_name_for_category(category_id: str, calendar_year: int) -> str:
    meta = CATEGORY_IMPORT_META.get(category_id)
    if not meta:
        return ""
    template = meta.get("event_name_template")
    if template:
        return str(template).format(calendar_year=calendar_year)
    return str(meta.get("event_name") or "")


@lru_cache(maxsize=1)
def load_source_registry(path: str | Path | None = None) -> List[TournamentSourceRow]:
    registry_path = Path(path or DEFAULT_REGISTRY_PATH)
    if not registry_path.is_file():
        return []

    rows: List[TournamentSourceRow] = []
    with registry_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            basename = (raw.get("file_basename") or "").strip()
            if not basename:
                continue
            year_raw = (raw.get("calendar_year") or "").strip()
            try:
                calendar_year = int(year_raw)
            except ValueError:
                continue
            enabled_raw = (raw.get("enabled") or "true").strip().lower()
            legacy_raw = (raw.get("legacy_event_names") or "").strip()
            legacy_names = tuple(
                part.strip() for part in legacy_raw.split("|") if part.strip()
            )
            rows.append(
                TournamentSourceRow(
                    file_basename=basename,
                    file_fingerprint=(raw.get("file_fingerprint") or "").strip(),
                    file_path=(raw.get("file_path") or "").strip(),
                    season=(raw.get("season") or "").strip(),
                    calendar_year=calendar_year,
                    category_id=(raw.get("category_id") or "").strip(),
                    tournament_id=(raw.get("tournament_id") or "").strip(),
                    event_name=(raw.get("event_name") or "").strip(),
                    gender=(raw.get("gender") or "").strip(),
                    format=(raw.get("format") or "").strip(),
                    enabled=enabled_raw not in {"0", "false", "no"},
                    notes=(raw.get("notes") or "").strip(),
                    legacy_event_names=legacy_names,
                    source_sheet=(raw.get("source_sheet") or "").strip(),
                )
            )
    return rows


def _index_registry(rows: Sequence[TournamentSourceRow]) -> tuple[Dict[str, TournamentSourceRow], Dict[str, TournamentSourceRow]]:
    by_basename: Dict[str, TournamentSourceRow] = {}
    by_fingerprint: Dict[str, TournamentSourceRow] = {}
    for row in rows:
        if not row.enabled:
            continue
        key = row.file_basename.lower()
        by_basename[key] = row
        if row.file_fingerprint:
            by_fingerprint[row.file_fingerprint] = row
    return by_basename, by_fingerprint


@lru_cache(maxsize=1)
def registry_by_basename(path: str | Path | None = None) -> Dict[str, TournamentSourceRow]:
    by_basename, _ = _index_registry(load_source_registry(path))
    return by_basename


@lru_cache(maxsize=1)
def registry_by_fingerprint(path: str | Path | None = None) -> Dict[str, TournamentSourceRow]:
    _, by_fingerprint = _index_registry(load_source_registry(path))
    return by_fingerprint


@lru_cache(maxsize=1)
def registry_by_season_event(path: str | Path | None = None) -> Dict[tuple[str, str], TournamentSourceRow]:
    out: Dict[tuple[str, str], TournamentSourceRow] = {}
    for row in load_source_registry(path):
        if not row.enabled or not row.season or not row.event_name:
            continue
        out[(row.season, row.event_name)] = row
    return out


def lookup_source_by_season_event(
    season: str,
    event_name: str,
    *,
    registry_path: str | Path | None = None,
) -> TournamentSourceRow | None:
    season_key = (season or "").strip()
    event_key = (event_name or "").strip()
    if not season_key or not event_key:
        return None
    hit = registry_by_season_event(registry_path).get((season_key, event_key))
    if hit is not None:
        return hit
    from database.tournament_import.source_exceptions import lookup_exception_target

    exc = lookup_exception_target(season=season_key, event_name=event_key)
    if exc is None:
        return None
    item, target = exc
    return TournamentSourceRow(
        file_basename=item.file_basename,
        file_fingerprint="",
        file_path=item.file_basename,
        season=item.season,
        calendar_year=item.calendar_year,
        category_id=target.category_id,
        tournament_id=target.tournament_id,
        event_name=target.event_name,
        gender=target.gender,
        format=item.format,
        enabled=True,
        notes=item.notes,
        source_sheet=target.sheet,
    )


def lookup_source_row(source: Path, *, registry_path: str | Path | None = None) -> TournamentSourceRow | None:
    """Resolve metadata for a tournament source file (basename, then fingerprint)."""
    resolved = source.resolve()
    by_basename = registry_by_basename(registry_path)
    hit = by_basename.get(resolved.name.lower())
    if hit is not None:
        return hit
    if resolved.is_file():
        fingerprint = compute_file_fingerprint(resolved)
        return registry_by_fingerprint(registry_path).get(fingerprint)
    return None


def write_source_registry(rows: Sequence[TournamentSourceRow], path: str | Path | None = None) -> Path:
    registry_path = Path(path or DEFAULT_REGISTRY_PATH)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_basename",
        "file_fingerprint",
        "file_path",
        "season",
        "calendar_year",
        "category_id",
        "tournament_id",
        "event_name",
        "gender",
        "format",
        "enabled",
        "notes",
        "legacy_event_names",
        "source_sheet",
    ]
    with registry_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item.calendar_year, item.category_id, item.file_basename)):
            writer.writerow(
                {
                    "file_basename": row.file_basename,
                    "file_fingerprint": row.file_fingerprint,
                    "file_path": row.file_path,
                    "season": row.season,
                    "calendar_year": row.calendar_year,
                    "category_id": row.category_id,
                    "tournament_id": row.tournament_id,
                    "event_name": row.event_name,
                    "gender": row.gender,
                    "format": row.format,
                    "enabled": "true" if row.enabled else "false",
                    "notes": row.notes,
                    "legacy_event_names": "|".join(row.legacy_event_names),
                    "source_sheet": row.source_sheet,
                }
            )
    load_source_registry.cache_clear()
    registry_by_basename.cache_clear()
    registry_by_fingerprint.cache_clear()
    registry_by_season_event.cache_clear()
    return registry_path


def _registry_merge_key(row: TournamentSourceRow) -> str:
    base = row.file_basename.lower()
    if row.source_sheet:
        return f"{base}::{row.source_sheet.lower()}"
    if row.season and row.event_name:
        return f"{base}::{row.season}::{row.event_name.lower()}"
    return base


def merge_registry_rows(
    existing: Sequence[TournamentSourceRow],
    incoming: Iterable[TournamentSourceRow],
    *,
    overwrite: bool = False,
    overwrite_format: bool = False,
) -> List[TournamentSourceRow]:
    merged: Dict[str, TournamentSourceRow] = {
        _registry_merge_key(row): row for row in existing
    }
    for row in incoming:
        key = _registry_merge_key(row)
        if overwrite or key not in merged:
            merged[key] = row
            continue
        prior = merged[key]
        merged[key] = TournamentSourceRow(
            file_basename=row.file_basename,
            file_fingerprint=row.file_fingerprint or prior.file_fingerprint,
            file_path=row.file_path or prior.file_path,
            season=row.season or prior.season,
            calendar_year=row.calendar_year or prior.calendar_year,
            category_id=row.category_id or prior.category_id,
            tournament_id=row.tournament_id or prior.tournament_id,
            event_name=row.event_name or prior.event_name,
            gender=row.gender or prior.gender,
            format=(row.format if overwrite_format else prior.format or row.format),
            enabled=row.enabled,
            notes=row.notes or prior.notes,
            legacy_event_names=row.legacy_event_names or prior.legacy_event_names,
            source_sheet=row.source_sheet or prior.source_sheet,
        )
    return list(merged.values())
