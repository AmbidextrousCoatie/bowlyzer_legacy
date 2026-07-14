"""SBM 2006 multi-column Vor./Zw./Fin. layout (spaced EDV-Nr, surname/first name split)."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence

from database.tournament_import.adapters.legacy_pdf_erg_2009 import PlayerBlock
from database.tournament_import.adapters.legacy_pdf_shared import is_score_token

SBM06_VOR = re.compile(r"^Vor\.?$", re.IGNORECASE)
SBM06_ZW = re.compile(r"^Zw\.?$", re.IGNORECASE)
SBM06_FIN = re.compile(r"^Fin\.?$", re.IGNORECASE)
SBM06_VOR_LINE = re.compile(r"^Vor\.\s+(.+)$", re.IGNORECASE)
SBM06_ZW_LINE = re.compile(r"^(?:(.+?)\s+)?Zw\.\s+(.+)$", re.IGNORECASE)
SBM06_AVG = re.compile(r"^\d+,\d{2}$")
SBM06_THOUSAND = re.compile(r"^\d{1}\.\d{3}$")
SBM06_RANK = re.compile(r"^\d{1,3}$")
SBM06_RANK_NAME = re.compile(r"^(\d{1,3})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-.]*)$")
SBM06_ID_PART = re.compile(r"^\d{2}$")
SBM06_NAME = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-.]*$")
SBM06_ROUND_WORDS = {"vor", "zw", "fin"}


def _is_person_name_token(token: str) -> bool:
    cleaned = token.rstrip(".")
    if cleaned.lower() in SBM06_ROUND_WORDS:
        return False
    return bool(SBM06_NAME.match(token))
SBM06_FIN_LINE = re.compile(
    r"^(\d{2})\s+(\d{2})\s+(\d{2})\s+(.+?)\s+Fin\.\s+(.+)$",
    re.IGNORECASE,
)
SBM06_NOISE = re.compile(
    r"^(südbayerische|meisterschaft|herren|endergebnis|auswertung|stand:)",
    re.IGNORECASE,
)


def is_sbm_2006_vor_zw_fin_layout(lines: Sequence[str]) -> bool:
    sample = "\n".join(lines[:120])
    if not re.search(r"Vor\. \d", sample):
        return False
    if not re.search(r"\bZw\.", sample):
        return False
    return bool(re.search(r"\d{2}\s+\d{2}\s+\d{2}", sample))


def pdf_spatial_text_lines(source: Path) -> List[str]:
    """Group PDF words into reading-order rows across the full page width."""
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("pymupdf is required for legacy PDF imports (pip package pymupdf)") from exc

    doc = fitz.open(source)
    lines: List[str] = []
    for page_index in range(doc.page_count):
        words = doc[page_index].get_text("words")
        if not words:
            continue
        by_y: dict[int, list] = defaultdict(list)
        for word in words:
            by_y[round(word[1] / 6) * 6].append(word)
        for y in sorted(by_y):
            line = " ".join(
                word[4] for word in sorted(by_y[y], key=lambda word: word[0])
            )
            if line.strip():
                lines.append(line.strip())
    doc.close()
    return lines


def pdf_column_text_lines(source: Path, *, columns: int = 2) -> List[str]:
    """Backward-compatible alias; SBM 2006 uses full-width spatial rows."""
    return pdf_spatial_text_lines(source)


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped == "Ø":
        return True
    return bool(SBM06_NOISE.match(stripped))


def _parse_score_tail(tail: str, *, max_scores: int = 6) -> List[int]:
    scores: List[int] = []
    for token in tail.split():
        if SBM06_AVG.match(token) or SBM06_THOUSAND.match(token) or token == "Ø":
            break
        if is_score_token(token):
            scores.append(int(token))
            if len(scores) >= max_scores:
                break
            continue
        if SBM06_RANK.match(token) and int(token) <= 130:
            break
        if _is_person_name_token(token):
            break
    return scores


def _strip_totals_from_name_line(line: str) -> str:
    parts = line.split()
    for part in parts:
        if SBM06_THOUSAND.match(part) or SBM06_AVG.match(part) or part == "Ø":
            continue
        if part.isdigit() and int(part) > 300:
            continue
        if _is_person_name_token(part):
            return part
    for part in parts:
        if SBM06_THOUSAND.match(part) or SBM06_AVG.match(part) or part == "Ø":
            continue
        if part.isdigit() and int(part) > 300:
            continue
        return part
    return line.strip()


def _is_total_footer_line(line: str) -> bool:
    tokens = line.split()
    if not tokens:
        return True
    return all(
        SBM06_THOUSAND.match(token) or SBM06_AVG.match(token) or token == "Ø"
        for token in tokens
    )


def _parse_rank_line(line: str) -> tuple[int, str]:
    parts = [part for part in line.split() if not SBM06_THOUSAND.match(part)]
    cleaned = " ".join(parts).strip()
    if SBM06_RANK.match(cleaned) and int(cleaned) <= 130:
        return int(cleaned), ""
    match = re.match(r"^(\d{1,3})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-.]*)", cleaned)
    if match and int(match.group(1)) <= 130:
        return int(match.group(1)), match.group(2)
    return 0, ""


def _parse_rank_zw_combined(line: str) -> tuple[int, str, List[int]]:
    zw_idx = re.search(r"\bZw\.\s*", line, re.IGNORECASE)
    if not zw_idx:
        return 0, "", []
    head = line[: zw_idx.start()].strip()
    tail = line[zw_idx.end() :].strip()
    rank, first_name = _parse_rank_line(head) if head else (0, "")
    if not first_name and head and _is_person_name_token(head):
        first_name = head
    zw_scores = _parse_score_tail(tail)
    return rank, first_name, zw_scores


def _parse_id_club_line(line: str) -> tuple[str, str, List[int], bool]:
    match = re.match(r"^(\d{2})\s+(\d{2})\s+(\d{2})\s+(.+)$", line)
    if not match:
        return "", "", [], False
    player_id = f"{match.group(1)}{match.group(2)}{match.group(3)}"
    rest = match.group(4)
    fin_parts = re.split(r"\bFin\.\s*", rest, maxsplit=1, flags=re.IGNORECASE)
    club_tokens: List[str] = []
    for token in fin_parts[0].split():
        if SBM06_THOUSAND.match(token) or SBM06_AVG.match(token):
            break
        club_tokens.append(token)
    club = " ".join(club_tokens).strip()
    has_fin = len(fin_parts) > 1
    fin_scores = _parse_score_tail(fin_parts[1]) if has_fin else []
    return player_id, club, fin_scores, has_fin


def _consume_score_only_line(filtered: Sequence[str], index: int) -> tuple[List[int], int]:
    if index >= len(filtered):
        return [], index
    line = filtered[index]
    if (
        SBM06_VOR_LINE.match(line)
        or re.match(r"^.+\s+Vor\.\s+", line, re.IGNORECASE)
        or re.match(r"^\d{2}\s+\d{2}\s+\d{2}\s+", line)
        or line.startswith("Fin.")
        or "Zw." in line
    ):
        return [], index
    scores = _parse_score_tail(line)
    if scores:
        return scores, index + 1
    return [], index


def _consume_zw_section(
    filtered: Sequence[str], index: int, *, first_name: str
) -> tuple[str, List[int], int]:
    if index >= len(filtered):
        return first_name, [], index
    zw_line = filtered[index]
    if re.search(r"\bZw\.\s*", zw_line, re.IGNORECASE) and not zw_line.startswith("Zw."):
        rank, combined_first, zw_scores = _parse_rank_zw_combined(zw_line)
        if combined_first and not first_name:
            first_name = combined_first
        index += 1
        if not zw_scores:
            peek_scores, peek_index = _consume_score_only_line(filtered, index)
            zw_scores = peek_scores
            index = peek_index
        return first_name, zw_scores, index
    zw_prefix, zw_label, zw_scores = _parse_round_line(zw_line)
    if zw_label != "zw":
        if first_name:
            peek_scores, peek_index = _consume_score_only_line(filtered, index)
            if peek_scores:
                return first_name, peek_scores, peek_index
        return first_name, [], index
    index += 1
    if zw_prefix and not first_name and _is_person_name_token(zw_prefix):
        first_name = zw_prefix
    if not zw_scores:
        peek_scores, peek_index = _consume_score_only_line(filtered, index)
        if peek_scores:
            zw_scores = peek_scores
            index = peek_index
    return first_name, zw_scores, index


def _consume_fin_section(
    filtered: Sequence[str], index: int
) -> tuple[str, str, List[int], int]:
    if index >= len(filtered):
        return "", "", [], index
    fin_line = filtered[index]
    player_id, club, fin_scores, has_fin = _parse_id_club_line(fin_line)
    if player_id:
        index += 1
        if has_fin and not fin_scores and index < len(filtered):
            next_line = filtered[index]
            if next_line.startswith("Fin."):
                _, _, fin_scores = _parse_round_line(next_line)
                index += 1
        elif not has_fin and index < len(filtered) and filtered[index].startswith("Fin."):
            _, _, fin_scores = _parse_round_line(filtered[index])
            index += 1
        return player_id, club, fin_scores, index
    if fin_line.startswith("Fin."):
        _, _, fin_scores = _parse_round_line(fin_line)
        return "", "", fin_scores, index + 1
    return "", "", [], index


def _parse_round_line(line: str) -> tuple[str, str, List[int]]:
    if re.fullmatch(r"Zw\.", line, re.IGNORECASE):
        return "", "zw", []
    if re.fullmatch(r"Fin\.", line, re.IGNORECASE):
        return "", "fin", []
    vor_only = SBM06_VOR_LINE.match(line)
    if vor_only:
        return "", "vor", _parse_score_tail(vor_only.group(1))
    zw_match = SBM06_ZW_LINE.match(line)
    if zw_match:
        prefix = (zw_match.group(1) or "").strip()
        return prefix, "zw", _parse_score_tail(zw_match.group(2))
    fin_idx = re.search(r"\bFin\.\s+", line, re.IGNORECASE)
    if fin_idx:
        prefix = line[: fin_idx.start()].strip()
        tail = line[fin_idx.end() :].strip()
        return prefix, "fin", _parse_score_tail(tail)
    combined = re.match(r"^(?P<prefix>.+?)\s+Vor\.\s+(?P<tail>.+)$", line, re.IGNORECASE)
    if combined:
        return combined.group("prefix").strip(), "vor", _parse_score_tail(combined.group("tail"))
    return "", "", []


def parse_sbm_2006_vor_zw_fin_blocks(lines: Sequence[str]) -> List[PlayerBlock]:
    """Parse spatial rows from SBM 2006 PDFs."""
    players: List[PlayerBlock] = []
    pending_surname = ""
    index = 0
    filtered = [line.strip() for line in lines if not _is_noise_line(line.strip())]

    while index < len(filtered):
        line = filtered[index]
        index += 1

        surname = pending_surname
        vor_scores: List[int] = []
        rank = 0
        first_name = ""
        zw_scores: List[int] = []
        player_id = ""
        club = ""
        fin_scores: List[int] = []

        prefix, label, scores = _parse_round_line(line)
        if label == "vor":
            if prefix and _is_person_name_token(prefix.split()[-1]):
                surname = prefix
            vor_scores = scores
        elif label == "" and _is_person_name_token(_strip_totals_from_name_line(line)):
            pending_surname = _strip_totals_from_name_line(line)
            continue
        elif label == "" and SBM06_VOR_LINE.match(line):
            _, _, vor_scores = _parse_round_line(line)
        else:
            stripped = _strip_totals_from_name_line(line)
            if _is_person_name_token(stripped):
                pending_surname = stripped
            continue

        if not vor_scores and index < len(filtered):
            peek_scores, peek_index = _consume_score_only_line(filtered, index)
            if peek_scores:
                vor_scores = peek_scores
                index = peek_index

        if not vor_scores:
            continue

        if index < len(filtered):
            rank_line = filtered[index]
            if re.search(r"\bZw\.\s*", rank_line, re.IGNORECASE):
                parsed_rank, rank_first, zw_scores = _parse_rank_zw_combined(rank_line)
                if parsed_rank:
                    rank = parsed_rank
                if rank_first:
                    first_name = rank_first
                index += 1
            else:
                parsed_rank, rank_first = _parse_rank_line(rank_line)
                if parsed_rank:
                    rank = parsed_rank
                    first_name = first_name or rank_first
                    index += 1

        if not zw_scores:
            first_name, zw_scores, index = _consume_zw_section(
                filtered, index, first_name=first_name
            )

        while index < len(filtered) and _is_total_footer_line(filtered[index]):
            index += 1

        player_id, club, fin_scores, index = _consume_fin_section(filtered, index)

        pending_surname = ""
        if surname and first_name:
            name = f"{surname}, {first_name}"
        elif surname:
            name = surname
        else:
            name = first_name

        if not player_id or not name or not vor_scores:
            continue

        rounds: Dict[int, List[int]] = {1: vor_scores}
        if zw_scores:
            rounds[2] = zw_scores
        if fin_scores:
            rounds[3] = fin_scores

        players.append(
            PlayerBlock(
                rank=rank or len(players) + 1,
                name=name,
                club=club,
                player_id=player_id,
                rounds=rounds,
            )
        )

    if not players:
        return players

    by_id: dict[str, PlayerBlock] = {}
    for player in players:
        if player.player_id not in by_id:
            by_id[player.player_id] = player
    deduped = sorted(by_id.values(), key=lambda player: (player.rank or 9999, player.name))
    for rank_index, player in enumerate(deduped, 1):
        if not player.rank:
            player.rank = rank_index
    return deduped
