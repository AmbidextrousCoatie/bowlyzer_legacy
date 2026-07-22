"""Bayerische Meisterschaft import: skip blank game cells and non-pin KO rows."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = ROOT / "scripts" / "data" / "import_bayerische_meisterschaft_xlsx.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_bayerische_meisterschaft_xlsx", IMPORTER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def imp():
    return _load_importer()


def test_as_int_score_blank_is_none(imp) -> None:
    assert imp._as_int_score(None) is None
    assert imp._as_int_score("") is None
    assert imp._as_int_score("  ") is None
    assert imp._as_int_score(215) == 215
    assert imp._as_int_score("215") == 215


def test_build_round_rows_skips_blank_game_cells(imp, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCell:
        def __init__(self, value):
            self.value = value

    class FakeWs:
        def cell(self, row: int, column: int):
            # row 6: player with pins in games 1–2 only (cols 3–4), blanks in 5–8 (cols 5–8)
            if row != 6:
                return FakeCell(None)
            if column == 1:
                return FakeCell("Test Spieler")
            if column == 2:
                return FakeCell(42)
            game_cols = {3: 200, 4: 210, 5: None, 6: "", 7: None, 8: None}
            return FakeCell(game_cols.get(column))

    class FakeWb:
        sheetnames = ["Optionen", "Vorrunde", "Zwischenlauf"]

        def __getitem__(self, name: str):
            if name == "Optionen":
                return FakeWs()
            return FakeWs()

    def fake_load_workbook(_path, data_only=True):
        return FakeWb()

    def fake_iter_round_rows(_path, sheet_name: str):
        if sheet_name != "Vorrunde":
            return []
        return [("Test Spieler", "42", [200, 210, None, None, None, None])]

    monkeypatch.setattr(imp, "load_workbook", fake_load_workbook)
    monkeypatch.setattr(imp, "_iter_round_rows", fake_iter_round_rows)

    meta = imp.TournamentMeta(
        season="25/26",
        event_name="Test - Einzel",
        location="Testort",
        dates={1: "2026-05-09", 2: "2026-05-10"},
    )
    rows, _ = imp._build_round_rows(meta, Path("dummy.xlsx"))
    assert len(rows) == 2
    assert all(int(r["Score"]) > 0 for r in rows)
    assert {r["Game Number"] for r in rows} == {"0", "1"}


def test_extract_ko_rows_skips_zero_pin_games(imp) -> None:
    class FakeWs:
        max_row = 0

        def cell(self, row: int, column: int):
            return type("C", (), {"value": None})()

    games, _ = imp._parse_ko_games(FakeWs(), 1)
    assert games == []

    class RowWs:
        max_row = 2

        def cell(self, row: int, column: int):
            values = {
                (1, 3): 0,
                (1, 4): ":",
                (1, 5): 0,
            }
            return type("C", (), {"value": values.get((row, column))})()

    games, _ = imp._parse_ko_games(RowWs(), 1)
    assert games == []


def test_parse_ko_games_scratch_total_skips_match_total_row(imp) -> None:
    """Two-game scratch totals (e.g. 295, 344) must not become a third game."""

    class FakeWs:
        max_row = 4

        def cell(self, row: int, column: int):
            # Match: 173:149, 171:146, then scratch total 344:295, then block end.
            rows = {
                1: {3: 173, 4: ":", 5: 149},
                2: {3: 171, 4: ":", 5: 146},
                3: {3: 344, 4: ":", 5: 295},
                4: {2: "gewonne spiele"},
            }
            return type("C", (), {"value": rows.get(row, {}).get(column)})()

    games, _ = imp._parse_ko_games(FakeWs(), 1, ko_finale_series="scratch_total_2g")
    assert games == [(173, 149), (171, 146)]


def test_parse_ko_games_bo3_skips_impossible_single(imp) -> None:
    class FakeWs:
        max_row = 2

        def cell(self, row: int, column: int):
            rows = {
                1: {3: 320, 4: ":", 5: 200},
                2: {3: 210, 4: ":", 5: 205},
            }
            return type("C", (), {"value": rows.get(row, {}).get(column)})()

    games, _ = imp._parse_ko_games(FakeWs(), 1, ko_finale_series="bo3_pins")
    assert games == [(210, 205)]
