from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.adapters.legacy_pdf_erg_2016 import (
    _parse_player_blocks,
    disambiguate_bayerische_event_name,
    parse_legacy_pdf_erg_2016,
)
from database.tournament_import.config import ImportEntry

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
PDF_2019 = PDF_DIR / "bm2019_akt_sb_he_erg.pdf"
PDF_2016 = PDF_DIR / "bm2016_sb_he_erg.pdf"
PDF_NBM_2016 = PDF_DIR / "bm2016_nb_he_erg.pdf"
PDF_NBM_2019 = PDF_DIR / "bm2019_akt_nb_he_erg.pdf"


def _player_map(lines: list[str], **kwargs: object) -> dict[str, object]:
    players = _parse_player_blocks(lines, **kwargs)
    return {p.player_id: p for p in players}


def test_disambiguate_bayerische_event_name_splits_herren_and_damen() -> None:
    title = "Bayerische Meisterschaft 2017"
    men = disambiguate_bayerische_event_name(
        title,
        Path("bm2017_akt_einz_he_erg.pdf"),
        2017,
    )
    women = disambiguate_bayerische_event_name(
        title,
        Path("bm2017_akt_einz_da_erg.pdf"),
        2017,
    )
    assert men == "Bayerische Meisterschaft Einzel 2017"
    assert women == "Bayerische Meisterschaft Einzel Damen 2017"
    assert men != women


def test_disambiguate_bayerische_event_name_inserts_damen_into_einzel_title() -> None:
    title = "Bayerische Meisterschaft Einzel 2018"
    women = disambiguate_bayerische_event_name(
        title,
        Path("bm2018_akt_einz_f_erg.pdf"),
        2018,
    )
    assert women == "Bayerische Meisterschaft Einzel Damen 2018"


def test_disambiguate_bayerische_event_name_recognizes_akt_einz_m_filename() -> None:
    title = "Bayerische Meisterschaft Einzel 2018"
    men = disambiguate_bayerische_event_name(
        title,
        Path("bm2018_akt_einz_m_erg.pdf"),
        2018,
    )
    assert men == "Bayerische Meisterschaft Einzel 2018"


def test_disambiguate_bayerische_event_name_recognizes_einz_erg_h_and_d_shortnames() -> None:
    title = "Bayerische Meisterschaft Einzel 2010"
    men = disambiguate_bayerische_event_name(title, Path("bm2010_einz_erg_h.pdf"), 2010)
    women = disambiguate_bayerische_event_name(title, Path("bm2010_einz_erg_d.pdf"), 2010)
    assert men == "Bayerische Meisterschaft Einzel 2010"
    assert women == "Bayerische Meisterschaft Einzel Damen 2010"


def test_disambiguate_bayerische_event_name_splits_doppel_m_and_f() -> None:
    title = "Bayerische Meisterschaft Doppel 2018"
    men = disambiguate_bayerische_event_name(title, Path("bm2018_akt_dopp_m_erg.pdf"), 2018)
    women = disambiguate_bayerische_event_name(title, Path("bm2018_akt_dopp_f_erg.pdf"), 2018)
    assert men == "Bayerische Meisterschaft Männer Doppel 2018"
    assert women == "Bayerische Meisterschaft Damen Doppel 2018"


