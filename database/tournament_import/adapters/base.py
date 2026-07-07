"""Adapter protocol and import result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Protocol

from database.tournament_import.config import ImportEntry


@dataclass
class ImportResult:
    entry_id: str
    source: Path
    event_names: List[str] = field(default_factory=list)
    raw_row_count: int = 0
    postprocessed_row_count: int = 0
    warnings: List[str] = field(default_factory=list)


class TournamentImportAdapter(Protocol):
    format_id: str

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        """Return pre-postprocess tournament rows."""
