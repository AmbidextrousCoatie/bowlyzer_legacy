"""CSV read/write and merge helpers for tournament imports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

from database.paths import get_data_dir
from database.tournament_import.schema import POSTPROCESSED_HEADERS

MANUAL_TOURNAMENT_CSV = get_data_dir() / "tournament_manual_postprocessed.csv"
GF_REGIONAL_TOURNAMENT_CSV = (
    Path(__file__).resolve().parents[1] / "input" / "gf_tables_export" / "gf_tournaments_2026__combined_postprocessed.csv"
)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return [{k: str(v or "") for k, v in row.items()} for row in reader]


def write_csv_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=POSTPROCESSED_HEADERS, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({h: str(row.get(h, "") or "") for h in POSTPROCESSED_HEADERS})


def merge_rows_by_event_name(
    target_path: Path,
    new_rows: List[Dict[str, str]],
) -> Tuple[int, int]:
    existing_rows = read_csv_rows(target_path)
    target_event_names = {row["Event Name"] for row in new_rows}
    kept_rows = [row for row in existing_rows if row.get("Event Name", "") not in target_event_names]
    merged_rows = kept_rows + new_rows
    merged_rows.sort(
        key=lambda r: (
            r.get("Season", ""),
            r.get("Date", ""),
            r.get("Event Name", ""),
            int(r.get("Round Number", "0") or "0"),
            int(r.get("Game Number", "0") or "0"),
            r.get("Player", ""),
            r.get("Player ID", ""),
        )
    )
    write_csv_rows(target_path, merged_rows)
    return len(existing_rows), len(merged_rows)


def strip_event_from_csv(csv_path: Path, event_name: str) -> int:
    rows = read_csv_rows(csv_path)
    before = len(rows)
    kept = [r for r in rows if str(r.get("Event Name", "")).strip() != event_name]
    removed = before - len(kept)
    if removed:
        write_csv_rows(csv_path, kept)
    return removed
