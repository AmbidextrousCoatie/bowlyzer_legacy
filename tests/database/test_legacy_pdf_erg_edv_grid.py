"""Tests for EDV-Nr wide-grid legacy PDF parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.adapters.legacy_pdf_erg_edv_grid import (
    _parse_player_blocks,
    parse_legacy_pdf_erg_edv_grid,
)
from database.tournament_import.config import ImportEntry

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")


def _entry(source: Path, *, season: str) -> ImportEntry:
    return ImportEntry(
        id="test",
        format="legacy_pdf_erg_edv_grid",
        source=str(source),
        enabled=True,
        merge_target="manual",
        output="out.csv",
        options={"event_name": "Nordbayerische Meisterschaft", "season": season},
    )


def test_parse_2007_grid_full_player() -> None:
    lines = [
        "1",
        "Hergenröder Dominik",
        "07881",
        "REG",
        "216",
        "224",
        "248",
        "191",
        "220",
        "258",
        "1.357",
        "67",
        "170",
        "196",
        "221",
        "257",
        "206",
        "257",
        "1.307",
        "50 167",
        "183",
        "219",
        "236",
        "216",
        "162",
        "1.183",
        "174",
        "3.847 18",
        "213,72",
    ]
    players = _parse_player_blocks(lines, layout="2007")
    assert len(players) == 1
    assert players[0].rounds[1] == [216, 224, 248, 191, 220, 258]
    assert players[0].rounds[2] == [170, 196, 221, 257, 206, 257]
    assert players[0].rounds[3] == [167, 183, 219, 236, 216, 162]


def test_parse_2007_grid_vor_only_summary_row() -> None:
    lines = [
        "88 Utz Helmut",
        "07933",
        "STE",
        "163",
        "171",
        "216",
        "157",
        "183",
        "156",
        "1.046",
        "60",
        "1.046",
        "1.046",
        "1.046",
        "6",
        "174,33",
    ]
    players = _parse_player_blocks(lines, layout="2007")
    assert len(players) == 1
    assert players[0].rounds == {1: [163, 171, 216, 157, 183, 156]}


def test_parse_2007_injury_partial_fin() -> None:
    lines = [
        "77 Hamfler Wolfgang",
        "07747",
        "BCN",
        "130",
        "145",
        "257",
        "214",
        "204",
        "172",
        "1.122 127",
        "183",
        "212",
        "199",
        "234",
        "178",
        "181",
        "1.187",
        "65 168",
        "172",
        "153",
        "148 Verletzung",
        "641",
        "546",
        "2.950 17",
        "173,53",
    ]
    players = _parse_player_blocks(lines, layout="2007")
    assert len(players) == 1
    assert players[0].rounds[3] == [168, 172, 153, 148]
    assert sum(len(v) for v in players[0].rounds.values()) == 16


def test_parse_2007_no_fin_twelve_game_row() -> None:
    prietz = [
        "78 Prietz Werner",
        "16262",
        "ABV",
        "236",
        "191",
        "168",
        "154",
        "128",
        "195",
        "1.072 108",
        "176",
        "233",
        "204",
        "173",
        "169",
        "178",
        "1.133",
        "61",
        "1.133",
        "2.205 12",
        "183,75",
    ]
    karl = [
        "79 Karl William",
        "16532",
        "BHB",
        "192",
        "166",
        "180",
        "145",
        "191",
        "193",
        "1.067",
        "48",
        "159",
        "154",
        "206",
        "163",
        "151",
        "197",
        "1.030",
        "37",
        "1.067",
        "2.097 12",
        "174,75",
    ]
    for lines in (prietz, karl):
        players = _parse_player_blocks(lines, layout="2007")
        assert len(players) == 1
        assert 3 not in players[0].rounds
        assert len(players[0].rounds[1]) == 6
        assert len(players[0].rounds[2]) == 6


def test_parse_2009_duplicate_edv_nr_keeps_both_players() -> None:
    holt = [
        "90",
        "Holt Timothy",
        "16554",
        "BHB",
        "204",
        "149",
        "168",
        "186",
        "140",
        "215",
        "1.062",
        "134",
        "192",
        "148",
        "158",
        "145",
        "163",
        "940",
        "172",
        "183",
        "168",
        "136",
        "205",
        "166",
        "122",
        "1.030",
        "3.032",
        "18",
        "168,44",
    ]
    batusha = [
        "93",
        "Batusha Burim",
        "16554",
        "LIF",
        "186",
        "171",
        "209",
        "181",
        "214",
        "176",
        "1.137",
        "171",
        "150",
        "160",
        "187",
        "198",
        "157",
        "1.023",
        "2.160",
        "12",
        "180,00",
    ]
    players = _parse_player_blocks(holt + batusha, layout="2009")
    assert len(players) == 2
    by_rank = {p.rank: p for p in players}
    assert by_rank[90].name == "Holt Timothy"
    assert by_rank[93].name == "Batusha Burim"
    assert by_rank[90].player_id == by_rank[93].player_id == "16554"


def test_parse_2009_partial_zw_row() -> None:
    lines = [
        "103 Fleischmann Marc",
        "25124",
        "ABV",
        "190",
        "181",
        "145",
        "249",
        "168",
        "189",
        "1.122",
        "157",
        "134",
        "291",
        "1.122",
        "1.413",
        "8",
        "176,63",
    ]
    players = _parse_player_blocks(lines, layout="2009")
    assert len(players) == 1
    assert players[0].rounds[1] == [190, 181, 145, 249, 168, 189]
    assert players[0].rounds[2] == [157, 134]
    assert 3 not in players[0].rounds


def test_parse_2009_grid_full_player() -> None:
    lines = [
        "1",
        "Weber Wolfgang",
        "16252",
        "BAM",
        "222",
        "269",
        "219",
        "228",
        "235",
        "210",
        "1.383",
        "222",
        "157",
        "258",
        "245",
        "213",
        "277",
        "1.372",
        "255",
        "177",
        "236",
        "266",
        "226",
        "226",
        "14",
        "1.386",
        "4.141",
        "18",
        "230,06",
    ]
    players = _parse_player_blocks(lines, layout="2009")
    assert len(players) == 1
    assert players[0].rounds[3] == [255, 177, 236, 266, 226, 226]


@pytest.mark.skipif(
    not (PDF_DIR / "bm2007_nb_h_erg.pdf").is_file(),
    reason="NBM 2007 PDF not on disk",
)
def test_parse_legacy_pdf_erg_edv_grid_nbm_2007() -> None:
    pdf = PDF_DIR / "bm2007_nb_h_erg.pdf"
    rows = parse_legacy_pdf_erg_edv_grid(pdf, _entry(pdf, season="06/07"))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 120
    hergen = next(row for row in rows if row["Player ID"] == "07881")
    assert "Hergenr" in hergen["Player"]
    hamfler_fin = [row for row in rows if row["Player ID"] == "07747" and row["Round Name"] == "Finalrunde"]
    assert len(hamfler_fin) == 4
    assert sorted(int(row["Score"]) for row in hamfler_fin) == [148, 153, 168, 172]
    prietz = [row for row in rows if row["Player ID"] == "16262"]
    assert all(row["Round Name"] != "Finalrunde" for row in prietz)
    karl = [row for row in rows if row["Player ID"] == "16532"]
    assert all(row["Round Name"] != "Finalrunde" for row in karl)


@pytest.mark.skipif(
    not (PDF_DIR / "bm2009_nb_he_erg.pdf").is_file(),
    reason="NBM 2009 PDF not on disk",
)
def test_parse_legacy_pdf_erg_edv_grid_nbm_2009() -> None:
    pdf = PDF_DIR / "bm2009_nb_he_erg.pdf"
    rows = parse_legacy_pdf_erg_edv_grid(pdf, _entry(pdf, season="08/09"))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 90
    weber = next(row for row in rows if row["Player ID"] == "16252")
    assert "Weber" in weber["Player"]
    holt = [row for row in rows if row["Player ID"] == "16554" and "Holt" in row["Player"]]
    batusha = [row for row in rows if row["Player ID"] == "16554" and "Batusha" in row["Player"]]
    assert len(holt) == 18
    assert len(batusha) == 12
    karl = [row for row in rows if row["Player ID"] == "16532"]
    assert len(karl) == 14
    fleisch = [row for row in rows if row["Player ID"] == "25124"]
    assert len(fleisch) == 8
    assert sorted(int(row["Score"]) for row in fleisch if row["Round Name"] == "Zwischenlauf") == [134, 157]
