"""BSKV PDF Ergebnisliste parser for 2015 inline sheet layout (no round labels)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from database.tournament_import.adapters.legacy_pdf_shared import (
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

ROUND_TOTAL = re.compile(r"^\d{1}\.\d{3}$")
ROUND_TOTAL_PLAIN = re.compile(r"^\d{3,4}$")
TAIL_TOTAL_AVG = re.compile(r"^(?:(\d{1}\.\d{3})|(\d{3,4}))\s+(\d+,\d+)")
AVG_ONLY = re.compile(r"^\d+,\d+")
SYMBOL_SUFFIX = re.compile(r"[§©€]\s*$")
SUMMARY_ROUNDS = {"vorlauf", "zwischenlauf", "finale"}


@dataclass
class PlayerBlock:
    rank: int = 0
    name: str = ""
    club: str = ""
    player_id: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def _normalize_name(text: str) -> str:
    if "," not in text:
        return text.strip()
    last, first = text.split(",", 1)
    return f"{last.strip()}, {first.strip()}"


def _is_comma_name(text: str) -> bool:
    candidate = text.strip()
    return bool(candidate and "," in candidate and re.match(r"^[A-Za-zÀ-ÿ]", candidate))


def _clean_token(text: str) -> str:
    return SYMBOL_SUFFIX.sub("", text.strip()).strip()


def _is_round_total(text: str, *, after_scores: List[int] | None = None) -> bool:
    token = _clean_token(text)
    if ROUND_TOTAL.match(token):
        return True
    if ROUND_TOTAL_PLAIN.match(token):
        value = int(token)
        if value >= 500:
            return True
        # Partial Zw totals (e.g. 313 after two games, 545 after three) exceed single-game range.
        if value > 300:
            return True
        if after_scores:
            return value >= sum(after_scores)
    return False


def _is_tail_line(text: str) -> bool:
    token = _clean_token(text)
    if TAIL_TOTAL_AVG.match(token):
        return True
    return bool(AVG_ONLY.match(token))


def _is_club_token(text: str) -> bool:
    token = _clean_token(text)
    if not token or _is_comma_name(token) or is_score_token(token):
        return False
    if normalize_player_id(token) or _is_round_total(token) or _is_tail_line(token):
        return False
    if token.lower() in SUMMARY_ROUNDS:
        return False
    if re.match(r"^\d{1,3}$", token):
        return False
    return len(token) <= 80


def _player_publishable(player: Optional[PlayerBlock]) -> bool:
    return bool(
        player
        and player.name
        and player.player_id
        and any(scores for scores in player.rounds.values())
    )


def _parse_player_at(lines: List[str], idx: int) -> tuple[Optional[PlayerBlock], int]:
    if idx >= len(lines) or not _is_comma_name(lines[idx]):
        return None, idx + 1

    name = _normalize_name(lines[idx])
    idx += 1

    scores1, idx = consume_score_tokens(lines, idx, max_scores=6)
    if len(scores1) != 6:
        return None, idx
    if idx >= len(lines) or not _is_round_total(lines[idx]):
        return None, idx
    idx += 1

    if idx >= len(lines):
        return None, idx
    player_id = normalize_player_id(lines[idx])
    if not player_id:
        return None, idx + 1
    idx += 1

    player = PlayerBlock(name=name, player_id=player_id, rounds={1: scores1})

    if idx < len(lines) and is_score_token(lines[idx]):
        scores2, idx = consume_score_tokens(lines, idx, max_scores=6)
        if scores2:
            player.rounds[2] = scores2
            if idx < len(lines) and _is_round_total(lines[idx], after_scores=scores2):
                idx += 1

    if idx < len(lines) and _is_club_token(lines[idx]):
        player.club = _clean_token(lines[idx])
        idx += 1

    if idx < len(lines) and is_score_token(lines[idx]):
        scores3, idx = consume_score_tokens(lines, idx, max_scores=6)
        if scores3:
            player.rounds[3] = scores3

    if idx < len(lines) and _is_tail_line(lines[idx]):
        idx += 1

    return player, idx


def _parse_player_blocks(lines: List[str]) -> List[PlayerBlock]:
    players: List[PlayerBlock] = []
    idx = 0

    while idx < len(lines):
        raw = lines[idx].strip()
        if not _is_comma_name(raw):
            idx += 1
            continue

        player, idx = _parse_player_at(lines, idx)
        if _player_publishable(player):
            player.rank = len(players) + 1
            players.append(player)

    return players


def parse_legacy_pdf_erg_2015(source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
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


class LegacyPdfErg2015Adapter:
    format_id = "legacy_pdf_erg_2015"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        return parse_legacy_pdf_erg_2015(source, entry)
