"""Cross-parser validation: PDF rank ladder vs extracted player blocks."""

from __future__ import annotations

import contextvars
import re
from typing import Iterable, List, Sequence

from database.tournament_import.adapters.legacy_pdf_shared import (
    HEADER_NOISE,
    is_score_token,
    normalize_player_id,
)

_parse_warnings: contextvars.ContextVar[List[str] | None] = contextvars.ContextVar(
    "_parse_warnings",
    default=None,
)

BLOCK_RANK_DOT_NAME = re.compile(r"^(\d{1,3})\.\s+(.+)$")
BLOCK_RANK_DOT_ONLY = re.compile(r"^(\d{1,3})\.\s*$")
BLOCK_RANK_INLINE = re.compile(r"^(\d{1,3})$")
BLOCK_RANK_SPACE_NAME = re.compile(r"^(\d{1,3})\s+(.+)$")

ROUND_ONE = re.compile(r"^(?:Vorrunde|Vor\.|Vorlauf|VL|Rd\.1)\b", re.IGNORECASE)
ROUND_TWO = re.compile(
    r"^(?:Zwi\.-?Runde|Zw-?Runde|Zwischenl\.?|Zwischenlauf|Zw\.|ZL|Rd\.2)\b",
    re.IGNORECASE,
)
ROUND_THREE = re.compile(r"^(?:Finale|Fin\.|Finalrunde|Rd\.3)\b", re.IGNORECASE)

DATE_HEADER = re.compile(r"^(\d{1,2}\./)?\d{1,2}\.\d{1,2}\.\d{4}$")
EVENT_TITLE = re.compile(r"Meisterschaft", re.IGNORECASE)
MIN_EXPECTED_PLAYERS = 5
MIN_RANK_COVERAGE = 0.85


def begin_parse_warnings() -> None:
    _parse_warnings.set([])


def extend_parse_warnings(messages: Iterable[str]) -> None:
    bucket = _parse_warnings.get()
    if bucket is not None:
        bucket.extend(messages)


def drain_parse_warnings() -> List[str]:
    bucket = _parse_warnings.get()
    if bucket is None:
        return []
    _parse_warnings.set([])
    return list(bucket)


def _looks_like_person_name(text: str) -> bool:
    candidate = text.strip()
    if not candidate or EVENT_TITLE.search(candidate):
        return False
    if ROUND_ONE.match(candidate) or ROUND_TWO.match(candidate) or ROUND_THREE.match(candidate):
        return False
    if is_score_token(candidate):
        return False
    return "," in candidate


def _is_rank_label_rest(rest: str) -> bool:
    text = rest.strip()
    if not text or DATE_HEADER.match(text) or EVENT_TITLE.search(text):
        return False
    if ROUND_ONE.match(text) or ROUND_TWO.match(text) or ROUND_THREE.match(text):
        return False
    if is_score_token(text):
        return False
    if normalize_player_id(text):
        return True
    if _looks_like_person_name(text):
        return True
    if re.match(r"^[A-Za-zÀ-ÿ]", text) and not re.match(r"^\d", text):
        return True
    return False


def _is_block_follower(text: str) -> bool:
    candidate = text.strip()
    if not candidate or HEADER_NOISE.match(candidate):
        return False
    if DATE_HEADER.match(candidate) or EVENT_TITLE.search(candidate):
        return False
    if ROUND_ONE.match(candidate) or ROUND_TWO.match(candidate) or ROUND_THREE.match(candidate):
        return False
    if is_score_token(candidate):
        return False
    if normalize_player_id(candidate):
        return True
    if _looks_like_person_name(candidate):
        return True
    if re.match(r"^[A-Za-zÀ-ÿ]", candidate):
        return True
    return False


