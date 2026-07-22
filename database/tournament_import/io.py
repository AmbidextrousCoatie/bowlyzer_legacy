"""CSV read/write and merge helpers for tournament imports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from database.paths import gf_tournaments_combined_postprocessed_csv, manual_tournament_postprocessed_csv
from database.tournament_import.schema import POSTPROCESSED_HEADERS

MANUAL_TOURNAMENT_CSV = manual_tournament_postprocessed_csv()
GF_REGIONAL_TOURNAMENT_CSV = gf_tournaments_combined_postprocessed_csv()


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


def _season_event_key(row: Dict[str, str]) -> Tuple[str, str]:
    return (str(row.get("Season", "") or "").strip(), str(row.get("Event Name", "") or "").strip())


def strip_rows_for_season_tournament(
    target_path: Path,
    *,
    season: str,
    tournament_id: str = "",
    legacy_event_names: Sequence[str] = (),
) -> int:
    """
    Remove prior rows for one season before a registry-driven re-import.

    Drops rows whose ``(Season, Event Name)`` matches ``legacy_event_names``, and
    rows in the same season that already map to ``tournament_id``.
    """
    from data_access.tournament_coverage import tournament_id_for_event

    season_s = str(season or "").strip()
    if not season_s:
        return 0
    legacy = {str(name or "").strip() for name in legacy_event_names if str(name or "").strip()}
    rows = read_csv_rows(target_path)
    before = len(rows)
    kept: List[Dict[str, str]] = []
    for row in rows:
        if str(row.get("Season", "") or "").strip() != season_s:
            kept.append(row)
            continue
        event_name = str(row.get("Event Name", "") or "").strip()
        if event_name in legacy:
            continue
        if tournament_id and tournament_id_for_event(event_name) == tournament_id:
            continue
        kept.append(row)
    removed = before - len(kept)
    if removed:
        write_csv_rows(target_path, kept)
    return removed


def merge_rows_by_season_events(
    target_path: Path,
    new_rows: List[Dict[str, str]],
) -> Tuple[int, int]:
    existing_rows = read_csv_rows(target_path)
    target_keys = {_season_event_key(row) for row in new_rows}
    kept_rows = [row for row in existing_rows if _season_event_key(row) not in target_keys]
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


def merge_rows_by_event_name(
    target_path: Path,
    new_rows: List[Dict[str, str]],
) -> Tuple[int, int]:
    """Backward-compatible alias — merge replaces ``(Season, Event Name)`` keys only."""
    return merge_rows_by_season_events(target_path, new_rows)


def strip_event_from_csv(csv_path: Path, event_name: str) -> int:
    rows = read_csv_rows(csv_path)
    before = len(rows)
    kept = [r for r in rows if str(r.get("Event Name", "")).strip() != event_name]
    removed = before - len(kept)
    if removed:
        write_csv_rows(csv_path, kept)
    return removed
