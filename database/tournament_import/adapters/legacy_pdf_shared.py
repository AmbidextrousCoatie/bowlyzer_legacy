"""Shared helpers for BSKV legacy PDF Ergebnisliste adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import ROUND_LABELS_PDF_2016, season_label_from_calendar_year

DATE_HEADER = re.compile(r"^(\d{1,2}\./)?\d{1,2}\.\d{1,2}\.\d{4}$")
DATUM_PREFIX = re.compile(r"^Datum\s+(\d{1,2}\.\d{1,2}\.\d{4})\.?$", re.IGNORECASE)
DATE_RANGE = re.compile(r"^(\d+)\./(\d+)\.(\d{1,2})\.(\d{4})$")
DATE_RANGE_DASH = re.compile(
    r"^(\d{1,2})\.\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})$",
)
EVENT_TITLE = re.compile(
    r"((?:Nord|Süd|Sud|Sued)?-?bayrische|Bayerische)\s+Meisterschaft[^\n]{0,80}\d{4}",
    re.IGNORECASE,
)
INT_TOKEN = re.compile(r"^-?\d+$")
HEADER_NOISE = re.compile(
    r"^(platz|sp\s*\d|summen|schnitt|quali|seite\s+\d+|endergebnis|finale|info an)",
    re.IGNORECASE,
)


@dataclass
class PdfMeta:
    season: str
    event_name: str
    location: str
    dates: Dict[int, str]
    calendar_year: int


def pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("pymupdf is required for legacy PDF imports (pip package pymupdf)") from exc

    doc = fitz.open(path)
    text = "\n".join(doc[i].get_text("text") for i in range(doc.page_count))
    doc.close()
    return text


def pdf_text_sample(path: Path, *, max_pages: int = 2) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("pymupdf is required for legacy PDF imports (pip package pymupdf)") from exc

    doc = fitz.open(path)
    pages = min(doc.page_count, max_pages)
    text = "\n".join(doc[i].get_text("text") for i in range(pages))
    doc.close()
    return text


def parse_date_token(token: str, year: int) -> str:
    token = token.strip().rstrip(".")
    if "." not in token:
        raise ValueError(f"Invalid date token: {token!r}")
    day_s, month_s = token.split(".", 1)
    return date(year, int(month_s), int(day_s)).isoformat()


def parse_date_range(header_line: str, year: int) -> Dict[int, str]:
    line = header_line.strip().rstrip(".")
    match = DATE_RANGE.match(line)
    if match:
        day1, day2, month, yr = match.groups()
        y = int(yr)
        mo = int(month)
        d1 = date(y, mo, int(day1)).isoformat()
        d2 = date(y, mo, int(day2)).isoformat()
        return {1: d1, 2: d2, 3: d2}

    match = DATE_RANGE_DASH.match(line)
    if match:
        _day1, day2, month, yr = match.groups()
        y = int(yr)
        mo = int(month)
        d = date(y, mo, int(day2)).isoformat()
        return {1: d, 2: d, 3: d}

    if DATE_HEADER.match(line):
        token = line
        if not re.search(r"\d{4}$", token):
            token = f"{token}.{year}"
        parts = token.rsplit(".", 3)
        d = parse_date_token(f"{parts[0]}.{parts[1]}", year)
        return {1: d, 2: d, 3: d}
    raise ValueError(f"Could not parse date range from {header_line!r}")


def _header_date_line(lines: List[str]) -> str:
    for ln in lines[:12]:
        text = ln.strip()
        datum = DATUM_PREFIX.match(text)
        if datum:
            return datum.group(1)
        if DATE_HEADER.match(text) or DATE_RANGE.match(text) or DATE_RANGE_DASH.match(text):
            return text
    return ""


def _title_line(lines: Iterable[str]) -> str:
    for ln in lines:
        if EVENT_TITLE.search(ln) and "qualifizieren" not in ln.lower():
            return ln.strip()
    return ""


def extract_pdf_meta(source: Path, entry: ImportEntry, text: str) -> PdfMeta:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header_date = _header_date_line(lines)
    location = ""
    if header_date:
        try:
            idx = lines.index(header_date)
            if idx + 1 < len(lines):
                candidate = lines[idx + 1]
                if not EVENT_TITLE.search(candidate) and not DATE_HEADER.match(candidate):
                    location = candidate
        except ValueError:
            pass

    title_line = str(entry.options.get("event_name") or "").strip() or _title_line(lines)
    year_override = entry.options.get("year")
    year_match = re.search(r"(20\d{2})", title_line) or re.search(r"bm(20\d{2})", source.name, re.I)
    calendar_year = int(year_override or (year_match.group(1) if year_match else 0))
    if calendar_year <= 0:
        raise ValueError(f"Could not determine calendar year for {source.name}")

    if not title_line:
        raise ValueError(f"Could not determine event name for {source.name}")

    from database.tournament_import.adapters.legacy_pdf_erg_2016 import disambiguate_bayerische_event_name

    event_name = title_line
    if not entry.options.get("event_name"):
        event_name = disambiguate_bayerische_event_name(title_line, source, calendar_year)

    if entry.options.get("location"):
        location = str(entry.options["location"])

    dates = (
        parse_date_range(header_date, calendar_year)
        if header_date
        else {
            1: f"{calendar_year}-01-01",
            2: f"{calendar_year}-01-01",
            3: f"{calendar_year}-01-01",
        }
    )

    return PdfMeta(
        season=str(entry.options.get("season") or season_label_from_calendar_year(calendar_year)),
        event_name=event_name,
        location=location,
        dates=dates,
        calendar_year=calendar_year,
    )


def rows_from_player_rounds(
    meta: PdfMeta,
    players: Iterable[object],
    *,
    round_labels: Dict[int, tuple[str, str]] | None = None,
) -> List[Dict[str, str]]:
    labels = round_labels or ROUND_LABELS_PDF_2016
    rows: List[Dict[str, str]] = []
    for player in players:
        name = str(getattr(player, "name", "") or "").strip()
        player_id = str(getattr(player, "player_id", "") or "").strip()
        club = str(getattr(player, "club", "") or "").strip()
        rounds = getattr(player, "rounds", {}) or {}
        if not name or not player_id or not rounds:
            continue
        for round_number, scores in sorted(rounds.items()):
            _sheet_name, round_name = labels[int(round_number)]
            round_date = meta.dates.get(int(round_number), meta.dates.get(1, ""))
            for game_idx, score in enumerate(scores):
                rows.append(
                    {
                        "Season": meta.season,
                        "Date": round_date,
                        "Location": meta.location,
                        "Event Type": "tournament",
                        "Event Name": meta.event_name,
                        "Round Number": str(round_number),
                        "Round Name": round_name,
                        "Player": name,
                        "Player ID": player_id,
                        "Club": club,
                        "Game Number": str(game_idx),
                        "Score": str(score),
                        "Handicap": "0",
                    }
                )
    return rows


def is_score_token(token: str) -> bool:
    if not INT_TOKEN.match(token):
        return False
    value = int(token)
    return 0 <= value <= 300


def consume_score_tokens(lines: List[str], idx: int, *, max_scores: int = 6) -> tuple[List[int], int]:
    scores: List[int] = []
    while idx < len(lines):
        token = lines[idx].strip()
        idx += 1
        if not token:
            continue
        if is_score_token(token):
            scores.append(int(token))
            if len(scores) >= max_scores:
                break
            continue
        if scores:
            idx -= 1
            break
    return scores, idx


def normalize_player_id(raw: str) -> str:
    text = str(raw or "").strip()
    spaced = re.match(r"^(\d{2})\s+(\d{3})$", text)
    if spaced:
        return f"{spaced.group(1)}{spaced.group(2)}"
    compact = text.replace(" ", "")
    if re.match(r"^\d{5,6}$", compact):
        return compact
    return ""
