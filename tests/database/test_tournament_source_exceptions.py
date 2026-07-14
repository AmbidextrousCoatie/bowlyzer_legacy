"""Tests for shared-workbook tournament source exceptions."""

from __future__ import annotations

from database.tournament_import.source_exceptions import (
    exception_for_basename,
    exception_for_scrape_href,
    exceptions_as_registry_dicts,
    exceptions_for_api,
    load_source_exceptions,
    lookup_exception_target,
)


def test_load_bm_2007_exception() -> None:
    items = load_source_exceptions()
    assert any(item.id == "bm-2007-einz-dual-xls" for item in items)


def test_exception_for_scrape_href_matches_bm_einz_xls() -> None:
    exc = exception_for_scrape_href("bm2007_einz_erg.xls")
    assert exc is not None
    assert exc.file_basename == "bm2007_einz_erg.xls"
    assert len(exc.targets) == 2


def test_exception_for_basename() -> None:
    exc = exception_for_basename("bm2007_einz_erg.xls")
    assert exc is not None
    assert exc.season == "06/07"


def test_lookup_exception_target_herren_and_damen() -> None:
    herren = lookup_exception_target(
        season="06/07",
        event_name="Bayerische Meisterschaft Einzel 2007",
    )
    damen = lookup_exception_target(
        season="06/07",
        event_name="Bayerische Meisterschaft Einzel Damen 2007",
    )
    assert herren is not None
    assert damen is not None
    assert herren[1].sheet == "Herren"
    assert damen[1].sheet == "Damen"


def test_exceptions_as_registry_dicts_dual_rows() -> None:
    rows = exceptions_as_registry_dicts()
    bm2007 = [row for row in rows if row["file_basename"] == "bm2007_einz_erg.xls"]
    assert len(bm2007) == 2
    sheets = {row["source_sheet"] for row in bm2007}
    assert sheets == {"Herren", "Damen"}


def test_exceptions_for_api_shape() -> None:
    payload = exceptions_for_api()
    item = next(row for row in payload if row["id"] == "bm-2007-einz-dual-xls")
    assert item["format"] == "legacy_bm_einz_xls_dual"
    assert len(item["targets"]) == 2