def test_parse_player_blocks_finalrunde_summary_does_not_swallow_next_player() -> None:
    """Summary-only Finalrunde must not swallow the next rank+name line."""
    lines = [
        "41. Hoke Alfred",
        "Vorrunde 243",
        "136",
        "217",
        "218",
        "191",
        "166",
        "1171",
        "41.",
        "Münchner Kegler-Verein e.V.",
        "Zw-Runde 234",
        "168",
        "192",
        "209",
        "160",
        "161",
        "1124",
        "Keine Teilnahme BM!",
        "41.",
        "16710",
        "Finalrunde",
        "2295",
        "/ 12",
        "191.25",
        "42. George Joe",
        "Vorrunde 175",
        "213",
        "219",
        "214",
        "147",
        "155",
        "1123",
        "42.",
        "BSV Augsburg",
        "Zw-Runde 191",
        "146",
        "236",
        "194",
        "210",
        "182",
        "1159",
        "42.",
        "07013",
        "Finalrunde",
        "2282",
        "/ 12",
        "190.17",
    ]
    players = _player_map(lines)

    hoke = players["16710"]
    assert hoke.name == "Hoke Alfred"
    assert hoke.club == "Münchner Kegler-Verein e.V."
    assert hoke.rank == 41
    assert hoke.rounds[1] == [243, 136, 217, 218, 191, 166]
    assert hoke.rounds[2] == [234, 168, 192, 209, 160, 161]
    assert not hoke.rounds.get(3)

    george = players["07013"]
    assert george.name == "George Joe"
    assert george.club == "BSV Augsburg"
    assert george.rank == 42
    assert george.rounds[1] == [175, 213, 219, 214, 147, 155]


def test_parse_player_blocks_verein_prefix_club_line() -> None:
    lines = [
        "49. Naujack Uwe",
        "Vorrunde 190",
        "212",
        "188",
        "186",
        "212",
        "160",
        "1148",
        "49.",
        "1. BBV Lindau",
        "Zw-Runde 170",
        "193",
        "204",
        "160",
        "184",
        "181",
        "1092",
        "49.",
        "07292",
        "Finalrunde",
        "2240",
        "/ 12",
        "186.67",
    ]
    players = _player_map(lines)
    naujack = players["07292"]
    assert naujack.name == "Naujack Uwe"
    assert naujack.club == "BBV Lindau"
    assert naujack.rank == 49


def test_parse_player_blocks_rank_marker_sets_club_not_player() -> None:
    """After Vorrunde, ``{rank}.`` marks the club line — not a new player."""
    lines = [
        "5. Muster Max",
        "Vorrunde 200",
        "200",
        "200",
        "200",
        "200",
        "200",
        "1200",
        "5.",
        "Totally Unknown Sportsverein XYZ",
        "Zw-Runde 200",
        "200",
        "200",
        "200",
        "200",
        "200",
        "1200",
        "5.",
        "12345",
        "Finalrunde 200",
        "200",
        "200",
        "200",
        "200",
        "200",
        "1200",
    ]
    players = _player_map(lines)
    player = players["12345"]
    assert player.name == "Muster Max"
    assert player.club == "Totally Unknown Sportsverein XYZ"


def test_parse_player_blocks_zw_runde_abg_then_player_id() -> None:
    lines = [
        "56. Karl William",
        "Vorrunde 247",
        "150",
        "233",
        "165",
        "198",
        "159",
        "1152",
        "56.",
        "BBH - BC Bamberger Bowlinghaus",
        "Zw-Runde abg",
        "56.",
        "16532",
        "Finalrunde",
        "1152",
        "/",
        "6",
        "192,00",
        "57. Odorfer René",
        "Vorrunde 194",
        "192",
        "151",
        "144",
        "209",
        "236",
        "1126",
        "57.",
        "STE - BF Rot-Weiß Lichtenhof 69",
        "Zw-Runde abg",
        "57.",
        "16782",
        "Finalrunde",
        "1126",
        "/",
        "6",
        "187,67",
    ]
    players = _player_map(lines)
    karl = players["16532"]
    assert karl.name == "Karl William"
    assert karl.club == "BBH - BC Bamberger Bowlinghaus"
    assert karl.rounds[1] == [247, 150, 233, 165, 198, 159]
    assert karl.rounds[2] == []
    rene = players["16782"]
    assert rene.name == "Odorfer René"
    assert rene.rounds[1] == [194, 192, 151, 144, 209, 236]


