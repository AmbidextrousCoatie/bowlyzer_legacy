"""Resolve legacy PDF imports from scraped flat files + tournament shorthand codes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from database.paths import get_data_dir, tournaments_input_dir
from database.tournament_import.config import ImportEntry
from database.tournament_scrape.categories import (
    TOURNAMENT_CODES,
    category_by_id,
    load_scrape_config,
    resolve_category_ids,
)
from database.tournament_scrape.discover import CALENDAR_YEAR_RE

_INVERSE_CODES = {category_id: code for code, category_id in TOURNAMENT_CODES.items()}

# Bayerische Einzel Herren/Damen PDFs share the same title line; keep merge keys distinct.
_EVENT_NAME_TEMPLATE: dict[str, str] = {
    "bm": "Bayerische Meisterschaft Einzel {year}",
    "bm_f": "Bayerische Meisterschaft Einzel Damen {year}",
}


@dataclass(frozen=True)
class LegacyPdfTarget:
    tournament_code: str
    category_id: str
    season_start_year: int
    calendar_year: int
    pdf_path: Path


@dataclass(frozen=True)
class LegacyPdfResolveSummary:
    targets: List[LegacyPdfTarget]
    missing: List[str]


def calendar_years_for_season_range(first_year: int, last_year: int) -> list[int]:
    """Season folder ``2016-17`` hosts calendar-year ``2017`` Meisterschaften."""
    if first_year > last_year:
        raise ValueError(f"first_year {first_year} must be <= last_year {last_year}")
    return [season_year + 1 for season_year in range(first_year, last_year + 1)]


def _calendar_year_from_name(name: str) -> int | None:
    match = CALENDAR_YEAR_RE.search(name)
    if match:
        return int(match.group(1))
    tail = re.search(r"(20\d{2})(?!.*20\d{2})", name)
    if tail:
        return int(tail.group(1))
    return None


def _matches_category(filename: str, category_id: str) -> bool:
    scrape_config = load_scrape_config()
    category = category_by_id(scrape_config, category_id)
    for pattern in category.filename_patterns:
        if pattern.search(filename):
            return True
    return False


def _score_candidate(filename: str) -> int:
    lower = filename.lower()
    score = 0
    if lower.endswith("_erg.pdf"):
        score += 15
    if "_akt_" in lower:
        score += 5
    if re.search(r"_erg_[a-z0-9]", lower):
        score -= 8
    return score


def resolve_legacy_pdf_targets(
    *,
    tournaments: Sequence[str],
    first_year: int,
    last_year: int,
    input_dir: Path | None = None,
) -> LegacyPdfResolveSummary:
    category_ids = resolve_category_ids(tournaments=list(tournaments)) or []
    codes = [_INVERSE_CODES[category_id] for category_id in category_ids]
    pdf_dir = (input_dir or tournaments_input_dir()).resolve()
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else []

    targets: list[LegacyPdfTarget] = []
    missing: list[str] = []

    for season_year, calendar_year in zip(
        range(first_year, last_year + 1),
        calendar_years_for_season_range(first_year, last_year),
    ):
        for code, category_id in zip(codes, category_ids):
            candidates = [
                path
                for path in pdfs
                if _calendar_year_from_name(path.name) == calendar_year
                and _matches_category(path.name, category_id)
            ]
            if not candidates:
                missing.append(
                    f"{code}:{calendar_year} (season {season_year}-{(season_year + 1) % 100:02d})"
                )
                continue
            best = max(candidates, key=lambda path: (_score_candidate(path.name), path.name))
            targets.append(
                LegacyPdfTarget(
                    tournament_code=code,
                    category_id=category_id,
                    season_start_year=season_year,
                    calendar_year=calendar_year,
                    pdf_path=best,
                )
            )

    return LegacyPdfResolveSummary(targets=targets, missing=missing)


def import_entry_for_target(target: LegacyPdfTarget) -> ImportEntry:
    options: dict = {}
    if target.tournament_code == "sbm":
        options["skip_line_patterns"] = ["Keine Teilnahme BM!"]

    template = _EVENT_NAME_TEMPLATE.get(target.tournament_code)
    if template:
        options["event_name"] = template.format(year=target.calendar_year)

    return ImportEntry(
        id=f"legacy-{target.tournament_code}-{target.calendar_year}",
        format="legacy_pdf_erg_2016",
        source=str(target.pdf_path),
        enabled=True,
        merge_target="manual",
        output=str(
            get_data_dir() / f"tournament_legacy_pdf_{target.tournament_code}_{target.calendar_year}_postprocessed.csv"
        ),
        options=options,
    )
