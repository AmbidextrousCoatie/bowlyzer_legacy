"""
CLI: postprocess a clean per-game tournament CSV into an aggregated CSV.

Expected input format (semicolon-separated):
- One row per player per game
- Includes at least: Round Number, Player ID, Player, Game Number, Score

Adds output columns:
- Cumulative Score (running within current round)
- Stage Rank (after each game within current round)
- Cut Line (current cut threshold score for configured rounds)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_COLUMNS = [
    "Round Number",
    "Player ID",
    "Player",
    "Game Number",
    "Score",
]

OUTPUT_EXTRA_COLUMNS = ["Cumulative Score", "Stage Rank", "Cut Line"]


def parse_cut_map(raw_rules: List[str]) -> Dict[int, int]:
    """
    Parse repeatable --cut arguments in the shape ROUND:CUT_TO.
    Example: --cut 1:8 --cut 2:4
    """
    cut_map: Dict[int, int] = {}
    for rule in raw_rules:
        if ":" not in rule:
            raise ValueError(f"Invalid cut rule '{rule}'. Expected format ROUND:CUT_TO")
        round_part, cut_part = rule.split(":", 1)
        round_number = int(round_part.strip())
        cut_to = int(cut_part.strip())
        if round_number <= 0 or cut_to <= 0:
            raise ValueError(f"Cut values must be positive in rule '{rule}'")
        cut_map[round_number] = cut_to
    return cut_map


def load_rows(input_path: Path) -> List[dict]:
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header row.")
        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"Input CSV missing required columns: {missing}")
        return list(reader)


def _as_int(row: dict, key: str) -> int:
    try:
        return int(str(row[key]).strip())
    except Exception as exc:
        raise ValueError(f"Invalid integer value for '{key}': {row.get(key)!r}") from exc


def process_rows(rows: List[dict], cut_map: Dict[int, int]) -> List[dict]:
    # Keep stable round ordering by round number.
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            _as_int(r, "Round Number"),
            str(r.get("Date", "")),
            _as_int(r, "Game Number"),
            str(r["Player"]),
            str(r["Player ID"]),
        ),
    )

    rows_by_round: Dict[int, List[dict]] = defaultdict(list)
    for row in rows_sorted:
        round_number = _as_int(row, "Round Number")
        rows_by_round[round_number].append(row)

    output_rows: List[dict] = []

    for round_number in sorted(rows_by_round.keys()):
        round_rows = rows_by_round[round_number]

        rows_by_game: Dict[int, List[dict]] = defaultdict(list)
        for row in round_rows:
            game_number = _as_int(row, "Game Number")
            rows_by_game[game_number].append(row)

        running_score: Dict[str, int] = defaultdict(int)
        player_name_by_id: Dict[str, str] = {}
        for row in round_rows:
            pid = str(row["Player ID"])
            player_name_by_id[pid] = str(row["Player"])

        for game_number in sorted(rows_by_game.keys()):
            game_rows = rows_by_game[game_number]

            for row in game_rows:
                pid = str(row["Player ID"])
                running_score[pid] += _as_int(row, "Score")

            ranked_players = sorted(
                running_score.keys(),
                key=lambda pid: (-running_score[pid], player_name_by_id.get(pid, "")),
            )
            rank_by_player = {pid: idx + 1 for idx, pid in enumerate(ranked_players)}

            cut_line_value = ""
            cut_to = cut_map.get(round_number)
            if cut_to is not None and ranked_players:
                cut_index = min(cut_to, len(ranked_players)) - 1
                cut_line_value = running_score[ranked_players[cut_index]]

            for row in game_rows:
                pid = str(row["Player ID"])
                out_row = dict(row)
                out_row["Cumulative Score"] = running_score[pid]
                out_row["Stage Rank"] = rank_by_player[pid]
                out_row["Cut Line"] = cut_line_value
                output_rows.append(out_row)

    return output_rows


def write_rows(output_path: Path, fieldnames: List[str], rows: List[dict]) -> None:
    output_fields = list(fieldnames)
    for extra in OUTPUT_EXTRA_COLUMNS:
        if extra not in output_fields:
            output_fields.append(extra)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Postprocess tournament per-game CSV.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to clean source CSV (semicolon-separated).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write postprocessed CSV (semicolon-separated).",
    )
    parser.add_argument(
        "--cut",
        action="append",
        default=[],
        help="Cut rule as ROUND:CUT_TO (repeatable), e.g. --cut 1:8 --cut 2:4",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    cut_map = parse_cut_map(args.cut)
    rows = load_rows(input_path)
    processed = process_rows(rows, cut_map)

    # Preserve original header order, append computed columns.
    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        fieldnames = reader.fieldnames or []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_rows(output_path, fieldnames, processed)

    print(f"Wrote {len(processed)} rows to {output_path}")
    if cut_map:
        print(f"Applied cut rules: {cut_map}")


if __name__ == "__main__":
    main()

