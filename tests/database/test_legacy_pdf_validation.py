"""Tests for PDF rank-ladder extraction validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import pytest

from database.tournament_import.adapters.legacy_pdf_validation import (
    collect_block_start_ranks,
    expected_participant_count,
    validate_player_extraction,
)
from database.tournament_import.config import ImportEntry

SBM_2007 = Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2007_sb_h_erg.pdf")


@dataclass
class _Player:
    rank: int = 0
    name: str = ""
    rounds: Dict[int, List[int]] = field(default_factory=dict)


def test_collect_block_start_ranks_inline_layout() -> None:
    lines = [
        "Platz Name",
        "1",
        "Pirzer, Robert",
        "Münchner KV",
        "2",
        "Köpf, Reiner",
        "BV München Land",
    ]
    ranks = collect_block_start_ranks(lines)
    assert ranks == [1, 2]
    assert expected_participant_count(ranks) == 2


def test_collect_block_start_ranks_dot_layout() -> None:
    lines = [
        "1. Pirzer, Robert",
        "Münchner KV",
        "07428",
        "2. Köpf, Reiner",
    ]
    ranks = collect_block_start_ranks(lines)
    assert ranks == [1, 2]
    assert expected_participant_count(ranks) == 2


def test_validate_player_extraction_count_mismatch() -> None:
    lines = [
        "1. Alpha, One",
        "2. Beta, Two",
        "3. Gamma, Three",
        "4. Delta, Four",
    ]
    players = [
        _Player(rank=1, name="Alpha, One", rounds={1: [200]}),
        _Player(rank=2, name="Beta, Two", rounds={1: [200]}),
    ]
    warnings = validate_player_extraction(lines, players)
    assert any("differs (+2)" in warning for warning in warnings)
    assert any("4 vs 2" in warning for warning in warnings)


def test_validate_player_extraction_flags_club_at_rank_one() -> None:
    lines = ["1. BSV Ulm/Neu Ulm", "2. Pirzer, Robert"]
    players = [_Player(rank=1, name="BSV Ulm/Neu Ulm", rounds={1: [200], 2: [200]})]
    warnings = validate_player_extraction(lines, players)
    assert any("rank 1 looks like a club" in warning for warning in warnings)


def test_validate_player_extraction_round_depth() -> None:
    lines = ["Vorrunde", "Zw.-runde", "Finale", "1. Pirzer, Robert"]
    players = [_Player(rank=1, name="Pirzer, Robert", rounds={1: [200], 2: [210]})]
    warnings = validate_player_extraction(lines, players)
    assert any("up to 3 round(s) but at most 2 extracted" in warning for warning in warnings)


@pytest.mark.skipif(not SBM_2007.is_file(), reason="SBM 2007 PDF not on disk")
def test_sbm_2007_expected_participant_count_is_116() -> None:
    from database.tournament_import.adapters.legacy_pdf_shared import pdf_text

    lines = [ln.strip() for ln in pdf_text(SBM_2007).splitlines()]
    ranks = collect_block_start_ranks(lines)
    assert expected_participant_count(ranks) == 116


@pytest.mark.skipif(not SBM_2007.is_file(), reason="SBM 2007 PDF not on disk")
def test_sbm_2007_2016_parser_validation_warnings() -> None:
    from database.tournament_import.adapters.legacy_pdf_erg_2009 import parse_legacy_pdf_erg_2009
    from database.tournament_import.adapters.legacy_pdf_validation import (
        begin_parse_warnings,
        drain_parse_warnings,
    )

    begin_parse_warnings()
    entry = ImportEntry(
        id="x",
        format="legacy_pdf_erg_2009",
        source=str(SBM_2007),
        options={"event_name": "SBM", "season": "06/07"},
    )
    parse_legacy_pdf_erg_2009(SBM_2007, entry)
    warnings = drain_parse_warnings()
    assert warnings == []
