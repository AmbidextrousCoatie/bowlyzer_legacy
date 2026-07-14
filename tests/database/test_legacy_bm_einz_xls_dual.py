"""Tests for legacy BM Einzel dual-sheet XLS adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.adapters.legacy_bm_einz_xls_dual import LegacyBmEinzXlsDualAdapter
from database.tournament_import.config import ImportEntry

SAMPLE_XLS = Path(r"C:\tmp\bowlyzer\data\tournaments\input\bm2007_einz_erg.xls")


@pytest.mark.skipif(not SAMPLE_XLS.is_file(), reason="bm2007_einz_erg.xls not on disk")
def test_parse_bm_2007_herren_sheet() -> None:
    adapter = LegacyBmEinzXlsDualAdapter()
    entry = ImportEntry(
        id="legacy-bm-2007-xls-herren",
        enabled=True,
        format="legacy_bm_einz_xls_dual",
        source=str(SAMPLE_XLS),
        merge_target="manual",
        output="out.csv",
        options={
            "sheet": "Herren",
            "season": "06/07",
            "calendar_year": 2007,
            "event_name": "Bayerische Meisterschaft Einzel 2007",
        },
    )
    rows = adapter.parse(SAMPLE_XLS, entry)
    assert len(rows) > 100
    assert all(row["Event Name"] == "Bayerische Meisterschaft Einzel 2007" for row in rows)
    assert all(row["Season"] == "06/07" for row in rows)
    players = {row["Player"] for row in rows}
    assert len(players) >= 50


@pytest.mark.skipif(not SAMPLE_XLS.is_file(), reason="bm2007_einz_erg.xls not on disk")
def test_parse_bm_2007_damen_sheet() -> None:
    adapter = LegacyBmEinzXlsDualAdapter()
    entry = ImportEntry(
        id="legacy-bm-2007-xls-damen",
        enabled=True,
        format="legacy_bm_einz_xls_dual",
        source=str(SAMPLE_XLS),
        merge_target="manual",
        output="out.csv",
        options={
            "sheet": "Damen",
            "season": "06/07",
            "calendar_year": 2007,
            "event_name": "Bayerische Meisterschaft Einzel Damen 2007",
        },
    )
    rows = adapter.parse(SAMPLE_XLS, entry)
    assert len(rows) > 50
    players = {row["Player"] for row in rows}
    assert len(players) >= 20
