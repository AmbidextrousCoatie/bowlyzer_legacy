"""BSKV PDF Ergebnisliste parser for 2009–2015 comma-name / Zwi.-Runde layout."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from database.tournament_import.adapters.legacy_pdf_shared import (
    extract_pdf_meta,
    is_score_token,
    normalize_player_id,
    pdf_text,
    rows_from_player_rounds,
)
from database.tournament_import.adapters.legacy_pdf_validation import report_player_extraction
from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import ROUND_LABELS_PDF_2016

LOCAL_HEADER_NOISE = re.compile(
    r"^(platz|sp\s*\d|summen|schnitt|quali|seite\s+\d+|endergebnis|info an)",
    re.IGNORECASE,
)

RANK_ONLY = re.compile(r"^(\d+)\.\s*$")
RANK_NAME = re.compile(r"^(\d+)\.\s+(.+)$")
ROUND_ONE = re.compile(r"^(?:Vorrunde|Vor\.|VL)(?:\s|$)", re.IGNORECASE)
ROUND_TWO = re.compile(r"^(?:Zwi\.-Runde|Zw\.|ZL|Zwischenlauf)(?:\s|$)", re.IGNORECASE)
ROUND_THREE = re.compile(r"^(?:Finale|Fin\.|Finalrunde)(?:\s|$)", re.IGNORECASE)
DECIMAL_AVERAGE = re.compile(r"^\d+,\d{2}$")
THOUSAND_SUM = re.compile(r"^\d+\.\d{3}$")
SYMBOL_LINE = re.compile(r"^[§©€]\s*$")
SKIP_LINE = re.compile(
    r"^(stand:|platz|pins|cut|endergebnis|/ \d+|info an|sp\.\d|quali|gratulation)",
    re.IGNORECASE,
)
LAYOUT_FOOTER_NUMBER = re.compile(r"^\d{1,3}$")
INT_TOKEN = re.compile(r"^-?\d+$")
INLINE_RANK = re.compile(r"^\d{1,3}$")
INLINE_ROUND_ONE = re.compile(r"^(?:Vorrunde|Vorlauf|Vor\.|VL)\.?$", re.IGNORECASE)
INLINE_ROUND_TWO = re.compile(
    r"^(?:Zwi\.-Runde|Zw-?Runde|Zwischenl\.?|Zwischenlauf|Zw\.|ZL)\.?$",
    re.IGNORECASE,
)
INLINE_ROUND_THREE = re.compile(r"^(?:Finale|Fin\.|Finalrunde)\.?$", re.IGNORECASE)


@dataclass
class PlayerBlock:
    rank: int = 0
    name: str = ""
    club: str = ""
    player_id: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def _looks_like_person_name(text: str) -> bool:
    candidate = text.strip()
    if not candidate:
        return False
    if ROUND_ONE.match(candidate) or ROUND_TWO.match(candidate) or ROUND_THREE.match(candidate):
        return False
    if is_score_token(candidate):
        return False
    return "," in candidate


def _is_player_name(text: str) -> bool:
    return _looks_like_person_name(text)


def _is_series_total(raw: str) -> bool:
    """Round or running pin total — not a player pass number."""
    text = raw.strip()
    if THOUSAND_SUM.match(text):
        return True
    if re.match(r"^\d{3,4}$", text):
        return 500 <= int(text) <= 9999
    return False


def _is_cut_diff(raw: str) -> bool:
    """Qualification margin after a summary block — never a game score."""
    text = raw.strip()
    if not INT_TOKEN.match(text):
        return False
    return int(text) < 0


def _player_publishable(player: Optional[PlayerBlock]) -> bool:
    return bool(
        player
        and player.name
        and player.player_id
        and any(scores for scores in player.rounds.values())
    )


def _flush_player(players: List[PlayerBlock], current: Optional[PlayerBlock]) -> None:
    if _player_publishable(current):
        players.append(current)


def _consume_round_scores(lines: List[str], idx: int, *, max_scores: int = 6) -> tuple[List[int], int]:
    scores: List[int] = []
    while idx < len(lines):
        token = lines[idx].strip()
        if not token:
            idx += 1
            continue
        if ROUND_ONE.match(token) or ROUND_TWO.match(token) or ROUND_THREE.match(token):
            break
        if _is_player_name(token):
            break
        if normalize_player_id(token):
            break
        if _is_series_total(token) or token == "/":
            break
        if is_score_token(token):
            scores.append(int(token))
            idx += 1
            if len(scores) >= max_scores:
                break
            continue
        if scores:
            break
        idx += 1
    return scores, idx


def _skip_round_summary_tail(lines: List[str], idx: int) -> int:
    """Skip total / N / average / cut-diff lines after a summary-only round."""
    while idx < len(lines):
        token = lines[idx].strip()
        if not token:
            idx += 1
            continue
        if _is_player_name(token):
            break
        rank_name = RANK_NAME.match(token)
        if rank_name and _is_player_name(rank_name.group(2)):
            break
        if ROUND_ONE.match(token):
            break
        if normalize_player_id(token) and not _is_series_total(token):
            break
        if _is_series_total(token) or token == "/" or token.startswith("/"):
            idx += 1
            continue
        if DECIMAL_AVERAGE.match(token) or _is_cut_diff(token):
            idx += 1
            continue
        if INT_TOKEN.match(token) and not is_score_token(token) and not _is_series_total(token):
            # Positive cut margins after averages (e.g. 15, 117) — not game scores.
            idx += 1
            continue
        if LAYOUT_FOOTER_NUMBER.match(token):
            idx += 1
            continue
        if is_score_token(token):
            break
        idx += 1
    return idx


def _try_assign_player_id(current: PlayerBlock, raw: str) -> bool:
    player_id = normalize_player_id(raw)
    if player_id and not current.player_id:
        current.player_id = player_id
        return True
    return False


def _resolve_rank(rank: int, players: List[PlayerBlock]) -> int:
    """Bump rank when PDF page seams repeat the prior Platz number."""
    seen = {player.rank for player in players if player.rank > 0}
    while rank in seen:
        rank += 1
    return rank


def _start_player(
    players: List[PlayerBlock],
    current: Optional[PlayerBlock],
    *,
    rank: int,
    name: str,
) -> PlayerBlock:
    _flush_player(players, current)
    return PlayerBlock(rank=_resolve_rank(rank, players), name=name.strip())


def _is_sbm_2006_vor_zw_fin_layout(lines: List[str]) -> bool:
    from database.tournament_import.adapters.legacy_pdf_sbm_2006 import (
        is_sbm_2006_vor_zw_fin_layout,
    )

    return is_sbm_2006_vor_zw_fin_layout(lines)


def _find_game_detail_section_start(lines: List[str]) -> Optional[int]:
    """
    SBM 2007-style PDFs: summary table first, then per-game detail after a
    second ``Platz`` header with ``1.`` / name / ``Vorrunde``.
    """
    for idx in range(len(lines) - 4):
        if lines[idx].strip() != "Platz":
            continue
        if not RANK_ONLY.match(lines[idx + 1].strip()):
            continue
        if not _is_player_name(lines[idx + 2].strip()):
            continue
        if not ROUND_ONE.match(lines[idx + 3].strip()):
            continue
        return idx
    return None


def _is_dual_summary_detail_layout(lines: List[str]) -> bool:
    head = "\n".join(lines[:12])
    return "Platz Name" in head and "Vorrunde Zw.-runde" in head


def _is_score_column_header_row(lines: List[str], idx: int, raw: str) -> bool:
    """True when a lone 1–6 is a Sp-column header, not a player rank."""
    if raw not in {str(n) for n in range(1, 7)}:
        return False
    j = idx
    while j < len(lines):
        nxt = lines[j].strip()
        if not nxt:
            j += 1
            continue
        if nxt in {str(n) for n in range(1, 7)}:
            return True
        if nxt in {"Ges.", "Ges", "Gesamt", "Total", "Schnitt", "Hdcp"}:
            return True
        return False
    return False


def _is_inline_name(text: str) -> bool:
    return _is_player_name(text) or _is_plain_name(text)


def _is_plain_name(text: str) -> bool:
    candidate = text.strip()
    if not candidate or "," in candidate:
        return False
    if (
        INLINE_ROUND_ONE.match(candidate)
        or INLINE_ROUND_TWO.match(candidate)
        or INLINE_ROUND_THREE.match(candidate)
    ):
        return False
    if is_score_token(candidate) or _is_series_total(candidate):
        return False
    if normalize_player_id(candidate):
        return False
    if not re.match(r"^[A-Za-zÀ-ÿ]", candidate):
        return False
    return len(candidate.split()) >= 2


def _parse_inline_rank_blocks(lines: List[str]) -> List[PlayerBlock]:
    players: List[PlayerBlock] = []
    current: Optional[PlayerBlock] = None
    pending_rank: Optional[int] = None
    idx = 0

    def flush() -> None:
        nonlocal current
        _flush_player(players, current)
        current = None

    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw or LOCAL_HEADER_NOISE.match(raw) or SKIP_LINE.search(raw):
            continue
        if DECIMAL_AVERAGE.match(raw) or THOUSAND_SUM.match(raw) or SYMBOL_LINE.match(raw):
            continue
        if _is_cut_diff(raw):
            continue
        if raw in {"Name", "Verein", "Platz", "Ges.", "Gesamt", "Total", "Schnitt", "Hdcp"}:
            continue
        if INLINE_RANK.match(raw) and _is_score_column_header_row(lines, idx, raw):
            continue

        if INLINE_RANK.match(raw):
            rank = int(raw)
            if 1 <= rank <= 200 and idx < len(lines) and _is_inline_name(lines[idx].strip()):
                flush()
                pending_rank = _resolve_rank(rank, players)
                continue

        if pending_rank is not None and _is_inline_name(raw):
            current = PlayerBlock(rank=pending_rank, name=raw.strip())
            pending_rank = None
            continue

        if current is None:
            continue

        if not current.player_id:
            player_id = normalize_player_id(raw)
            if player_id and not INLINE_ROUND_ONE.match(raw):
                current.player_id = player_id
                continue

        if (
            not current.club
            and not is_score_token(raw)
            and not _is_series_total(raw)
            and not INLINE_ROUND_ONE.match(raw)
            and not INLINE_ROUND_TWO.match(raw)
            and not INLINE_ROUND_THREE.match(raw)
            and not normalize_player_id(raw)
            and len(raw) <= 80
        ):
            current.club = raw.strip()
            continue

        if INLINE_ROUND_ONE.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            if scores:
                current.rounds[1] = scores
            continue

        if INLINE_ROUND_TWO.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            current.rounds[2] = scores
            continue

        if INLINE_ROUND_THREE.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            current.rounds[3] = scores
            if not scores:
                idx = _skip_round_summary_tail(lines, idx)
            flush()
            continue

    flush()
    return players


def _parse_player_blocks(lines: List[str]) -> List[PlayerBlock]:
    players: List[PlayerBlock] = []
    current: Optional[PlayerBlock] = None
    pending_rank: Optional[int] = None
    expect_verein = False
    expect_player_id = False
    idx = 0

    while idx < len(lines):
        raw = lines[idx].strip()
        idx += 1
        if not raw or LOCAL_HEADER_NOISE.match(raw) or SKIP_LINE.search(raw):
            continue
        if DECIMAL_AVERAGE.match(raw) or THOUSAND_SUM.match(raw) or SYMBOL_LINE.match(raw):
            continue
        if _is_cut_diff(raw):
            continue

        if current is None and LAYOUT_FOOTER_NUMBER.match(raw):
            continue

        rank_name = RANK_NAME.match(raw)
        if rank_name and _is_player_name(rank_name.group(2)):
            current = _start_player(
                players,
                current,
                rank=int(rank_name.group(1)),
                name=rank_name.group(2),
            )
            expect_verein = False
            expect_player_id = False
            continue

        if RANK_ONLY.match(raw):
            rank = int(RANK_ONLY.match(raw).group(1))
            if current is not None and current.name and 1 not in current.rounds:
                continue
            pending_rank = _resolve_rank(rank, players)
            continue

        if pending_rank is not None:
            if _is_player_name(raw):
                current = _start_player(players, current, rank=pending_rank, name=raw)
                pending_rank = None
                expect_verein = False
                expect_player_id = False
            continue

        if _is_player_name(raw):
            rank = pending_rank if pending_rank is not None else len(players) + 1
            if pending_rank is None:
                rank = _resolve_rank(rank, players)
            current = _start_player(players, current, rank=rank, name=raw)
            pending_rank = None
            expect_verein = False
            expect_player_id = False
            continue

        if current is None:
            continue

        if expect_verein:
            if _is_series_total(raw):
                continue
            if ROUND_TWO.match(raw):
                expect_verein = False
                idx -= 1
                continue
            if not is_score_token(raw) and not ROUND_THREE.match(raw):
                current.club = raw.strip()
            expect_verein = False
            continue

        if expect_player_id:
            if _is_series_total(raw):
                continue
            if _try_assign_player_id(current, raw):
                expect_player_id = False
                continue
            if ROUND_THREE.match(raw):
                expect_player_id = False
                idx -= 1
                continue
            continue

        if _try_assign_player_id(current, raw):
            continue

        if ROUND_ONE.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            if scores:
                current.rounds[1] = scores
                expect_verein = True
            continue

        if ROUND_TWO.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            current.rounds[2] = scores
            expect_player_id = bool(scores)
            continue

        if ROUND_THREE.match(raw):
            scores, idx = _consume_round_scores(lines, idx)
            current.rounds[3] = scores
            if not scores:
                idx = _skip_round_summary_tail(lines, idx)
            _flush_player(players, current)
            current = None
            expect_verein = False
            expect_player_id = False
            continue

    _flush_player(players, current)

    return players


def parse_legacy_pdf_erg_2009(source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
    if not source.is_file():
        raise FileNotFoundError(source)
    text = pdf_text(source)
    meta = extract_pdf_meta(source, entry, text)
    lines = [ln.strip() for ln in text.splitlines()]
    if _is_sbm_2006_vor_zw_fin_layout(lines):
        from database.tournament_import.adapters.legacy_pdf_sbm_2006 import (
            pdf_column_text_lines,
            parse_sbm_2006_vor_zw_fin_blocks,
        )

        column_lines = pdf_column_text_lines(source)
        players = parse_sbm_2006_vor_zw_fin_blocks(column_lines)
        if not players:
            raise ValueError(f"No player blocks parsed from {source.name}")
        report_player_extraction(lines, players, source_name=source.name)
        return rows_from_player_rounds(meta, players, round_labels=ROUND_LABELS_PDF_2016)
    if _is_dual_summary_detail_layout(lines):
        detail_start = _find_game_detail_section_start(lines)
        if detail_start is not None:
            lines = lines[detail_start:]
    players = _parse_player_blocks(lines)
    if len(players) < 10:
        inline = _parse_inline_rank_blocks(lines)
        if len(inline) >= 10 and len(inline) > len(players):
            players = inline
    if not players:
        raise ValueError(f"No player blocks parsed from {source.name}")
    report_player_extraction(lines, players, source_name=source.name)
    return rows_from_player_rounds(meta, players, round_labels=ROUND_LABELS_PDF_2016)


class LegacyPdfErg2009Adapter:
    format_id = "legacy_pdf_erg_2009"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        return parse_legacy_pdf_erg_2009(source, entry)
