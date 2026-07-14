"""Tournament source registry lookup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from database.tournament_import.legacy_pdf_targets import LegacyPdfTarget, import_entry_for_target
from database.tournament_import.source_registry import (
    TournamentSourceRow,
    lookup_source_row,
    merge_registry_rows,
    write_source_registry,
)


def test_lookup_source_row_by_basename(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.csv"
    pdf_path = tmp_path / "bm2017_sb_he_erg.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 sample")

    write_source_registry(
        [
            TournamentSourceRow(
                file_basename=pdf_path.name,
                file_fingerprint="",
                file_path=str(pdf_path),
                season="16/17",
                calendar_year=2017,
                category_id="suedbayerische-herren",
                tournament_id="SBM M",
                event_name="Südbayerische Meisterschaft",
                gender="male",
                format="legacy_pdf_erg_2016",
                enabled=True,
            )
        ],
        registry_path,
    )

    hit = lookup_source_row(pdf_path, registry_path=registry_path)
    assert hit is not None
    assert hit.event_name == "Südbayerische Meisterschaft"
    assert hit.tournament_id == "SBM M"


def test_import_entry_for_target_uses_registry(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.csv"
    pdf_path = tmp_path / "bm2017_sb_he_erg.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 sample")

    write_source_registry(
        [
            TournamentSourceRow(
                file_basename=pdf_path.name,
                file_fingerprint="",
                file_path=str(pdf_path),
                season="16/17",
                calendar_year=2017,
                category_id="suedbayerische-herren",
                tournament_id="SBM M",
                event_name="Südbayerische Meisterschaft",
                gender="male",
                format="legacy_pdf_erg_2016",
                enabled=True,
            )
        ],
        registry_path,
    )

    target = LegacyPdfTarget(
        tournament_code="sbm",
        category_id="suedbayerische-herren",
        season_start_year=2016,
        calendar_year=2017,
        pdf_path=pdf_path,
    )
    with patch(
        "database.tournament_import.legacy_pdf_targets.lookup_source_row",
        return_value=TournamentSourceRow(
            file_basename=pdf_path.name,
            file_fingerprint="",
            file_path=str(pdf_path),
            season="16/17",
            calendar_year=2017,
            category_id="suedbayerische-herren",
            tournament_id="SBM M",
            event_name="Südbayerische Meisterschaft",
            gender="male",
            format="legacy_pdf_erg_2016",
            enabled=True,
        ),
    ):
        entry = import_entry_for_target(target)

    assert entry.format == "legacy_pdf_erg_2016"
    assert entry.options["event_name"] == "Südbayerische Meisterschaft"


def test_merge_registry_rows_preserves_manual_fields() -> None:
    existing = [
        TournamentSourceRow(
            file_basename="bm2012_sbm_h_erg.pdf",
            file_fingerprint="abc",
            file_path="",
            season="11/12",
            calendar_year=2012,
            category_id="suedbayerische-herren",
            tournament_id="SBM M",
            event_name="Südbayerische Meisterschaft",
            gender="male",
            format="legacy_pdf_erg_2012",
            enabled=True,
            notes="manual",
        )
    ]
    incoming = [
        TournamentSourceRow(
            file_basename="bm2012_sbm_h_erg.pdf",
            file_fingerprint="",
            file_path="/tmp/bm2012_sbm_h_erg.pdf",
            season="",
            calendar_year=2012,
            category_id="",
            tournament_id="",
            event_name="",
            gender="",
            format="",
            enabled=True,
            notes="scan",
        )
    ]
    merged = merge_registry_rows(existing, incoming)
    assert len(merged) == 1
    row = merged[0]
    assert row.file_fingerprint == "abc"
    assert row.format == "legacy_pdf_erg_2012"
    assert row.notes == "scan"


def test_merge_registry_rows_fills_empty_prior_fingerprint_from_incoming() -> None:
    existing = [
        TournamentSourceRow(
            file_basename="bm2018_akt_einz_m_erg.pdf",
            file_fingerprint="",
            file_path="",
            season="17/18",
            calendar_year=2018,
            category_id="bayerische-einzel-herren",
            tournament_id="BM M",
            event_name="Bayerische Meisterschaft Einzel 2018",
            gender="male",
            format="legacy_pdf_erg_2016",
            enabled=True,
            notes="seed basename (file missing)",
        )
    ]
    incoming = [
        TournamentSourceRow(
            file_basename="bm2018_akt_einz_m_erg.pdf",
            file_fingerprint="e35f28acc18c",
            file_path="bm2018_akt_einz_m_erg.pdf",
            season="17/18",
            calendar_year=2018,
            category_id="bayerische-einzel-herren",
            tournament_id="BM M",
            event_name="Bayerische Meisterschaft Einzel 2018",
            gender="male",
            format="legacy_pdf_erg_2016",
            enabled=True,
            notes="resolved from input dir",
        )
    ]
    merged = merge_registry_rows(existing, incoming)
    assert merged[0].file_fingerprint == "e35f28acc18c"


def test_merge_registry_rows_keeps_manual_format_over_detected() -> None:
    existing = [
        TournamentSourceRow(
            file_basename="bm2011_sbm_h_erg.pdf",
            file_fingerprint="abc",
            file_path="",
            season="10/11",
            calendar_year=2011,
            category_id="suedbayerische-herren",
            tournament_id="SBM M",
            event_name="Südbayerische Meisterschaft",
            gender="male",
            format="legacy_pdf_erg_2009",
            enabled=True,
            notes="manual override",
        )
    ]
    incoming = [
        TournamentSourceRow(
            file_basename="bm2011_sbm_h_erg.pdf",
            file_fingerprint="def",
            file_path="/tmp/bm2011_sbm_h_erg.pdf",
            season="10/11",
            calendar_year=2011,
            category_id="suedbayerische-herren",
            tournament_id="SBM M",
            event_name="Südbayerische Meisterschaft",
            gender="male",
            format="legacy_pdf_erg_2016",
            enabled=True,
            notes="bootstrap detect",
        )
    ]
    merged = merge_registry_rows(existing, incoming)
    assert merged[0].format == "legacy_pdf_erg_2009"


def test_merge_registry_rows_keeps_dual_sheet_rows_for_same_basename() -> None:
    shared = dict(
        file_basename="bm2007_einz_erg.xls",
        file_fingerprint="",
        file_path="bm2007_einz_erg.xls",
        season="06/07",
        calendar_year=2007,
        format="legacy_bm_einz_xls_dual",
        enabled=True,
        notes="exception",
    )
    incoming = [
        TournamentSourceRow(
            **shared,
            category_id="bayerische-einzel-herren",
            tournament_id="BM M",
            event_name="Bayerische Meisterschaft Einzel 2007",
            gender="male",
            source_sheet="Herren",
        ),
        TournamentSourceRow(
            **shared,
            category_id="bayerische-einzel-frauen",
            tournament_id="BM D",
            event_name="Bayerische Meisterschaft Einzel Damen 2007",
            gender="female",
            source_sheet="Damen",
        ),
    ]
    merged = merge_registry_rows([], incoming)
    assert len(merged) == 2
    sheets = {row.source_sheet for row in merged}
    assert sheets == {"Herren", "Damen"}
