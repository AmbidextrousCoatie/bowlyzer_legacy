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
    assert 3 not in hoke.rounds

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
    assert 3 not in dropout.rounds


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
