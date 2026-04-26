from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


CANONICAL_HEADERS = [
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

STAGE_META_HEADERS = [
    "Date",
    "Location",
    "Tournament Stage Id",
    "Tournament Stage Name",
    "Tournament Stage Cut",
    "Tournament Stage Evaluation",
    "Game Start",
    "Game End",
]


@dataclass(frozen=True)
class StageDef:
    stage_id: int
    stage_name: str
    stage_cut: str
    stage_evaluation: str
    date: str
    location: str
    game_start: int
    game_end: int

    @property
    def game_count(self) -> int:
        return self.game_end - self.game_start + 1


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        headers = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in row.items()} for row in reader]
    return headers, rows


def _write_csv(path: Path, headers: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _parse_stage(raw: str) -> StageDef:
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 8:
        raise ValueError(
            "Invalid --stage value. Expected: "
            "stage_id|stage_name|stage_cut|stage_evaluation|date|location|game_start|game_end"
        )
    stage_id = int(parts[0])
    stage_name = parts[1]
    stage_cut = parts[2]
    stage_evaluation = parts[3]
    date = parts[4]
    location = parts[5]
    game_start = int(parts[6])
    game_end = int(parts[7])
    if game_end < game_start:
        raise ValueError(f"Invalid stage {stage_id}: game_end < game_start")
    return StageDef(
        stage_id=stage_id,
        stage_name=stage_name,
        stage_cut=stage_cut,
        stage_evaluation=stage_evaluation,
        date=date,
        location=location,
        game_start=game_start,
        game_end=game_end,
    )


def _parse_stages(raw_stages: List[str]) -> List[StageDef]:
    if not raw_stages:
        raise ValueError("At least one --stage is required.")
    stages = sorted((_parse_stage(raw) for raw in raw_stages), key=lambda s: s.stage_id)
    ranges = []
    for s in stages:
        for game in range(s.game_start, s.game_end + 1):
            if game in ranges:
                raise ValueError(f"Game number {game} is assigned to multiple stages.")
            ranges.append(game)
    return stages


def _find_field_id(field_map_rows: List[Dict[str, str]], resolved_label: str) -> str:
    target = resolved_label.strip().lower()
    for row in field_map_rows:
        if (row.get("resolved_label") or "").strip().lower() == target:
            return (row.get("field_id") or "").strip()
    return ""


def _build_score_columns(field_map_rows: List[Dict[str, str]]) -> Dict[int, str]:
    score_cols: Dict[int, str] = {}
    for row in field_map_rows:
        label = (row.get("resolved_label") or "").strip()
        field_id = (row.get("field_id") or "").strip()
        if not label.startswith("Spiel "):
            continue
        suffix = label.replace("Spiel ", "", 1).strip()
        if not suffix.isdigit():
            continue
        if not field_id.isdigit():
            continue
        score_cols[int(suffix)] = field_id
    return score_cols


def _build_player_lookup(path: Path | None) -> Dict[str, Dict[str, str]]:
    if path is None:
        return {}
    _, rows = _read_csv(path)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        pid = (row.get("Player ID") or "").strip()
        if not pid:
            continue
        out[pid] = {
            "Player": (row.get("Player") or "").strip(),
            "Club": (row.get("Club") or row.get("Team") or "").strip(),
        }
    return out


def _score_or_empty(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    try:
        # GF number fields may appear as integer strings or decimal strings.
        return str(int(float(val)))
    except ValueError:
        return ""


def transform(
    source_rows: List[Dict[str, str]],
    field_map_rows: List[Dict[str, str]],
    season: str,
    event_name: str,
    event_type: str,
    stages: List[StageDef],
    handicap: str,
    player_lookup: Dict[str, Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    player_id_field = _find_field_id(field_map_rows, "EDV-Nummer")
    player_name_field = _find_field_id(field_map_rows, "Name")
    score_columns = _build_score_columns(field_map_rows)
    if not player_id_field:
        raise ValueError("Could not resolve player id field from field map (expected 'EDV-Nummer').")
    if not player_name_field:
        raise ValueError("Could not resolve player name field from field map (expected 'Name').")
    if not score_columns:
        raise ValueError("Could not resolve any 'Spiel n' score fields from field map.")

    canonical_rows: List[Dict[str, str]] = []
    for src in source_rows:
        player_id = (src.get(player_id_field) or "").strip()
        if not player_id:
            continue
        lookup = player_lookup.get(player_id, {})
        player_name = lookup.get("Player") or (src.get(player_name_field) or "").strip()
        club = lookup.get("Club") or ""
        for stage in stages:
            for game_num in range(stage.game_start, stage.game_end + 1):
                field_id = score_columns.get(game_num)
                if not field_id:
                    continue
                score = _score_or_empty(src.get(field_id) or "")
                if not score:
                    continue
                canonical_rows.append(
                    {
                        "Season": season,
                        "Date": stage.date,
                        "Location": stage.location,
                        "Event Type": event_type,
                        "Event Name": event_name,
                        "Round Number": str(stage.stage_id),
                        "Round Name": stage.stage_name,
                        "Player": player_name,
                        "Player ID": player_id,
                        "Club": club,
                        "Game Number": str(game_num - stage.game_start),
                        "Score": score,
                        "Handicap": handicap,
                    }
                )

    stage_meta_rows = [
        {
            "Date": stage.date,
            "Location": stage.location,
            "Tournament Stage Id": str(stage.stage_id),
            "Tournament Stage Name": stage.stage_name,
            "Tournament Stage Cut": stage.stage_cut,
            "Tournament Stage Evaluation": stage.stage_evaluation,
            "Game Start": str(stage.game_start),
            "Game End": str(stage.game_end),
        }
        for stage in stages
    ]
    return canonical_rows, stage_meta_rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transform GF tournament export into canonical per-game CSV.")
    p.add_argument("--source-csv", required=True, help="GF export CSV (raw or labeled).")
    p.add_argument("--field-map-csv", required=True, help="Field map CSV generated by export script.")
    p.add_argument("--output-csv", required=True, help="Canonical output CSV path.")
    p.add_argument("--stage-meta-csv", required=True, help="Tournament stage metadata output CSV path.")
    p.add_argument("--season", required=True, help="Season value, e.g. 2026.")
    p.add_argument("--event-name", required=True, help="Canonical Event Name.")
    p.add_argument("--event-type", default="tournament", help="Canonical Event Type.")
    p.add_argument("--handicap", default="0", help="Handicap value to write for every row.")
    p.add_argument(
        "--player-lookup-csv",
        default="",
        help="Optional canonical/player lookup CSV containing Player ID, Player, Club/Team.",
    )
    p.add_argument(
        "--stage",
        action="append",
        default=[],
        help=(
            "Repeatable stage definition: "
            "stage_id|stage_name|stage_cut|stage_evaluation|date|location|game_start|game_end "
            "(example: 1|Vorlauf|80|Scratch Total|2026-04-25|Dream Bowl|1|6)"
        ),
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    source_csv = Path(args.source_csv).resolve()
    field_map_csv = Path(args.field_map_csv).resolve()
    output_csv = Path(args.output_csv).resolve()
    stage_meta_csv = Path(args.stage_meta_csv).resolve()
    player_lookup_csv = Path(args.player_lookup_csv).resolve() if args.player_lookup_csv.strip() else None

    _, source_rows = _read_csv(source_csv)
    _, field_map_rows = _read_csv(field_map_csv)
    stages = _parse_stages(args.stage)
    player_lookup = _build_player_lookup(player_lookup_csv)

    canonical_rows, stage_meta_rows = transform(
        source_rows=source_rows,
        field_map_rows=field_map_rows,
        season=args.season.strip(),
        event_name=args.event_name.strip(),
        event_type=args.event_type.strip(),
        stages=stages,
        handicap=args.handicap.strip(),
        player_lookup=player_lookup,
    )
    _write_csv(output_csv, CANONICAL_HEADERS, canonical_rows)
    _write_csv(stage_meta_csv, STAGE_META_HEADERS, stage_meta_rows)
    print(f"Wrote canonical rows: {len(canonical_rows)} -> {output_csv}")
    print(f"Wrote stage metadata rows: {len(stage_meta_rows)} -> {stage_meta_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
