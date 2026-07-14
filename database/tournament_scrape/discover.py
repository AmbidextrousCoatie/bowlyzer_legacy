"""Discover Meisterschaften result PDFs on the legacy BSKV homepage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Sequence
from urllib.parse import unquote, urljoin

from database.tournament_import.source_registry import season_label
from database.tournament_scrape.categories import TournamentCategory, TournamentScrapeConfig

BASE_HOST = "http://sektion-bowling.bowling-bayern.de/dateien"
RESULT_LABEL_RE = re.compile(r"ergebnis", re.IGNORECASE)
CALENDAR_YEAR_RE = re.compile(r"bm(20\d{2})_", re.IGNORECASE)


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


@dataclass(frozen=True)
class DiscoveredPdf:
    category_id: str
    category_label: str
    label: str
    href: str
    rel_path: str
    url: str
    basename: str
    calendar_year: int | None
    score: int


def meisterschaften_index_url(folder_slug: str, liga_slug: str) -> str:
    """Primary tournament index URL (first candidate — may 404 on some seasons)."""
    from database.tournament_scrape.urls import tournament_index_candidates

    return tournament_index_candidates(folder_slug, liga_slug)[0]


def _normalize_href(href: str, *, page_url: str, folder_slug: str) -> tuple[str, str]:
    cleaned = unquote(href).replace("\\", "/").strip()
    abs_url = urljoin(page_url, cleaned)
    if "/dateien/" in abs_url:
        rel_path = abs_url.split("/dateien/", 1)[-1]
    else:
        rel_path = cleaned.lstrip("./")
        while rel_path.startswith("../"):
            rel_path = rel_path[3:]
        if not rel_path.startswith(f"saison{folder_slug}/"):
            rel_path = f"saison{folder_slug}/meisterschaften/{rel_path}"
    rel_path = rel_path.replace("\\", "/")
    return rel_path, abs_url


def _matches_any(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _calendar_year_from_href(href: str) -> int | None:
    match = CALENDAR_YEAR_RE.search(href)
    return int(match.group(1)) if match else None


def _score_candidate(label: str, href: str, *, multi_file: bool) -> int:
    basename = PurePosixPath(href).name.lower()
    score = 0
    if RESULT_LABEL_RE.search(label):
        score += 20
    if basename.endswith("_erg.pdf") or basename.endswith("_erg_neu.pdf"):
        score += 15
    if basename.endswith("_erg.xls") or basename.endswith("_erg.xlsx"):
        score += 15
    if basename.endswith("_erg_neu.pdf"):
        score += 12
    if "_akt_" in basename:
        score += 5
    if (
        not multi_file
        and re.search(r"_erg_[a-z0-9]", basename)
        and not basename.endswith("_erg_neu.pdf")
    ):
        score -= 8
    return score


def _category_for_href(
    href: str,
    config: TournamentScrapeConfig,
    categories: Sequence[TournamentCategory],
) -> TournamentCategory | None:
    if _matches_any(config.global_exclude_href_patterns, href):
        return None
    for category in categories:
        if category.exclude_href_patterns and _matches_any(category.exclude_href_patterns, href):
            continue
        if _matches_any(category.filename_patterns, href):
            return category
    return None


def _discover_exception_workbooks(
    html_text: str,
    *,
    page_url: str,
    folder_slug: str,
    config: TournamentScrapeConfig,
    category_ids: Iterable[str] | None = None,
) -> List[DiscoveredPdf]:
    from database.tournament_import.source_exceptions import exception_for_scrape_href

    wanted: set[str] | None = None
    if category_ids:
        wanted = {category_id.strip() for category_id in category_ids}

    start_year = int(folder_slug.split("-", 1)[0])
    expected_season = season_label(start_year)
    by_category = {category.id: category for category in config.categories}

    parser = _HtmlLinkParser()
    parser.feed(html_text)

    discovered: List[DiscoveredPdf] = []
    seen_paths: set[str] = set()
    for href, label in parser.links:
        if not re.search(r"\.xls[x]?$", href, re.IGNORECASE):
            continue
        exc = exception_for_scrape_href(href)
        if exc is None or exc.season != expected_season:
            continue
        rel_path, abs_url = _normalize_href(href, page_url=page_url, folder_slug=folder_slug)
        path_key = rel_path.lower()
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        basename = PurePosixPath(rel_path).name
        for target in exc.targets:
            if wanted is not None and target.category_id not in wanted:
                continue
            category = by_category.get(target.category_id)
            if category is None:
                continue
            discovered.append(
                DiscoveredPdf(
                    category_id=target.category_id,
                    category_label=category.label,
                    label=label or target.sheet,
                    href=href,
                    rel_path=rel_path,
                    url=abs_url,
                    basename=basename,
                    calendar_year=exc.calendar_year,
                    score=_score_candidate(label, rel_path, multi_file=True),
                )
            )
    return discovered


def discover_tournament_pdfs(
    html_text: str,
    *,
    page_url: str,
    folder_slug: str,
    config: TournamentScrapeConfig,
    category_ids: Iterable[str] | None = None,
) -> List[DiscoveredPdf]:
    if category_ids:
        wanted = {category_id.strip() for category_id in category_ids}
        categories = [category for category in config.categories if category.id in wanted]
    else:
        categories = list(config.categories)

    parser = _HtmlLinkParser()
    parser.feed(html_text)

    discovered: List[DiscoveredPdf] = []
    for href, label in parser.links:
        if ".pdf" not in href.lower() and not re.search(r"\.xls[x]?$", href, re.IGNORECASE):
            continue
        rel_path, abs_url = _normalize_href(href, page_url=page_url, folder_slug=folder_slug)
        category = _category_for_href(rel_path, config, categories)
        if category is None and href != rel_path:
            category = _category_for_href(href, config, categories)
        if category is None:
            continue
        basename = PurePosixPath(rel_path).name
        discovered.append(
            DiscoveredPdf(
                category_id=category.id,
                category_label=category.label,
                label=label,
                href=href,
                rel_path=rel_path,
                url=abs_url,
                basename=basename,
                calendar_year=_calendar_year_from_href(rel_path) or _calendar_year_from_href(href),
                score=_score_candidate(label, rel_path, multi_file=category.multi_file),
            )
        )
    discovered.extend(
        _discover_exception_workbooks(
            html_text,
            page_url=page_url,
            folder_slug=folder_slug,
            config=config,
            category_ids=category_ids,
        )
    )
    return discovered


def season_calendar_year(folder_slug: str) -> int:
    """Bowling season folder ``2016-17`` hosts calendar-year 2017 Meisterschaften."""
    start_year = int(folder_slug.split("-", 1)[0])
    return start_year + 1


def canonical_basename(item: DiscoveredPdf, folder_slug: str) -> str:
    """Stable flat filename for tournaments/input (avoid collisions across seasons)."""
    basename = PurePosixPath(item.rel_path).name
    if CALENDAR_YEAR_RE.search(basename):
        return basename
    year = item.calendar_year or season_calendar_year(folder_slug)
    if re.search(rf"bm{year}_", basename, re.IGNORECASE):
        return basename
    if basename.lower().startswith("bm_"):
        return f"bm{year}_{basename[3:]}"
    return f"bm{year}_{basename}"


def select_downloads(
    discovered: Sequence[DiscoveredPdf],
    config: TournamentScrapeConfig,
) -> List[DiscoveredPdf]:
    """Pick primary PDF per category/year, or keep all files for multi-file categories."""
    by_category: dict[str, TournamentCategory] = {category.id: category for category in config.categories}
    grouped: dict[tuple[str, int | None], list[DiscoveredPdf]] = {}
    for item in discovered:
        category = by_category.get(item.category_id)
        if category is None:
            continue
        key = (item.category_id, item.calendar_year)
        grouped.setdefault(key, []).append(item)

    selected: list[DiscoveredPdf] = []
    for (category_id, _year), items in sorted(grouped.items()):
        category = by_category[category_id]
        if category.multi_file:
            selected.extend(sorted(items, key=lambda row: (row.basename, -row.score)))
            continue
        best = max(items, key=lambda row: (row.score, row.basename))
        selected.append(best)
    return selected
