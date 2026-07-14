"""Registry-authoritative legacy PDF format resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from database.tournament_import.legacy_pdf_format import (
    FORMAT_2012,
    FORMAT_2016,
    resolve_legacy_pdf_import_format,
)
from database.tournament_import.source_registry import TournamentSourceRow


def _row(*, basename: str = "bm2011_sbm_h_erg.pdf", fmt: str = "") -> TournamentSourceRow:
    return TournamentSourceRow(
        file_basename=basename,
        file_fingerprint="",
        file_path="",
        season="10/11",
        calendar_year=2011,
        category_id="suedbayerische-herren",
        tournament_id="SBM M",
        event_name="Südbayerische Meisterschaft",
        gender="male",
        format=fmt,
        enabled=True,
    )


def test_resolve_uses_registry_format(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2011_sbm_h_erg.pdf"
    pdf.write_bytes(b"%PDF")
    fmt = resolve_legacy_pdf_import_format(pdf, _row(fmt=FORMAT_2016))
    assert fmt == FORMAT_2016


def test_resolve_rejects_empty_registry_format(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2011_sbm_h_erg.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="has no format"):
        resolve_legacy_pdf_import_format(pdf, _row(fmt=""))


def test_resolve_allows_detect_when_unregistered(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2012_sbm_h_erg.pdf"
    pdf.write_bytes(b"%PDF")
    with patch(
        "database.tournament_import.legacy_pdf_format.detect_legacy_pdf_format",
        return_value=FORMAT_2012,
    ):
        fmt = resolve_legacy_pdf_import_format(pdf, None, allow_detect_fallback=True)
    assert fmt == FORMAT_2012


def test_resolve_rejects_unregistered_without_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2012_sbm_h_erg.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="No registry row"):
        resolve_legacy_pdf_import_format(pdf, None, allow_detect_fallback=False)
