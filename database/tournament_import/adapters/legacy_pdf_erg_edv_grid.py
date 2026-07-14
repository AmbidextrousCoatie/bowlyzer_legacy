"""BSKV EDV-Nr wide-grid PDF parser (2007 / 2009 NBM-style 18-game rows)."""

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

COMBINED_TOTAL_DIFF = re.compile(r"^(\d{1}\.\d{3})\s+(\d{1,3})$")
INJURY_LINE = re.compile(r"verletzung|verzicht|keine teilnahme", re.I)
THOUSAND_TOTAL = re.compile(r"^\d{1}\.\d{3}$")
PLAIN_TOTAL = re.compile(r"^\d{3,4}$")
GESAMT_LINE = re.compile(r"^\d{1}\.\d{3}\s+\d+$")
DIFF_PAIR = re.compile(r"^(\d{1,3})\s+(\d{1,3})$")
SCORE_WITH_INJURY = re.compile(
    r"^(\d{1,3})\s+(?:verletzung|verzicht|keine\s+teilnahme).*$",
    re.I,
)
TWELVE_GAME_GESAMT = re.compile(r"^2\.\d{3}\s+12$")
RANK_NAME = re.compile(r"^(\d{1,3})\s+(.+)$")
RANK_DOT_NAME = re.compile(r"^(\d{1,3})\.\s+(.+)$")
HEADER_NOISE = re.compile(
    r"^(platz|name|verein|gesamt|schnitt|diff\.?|sp\s*\d|s\s*\d|auswertung|vorlauf|zw\.?lauf|finale|"
    r"vorl\.|zw\.|fin\.|gesamt\s+sp|nordbay|nordbayer|herren|einzel|mainfranken|\]|$)",
    re.IGNORECASE,
)
SECTION_TITLE = re.compile(r"^(Nordbay|NORDBAYER|Meisterschaft|Brunswick|Bowling|Fürth|Phönix)", re.I)
DATE_STAMP = re.compile(r"^\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\s+\d{1,2}:\d{2}$")


@dataclass
class PlayerBlock:
    rank: int = 0
    name: str = ""
    club: str = ""
    player_id: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def _is_noise(text: str) -> bool:
    token = text.strip()
    if not token or HEADER_NOISE.search(token):
        return True
    if SECTION_TITLE.search(token):
        return True
    if DATE_STAMP.match(token):
        return True
    if token.lower().startswith("verein sp"):
        return True
    return False


def _is_round_total(text: str) -> bool:
    token = text.strip()
    if COMBINED_TOTAL_DIFF.match(token):
        return True
    if THOUSAND_TOTAL.match(token):
        return True
    if PLAIN_TOTAL.match(token):
        return int(token) >= 500
    return False


def _parse_score_line(token: str) -> Optional[int]:
    text = token.strip()
    injury = SCORE_WITH_INJURY.match(text)
    if injury and is_score_token(injury.group(1)):
        return int(injury.group(1))
    if is_score_token(text):
        return int(text)
    return None


def _is_club_token(text: str) -> bool:
    token = text.strip()
    if not token or is_score_token(token) or normalize_player_id(token):
        return False
    if _is_round_total(token) or GESAMT_LINE.match(token):
        return False
    if re.match(r"^\d+,\d+", token):
        return False
    if re.match(r"^\d{1,3}$", token):
        return False
    return len(token) <= 80


def _skip_round_total(lines: List[str], idx: int) -> int:
    if idx < len(lines) and _is_round_total(lines[idx]):
        return idx + 1
    return idx


def _score_run_ahead(lines: List[str], idx: int, *, max_scores: int = 6) -> int:
    count = 0
    pos = idx
    while pos < len(lines) and count < max_scores:
        if is_score_token(lines[pos]):
            count += 1
            pos += 1
            continue
        break
    return count


def _read_six_scores(lines: List[str], idx: int) -> tuple[List[int], int]:
    scores, end = _consume_scores(lines, idx, count=6)
    return scores, end


