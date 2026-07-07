"""Build database/data/tournament_stage_definitions.json from published tournament CSVs."""

from __future__ import annotations

import json
import sys
from glob import glob
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_access.competition_schema import competition_event_column

OUTPUT = ROOT / "database" / "data" / "tournament_stage_definitions.json"
GF_DEFS = ROOT / "database" / "input" / "gf_tournament_stage_definitions.json"

# Official GF cuts override data-derived player counts when present.
_GF_KEY_TO_EVENT: dict[tuple[str, str], str] = {
    ("SBM", "2026"): "Südbayerische Meisterschaft",
    ("NBM", "2026"): "Nordbayerische Meisterschaft",
}


def _is_three_tier(names: str) -> bool:
    n = names.lower()
    return "vorlauf" in n and "zwischen" in n and (
        "finale" in n or "finalrunde" in n or "ko-finale" in n
    )


def _gf_official_cuts() -> dict[tuple[str, str], list[int]]:
    if not GF_DEFS.is_file():
        return {}
    raw = json.loads(GF_DEFS.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], list[int]] = {}
    for tkey, years in raw.items():
        if not isinstance(years, dict):
            continue
        for year, block in years.items():
            if not isinstance(block, dict):
                continue
            event = _GF_KEY_TO_EVENT.get((tkey, str(year)))
            if not event:
                continue
            stages = block.get("stages")
            if not isinstance(stages, list):
                continue
            cuts: list[int] = []
            for st in stages:
                if not isinstance(st, dict):
                    continue
                cut_raw = str(st.get("cut") or "").strip()
                try:
                    cuts.append(int(cut_raw))
                except ValueError:
                    cuts.append(-1)
            if cuts:
                out[("25/26", event)] = cuts
    return out


def _load_tournament_df() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    parquet = ROOT / "database" / "data" / "tournaments_postprocessed.parquet"
    if parquet.is_file():
        frames.append(pd.read_parquet(parquet))
    for path in glob(str(ROOT / "database" / "data" / "tournament_*postprocessed.csv")):
        frames.append(pd.read_csv(path, sep=";", low_memory=False))
    if not frames:
        raise SystemExit("No tournament data files found")
    df = pd.concat(frames, ignore_index=True)
    return df[df["Event Type"].astype(str).str.lower().eq("tournament")]


def _build_event_block(
    df: pd.DataFrame,
    season: str,
    event_name: str,
    official_cuts: list[int] | None,
) -> dict[str, Any] | None:
    sub = df[
        df["Season"].astype(str).str.strip().eq(season)
        & df[competition_event_column(df)].astype(str).str.strip().eq(event_name)
    ]
    if sub.empty:
        return None

    rounds = sorted(int(x) for x in pd.to_numeric(sub["Round Number"], errors="coerce").dropna().unique())
    if not rounds:
        return None

    players_by_round: dict[int, int] = {}
    meta_by_round: dict[int, dict[str, Any]] = {}
    game_start = 1
    for rn in rounds:
        rsub = sub[pd.to_numeric(sub["Round Number"], errors="coerce").eq(rn)]
        name = str(rsub["Round Name"].dropna().astype(str).str.strip().mode().iloc[0])
        max_game = int(pd.to_numeric(rsub["Game Number"], errors="coerce").max())
        games = max_game + 1
        players_by_round[rn] = int(rsub["Player"].astype(str).str.strip().nunique())
        date_s = rsub["Date"].dropna().astype(str).mode()
        date = str(date_s.iloc[0]) if len(date_s) else ""
        loc_s = rsub["Location"].dropna().astype(str).mode()
        location = str(loc_s.iloc[0]) if len(loc_s) else ""
        meta_by_round[rn] = {
            "name": name,
            "games": games,
            "game_start": game_start,
            "game_end": game_start + games - 1,
            "date": date,
            "location": location,
        }
        game_start += games

    stages: list[dict[str, Any]] = []
    for i, rn in enumerate(rounds):
        meta = meta_by_round[rn]
        cut: str | int = "n/a"
        if i + 1 < len(rounds):
            if official_cuts and i < len(official_cuts) and official_cuts[i] > 0:
                cut = official_cuts[i]
            else:
                cut = players_by_round[rounds[i + 1]]
        stages.append(
            {
                "id": rn,
                "name": meta["name"],
                "cut": str(cut),
                "cut_basis": "overall_total",
                "evaluation": "Scratch Total",
                "date": meta["date"],
                "location": meta["location"],
                "game_start": meta["game_start"],
                "game_end": meta["game_end"],
            }
        )

    default_loc = meta_by_round[rounds[0]]["location"] if rounds else ""
    return {
        "event_name": event_name,
        "season": season,
        "event_type": "tournament",
        "default_location": default_loc,
        "stages": stages,
    }


def main() -> int:
    df = _load_tournament_df()
    event_col = competition_event_column(df)
    gf_cuts = _gf_official_cuts()

    out: dict[str, Any] = {}
    seen: set[tuple[str, str]] = set()
    for season, event_name in df.groupby(["Season", event_col]).groups:
        season_s = str(season).strip()
        event_s = str(event_name).strip()
        key = (season_s, event_s)
        if key in seen:
            continue
        seen.add(key)
        sub = df[(df["Season"] == season) & (df[event_col] == event_name)]
        names = " ".join(sub["Round Name"].dropna().astype(str).str.lower().unique())
        if not _is_three_tier(names):
            continue
        official = gf_cuts.get(key)
        block = _build_event_block(df, season_s, event_s, official)
        if block:
            out[f"{season_s}||{event_s}"] = block

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} events -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
