"""Tests for legacy PDF era detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.tournament_import.legacy_pdf_format import (
    FORMAT_2009,
    FORMAT_2012,
    FORMAT_2016,
    detect_legacy_pdf_format,
)

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("bm2012_sbm_h_erg.pdf", FORMAT_2012),
        ("bm2009_sb_da_erg.pdf", FORMAT_2009),
        ("bm2010_sb_he_erg.pdf", FORMAT_2009),
        ("bm2013_sb_herren_erg.pdf", FORMAT_2016),
        ("bm2016_sb_he_erg.pdf", FORMAT_2016),
    ],
)
def test_detect_legacy_pdf_format(filename: str, expected: str) -> None:
    pdf = PDF_DIR / filename
    if not pdf.is_file():
        pytest.skip(f"missing fixture PDF: {pdf}")
    assert detect_legacy_pdf_format(pdf) == expected
