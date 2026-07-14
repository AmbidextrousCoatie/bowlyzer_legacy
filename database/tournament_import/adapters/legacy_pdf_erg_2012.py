"""BSKV PDF Ergebnisliste parser for 2012 wide-grid Rd.1/Rd.2/Rd.3 layout."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from database.tournament_import.adapters.legacy_pdf_shared import (
    HEADER_NOISE,
    consume_score_tokens,
    extract_pdf_meta,
    is_score_token,
    normalize_player_id,
    pdf_text,
    rows_from_player_rounds,
)
from database.tournament_import.adapters.legacy_pdf_validation import report_player_extraction
from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import ROUND_LABELS_PDF_2016

ROUND_ONE = re.compile(r"^Rd\.1$", re.IGNORECASE)
ROUND_TWO = re.compile(r"^Rd\.2$", re.IGNORECASE)
ROUND_THREE = re.compile(r"^Rd\.3$", re.IGNORECASE)
DECIMAL_AVERAGE = re.compile(r"^[§€]?\s*\d+,\d+$")
SKIP_LINE = re.compile(
    r"^(sp\.\d|summen|schnitt|quali|zur bm|platz\s+\d|info an)",
    re.IGNORECASE,
)
NAME_LINE = re.compile(r"^[A-Za-zÀ-ÿ].+ [A-Za-zÀ-ÿ].+$")


@dataclass
class PlayerBlock:
    rank: int = 0
    name: str = ""
    club: str = ""
    player_id: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def _is_name_line(text: str) -> bool:
    candidate = text.strip()
    if not candidate or ROUND_ONE.match(candidate) or ROUND_TWO.match(candidate) or ROUND_THREE.match(candidate):
        return False
    if candidate.lower().startswith("club -"):
        return False
    if is_score_token(candidate) or DECIMAL_AVERAGE.match(candidate):
        return False
    if SKIP_LINE.search(candidate):
        return False
  # Verein lines often contain "e.V." but player names are "First Last"
    if " e.V." in candidate or candidate.startswith("1.") or candidate.startswith("BV "):
        return False
    return bool(NAME_LINE.match(candidate))


def _player_complete(player: Optional[PlayerBlock]) -> bool:
    return bool(
        player
        and player.name
        and player.player_id
        and 1 in player.rounds
        and 2 in player.rounds
        and 3 in player.rounds
    )


def _parse_player_blocks(lines: List[str]) -> List[PlayerBlock]:
    players: List[PlayerBlock] = []
    current: Optional[PlayerBlock] = None
    pending_name: str = ""
    verein: str = ""
    idx = 0

    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw or HEADER_NOISE.match(raw) or SKIP_LINE.search(raw):
            continue
        if DECIMAL_AVERAGE.match(raw):
            continue
        if raw in {"0", "1", "2", "3"} and current is not None and 3 in current.rounds:
            continue

        if ROUND_ONE.match(raw):
            if pending_name:
                if current and _player_complete(current):
                    players.append(current)
                current = PlayerBlock(rank=len(players) + 1, name=pending_name, club=verein)
                verein = ""
                pending_name = ""
            if current is None:
                continue
            scores, idx = consume_score_tokens(lines, idx)
            if scores:
                current.rounds[1] = scores
            continue

        if ROUND_TWO.match(raw):
            if current is None:
                continue
            scores, idx = consume_score_tokens(lines, idx)
            if scores:
                current.rounds[2] = scores
            continue

        if ROUND_THREE.match(raw):
            if current is None:
                continue
            scores, idx = consume_score_tokens(lines, idx)
            if scores:
                current.rounds[3] = scores
            continue

        player_id = normalize_player_id(raw)
        if player_id and current is not None and 3 in current.rounds and not current.player_id:
            current.player_id = player_id
            if not current.club and verein:
                current.club = verein
            if _player_complete(current):
                players.append(current)
                current = None
                verein = ""
            continue

        if raw.lower().startswith("club -"):
            if current is not None:
                current.club = raw
            continue

        if _is_name_line(raw):
            pending_name = raw
            continue

        if current is None and pending_name and not is_score_token(raw):
            verein = raw
            continue

        if current is not None and 1 in current.rounds and 2 not in current.rounds and not current.club:
            if not is_score_token(raw) and not ROUND_TWO.match(raw):
                verein = raw
                continue

    if current and _player_complete(current):
        players.append(current)

    return players


def parse_legacy_pdf_erg_2012(source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
    if not source.is_file():
        raise FileNotFoundError(source)
    text = pdf_text(source)
    meta = extract_pdf_meta(source, entry, text)
    lines = [ln.strip() for ln in text.splitlines()]
    players = _parse_player_blocks(lines)
    if not players:
        raise ValueError(f"No player blocks parsed from {source.name}")
    report_player_extraction(lines, players, source_name=source.name)
    return rows_from_player_rounds(meta, players, round_labels=ROUND_LABELS_PDF_2016)


class LegacyPdfErg2012Adapter:
    format_id = "legacy_pdf_erg_2012"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        return parse_legacy_pdf_erg_2012(source, entry)