def _find_next_thousand_total(lines: List[str], idx: int, *, within: int = 12) -> tuple[Optional[int], int]:
    for pos in range(idx, min(idx + within, len(lines))):
        token = lines[pos].strip()
        combined = COMBINED_TOTAL_DIFF.match(token)
        if combined:
            return int(combined.group(1).replace(".", "")), pos
        if THOUSAND_TOTAL.match(token):
            return int(token.replace(".", "")), pos
    return None, idx


def _skip_leading_fin_diff(lines: List[str], idx: int) -> int:
    if idx >= len(lines):
        return idx
    token = lines[idx].strip()
    pair = DIFF_PAIR.match(token)
    if pair and is_score_token(pair.group(2)):
        return idx
    if not re.match(r"^\d{1,3}$", token):
        return idx

    as_first, end_first = _read_six_scores(lines, idx)
    total_first, _ = _find_next_thousand_total(lines, end_first, within=6)
    if len(as_first) == 6 and total_first is not None and sum(as_first) == total_first:
        return idx

    from_next, end = _read_six_scores(lines, idx + 1)
    total, _ = _find_next_thousand_total(lines, end, within=5)
    if total is None:
        return idx
    if len(from_next) == 6 and sum(from_next) == total:
        return idx
    if len(from_next) >= 5 and int(token) + sum(from_next[:5]) == total:
        return idx + 1
    return idx


def _consume_finale_round(lines: List[str], idx: int) -> tuple[List[int], int]:
    if idx >= len(lines):
        return [], idx

    token = lines[idx].strip()
    pair = DIFF_PAIR.match(token)
    if pair and is_score_token(pair.group(2)):
        scores, end = _consume_scores(lines, idx + 1, count=6, prefix=[int(pair.group(2))])
        if scores:
            return scores, end
        return [], idx

    idx = _skip_leading_fin_diff(lines, idx)

    scores: List[int] = []
    while idx < len(lines) and len(scores) < 6:
        token = lines[idx].strip()
        score = _parse_score_line(token)
        if score is None:
            if INJURY_LINE.search(token):
                break
            break
        scores.append(score)
        idx += 1
        if INJURY_LINE.search(token):
            break

    if scores:
        total, _ = _find_next_thousand_total(lines, idx, within=6)
        while total is not None and len(scores) > 1 and sum(scores) > total:
            scores.pop()

    if idx < len(lines) and re.match(r"^\d{1,3}$", lines[idx].strip()):
        total, _ = _find_next_thousand_total(lines, idx + 1, within=4)
        if total is not None and scores and sum(scores) == total:
            idx += 1
        elif total is not None and scores and sum(scores) != total:
            idx += 1

    return scores, idx


def _skip_cut_diff_after_total(lines: List[str], idx: int) -> int:
    if idx >= len(lines):
        return idx
    token = lines[idx].strip()
    if DIFF_PAIR.match(token):
        return idx + 1
    if not re.match(r"^\d{1,3}$", token):
        return idx
    _, end_next = _read_six_scores(lines, idx + 1)
    total_next, _ = _find_next_thousand_total(lines, end_next)
    if total_next is None:
        return idx
    from_next, _ = _read_six_scores(lines, idx + 1)
    if len(from_next) == 6 and sum(from_next) == total_next:
        return idx + 1
    return idx


def _consume_scores(
    lines: List[str],
    idx: int,
    *,
    count: int = 6,
    prefix: Optional[List[int]] = None,
) -> tuple[List[int], int]:
    scores = list(prefix or [])
    while idx < len(lines) and len(scores) < count:
        token = lines[idx].strip()
        score = _parse_score_line(token)
        if score is None:
            break
        if (
            scores
            and score == sum(scores)
            and len(scores) in {2, 3}
            and len(scores) < count
            and idx + 1 < len(lines)
            and _is_round_total(lines[idx + 1])
        ):
            idx += 1
            break
        scores.append(score)
        idx += 1
        if INJURY_LINE.search(token):
            break
    return scores, idx


