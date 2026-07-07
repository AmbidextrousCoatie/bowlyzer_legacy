"""Adapter registry."""

from __future__ import annotations

from typing import Dict

from database.tournament_import.adapters.base import TournamentImportAdapter
from database.tournament_import.adapters.bm_xlsx_optionen import BmXlsxOptionenAdapter
from database.tournament_import.adapters.club_donaubowler_xlsx import ClubDonaubowlerXlsxAdapter
from database.tournament_import.adapters.legacy_pdf_erg_2016 import LegacyPdfErg2016Adapter

_ADAPTERS: Dict[str, TournamentImportAdapter] = {
    BmXlsxOptionenAdapter.format_id: BmXlsxOptionenAdapter(),
    ClubDonaubowlerXlsxAdapter.format_id: ClubDonaubowlerXlsxAdapter(),
    LegacyPdfErg2016Adapter.format_id: LegacyPdfErg2016Adapter(),
}


def get_adapter(adapter_id: str) -> TournamentImportAdapter:
    adapter = _ADAPTERS.get(adapter_id)
    if adapter is None:
        known = ", ".join(sorted(_ADAPTERS))
        raise KeyError(f"Unknown tournament import adapter '{adapter_id}'. Known: {known}")
    return adapter
