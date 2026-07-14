"""Tests for 2015 inline sheet legacy PDF parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.adapters.legacy_pdf_erg_2015 import (
    _parse_player_blocks,
    parse_legacy_pdf_erg_2015,
)
from database.tournament_import.config import ImportEntry

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")


def _entry(source: Path) -> ImportEntry:
    return ImportEntry(
        id="test",
        format="legacy_pdf_erg_2015",
        source=str(source),
        enabled=True,
        merge_target="manual",
        output="out.csv",
        options={"event_name": "Nordbayerische Meisterschaft", "season": "14/15"},
    )


def test_parse_2015_sheet_full_three_rounds() -> None:
    lines = [
        "Datum  29.03.2015",
        "Mainfranken-Bowling Bamberg",
        "Harles,  Michael",
        "254",
        "201",
        "258",
        "278",
        "256",
        "220",
        "1.467",
        "00 71 87",
        "224",
        "245",
        "219",
        "244",
        "184",
        "212",
        "1.328",
        "BCN",
        "239",
        "245",
        "245",
        "227",
        "224",
        "168",
        "1.348 230,17",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 1
    player = players[0]
    assert player.name == "Harles, Michael"
    assert player.player_id == "007187"
    assert player.club == "BCN"
    assert player.rounds[1] == [254, 201, 258, 278, 256, 220]
    assert player.rounds[2] == [224, 245, 219, 244, 184, 212]
    assert player.rounds[3] == [239, 245, 245, 227, 224, 168]


def test_parse_2015_sheet_no_finale() -> None:
    lines = [
        "Saffer,  Stefan",
        "220",
        "150",
        "157",
        "179",
        "238",
        "244",
        "1.188",
        "01 64 54",
        "163",
        "177",
        "236",
        "199",
        "240",
        "283",
        "1.298",
        "STE",
        "207,17",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 1
    assert players[0].player_id == "016454"
    assert players[0].club == "STE"
    assert 3 not in players[0].rounds


def test_parse_2015_sheet_skips_page_cut_summary() -> None:
    lines = [
        "Prüfer,  Gerhardt",
        "128",
        "222",
        "237",
        "229",
        "188",
        "180",
        "1.184",
        "01 67 77",
        "234",
        "193",
        "224",
        "201",
        "174",
        "204",
        "1.230",
        "COB",
        "267",
        "175",
        "211",
        "241",
        "215",
        "193",
        "1.302 206,44",
        "Nordbayerische Meisterschaft 2015 - Herren Einzel",
        "15",
        "Vorlauf",
        "3.716",
        "Zwischenlauf",
        "Finale",
        "Hernitschek,  Andreas",
        "193",
        "225",
        "238",
        "203",
        "237",
        "186",
        "1.282",
        "01 63 86",
        "201",
        "234",
        "216",
        "191",
        "195",
        "183",
        "1.220",
        "REG",
        "199",
        "244",
        "180",
        "216",
        "169",
        "178",
        "1.186 204,89",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 2
    assert players[0].name == "Prüfer, Gerhardt"
    assert players[1].name == "Hernitschek, Andreas"


def test_parse_2015_sheet_partial_zw_round() -> None:
    lines = [
        "Görz,  Wolfgang",
        "213",
        "215",
        "196",
        "188",
        "208",
        "223",
        "1.243",
        "01 60 95",
        "164",
        "192",
        "189",
        "545",
        "WÜR",
        "198,67",
        "Woyscheszik,  Jörg",
        "193",
        "221",
        "216",
        "189",
        "171",
        "222",
        "1.212",
        "02 53 50",
        "151",
        "162",
        "313",
        "BCN",
        "190,63",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 2
    assert players[0].name == "Görz, Wolfgang"
    assert players[0].player_id == "016095"
    assert players[0].club == "WÜR"
    assert players[0].rounds[2] == [164, 192, 189]
    assert players[1].name == "Woyscheszik, Jörg"
    assert players[1].player_id == "025350"
    assert players[1].club == "BCN"
    assert players[1].rounds[2] == [151, 162]


def test_parse_2015_sheet_vor_only() -> None:
    lines = [
        "Striefler,  Edmund",
        "158",
        "152",
        "136",
        "138",
        "199",
        "159",
        "942",
        "02 50 63",
        "BBH",
        "157,00",
        "95",
        "Vorlauf",
        "942",
        "Zwischenlauf",
        "Finale",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 1
    assert players[0].player_id == "025063"
    assert players[0].club == "BBH"
    assert players[0].rounds == {1: [158, 152, 136, 138, 199, 159]}


@pytest.mark.skipif(
    not (PDF_DIR / "bm2015_nb_he_erg.pdf").is_file(),
    reason="NBM 2015 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2015_nbm_full_field() -> None:
    pdf = PDF_DIR / "bm2015_nb_he_erg.pdf"
    rows = parse_legacy_pdf_erg_2015(pdf, _entry(pdf))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 90
    harles = next(row for row in rows if row["Player ID"] == "007187")
    assert "Harles" in harles["Player"]
    assert harles["Date"] == "2015-03-29"