def _is_no_finale_row(lines: List[str], idx: int) -> bool:
    if idx >= len(lines):
        return False
    token = lines[idx].strip()
    if DIFF_PAIR.match(token):
        return False
    if not re.match(r"^\d{1,3}$", token):
        return False
    for pos in range(idx, min(idx + 6, len(lines))):
        line = lines[pos].strip()
        if TWELVE_GAME_GESAMT.match(line):
            return True
        if RANK_NAME.match(line) or RANK_DOT_NAME.match(line):
            return False
    return False


def _skip_no_finale_footer(lines: List[str], idx: int) -> int:
    if idx < len(lines) and re.match(r"^\d{1,3}$", lines[idx].strip()):
        idx += 1
    while idx < len(lines):
        token = lines[idx].strip()
        if TWELVE_GAME_GESAMT.match(token):
            idx += 1
            break
        if _is_round_total(token):
            idx += 1
            continue
        break
    if idx < len(lines) and re.match(r"^\d+,\d+", lines[idx].strip()):
        idx += 1
    return idx


def _skip_player_tail(lines: List[str], idx: int) -> int:
    while idx < len(lines):
        token = lines[idx].strip()
        if not token:
            idx += 1
            continue
        if _is_noise(token):
            break
        if RANK_NAME.match(token) or RANK_DOT_NAME.match(token):
            break
        if re.match(r"^\d{1,3}$", token) and idx + 1 < len(lines) and re.match(r"^[A-Za-z]", lines[idx + 1]):
            if not DIFF_PAIR.match(token):
                break
        if is_score_token(token):
            break
        if _is_round_total(token) or GESAMT_LINE.match(token):
            idx += 1
            continue
        if re.match(r"^\d{1,3}$", token) and not is_score_token(token):
            idx += 1
            continue
        if re.match(r"^\d+,\d+", token):
            idx += 1
            continue
        if token in {"18"}:
            idx += 1
            continue
        break
    return idx


def _skip_vor_only_tail(lines: List[str], idx: int) -> int:
    while idx < len(lines):
        token = lines[idx].strip()
        if not token:
            idx += 1
            continue
        if _is_round_total(token) or GESAMT_LINE.match(token):
            idx += 1
            continue
        if token in {"6", "12", "18"}:
            idx += 1
            continue
        if re.match(r"^\d{1,2}$", token) and int(token) <= 18:
            idx += 1
            continue
        if re.match(r"^\d+,\d+", token):
            idx += 1
            continue
        break
    return idx


def _read_rank_name(lines: List[str], idx: int) -> tuple[Optional[int], str, int]:
    if idx >= len(lines):
        return None, "", idx
    token = lines[idx].strip()
    rank_name = RANK_NAME.match(token) or RANK_DOT_NAME.match(token)
    if rank_name:
        name = rank_name.group(2).strip()
        if INJURY_LINE.search(name):
            return None, "", idx + 1
        return int(rank_name.group(1)), name, idx + 1
    if re.match(r"^\d{1,3}$", token) and idx + 1 < len(lines):
        nxt = lines[idx + 1].strip()
        if (
            re.match(r"^[A-Za-z]", nxt)
            and not _is_noise(nxt)
            and not DIFF_PAIR.match(token)
            and not INJURY_LINE.search(nxt)
        ):
            return int(token), nxt, idx + 2
    return None, "", idx