def collect_block_start_ranks(lines: Sequence[str]) -> List[int]:
    """Collect Platz/rank integers that begin a participant block in PDF text."""
    ranks: List[int] = []
    total = len(lines)

    for idx, raw_line in enumerate(lines):
        raw = raw_line.strip()
        if not raw or HEADER_NOISE.match(raw):
            continue

        match = BLOCK_RANK_DOT_NAME.match(raw)
        if match:
            rank = int(match.group(1))
            if 1 <= rank <= 250 and _is_rank_label_rest(match.group(2)):
                ranks.append(rank)
            continue

        match = BLOCK_RANK_DOT_ONLY.match(raw)
        if match and idx + 1 < total:
            rank = int(match.group(1))
            if 1 <= rank <= 250 and _is_block_follower(lines[idx + 1]):
                ranks.append(rank)
            continue

        match = BLOCK_RANK_INLINE.match(raw)
        if match and idx + 1 < total:
            rank = int(match.group(1))
            follower = lines[idx + 1].strip()
            if (
                1 <= rank <= 250
                and "," in follower
                and re.match(r"^[A-Za-zÀ-ÿ]", follower)
                and not is_score_token(follower)
            ):
                ranks.append(rank)
            continue

        match = BLOCK_RANK_SPACE_NAME.match(raw)
        if match:
            rank = int(match.group(1))
            rest = match.group(2).strip()
            if 1 <= rank <= 250 and _is_rank_label_rest(rest):
                ranks.append(rank)

    return ranks


def expected_participant_count(ranks: Sequence[int]) -> int | None:
    """
    Infer field size from block-start ranks.

    Uses the highest rank seen when rank 1 is present and ranks 1..max have
    sufficient coverage (guards against stray integers misread as Platz).
    """
    if not ranks or 1 not in ranks:
        return None

    max_rank = max(ranks)
    seen = set(ranks)
    present = sum(1 for rank in range(1, max_rank + 1) if rank in seen)
    coverage = present / max_rank
    if max_rank < MIN_EXPECTED_PLAYERS:
        return max_rank if coverage == 1.0 else None
    if coverage < MIN_RANK_COVERAGE:
        return None
    return max_rank


def max_rounds_declared_in_pdf(lines: Sequence[str]) -> int:
    found: set[int] = set()
    for raw_line in lines:
        raw = raw_line.strip()
        if ROUND_THREE.search(raw):
            found.add(3)
        elif ROUND_TWO.search(raw):
            found.add(2)
        elif ROUND_ONE.search(raw):
            found.add(1)
    return max(found) if found else 0


def _extracted_player_count(players: Sequence[object]) -> int:
    ranked = [int(getattr(player, "rank", 0) or 0) for player in players]
    positive = [rank for rank in ranked if rank > 0]
    if positive and len(set(positive)) == len(players):
        return len(players)

    player_ids = {
        str(getattr(player, "player_id", "") or "").strip()
        for player in players
        if str(getattr(player, "player_id", "") or "").strip()
    }
    if player_ids:
        return len(player_ids)

    if positive:
        return len(set(positive))
    return len(players)


def validate_player_extraction(
    lines: Sequence[str],
    players: Sequence[object],
    *,
    source_name: str = "",
) -> List[str]:
    warnings: List[str] = []
    ranks = collect_block_start_ranks(lines)
    expected = expected_participant_count(ranks)
    extracted = _extracted_player_count(players)

    if expected is not None and expected != extracted:
        diff = expected - extracted
        sign = f"+{diff}" if diff > 0 else str(diff)
        message = (
            f"expected number of players differs ({sign}) from extracted "
            f"({expected} vs {extracted})"
        )
        if source_name:
            message = f"{source_name}: {message}"
        warnings.append(message)

    rank_one = next((player for player in players if int(getattr(player, "rank", 0) or 0) == 1), None)
    if rank_one is None and players:
        rank_one = players[0]
    if rank_one is not None:
        name = str(getattr(rank_one, "name", "") or "").strip()
        if name and not _looks_like_person_name(name):
            label = f"{source_name}: " if source_name else ""
            warnings.append(f"{label}extracted player at rank 1 looks like a club, not a person: {name!r}")

    pdf_rounds = max_rounds_declared_in_pdf(lines)
    if players and pdf_rounds:
        extracted_max = max(len(getattr(player, "rounds", {}) or {}) for player in players)
        if pdf_rounds > extracted_max:
            label = f"{source_name}: " if source_name else ""
            warnings.append(
                f"{label}PDF declares up to {pdf_rounds} round(s) but at most "
                f"{extracted_max} extracted"
            )

    return warnings


def report_player_extraction(
    lines: Sequence[str],
    players: Sequence[object],
    *,
    source_name: str = "",
) -> None:
    extend_parse_warnings(validate_player_extraction(lines, players, source_name=source_name))
