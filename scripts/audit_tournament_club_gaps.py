#!/usr/bin/env python3
"""Audit tournament club resolution gaps (crosswalk + extrapolation + unresolved)."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.affiliation_registry import (
    build_affiliation_index_dataframe,
    load_rangliste_club_crosswalk,
)
from data_access.player_id_name_normalization import normalize_player_id
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label
from data_access.tournament_club_resolution import apply_tournament_affiliation_resolution
from database.paths import get_work_data_dir, tournaments_postprocessed_csv

CSV_READ_KW = {"sep": ";", "dtype": str, "low_memory": False}

GAP_KEY_FIELDS = ("player_id", "season", "raw_club", "reason", "verein", "neighbor_season")


def _load_tournament_frame(path: Path) -> pd.DataFrame:
    from data_access.parquet_sidecar import resolve_load_path

    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, **CSV_READ_KW)


def _gap_identity(row: Mapping[str, Any]) -> Tuple[str, ...]:
    return tuple(normalize_unicode_label(row.get(field) or "") for field in GAP_KEY_FIELDS)


def dedupe_gap_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse per-game gap noise to unique player/season/label findings."""
    buckets: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for raw in rows:
        key = _gap_identity(raw)
        if key in buckets:
            buckets[key]["game_rows"] = int(buckets[key]["game_rows"]) + 1
            continue
        player_id = normalize_player_id(raw.get("player_id"))
        buckets[key] = {
            "player_id": player_id,
            "season": normalize_unicode_label(raw.get("season") or ""),
            "raw_club": normalize_unicode_label(raw.get("raw_club") or ""),
            "reason": normalize_unicode_label(raw.get("reason") or ""),
            "verein": normalize_unicode_label(raw.get("verein") or ""),
            "neighbor_season": normalize_unicode_label(raw.get("neighbor_season") or ""),
            "game_rows": 1,
        }
    out = list(buckets.values())
    out.sort(key=lambda row: (row["season"], row["player_id"], row["reason"], row["raw_club"]))
    return out


def _unique_player_seasons(rows: Iterable[Mapping[str, Any]]) -> int:
    return len(
        {
            (
                normalize_player_id(row.get("player_id")),
                normalize_unicode_label(row.get("season") or ""),
            )
            for row in rows
            if normalize_player_id(row.get("player_id"))
            and normalize_unicode_label(row.get("season") or "")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tournaments",
        type=Path,
        default=None,
        help="Tournament postprocessed path (default: published tournaments)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write gap CSV to this path (default: work dir)",
    )
    args = parser.parse_args()

    tournament_path = args.tournaments or tournaments_postprocessed_csv()
    if not tournament_path.is_file():
        print(f"Error: tournament file not found: {tournament_path}", file=sys.stderr)
        return 1

    _, build_stats = build_affiliation_index_dataframe(crosswalk=load_rangliste_club_crosswalk())
    print(
        f"Rangliste crosswalk gaps (unmapped club labels): {build_stats.crosswalk_gaps} "
        f"across {build_stats.unique_player_seasons} player-season rows"
    )

    frame = _load_tournament_frame(tournament_path)
    if Columns.event_type in frame.columns:
        frame = frame.loc[
            frame[Columns.event_type].fillna("").astype(str).str.strip().str.lower().eq("tournament")
        ].copy()

    _, stats = apply_tournament_affiliation_resolution(frame)
    same = int(stats.get("index_same_season") or stats.get("rangliste_same_season") or 0)
    extrap = int(stats.get("extrapolation_gap_count") or 0)
    league_same = int(stats.get("league_same_season") or 0)
    unresolved_game_rows = int(stats.get("unresolved_gap_count") or 0)
    print(f"Tournament rows with same-season index hit: {same} ({league_same} from league pass 2)")
    print(f"Rows resolved via Verein-gated extrapolation: {extrap}")
    print(f"Unresolved game rows: {unresolved_game_rows}")

    gap_rows = dedupe_gap_rows(list(stats.get("unresolved_gaps") or []))
    unique_player_seasons = _unique_player_seasons(gap_rows)
    print(
        f"Unresolved unique findings: {len(gap_rows)} "
        f"({unique_player_seasons} unique player-season)"
    )

    reason_counts = Counter(str(item.get("reason") or "") for item in gap_rows)
    if reason_counts:
        print("Unresolved reasons (deduped):")
        for reason, count in reason_counts.most_common():
            print(f"  {reason}: {count}")

    out_path = args.out or (get_work_data_dir() / "tournament_affiliation_gaps.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "player_id",
            "season",
            "raw_club",
            "reason",
            "verein",
            "neighbor_season",
            "game_rows",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in gap_rows:
            writer.writerow(row)
    print(f"Gap report: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