def _parse_player_at(lines: List[str], idx: int, *, diff_after_vor: bool) -> tuple[Optional[PlayerBlock], int]:
    rank, name, idx = _read_rank_name(lines, idx)
    if rank is None or not name:
        return None, idx

    if idx >= len(lines):
        return None, idx
    player_id = normalize_player_id(lines[idx]) or (
        lines[idx].strip() if re.match(r"^\d{4,6}$", lines[idx].strip()) else ""
    )
    if not player_id:
        return None, idx + 1
    idx += 1

    if idx >= len(lines) or not _is_club_token(lines[idx]):
        return None, idx
    club = lines[idx].strip()
    idx += 1

    scores1, idx = _consume_scores(lines, idx)
    if len(scores1) != 6:
        return None, idx
    idx = _skip_round_total(lines, idx)
    if diff_after_vor:
        idx = _skip_cut_diff_after_total(lines, idx)
        if idx < len(lines) and _is_round_total(lines[idx]):
            idx = _skip_vor_only_tail(lines, idx)
            player = PlayerBlock(
                rank=rank,
                name=name,
                club=club,
                player_id=player_id,
                rounds={1: scores1},
            )
            return player, idx

    scores2, idx = _consume_scores(lines, idx)
    if len(scores2) != 6:
        rounds: Dict[int, List[int]] = {1: scores1}
        if scores2 and not diff_after_vor:
            rounds[2] = scores2
        idx = _skip_vor_only_tail(lines, idx)
        player = PlayerBlock(
            rank=rank,
            name=name,
            club=club,
            player_id=player_id,
            rounds=rounds,
        )
        return player, idx

    idx = _skip_round_total(lines, idx)

    rounds: Dict[int, List[int]] = {1: scores1, 2: scores2}
    if diff_after_vor and _is_no_finale_row(lines, idx):
        idx = _skip_no_finale_footer(lines, idx)
    else:
        scores3, idx = _consume_finale_round(lines, idx)
        if scores3:
            rounds[3] = scores3
        idx = _skip_player_tail(lines, idx)
        player = PlayerBlock(
            rank=rank,
            name=name,
            club=club,
            player_id=player_id,
            rounds=rounds,
        )
        return player, idx

    idx = _skip_player_tail(lines, idx)

    player = PlayerBlock(
        rank=rank,
        name=name,
        club=club,
        player_id=player_id,
        rounds=rounds,
    )
    return player, idx


def _detect_layout(text: str) -> str:
    if re.search(r"^Sp 7$", text, flags=re.MULTILINE) and re.search(r"^Sp 13", text, flags=re.MULTILINE):
        return "2009"
    if "Zw.Lauf" in text or re.search(r"^Diff\.$", text, flags=re.MULTILINE):
        return "2007"
    return "2009"


def _parse_player_blocks(lines: List[str], *, layout: str) -> List[PlayerBlock]:
    diff_after_vor = layout == "2007"
    players_by_rank: dict[int, PlayerBlock] = {}
    idx = 0

    while idx < len(lines):
        token = lines[idx].strip()
        if _is_noise(token):
            idx += 1
            continue

        rank, name, _ = _read_rank_name(lines, idx)
        if rank is None:
            idx += 1
            continue

        start = idx
        player, idx = _parse_player_at(lines, idx, diff_after_vor=diff_after_vor)
        if player:
            players_by_rank[player.rank] = player
        elif idx <= start:
            idx = start + 1

    players = sorted(players_by_rank.values(), key=lambda p: p.rank)
    return players


def parse_legacy_pdf_erg_edv_grid(source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
    if not source.is_file():
        raise FileNotFoundError(source)
    text = pdf_text(source)
    meta = extract_pdf_meta(source, entry, text)
    layout = str(entry.options.get("grid_layout") or _detect_layout(text))
    lines = [ln.strip() for ln in text.splitlines()]
    players = _parse_player_blocks(lines, layout=layout)
    if not players:
        raise ValueError(f"No player blocks parsed from {source.name}")
    report_player_extraction(lines, players, source_name=source.name)
    return rows_from_player_rounds(meta, players, round_labels=ROUND_LABELS_PDF_2016)


class LegacyPdfErgEdvGridAdapter:
    format_id = "legacy_pdf_erg_edv_grid"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        return parse_legacy_pdf_erg_edv_grid(source, entry)