def test_parse_player_blocks_verl_stops_vorrunde_and_keeps_player() -> None:
    lines = [
        "99. Montag Wolfgang",
        "Vorrunde 169",
        "184",
        "verl.",
        "353",
        "99.",
        "BBH - BC Bamberger Bowlinghaus",
        "Zw-Runde",
        "99.",
        "16534",
        "Finalrunde",
        "353",
        "/",
        "2",
        "176,50",
    ]
    players = _player_map(lines)
    montag = players["16534"]
    assert montag.name == "Montag Wolfgang"
    assert montag.club == "BBH - BC Bamberger Bowlinghaus"
    assert montag.rounds[1] == [169, 184]
    assert montag.rounds[2] == []


def test_line_contains_game_scores() -> None:
    from database.tournament_import.adapters.legacy_pdf_erg_2016 import _line_contains_game_scores

    assert _line_contains_game_scores("Vorrunde 243")
    assert _line_contains_game_scores("175")
    assert not _line_contains_game_scores("George Joe")
    assert not _line_contains_game_scores("Totally Unknown Sportsverein XYZ")
    assert not _line_contains_game_scores("1. BBV Lindau")


def test_parse_player_blocks_configurable_cut_line() -> None:
    lines = [
        "1. Dropout Test",
        "Vorrunde 200",
        "200",
        "200",
        "200",
        "200",
        "200",
        "1200",
        "1.",
        "Club Irrelevant",
        "Zw-Runde 200",
        "200",
        "200",
        "200",
        "200",
        "200",
        "1200",
        "CUSTOM CUT PHRASE",
        "1.",
        "99999",
        "Finalrunde",
        "2400",
        "/ 12",
        "200.00",
    ]
    players = _player_map(lines, extra_skip_patterns=["CUSTOM CUT PHRASE"])
    dropout = players["99999"]
    assert dropout.name == "Dropout Test"
    assert not dropout.rounds.get(3)


def test_parse_player_blocks_ignores_date_range_dash_header() -> None:
    lines = [
        "29. - 30.03.2014",
        "Platz",
        "1",
        "2",
        "3",
        "1.",
        "Börding, Tobias",
        "1.",
        "BV 68 Regensburg",
        "Vorrunde",
        "203",
        "215",
        "206",
        "201",
        "223",
        "225",
        "1.",
        "Ratisbona",
        "Zwi.-Runde",
        "219",
        "256",
        "181",
        "299",
        "267",
        "243",
        "1.",
        "07592",
        "Finalrunde",
        "220",
        "197",
        "234",
        "194",
        "172",
        "225",
        "3980",
        "/ 18",
        "221,11",
    ]
    players = _player_map(lines)
    leader = players["07592"]
    assert leader.rank == 1
    assert leader.name == "Börding, Tobias"
    assert leader.club == "Ratisbona"
    assert leader.verein == "BV 68 Regensburg"


@pytest.mark.skipif(
    not Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2014_nb_he_erg.pdf").is_file(),
    reason="bm2014 NBM sample PDF not on disk",
)
def test_parse_player_blocks_2014_nbm_pdf_leaderboard() -> None:
    from database.tournament_import.adapters.legacy_pdf_erg_2016 import _pdf_text

    pdf = Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2014_nb_he_erg.pdf")
    lines = [ln.strip() for ln in _pdf_text(pdf).splitlines()]
    players = _parse_player_blocks(lines)
    by_rank = {player.rank: player for player in players}

    assert by_rank[1].name == "Börding, Tobias"
    assert by_rank[1].player_id == "07592"
    assert by_rank[1].club == "Ratisbona"
    assert by_rank[1].verein == "BV 68 Regensburg"
    assert by_rank[9].name == "Harles, Michael"
    assert by_rank[9].club == "Comet"
    assert by_rank[9].verein == "BC Nürnberg"
    assert by_rank[10].name == "Völlmerk, Oliver"
    assert by_rank[10].club != "/ 18"
    assert set(by_rank) >= set(range(1, 10))


