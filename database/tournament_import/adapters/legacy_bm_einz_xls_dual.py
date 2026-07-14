"""Legacy Bayerische Meisterschaft Einzel XLS (dual Herren/Damen sheets, e.g. 06/07)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import xlrd

from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import ROUND_LABELS_PDF_2016

_ROUND_LABELS = {
    1: ROUND_LABELS_PDF_2016[1],
    2: ROUND_LABELS_PDF_2016[2],
    3: ROUND_LABELS_PDF_2016[3],
}


def _round_number(label: object) -> int:
    text = str(label or "").strip().lower()
    if text.startswith("vor"):
        return 1
    if text.startswith("zw"):
        return 2
    if text.startswith("fin"):
        return 3
    return 0


def _int_cell(value: object) -> int | None:
    if isinstance(value, (int, float)) and value == int(value):
        return int(value)
    return None


def _parse_sheet_rows(
    sheet,
    *,
    season: str,
    event_name: str,
    location: str = "",
    calendar_year: int,
) -> List[Dict[str, str]]:
    default_date = f"{calendar_year}-01-01"
    rows: List[Dict[str, str]] = []
    row_idx = 2
    while row_idx < sheet.nrows:
        rank = _int_cell(sheet.cell_value(row_idx, 0))
        name = str(sheet.cell_value(row_idx, 1) or "").strip()
        round_label = sheet.cell_value(row_idx, 2)
        if rank is None or rank <= 0 or not name or _round_number(round_label) != 1:
            row_idx += 1
            continue

        club = ""
        player_id = ""
        if row_idx + 1 < sheet.nrows:
            club = str(sheet.cell_value(row_idx + 1, 1) or "").strip()
        if row_idx + 2 < sheet.nrows:
            player_id = str(_int_cell(sheet.cell_value(row_idx + 2, 1)) or "")

        for offset in range(3):
            line = row_idx + offset
            if line >= sheet.nrows:
                break
            round_number = _round_number(sheet.cell_value(line, 2))
            if round_number <= 0:
                continue
            for game_idx in range(6):
                col = 3 + game_idx
                if col >= sheet.ncols:
                    break
                score = _int_cell(sheet.cell_value(line, col))
                if score is None:
                    continue
                rows.append(
                    {
                        "Season": season,
                        "Date": default_date,
                        "Location": location,
                        "Event Type": "tournament",
                        "Event Name": event_name,
                        "Round Number": str(round_number),
                        "Round Name": _ROUND_LABELS[round_number],
                        "Player": name,
                        "Player ID": player_id,
                        "Club": club,
                        "Game Number": str(game_idx),
                        "Score": str(score),
                        "Handicap": "0",
                    }
                )
        row_idx += 3
    return rows


class LegacyBmEinzXlsDualAdapter:
    format_id = "legacy_bm_einz_xls_dual"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        if not source.is_file():
            raise FileNotFoundError(source)
        sheet_name = str(entry.options.get("sheet") or "").strip()
        if not sheet_name:
            raise ValueError(f"legacy_bm_einz_xls_dual requires options.sheet for {source.name}")
        event_name = str(entry.options.get("event_name") or "").strip()
        season = str(entry.options.get("season") or "").strip()
        if not event_name or not season:
            raise ValueError(f"legacy_bm_einz_xls_dual requires event_name and season for {source.name}")
        calendar_year = int(entry.options.get("calendar_year") or 2007)

        workbook = xlrd.open_workbook(source)
        if sheet_name not in workbook.sheet_names():
            raise ValueError(f"Sheet {sheet_name!r} missing in {source.name}")
        sheet = workbook.sheet_by_name(sheet_name)
        location = str(entry.options.get("location") or "").strip()
        rows = _parse_sheet_rows(
            sheet,
            season=season,
            event_name=event_name,
            location=location,
            calendar_year=calendar_year,
        )
        if not rows:
            raise ValueError(f"No player rows parsed from {source.name} sheet {sheet_name}")
        return rows
