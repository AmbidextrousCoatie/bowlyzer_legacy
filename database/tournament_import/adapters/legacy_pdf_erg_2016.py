"""BSKV Excel-export PDF Ergebnisliste parser (2016+ vertical block layout)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import ROUND_LABELS_PDF_2016, season_label_from_calendar_year

ROUND_LINE = re.compile(
    r"^(Vorrunde|Zw-?Runde|Finalrunde)\b",
    re.IGNORECASE,
)
RANK_ONLY = re.compile(r"^(\d+)\.\s*$")
RANK_NAME = re.compile(r"^(\d+)\.\s+(.+)$")
PLAYER_ID = re.compile(r"^(\d{5})$")
INT_TOKEN = re.compile(r"^-?\d+$")
DATE_HEADER = re.compile(r"^(\d{1,2}\./)?\d{1,2}\.\d{1,2}\.\d{4}$")
EVENT_TITLE = re.compile(
    r"((?:Nord|Süd|Sud|Sued)?bayrische|Bayerische)\s+Meisterschaft.*\d{4}",
    re.IGNORECASE,
)
SKIP_LINE_BASE = (
    r"verzicht|keine teilnahme|zw-rundeabges|qualifizieren sich|stand:|auswertung:"
    r"|^platz$|^sp\s*\d|^männer$|^maenner$"
)
HEADER_NOISE = re.compile(r"^(platz|sp\s*\d|summen|schnitt|quali|seite\s+\d+|\d{1,2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})$", re.I)


def _skip_line_pattern(extra: Iterable[str] = ()) -> re.Pattern[str]:
    parts = [SKIP_LINE_BASE]
    for phrase in extra:
        text = str(phrase).strip()
        if text:
            parts.append(re.escape(text))
    return re.compile("|".join(parts), re.IGNORECASE)


@dataclass
class PdfMeta:
    season: str
    event_name: str
    location: str
    dates: Dict[int, str]
    calendar_year: int


@dataclass
class PlayerBlock:
    rank: int = 0
    name: str = ""
    club: str = ""
    player_id: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def _pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("pymupdf is required for legacy PDF imports (pip package pymupdf)") from exc

    doc = fitz.open(path)
    text = "\n".join(doc[i].get_text("text") for i in range(doc.page_count))
    doc.close()
    return text


def _parse_date_token(token: str, year: int) -> str:
    token = token.strip().rstrip(".")
    if "." not in token:
        raise ValueError(f"Invalid date token: {token!r}")
    day_s, month_s = token.split(".", 1)
    return date(year, int(month_s), int(day_s)).isoformat()


DATE_RANGE = re.compile(r"^(\d+)\./(\d+)\.(\d{1,2})\.(\d{4})$")


def _parse_date_range(header_line: str, year: int) -> Dict[int, str]:
    line = header_line.strip().rstrip(".")
    m = DATE_RANGE.match(line)
    if m:
        day1, day2, month, yr = m.groups()
        y = int(yr)
        mo = int(month)
        d1 = date(y, mo, int(day1)).isoformat()
        d2 = date(y, mo, int(day2)).isoformat()
        return {1: d1, 2: d2, 3: d2}

    # fallback: single date token d.m.yyyy
    if DATE_HEADER.match(line):
        token = line
        if not re.search(r"\d{4}$", token):
            token = f"{token}.{year}"
        d = _parse_date_token(token.rsplit(".", 3)[0] + "." + token.rsplit(".", 3)[1], year)
        return {1: d, 2: d, 3: d}
    raise ValueError(f"Could not parse date range from {header_line!r}")


_BAYERISCHE_MEISTERSCHAFT = re.compile(r"^Bayerische\s+Meisterschaft\b", re.IGNORECASE)
_TOKEN_BOUNDARY = r"(?:_|\.|$)"
_WOMEN_PDF_RE = re.compile(
    rf"einz_(?:da|f){_TOKEN_BOUNDARY}|einzel_(?:da|f){_TOKEN_BOUNDARY}|_da_",
    re.IGNORECASE,
)
_MEN_PDF_RE = re.compile(
    rf"einz_he{_TOKEN_BOUNDARY}|einzel_he{_TOKEN_BOUNDARY}|_he_erg",
    re.IGNORECASE,
)


def disambiguate_bayerische_event_name(
    event_name: str,
    source: Path,
    calendar_year: int,
) -> str:
    """
    PDF titles for Bayerische Meisterschaft Herren and Damen are often identical
    (e.g. ``Bayerische Meisterschaft 2017``). Use filename tokens to split them.
    """
    title = event_name.strip()
    if not title or not _BAYERISCHE_MEISTERSCHAFT.match(title):
        return title

    filename = source.name.lower()
    is_women = bool(_WOMEN_PDF_RE.search(filename))
    is_men = bool(_MEN_PDF_RE.search(filename)) and not is_women
    if not is_women and not is_men:
        return title

    if is_women:
        if re.search(r"damen|frauen", title, re.IGNORECASE):
            return title
        if re.search(r"einzel", title, re.IGNORECASE):
            return re.sub(
                r"(Bayerische\s+Meisterschaft\s+Einzel)\s+",
                r"\1 Damen ",
                title,
                count=1,
                flags=re.IGNORECASE,
            )
        return f"Bayerische Meisterschaft Einzel Damen {calendar_year}"

    if re.search(r"einzel", title, re.IGNORECASE):
        return title
    return f"Bayerische Meisterschaft Einzel {calendar_year}"


def _extract_meta(text: str, entry: ImportEntry, source: Path) -> PdfMeta:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header_date = next((ln for ln in lines[:8] if DATE_HEADER.match(ln)), "")
    location = ""
    if header_date and lines.index(header_date) + 1 < len(lines):
        location = lines[lines.index(header_date) + 1]

    title_line = ""
    for ln in lines:
        if EVENT_TITLE.search(ln) and "qualifizieren" not in ln.lower():
            title_line = ln.strip()
            break

    year_override = entry.options.get("year")
    year_match = re.search(r"(20\d{2})", title_line) or re.search(r"bm(20\d{2})", source.name, re.I)
    calendar_year = int(year_override or (year_match.group(1) if year_match else 0))
    if calendar_year <= 0:
        raise ValueError(f"Could not determine calendar year for {source.name}")

    event_name = str(entry.options.get("event_name") or "").strip() or title_line
    if not event_name:
        raise ValueError(f"Could not determine event name for {source.name}")
    if not entry.options.get("event_name"):
        event_name = disambiguate_bayerische_event_name(event_name, source, calendar_year)

    dates = _parse_date_range(header_date, calendar_year) if header_date else {
        1: f"{calendar_year}-01-01",
        2: f"{calendar_year}-01-01",
        3: f"{calendar_year}-01-01",
    }
    if entry.options.get("location"):
        location = str(entry.options["location"])

    return PdfMeta(
        season=str(entry.options.get("season") or season_label_from_calendar_year(calendar_year)),
        event_name=event_name,
        location=location,
        dates=dates,
        calendar_year=calendar_year,
    )


def _round_label_and_first_score(raw: str) -> Tuple[str, Optional[int]]:
    match = re.match(r"^(Vorrunde|Zw-?Runde|Finalrunde)\b\s*(\d{1,3})?", raw, flags=re.IGNORECASE)
    if not match:
        return "", None
    label = match.group(1).lower()
    first_score = int(match.group(2)) if match.group(2) else None
    return label, first_score


def _is_score_token(token: str) -> bool:
    if not INT_TOKEN.match(token):
        return False
    value = int(token)
    return 0 <= value <= 300


def _line_contains_game_scores(raw: str) -> bool:
    """True when the line is score data (not a player/club name)."""
    if ROUND_LINE.match(raw):
        return True
    tokens = raw.split()
    if not tokens:
        return False
    score_tokens = [token for token in tokens if _is_score_token(token)]
    if not score_tokens:
        return False
    if len(score_tokens) == len(tokens):
        return True
    return len(tokens) == 1 and _is_score_token(tokens[0])


def _club_from_line(raw: str, tournament_rank: int) -> str:
    """Club lines may embed a Verein list prefix: ``1. BBV Lindau``."""
    rank_name = RANK_NAME.match(raw)
    if rank_name:
        prefix_rank = int(rank_name.group(1))
        if prefix_rank < tournament_rank:
            return rank_name.group(2).strip()
    return raw.strip()


def _consume_scores(
    lines: List[str],
    idx: int,
    first_score: Optional[int],
    skip_line: re.Pattern[str],
) -> Tuple[List[int], int]:
    scores: List[int] = []
    if first_score is not None and _is_score_token(str(first_score)):
        scores.append(int(first_score))
    while idx < len(lines):
        token = lines[idx].strip()
        if not token or skip_line.search(token):
            idx += 1
            continue
        if (
            RANK_ONLY.match(token)
            or RANK_NAME.match(token)
            or ROUND_LINE.match(token)
            or PLAYER_ID.match(token)
        ):
            break
        if token in {"/"}:
            idx += 1
            break
        if not _is_score_token(token):
            if scores:
                break
            idx += 1
            continue
        scores.append(int(token))
        idx += 1
        if len(scores) >= 6:
            break
    return scores, idx


def _parse_player_blocks(
    lines: List[str],
    *,
    extra_skip_patterns: Iterable[str] = (),
) -> List[PlayerBlock]:
    skip_line = _skip_line_pattern(extra_skip_patterns)
    players: List[PlayerBlock] = []
    current: Optional[PlayerBlock] = None
    pending_new_rank: Optional[int] = None
    expect_club = False
    expect_id = False
    idx = 0

    def _player_complete(player: Optional[PlayerBlock]) -> bool:
        return bool(
            player
            and player.name
            and player.player_id
            and player.rounds
        )

    def _start_player(rank: int, name: str = "") -> None:
        nonlocal current, pending_new_rank
        current = PlayerBlock(rank=rank, name=name.strip())
        players.append(current)
        pending_new_rank = None

    skip_page_reheader = False

    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw or HEADER_NOISE.match(raw) or skip_line.search(raw):
            continue
        if DATE_HEADER.match(raw) or DATE_RANGE.match(raw):
            if players:
                skip_page_reheader = True
            continue
        if skip_page_reheader:
            if RANK_NAME.match(raw):
                skip_page_reheader = False
            else:
                continue
        if raw in {"/"} or re.match(r"^\d+,\d{2}$", raw):
            continue

        if expect_club and current is not None:
            expect_club = False
            current.club = _club_from_line(raw, current.rank)
            continue

        if expect_id and current is not None:
            expect_id = False
            id_match = PLAYER_ID.match(raw)
            if id_match:
                current.player_id = id_match.group(1)
            continue

        if current is not None and current.rounds and not current.player_id and not expect_id:
            id_match = PLAYER_ID.match(raw)
            if id_match:
                current.player_id = id_match.group(1)
                continue

        if INT_TOKEN.match(raw) and int(raw) > 300:
            continue

        rank_name = RANK_NAME.match(raw)
        if rank_name:
            rank = int(rank_name.group(1))
            rest = rank_name.group(2).strip()
            if DATE_HEADER.match(rest) or DATE_RANGE.match(rest) or rest.startswith("/"):
                continue
            if not ROUND_LINE.match(rest) and not PLAYER_ID.match(rest):
                if current is None or _player_complete(current) or rank > (current.rank if current else 0):
                    _start_player(rank, rest)
                    continue

        rank_match = RANK_ONLY.match(raw)
        if rank_match:
            rank = int(rank_match.group(1))
            if current is not None and rank == current.rank:
                if 1 in current.rounds and not current.club:
                    expect_club = True
                elif 2 in current.rounds and not current.player_id:
                    expect_id = True
                continue
            if current is None or (_player_complete(current) and rank > current.rank):
                pending_new_rank = rank
            continue

        if pending_new_rank is not None:
            if ROUND_LINE.match(raw) or PLAYER_ID.match(raw) or _line_contains_game_scores(raw):
                pending_new_rank = None
            elif not RANK_ONLY.match(raw):
                _start_player(pending_new_rank, raw)
                continue

        round_match = ROUND_LINE.match(raw)
        if round_match and current is not None:
            label, first_score = _round_label_and_first_score(raw)
            if label.startswith("vor"):
                pending_round = 1
            elif label.startswith("zw"):
                pending_round = 2
            else:
                if 3 in current.rounds:
                    continue
                pending_round = 3
            scores, idx = _consume_scores(lines, idx, first_score, skip_line)
            if scores:
                current.rounds[pending_round] = scores
            continue

        if current is None:
            continue

        if not current.name and 1 not in current.rounds:
            if PLAYER_ID.match(raw) or ROUND_LINE.match(raw):
                continue
            current.name = raw
            continue

        if 1 in current.rounds and not current.club and not expect_club:
            if ROUND_LINE.match(raw) or PLAYER_ID.match(raw) or RANK_ONLY.match(raw):
                continue
            if not _line_contains_game_scores(raw):
                current.club = _club_from_line(raw, current.rank)
            continue

    return [p for p in players if p.name and p.player_id and p.rounds]


def _extra_skip_patterns(entry: ImportEntry) -> List[str]:
    raw = entry.options.get("skip_line_patterns") or []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw]


def _rows_from_players(meta: PdfMeta, players: Iterable[PlayerBlock]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for player in players:
        for round_number, scores in sorted(player.rounds.items()):
            _sheet_name, round_name = ROUND_LABELS_PDF_2016[round_number]
            round_date = meta.dates.get(round_number, meta.dates.get(1, ""))
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
                        "Player": player.name.strip(),
                        "Player ID": player.player_id,
                        "Club": player.club.strip(),
                        "Game Number": str(game_idx),
                        "Score": str(score),
                        "Handicap": "0",
                    }
                )
    return rows


def parse_legacy_pdf_erg_2016(source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
    if not source.is_file():
        raise FileNotFoundError(source)
    text = _pdf_text(source)
    meta = _extract_meta(text, entry, source)
    lines = [ln.strip() for ln in text.splitlines()]
    players = _parse_player_blocks(lines, extra_skip_patterns=_extra_skip_patterns(entry))
    if not players:
        raise ValueError(f"No player blocks parsed from {source.name}")
    return _rows_from_players(meta, players)


class LegacyPdfErg2016Adapter:
    format_id = "legacy_pdf_erg_2016"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        return parse_legacy_pdf_erg_2016(source, entry)
