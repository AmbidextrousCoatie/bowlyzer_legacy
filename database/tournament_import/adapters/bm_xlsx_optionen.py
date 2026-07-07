"""Bayerische Meisterschaft XLSX adapter (Optionen + Vorrunde + Zwischenlauf [+ KO])."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List

from database.paths import REPO_ROOT
from database.tournament_import.config import ImportEntry


def _load_legacy_module():
    path = REPO_ROOT / "database" / "input" / "import_bayerische_meisterschaft_xlsx.py"
    name = "import_bayerische_meisterschaft_xlsx"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class BmXlsxOptionenAdapter:
    format_id = "bm_xlsx_optionen"

    def parse(self, source: Path, entry: ImportEntry) -> List[Dict[str, str]]:
        legacy = _load_legacy_module()
        include_ko = bool(entry.options.get("include_ko_finale", False))

        paths: List[Path]
        if source.is_dir():
            paths = sorted(source.glob("*.xlsx"))
        elif source.is_file():
            paths = [source]
        else:
            raise FileNotFoundError(f"XLSX source not found: {source}")

        rows: List[Dict[str, str]] = []
        for workbook_path in paths:
            meta = legacy._read_optionen_meta(workbook_path)
            workbook_rows, player_id_by_name = legacy._build_round_rows(meta, workbook_path)
            if include_ko:
                workbook_rows.extend(legacy._extract_ko_rows(meta, workbook_path, player_id_by_name))
            rows.extend(workbook_rows)
        if not rows:
            raise ValueError(f"No tournament rows parsed from {source}")
        return rows
