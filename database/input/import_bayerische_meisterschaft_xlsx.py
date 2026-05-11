"""
Import Bayerische Meisterschaft XLSX files into tournament postprocessed CSV.

Expected workbook structure:
- Sheet "Optionen": B3 (name), B4 (subgroup), B5 (season year), B7 (date range)
- Sheet "Vorrunde": rows from 6, columns A..H (name, id, six games), I optional total
- Sheet "Zwischenlauf": rows from 6, columns A..H (name, id, six games), I optional total

Output:
- Per-import postprocessed CSV under database/data/
- Merged append/update into database/input/gf_tables_export/gf_tournaments_2026__combined_postprocessed.csv
- Rebuilds database/data/player_stats_merged_plus_tournaments.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GF_COMBINED_POSTPROCESSED = (
    ROOT / "database" / "input" / "gf_tables_export" / "gf_tournaments_2026__combined_postprocessed.csv"
)
DEFAULT_OUTPUT = ROOT / "database" / "data" / "tournament_bayerische_meisterschaft_2026_postprocessed.csv"

POSTPROCESSED_HEADERS = [
    "Season",
    "Date",
    "Location",
    "Event Type",
    "Event Name",
    "Round Number",
    "Round Name",
    "Player",
    "Player ID",
    "Club",
    "Game Number",
    "Score",
    "Handicap",
    "Cumulative Score",
    "Stage Rank",
    "Cut Line",
    "Cut Basis",
    "Overall Cumulative Score",
]


@dataclass(frozen=True)
class TournamentMeta:
    season: str
    event_name: str
    location: str
    dates: Dict[int, str]


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
        return int(float(value))
    except Exception:
        return default


def _season_label(year: int) -> str:
    # Keep same style used by SBM/NBM GF exports, e.g. 2026 -> 25/26.
    prev_yy = (year - 1) % 100
    curr_yy = year % 100
    return f"{prev_yy:02d}/{curr_yy:02d}"


def _parse_date_token(token: str, season_year: int) -> str:
    token = token.strip()
    if "." not in token:
        raise ValueError(f"Invalid date token '{token}', expected d.m")
    day_s, month_s = token.split(".", 1)
    day = int(day_s)
    month = int(month_s)
    return date(season_year, month, day).isoformat()


def _parse_date_range(raw: str, season_year: int) -> Dict[int, str]:
    value = raw.replace("bis", "-")
    parts = [p.strip() for p in value.split("-") if p.strip()]
    if len(parts) < 2:
        raise ValueError(f"Invalid date range '{raw}'")
    return {1: _parse_date_token(parts[0], season_year), 2: _parse_date_token(parts[1], season_year)}


def _read_optionen_meta(workbook_path: Path) -> TournamentMeta:
    wb = load_workbook(workbook_path, data_only=True)
    if "Optionen" not in wb.sheetnames:
        raise ValueError(f"Workbook missing 'Optionen' sheet: {workbook_path}")

    ws = wb["Optionen"]
    event_base = _clean_text(ws["B3"].value)
    subgroup = _clean_text(ws["B4"].value)
    season_year = _as_int(ws["B5"].value)
    date_range = _clean_text(ws["B7"].value)
    location = _clean_text(ws["B12"].value)

    if not event_base or not subgroup or season_year <= 0 or not date_range:
        raise ValueError(f"Incomplete Optionen metadata in '{workbook_path.name}'")

    event_name = f"{event_base} - {subgroup}"
    season = _season_label(season_year)
    dates = _parse_date_range(date_range, season_year)
    return TournamentMeta(season=season, event_name=event_name, location=location, dates=dates)


def _iter_round_rows(workbook_path: Path, sheet_name: str) -> Iterable[Tuple[str, str, List[int]]]:
    wb = load_workbook(workbook_path, data_only=True)
    if sheet_name not in wb.sheetnames:
        return []

    ws = wb[sheet_name]
    rows: List[Tuple[str, str, List[int]]] = []
    row_idx = 6
    consecutive_empty = 0
    # Some sheets contain visual spacer rows in the middle; only stop after
    # a longer empty run near the real end of data.
    max_consecutive_empty = 20
    max_scan_row = 800
    while row_idx <= max_scan_row:
        name = _clean_text(ws.cell(row=row_idx, column=1).value)
        pid = _as_int(ws.cell(row=row_idx, column=2).value)
        if not name and pid <= 0:
            consecutive_empty += 1
            if consecutive_empty >= max_consecutive_empty:
                break
            row_idx += 1
            continue
        consecutive_empty = 0
        if name and pid > 0:
            games = [_as_int(ws.cell(row=row_idx, column=col).value) for col in range(3, 9)]
            rows.append((name, str(pid), games))
        row_idx += 1
    return rows


def _build_round_rows(meta: TournamentMeta, workbook_path: Path) -> List[Dict[str, str]]:
    round_map = {
        1: ("Vorrunde", "Vorlauf"),
        2: ("Zwischenlauf", "Zwischenlauf"),
    }
    rows: List[Dict[str, str]] = []
    for round_number, (sheet_name, round_name) in round_map.items():
        source_rows = list(_iter_round_rows(workbook_path, sheet_name))
        for player_name, player_id, game_scores in source_rows:
            for game_idx, score in enumerate(game_scores):
                rows.append(
                    {
                        "Season": meta.season,
                        "Date": meta.dates[round_number],
                        "Location": meta.location,
                        "Event Type": "tournament",
                        "Event Name": meta.event_name,
                        "Round Number": str(round_number),
                        "Round Name": round_name,
                        "Player": player_name,
                        "Player ID": player_id,
                        "Club": "",
                        "Game Number": str(game_idx),
                        "Score": str(score),
                        "Handicap": "0",
                    }
                )
    return rows


def _postprocess(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    by_event: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_event[row["Event Name"]].append(row)

    out: List[Dict[str, str]] = []
    for _, event_rows in sorted(by_event.items()):
        by_round: Dict[int, List[Dict[str, str]]] = defaultdict(list)
        for row in event_rows:
            by_round[int(row["Round Number"])].append(row)

        overall_running: Dict[str, int] = defaultdict(int)
        for round_number in sorted(by_round.keys()):
            round_rows = by_round[round_number]
            by_game: Dict[int, List[Dict[str, str]]] = defaultdict(list)
            for row in round_rows:
                by_game[int(row["Game Number"])].append(row)

            stage_running: Dict[str, int] = defaultdict(int)
            cut_players = 0
            cut_basis = ""

            for game_number in sorted(by_game.keys()):
                game_rows = sorted(by_game[game_number], key=lambda r: (r["Player"], r["Player ID"]))
                for row in game_rows:
                    pid = row["Player ID"]
                    score = int(row["Score"])
                    stage_running[pid] += score
                    overall_running[pid] += score

                ranked_pids = sorted(
                    stage_running.keys(),
                    key=lambda pid: (-stage_running[pid], next(r["Player"] for r in game_rows if r["Player ID"] == pid)),
                )
                rank_by_pid = {pid: idx + 1 for idx, pid in enumerate(ranked_pids)}

                cut_line = ""
                if cut_players > 0 and ranked_pids:
                    cut_idx = min(cut_players, len(ranked_pids)) - 1
                    cut_line = str(stage_running[ranked_pids[cut_idx]])

                for row in game_rows:
                    pid = row["Player ID"]
                    out_row = dict(row)
                    out_row["Cumulative Score"] = str(stage_running[pid])
                    out_row["Stage Rank"] = str(rank_by_pid[pid])
                    out_row["Cut Line"] = cut_line
                    out_row["Cut Basis"] = cut_basis
                    out_row["Overall Cumulative Score"] = str(overall_running[pid])
                    out.append(out_row)
    return out


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        return [{k: str(v or "") for k, v in row.items()} for row in reader]


def _write_csv_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=POSTPROCESSED_HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _merge_into_combined(new_rows: List[Dict[str, str]]) -> Tuple[int, int]:
    existing_rows = _read_csv_rows(GF_COMBINED_POSTPROCESSED)
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
    _write_csv_rows(GF_COMBINED_POSTPROCESSED, merged_rows)
    return len(existing_rows), len(merged_rows)


def _rebuild_player_hybrid() -> None:
    # Reuse existing app config merge logic to keep schema in sync.
    from app.config.database_config import _build_player_merged_hybrid_csv

    _build_player_merged_hybrid_csv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Bayerische Meisterschaft XLSX files.")
    parser.add_argument(
        "--xlsx-dir",
        required=True,
        help="Directory containing Bayerische Meisterschaft XLSX files.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output postprocessed CSV for this import batch.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    xlsx_dir = Path(args.xlsx_dir).resolve()
    output_path = Path(args.output).resolve()
    if not xlsx_dir.is_dir():
        raise FileNotFoundError(f"XLSX directory not found: {xlsx_dir}")

    all_clean_rows: List[Dict[str, str]] = []
    for workbook_path in sorted(xlsx_dir.glob("*.xlsx")):
        meta = _read_optionen_meta(workbook_path)
        workbook_rows = _build_round_rows(meta, workbook_path)
        all_clean_rows.extend(workbook_rows)

    if not all_clean_rows:
        raise ValueError(f"No tournament rows found in '{xlsx_dir}'")

    postprocessed_rows = _postprocess(all_clean_rows)
    _write_csv_rows(output_path, postprocessed_rows)
    before_count, after_count = _merge_into_combined(postprocessed_rows)
    _rebuild_player_hybrid()

    event_names = sorted({row["Event Name"] for row in postprocessed_rows})
    print(f"Imported events: {event_names}")
    print(f"Wrote batch output: {output_path} ({len(postprocessed_rows)} rows)")
    print(
        "Updated combined tournaments CSV: "
        f"{GF_COMBINED_POSTPROCESSED} ({before_count} -> {after_count} rows)"
    )
    print("Rebuilt player hybrid CSV: database/data/player_stats_merged_plus_tournaments.csv")


if __name__ == "__main__":
    main()
