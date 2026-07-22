"""
CLI: generate a clean per-game tournament CSV from existing player IDs/names.

Source player pool defaults to:
database/data/bowling_ergebnisse_real_from_bowlingbayern.csv

Output is semicolon-separated and intended as input for
postprocess_tournament_results.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_PLAYER_SOURCE = ROOT / "database" / "data" / "bowling_ergebnisse_real_from_bowlingbayern.csv"


@dataclass(frozen=True)
class StageConfig:
    round_number: int
    round_name: str
    date: str
    games: int


def _stable_int(text: str) -> int:
    # Stable across runs/platforms (unlike built-in hash()).
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate clean tournament per-game CSV.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--player-source",
        default=str(DEFAULT_PLAYER_SOURCE),
        help="CSV source file to pick players from.",
    )
    parser.add_argument("--season", default="2026", help="Season value.")
    parser.add_argument("--event-name", default="Nordbayerische Meisterschaft", help="Event name.")
    parser.add_argument("--event-type", default="tournament", help="Event type label.")
    parser.add_argument("--location", default="Dream Bowl Palace Unterfoehring", help="Venue/location name.")
    parser.add_argument("--field-size", type=int, default=10, help="Number of players to include.")
    parser.add_argument("--seed", default="nordbayerische-2026", help="Selection seed for deterministic sampling.")
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        help="Stage as ROUND|NAME|DATE|GAMES, repeatable. Example: 1|Vorlauf|2026-05-01|6",
    )
    return parser


def parse_stage(raw: str) -> StageConfig:
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 4:
        raise ValueError(f"Invalid --stage '{raw}'. Expected ROUND|NAME|DATE|GAMES")
    return StageConfig(
        round_number=int(parts[0]),
        round_name=parts[1],
        date=parts[2],
        games=int(parts[3]),
    )


def parse_stages(raw_stages: List[str]) -> List[StageConfig]:
    if not raw_stages:
        # default 3x6 format
        return [
            StageConfig(1, "Vorlauf", "2026-05-01", 6),
            StageConfig(2, "Zwischenlauf", "2026-05-02", 6),
            StageConfig(3, "Finale", "2026-05-03", 6),
        ]
    stages = [parse_stage(s) for s in raw_stages]
    return sorted(stages, key=lambda s: s.round_number)


def load_player_pool(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Player source file not found: {path}")

    players_by_id = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        needed = {"Player", "Player ID", "Team"}
        if reader.fieldnames is None or not needed.issubset(set(reader.fieldnames)):
            raise ValueError(f"Source CSV must include columns: {sorted(needed)}")

        for row in reader:
            player = str(row.get("Player", "")).strip()
            pid = str(row.get("Player ID", "")).strip()
            club = str(row.get("Team", "")).strip()
            if not player or player == "Team Total":
                continue
            if not pid.isdigit() or int(pid) <= 0:
                continue
            if pid not in players_by_id:
                players_by_id[pid] = {"Player": player, "Player ID": pid, "Club": club or "Unknown Club"}

    pool = list(players_by_id.values())
    if not pool:
        raise ValueError("No valid players found in source CSV.")
    return pool


def pick_players(pool: List[dict], field_size: int, seed: str) -> List[dict]:
    if field_size <= 0:
        raise ValueError("field-size must be > 0")
    if len(pool) < field_size:
        raise ValueError(f"Requested field-size={field_size}, but only {len(pool)} players available.")

    ranked = sorted(pool, key=lambda p: (_stable_int(f"{seed}:{p['Player ID']}"), p["Player"]))
    selected = ranked[:field_size]
    # deterministic display order for readability
    return sorted(selected, key=lambda p: p["Player"])


def score_for(player_id: str, player_name: str, stage_idx: int, game_number: int) -> int:
    # deterministic pseudo-random but realistic scratch range
    base = 165 + (_stable_int(f"base:{player_id}:{player_name}") % 56)  # 165..220
    swing = (_stable_int(f"swing:{player_id}:{stage_idx}:{game_number}") % 19) - 9  # -9..+9
    trend = game_number * 3 + stage_idx * 2
    score = base + swing + trend
    return max(100, min(300, score))


def generate_rows(
    season: str,
    event_type: str,
    event_name: str,
    location: str,
    stages: List[StageConfig],
    players: List[dict],
) -> List[dict]:
    rows = []
    for stage_idx, stage in enumerate(stages):
        for player in players:
            for game_number in range(stage.games):
                rows.append(
                    {
                        "Season": season,
                        "Date": stage.date,
                        "Location": location,
                        "Event Type": event_type,
                        "Event Name": event_name,
                        "Round Number": stage.round_number,
                        "Round Name": stage.round_name,
                        "Player": player["Player"],
                        "Player ID": player["Player ID"],
                        "Club": player["Club"],
                        "Game Number": game_number,
                        "Score": score_for(player["Player ID"], player["Player"], stage_idx, game_number),
                        "Handicap": 0,
                    }
                )
    return rows


def main() -> None:
    args = build_parser().parse_args()
    source = Path(args.player_source).resolve()
    output = Path(args.output).resolve()

    stages = parse_stages(args.stage)
    pool = load_player_pool(source)
    selected_players = pick_players(pool, args.field_size, args.seed)
    rows = generate_rows(args.season, args.event_type, args.event_name, args.location, stages, selected_players)

    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    ]
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output}")
    print(f"Selected {len(selected_players)} players from {source.name} using seed '{args.seed}'")


if __name__ == "__main__":
    main()