@pytest.mark.skipif(not PDF_2019.is_file(), reason="sample PDF not on disk")
def test_legacy_pdf_erg_2016_parses_sbm_2019_leader() -> None:
    entry = ImportEntry(
        id="sbm-2019-herren",
        format="legacy_pdf_erg_2016",
        source=str(PDF_2019),
    )
    rows = parse_legacy_pdf_erg_2016(PDF_2019, entry)

    assert rows
    assert {r["Event Name"] for r in rows} == {"Südbayerische Meisterschaft Einzel 2019"}

    leader = [r for r in rows if r["Player ID"] == "07592" and r["Round Number"] == "1"]
    assert leader
    assert leader[0]["Player ID"] == "07592"
    assert leader[0]["Score"] == "245"
    assert leader[0]["Club"] == "MKV - BK München"


@pytest.mark.skipif(not PDF_2016.is_file(), reason="sample PDF not on disk")
def test_legacy_pdf_erg_2016_sbm_2016_dropout_players() -> None:
    entry = ImportEntry(
        id="sbm-2016-herren",
        format="legacy_pdf_erg_2016",
        source=str(PDF_2016),
        options={"event_name": "Südbayerische Meisterschaft Einzel 2016", "season": "15/16"},
    )
    rows = parse_legacy_pdf_erg_2016(PDF_2016, entry)
    by_id = {r["Player ID"]: r for r in rows if r["Round Number"] == "1"}

    assert by_id["16710"]["Player"] == "Hoke Alfred"
    assert by_id["07013"]["Player"] == "George Joe"
    assert by_id["07292"]["Player"] == "Naujack Uwe"

    club_as_player = {
        r["Player"]
        for r in rows
        if r["Player"].endswith("e.V.") or r["Player"].startswith(("BSV ", "BV ", "BBV ", "BSC "))
    }
    assert not club_as_player
@pytest.mark.skipif(not PDF_2019.is_file(), reason="sample PDF not on disk")
def test_legacy_pdf_erg_2016_player_coverage() -> None:
    entry = ImportEntry(id="sbm-2019", format="legacy_pdf_erg_2016", source=str(PDF_2019))
    rows = parse_legacy_pdf_erg_2016(PDF_2019, entry)
    players = {r["Player ID"] for r in rows}
    assert len(players) >= 40
    assert all(0 <= int(r["Score"]) <= 300 for r in rows)


@pytest.mark.skipif(not PDF_NBM_2016.is_file(), reason="NBM 2016 PDF not on disk")
def test_legacy_pdf_erg_2016_nbm_2016_includes_abg_dropout_players() -> None:
    entry = ImportEntry(
        id="nbm-2016-herren",
        format="legacy_pdf_erg_2016",
        source=str(PDF_NBM_2016),
        options={"event_name": "Nordbayerische Meisterschaft", "season": "15/16"},
    )
    rows = parse_legacy_pdf_erg_2016(PDF_NBM_2016, entry)
    by_id = {r["Player ID"]: r["Player"] for r in rows}
    assert "16532" in by_id
    assert by_id["16532"] == "Karl William"
    assert len({r["Player ID"] for r in rows}) >= 80


@pytest.mark.skipif(not PDF_NBM_2019.is_file(), reason="NBM 2019 PDF not on disk")
def test_legacy_pdf_erg_2016_nbm_2019_includes_verl_dropout_player() -> None:
    entry = ImportEntry(
        id="nbm-2019-herren",
        format="legacy_pdf_erg_2016",
        source=str(PDF_NBM_2019),
        options={"event_name": "Nordbayerische Meisterschaft", "season": "18/19"},
    )
    rows = parse_legacy_pdf_erg_2016(PDF_NBM_2019, entry)
    by_id = {r["Player ID"]: r["Player"] for r in rows}
    assert "16534" in by_id
    assert by_id["16534"] == "Montag Wolfgang"
    montag_scores = [int(r["Score"]) for r in rows if r["Player ID"] == "16534" and r["Round Number"] == "1"]
    assert montag_scores == [169, 184]
    assert len({r["Player ID"] for r in rows}) >= 98
