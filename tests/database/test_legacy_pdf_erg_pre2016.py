"""Tests for pre-2016 legacy PDF parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.adapters.legacy_pdf_erg_2009 import (
    _parse_inline_rank_blocks,
    _parse_player_blocks,
    parse_legacy_pdf_erg_2009,
)
from database.tournament_import.adapters.legacy_pdf_erg_2012 import parse_legacy_pdf_erg_2012
from database.tournament_import.config import ImportEntry

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")


def _entry(source: Path) -> ImportEntry:
    return ImportEntry(
        id="test",
        format="legacy_pdf",
        source=str(source),
        enabled=True,
        merge_target="manual",
        output="out.csv",
        options={},
    )


def test_parse_inline_rank_blocks_2008_layout() -> None:
    lines = [
        "Name",
        "EDV-Nummer",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "Ges.",
        "Schnitt",
        "1",
        "Renner Peter",
        "07869",
        "REG",
        "Vorrunde",
        "224",
        "215",
        "208",
        "290",
        "210",
        "226",
        "1373",
        "Zwi.-Runde",
        "205",
        "256",
        "201",
        "243",
        "161",
        "246",
        "1312",
        "Finale",
        "195",
        "228",
        "204",
        "237",
        "227",
        "215",
        "1306",
        "3991",
        "/",
        "221,72",
        "2",
        "Beck Joseph",
        "07833",
        "REG",
        "Vorrunde",
        "280",
        "243",
        "248",
        "214",
        "235",
        "211",
        "1431",
    ]
    players = _parse_inline_rank_blocks(lines)
    assert len(players) == 2
    assert players[0].rank == 1
    assert players[0].name == "Renner Peter"
    assert players[0].player_id == "07869"
    assert players[0].club == "REG"
    assert players[0].rounds[1] == [224, 215, 208, 290, 210, 226]


def test_parse_inline_rank_blocks_2006_vorlauf_layout() -> None:
    lines = [
        "1",
        "Hergenröder Dominik",
        "Vorlauf",
        "178",
        "227",
        "258",
        "195",
        "248",
        "289",
        "1395",
        "REG",
        "Zwischenl.",
        "243",
        "142",
        "259",
        "214",
        "233",
        "213",
        "1304",
        "120641",
        "Finale",
        "255",
        "213",
        "195",
        "199",
        "191",
        "187",
        "1240",
        "3939",
        "/ 18",
        "218,83",
    ]
    players = _parse_inline_rank_blocks(lines)
    assert len(players) == 1
    assert players[0].rank == 1
    assert players[0].name == "Hergenröder Dominik"
    assert players[0].club == "REG"
    assert players[0].player_id == "120641"
    assert players[0].rounds[1] == [178, 227, 258, 195, 248, 289]
    assert players[0].rounds[2] == [243, 142, 259, 214, 233, 213]
    assert players[0].rounds[3] == [255, 213, 195, 199, 191, 187]


@pytest.mark.skipif(
    not (PDF_DIR / "bm2006_nb_he_erg.pdf").is_file(),
    reason="NBM 2006 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_nbm_2006_full_field() -> None:
    pdf = PDF_DIR / "bm2006_nb_he_erg.pdf"
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 110
    hergen = next(row for row in rows if row["Player ID"] == "120641")
    assert "Hergenr" in hergen["Player"]


@pytest.mark.skipif(
    not (PDF_DIR / "bm2008_nb_he_erg.pdf").is_file(),
    reason="NBM 2008 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_nbm_2008_replaces_partial_import() -> None:
    pdf = PDF_DIR / "bm2008_nb_he_erg.pdf"
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 110
    renner = next(row for row in rows if row["Player ID"] == "07869")
    assert "Renner" in renner["Player"]


def test_parse_legacy_pdf_erg_2009_block_maps_verein_and_pass_number() -> None:
    lines = [
        "Börding, Tobias",
        "Vorrunde",
        "237",
        "202",
        "182",
        "191",
        "210",
        "222",
        "1244",
        "Münchner Kegler-Verein e.V.",
        "Zwi.-Runde",
        "234",
        "220",
        "216",
        "212",
        "223",
        "279",
        "1384",
        "2628",
        "007592",
        "Finale",
        "221",
        "246",
        "268",
        "222",
        "225",
        "259",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 1
    player = players[0]
    assert player.name == "Börding, Tobias"
    assert player.club == "Münchner Kegler-Verein e.V."
    assert player.player_id == "007592"
    assert player.rounds[1] == [237, 202, 182, 191, 210, 222]
    assert player.rounds[2] == [234, 220, 216, 212, 223, 279]


def test_parse_legacy_pdf_erg_2012_sbm() -> None:
    pdf = PDF_DIR / "bm2012_sbm_h_erg.pdf"
    if not pdf.is_file():
        pytest.skip(f"missing fixture PDF: {pdf}")
    rows = parse_legacy_pdf_erg_2012(pdf, _entry(pdf))
    players = {(row["Player"], row["Player ID"]) for row in rows}
    assert len(players) >= 100
    assert rows[0]["Event Name"]
    assert all(row["Round Number"] in {"1", "2", "3"} for row in rows)


def test_parse_legacy_pdf_erg_2009_sb_damen() -> None:
    pdf = PDF_DIR / "bm2009_sb_da_erg.pdf"
    if not pdf.is_file():
        pytest.skip(f"missing fixture PDF: {pdf}")
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    players = {(row["Player"], row["Player ID"]) for row in rows}
    assert len(players) >= 35
    assert rows[0]["Season"] == "08/09"
    laub = next(row for row in rows if row["Player"].startswith("Laub, Sabrina"))
    assert laub["Club"] == "BSV Augsburg"
    assert laub["Player ID"] == "07445"


def test_parse_legacy_pdf_erg_2009_2010_vor_zw_fin() -> None:
    pdf = PDF_DIR / "bm2010_sb_he_erg.pdf"
    if not pdf.is_file():
        pytest.skip(f"missing fixture PDF: {pdf}")
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    players = {(row["Player"], row["Player ID"]) for row in rows}
    assert len(players) >= 70
    mrosek = next(row for row in rows if "Mrosek" in row["Player"])
    assert mrosek["Club"] == "Münchner KV"
    assert mrosek["Player ID"] == "07653"


def test_parse_legacy_pdf_erg_2009_2011_sbm_verein_and_pass_number() -> None:
    pdf = PDF_DIR / "bm2011_sbm_h_erg.pdf"
    if not pdf.is_file():
        pytest.skip(f"missing fixture PDF: {pdf}")
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    tobias = next(row for row in rows if "Tobias" in row["Player"] and "Börding" in row["Player"])
    assert tobias["Club"] == "Münchner Kegler-Verein e.V."
    assert tobias["Player ID"] == "007592"
    assert tobias["Player ID"] != "1244"
    assert tobias["Club"] != "1244"


def test_parse_legacy_pdf_erg_2009_summary_finale_does_not_steal_next_player_vorrunde() -> None:
    lines = [
        "Bauer, Kurt",
        "Vorrunde",
        "186",
        "159",
        "187",
        "172",
        "211",
        "196",
        "1111",
        "BV Würzburg",
        "Zwi.-Runde",
        "157",
        "162",
        "151",
        "205",
        "168",
        "196",
        "1039",
        "2150",
        "016096",
        "Finale",
        "2150",
        "/ 12",
        "119,44",
        "-19",
        "511",
        "Burgis, Stefan",
        "Vorrunde",
        "191",
        "157",
        "203",
        "185",
        "148",
        "182",
        "1066",
    ]
    players = _parse_player_blocks(lines)
    by_id = {p.player_id: p for p in players}
    assert by_id["016096"].name == "Bauer, Kurt"
    assert 3 not in by_id["016096"].rounds or not by_id["016096"].rounds.get(3)
    assert by_id["016096"].rounds[1] == [186, 159, 187, 172, 211, 196]
    assert len(players) == 1


def test_parse_legacy_pdf_erg_2009_zw_runde_total_only_player() -> None:
    lines = [
        "Baier, Gerhard",
        "Vorrunde",
        "178",
        "164",
        "199",
        "183",
        "140",
        "188",
        "1052",
        "BSV Kitzingen",
        "Zwi.-Runde",
        "1052",
        "007393",
        "Finale",
        "1052",
        "/",
        "6",
        "175,33",
        "-78",
    ]
    players = _parse_player_blocks(lines)
    assert len(players) == 1
    assert players[0].player_id == "007393"
    assert players[0].rounds[1] == [178, 164, 199, 183, 140, 188]
    assert players[0].rounds[2] == []


@pytest.mark.skipif(
    not (PDF_DIR / "bm2011_nbm_h_erg_neu.pdf").is_file(),
    reason="NBM 2011 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_nbm_2011_full_field() -> None:
    pdf = PDF_DIR / "bm2011_nbm_h_erg_neu.pdf"
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    players = {row["Player ID"] for row in rows}
    assert len(players) >= 140
    kurt = next(row for row in rows if row["Player ID"] in {"16096", "016096"})
    assert "Bauer" in kurt["Player"]
    assert any("Burgis" in row["Player"] for row in rows)


@pytest.mark.skipif(
    not (PDF_DIR / "bm2012_nbm_h_erg.pdf").is_file(),
    reason="NBM 2012 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_nbm_2012_no_cut_diff_scores() -> None:
    pdf = PDF_DIR / "bm2012_nbm_h_erg.pdf"
    rows = parse_legacy_pdf_erg_2009(pdf, _entry(pdf))
    hamfler = [row for row in rows if row["Player ID"] == "07742"]
    assert hamfler
    assert not [row for row in hamfler if row["Round Number"] == "3"]
    assert len({row["Player ID"] for row in rows}) >= 100


@pytest.mark.skipif(
    not (PDF_DIR / "bm2007_sb_h_erg.pdf").is_file(),
    reason="SBM 2007 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_sbm_2007_full_field_and_page_seams() -> None:
    pdf = PDF_DIR / "bm2007_sb_h_erg.pdf"
    entry = ImportEntry(
        id="sbm-2007",
        format="legacy_pdf_erg_2009",
        source=str(pdf),
        options={"event_name": "Südbayerische Meisterschaft", "season": "06/07"},
    )
    rows = parse_legacy_pdf_erg_2009(pdf, entry)
    names = {row["Player"] for row in rows}
    assert len(names) == 116
    assert any(row["Player"] == "Nierlich, Peter" for row in rows)
    assert any(row["Player"] == "Naujack, Uwe" for row in rows)
    nierlich = {row["Round Number"] for row in rows if row["Player"] == "Nierlich, Peter"}
    naujack = {row["Round Number"] for row in rows if row["Player"] == "Naujack, Uwe"}
    assert nierlich == {"1", "2", "3"}
    assert naujack == {"1", "2", "3"}
    assert rows[0]["Player"] == "Pirzer, Robert"


@pytest.mark.skipif(
    not (PDF_DIR / "bm2006_sb_he_erg.pdf").is_file(),
    reason="SBM 2006 PDF not on disk",
)
def test_parse_legacy_pdf_erg_2009_sbm_2006_spatial_vor_zw_fin_layout() -> None:
    pdf = PDF_DIR / "bm2006_sb_he_erg.pdf"
    entry = ImportEntry(
        id="sbm-2006",
        format="legacy_pdf_erg_2009",
        source=str(pdf),
        options={"event_name": "Südbayerische Meisterschaft", "season": "05/06"},
    )
    rows = parse_legacy_pdf_erg_2009(pdf, entry)
    names = {row["Player"] for row in rows}
    assert len(names) == 127
    assert not any("Ø" in name for name in names)
    assert not any(name.endswith(",00") for name in names)
    peinelt = [row for row in rows if row["Player"] == "Peinelt, Helmut"]
    assert peinelt
    assert peinelt[0]["Player ID"] == "102523"
    assert peinelt[0]["Club"] == "München"
    peinelt_vor = sorted(
        int(row["Score"]) for row in peinelt if row["Round Number"] == "1"
    )
    assert peinelt_vor == [202, 225, 227, 232, 235, 246]
    for surname, rounds in (
        ("Milkau, Daniel", {"1", "2", "3"}),
        ("Gernböck, Udo", {"1", "2", "3"}),
        ("Huber, Johann", {"1", "2", "3"}),
    ):
        player_rounds = {row["Round Number"] for row in rows if row["Player"] == surname}
        assert player_rounds == rounds
    assert any(row["Player"] == "Niedner, Ralf" for row in rows)
    assert any(row["Player"] == "Kuchling, Matthias" for row in rows)
    assert not any("987" in row["Player"] for row in rows)
    assert not any("871" in row["Player"] for row in rows)
