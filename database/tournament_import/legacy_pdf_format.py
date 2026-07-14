"""Detect legacy PDF era / adapter for scraped Ergebnisliste files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from database.tournament_import.adapters.legacy_pdf_shared import pdf_text_sample

if TYPE_CHECKING:
    from database.tournament_import.source_registry import TournamentSourceRow

FORMAT_EDV_GRID = "legacy_pdf_erg_edv_grid"
FORMAT_2015 = "legacy_pdf_erg_2015"
FORMAT_2016 = "legacy_pdf_erg_2016"
FORMAT_2012 = "legacy_pdf_erg_2012"
FORMAT_2009 = "legacy_pdf_erg_2009"

LEGACY_PDF_FORMAT_IDS = frozenset({FORMAT_2009, FORMAT_2012, FORMAT_2015, FORMAT_2016, FORMAT_EDV_GRID})


def detect_legacy_pdf_format(source: Path) -> str:
    """Heuristic layout guess from PDF text (bootstrap / audit only)."""
    if not source.is_file():
        return FORMAT_2016
    text = pdf_text_sample(source)
    if _is_edv_grid_layout(text):
        return FORMAT_EDV_GRID
    if _is_2015_sheet_layout(text):
        return FORMAT_2015
    if _is_wide_table_layout(text):
        return FORMAT_2009
    if _is_2012_grid_layout(text):
        return FORMAT_2012
    if _is_2016_vertical_layout(text):
        return FORMAT_2016
    if _is_2009_vertical_layout(text):
        return FORMAT_2009
    return FORMAT_2016


def resolve_legacy_pdf_import_format(
    source: Path,
    registry: "TournamentSourceRow | None",
    *,
    allow_detect_fallback: bool = False,
) -> str:
    """Pick parser format for import.

    Registered PDFs use ``tournament_source_registry.csv`` ``format`` column only.
    Auto-detect is opt-in for unregistered files (bootstrap / one-off imports).
    """
    if registry is not None:
        assigned = (registry.format or "").strip()
        if not assigned:
            raise ValueError(
                f"Registry row for {registry.file_basename!r} has no format; "
                "set format in database/config/tournament_source_registry.csv "
                f"(known: {', '.join(sorted(LEGACY_PDF_FORMAT_IDS))})"
            )
        if assigned not in LEGACY_PDF_FORMAT_IDS:
            raise ValueError(
                f"Registry format {assigned!r} for {registry.file_basename!r} is unknown; "
                f"known: {', '.join(sorted(LEGACY_PDF_FORMAT_IDS))}"
            )
        return assigned

    if allow_detect_fallback:
        return detect_legacy_pdf_format(source)

    raise ValueError(
        f"No registry row for {source.name!r}; add it to "
        "database/config/tournament_source_registry.csv or pass allow_detect_fallback"
    )

def _is_edv_grid_layout(text: str) -> bool:
    if "EDV-Nr" not in text and "EDV-Nr." not in text:
        return False
    if re.search(r"^Sp 1$", text, flags=re.MULTILINE):
        return True
    if "Zw.Lauf" in text and "Vorlauf" in text:
        return True
    return False


def _is_2015_sheet_layout(text: str) -> bool:
    if not re.search(r"^Datum\s+\d", text, flags=re.MULTILINE | re.IGNORECASE):
        return False
    if re.search(r"^Vorrunde$", text, flags=re.MULTILINE):
        return False
    if re.search(r"^Zw-Runde\b", text, flags=re.MULTILINE | re.IGNORECASE):
        return False
    comma_names = re.findall(r"^[A-Za-zÀ-ÿ][^\n,]{0,40},\s+[A-Za-zÀ-ÿ]", text, flags=re.MULTILINE)
    spaced_pass = re.search(r"^\d{2}\s+\d{2}\s+\d{2}$", text, flags=re.MULTILINE)
    return len(comma_names) >= 10 and bool(spaced_pass)


def _is_wide_table_layout(text: str) -> bool:
    return "EDV-Nr" in text and bool(re.search(r"^Sp 1$", text, flags=re.MULTILINE))


def _is_2012_grid_layout(text: str) -> bool:
    if re.search(r"^Rd\.1$", text, flags=re.MULTILINE):
        return True
    if text.count("Rd.1") >= 3 and "Rd.2" in text and "Rd.3" in text:
        return True
    return False


def _is_2016_vertical_layout(text: str) -> bool:
    if re.search(r"^Zw-Runde\b", text, flags=re.MULTILINE | re.IGNORECASE):
        return True
    if "Zwischenlauf" in text:
        return True
    if "Zwi.-Runde" in text and "Finalrunde" in text:
        return True
    return False


def _is_2009_vertical_layout(text: str) -> bool:
    if "Zwi.-Runde" in text and "Finale" in text and "Finalrunde" not in text:
        return True
    if re.search(r"^Vor\.$", text, flags=re.MULTILINE) and re.search(r"^Zw\.$", text, flags=re.MULTILINE):
        return True
    return False
