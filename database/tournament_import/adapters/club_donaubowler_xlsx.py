"""Clubmeisterschaft Donaubowler XLSX adapter."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List

from database.paths import REPO_ROOT
from database.tournament_import.config import ImportEntry
from database.tournament_import.schema import season_label_from_calendar_year
from openpyxl import load_workbook


def _load_club_module():
    path = REPO_ROOT / "database" / "input" / "import_clubmeisterschaft_donaubowler_xlsx.py"
    name = "import_clubmeisterschaft_donaubowler_xlsx"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class ClubDonaubowlerXlsxAdapter:
    format_id = "club_donaubowler_xlsx"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        club = _load_club_module()
        opts = entry.options

        if source.is_dir():
            candidates = sorted(
                p for p in source.glob("*.xlsx") if not p.name.startswith("~") and not p.name.startswith(".~")
            )
            if not candidates:
                raise FileNotFoundError(f"No .xlsx files in {source}")
            xlsx_path = candidates[0]
        else:
            xlsx_path = source

        if not xlsx_path.is_file():
            raise FileNotFoundError(xlsx_path)

        year = int(opts.get("year", 2026))
        season = str(opts.get("season") or "").strip() or season_label_from_calendar_year(year)
        event_date = str(opts.get("date") or "2026-05-15").strip()
        location = str(opts.get("location") or "").strip()
        sheet = str(opts.get("sheet") or "").strip()
        first_data_row = int(opts.get("first_data_row", 2))
        league_csv = Path(str(opts.get("league_csv") or club.DEFAULT_LEAGUE_CSV)).resolve()

        player_lookup = club._build_player_id_lookup(league_csv)
        wb = load_workbook(xlsx_path, data_only=True)
        sheet_name = sheet or wb.sheetnames[0]
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not in workbook. Available: {wb.sheetnames}")
        ws = wb[sheet_name]

        clean_rows, _unmatched = club._extract_rows_for_sheet(
            ws,
            season=season,
            event_date=event_date,
            location=location,
            player_lookup=player_lookup,
            first_data_row=first_data_row,
        )
        if not clean_rows:
            raise ValueError(f"No score rows extracted from {xlsx_path}")
        return clean_rows
