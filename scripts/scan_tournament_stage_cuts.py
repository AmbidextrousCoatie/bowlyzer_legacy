"""Scan tournament CSVs and print inferred 3-tier stage cuts (for config authoring)."""

from __future__ import annotations

from glob import glob
from pathlib import Path

import pandas as pd


def _is_three_tier_round_names(names: str) -> bool:
    n = names.lower()
    return "vorlauf" in n and "zwischen" in n and (
        "finale" in n or "finalrunde" in n or "ko-finale" in n
    )


def analyze_event(df: pd.DataFrame, season: str, event_name: str) -> list[dict]:
    sub = df[
        df["Season"].astype(str).str.strip().eq(season)
        & df["Event Name"].astype(str).str.strip().eq(event_name)
    ]
    rounds = sorted(int(x) for x in pd.to_numeric(sub["Round Number"], errors="coerce").dropna().unique())
    stages: list[dict] = []
    game_start = 1
    for rn in rounds:
        rsub = sub[pd.to_numeric(sub["Round Number"], errors="coerce").eq(rn)]
        name = str(rsub["Round Name"].dropna().astype(str).str.strip().mode().iloc[0])
        max_game = int(pd.to_numeric(rsub["Game Number"], errors="coerce").max())
        games = max_game + 1
        players = int(rsub["Player"].astype(str).str.strip().nunique())
        date_s = rsub["Date"].dropna().astype(str).mode()
        date = str(date_s.iloc[0]) if len(date_s) else ""
        loc_s = rsub["Location"].dropna().astype(str).mode()
        location = str(loc_s.iloc[0]) if len(loc_s) else ""
        stages.append(
            {
                "id": rn,
                "name": name,
                "players": players,
                "games": games,
                "game_start": game_start,
                "game_end": game_start + games - 1,
                "date": date,
                "location": location,
            }
        )
        game_start += games
    return stages


def main() -> None:
    files = glob("database/data/tournament_*postprocessed.csv")
    df = pd.concat([pd.read_csv(f, sep=";", low_memory=False) for f in files], ignore_index=True)
    df = df[df["Event Type"].astype(str).str.lower().eq("tournament")]

    targets: list[tuple[str, str]] = []
    for season, ev in df.groupby(["Season", "Event Name"]).groups:
        sub = df[(df["Season"] == season) & (df["Event Name"] == ev)]
        names = " ".join(sub["Round Name"].dropna().astype(str).str.lower().unique())
        if _is_three_tier_round_names(names):
            targets.append((str(season).strip(), str(ev).strip()))

    for season, ev in sorted(targets):
        stages = analyze_event(df, season, ev)
        print(f"{season} || {ev}")
        for i, st in enumerate(stages):
            cut = stages[i + 1]["players"] if i + 1 < len(stages) else None
            print(
                f"  r{st['id']} {st['name']}: {st['players']} players, "
                f"games {st['game_start']}-{st['game_end']}, cut={cut}"
            )
        print()

    parquet = Path("database/data/tournaments_postprocessed.parquet")
    if parquet.is_file():
        pdf = pd.read_parquet(parquet)
        pdf = pdf[pdf["Event Type"].astype(str).str.lower().eq("tournament")]
        ec = competition_event_column(pdf)
        print(f"parquet distinct events: {pdf.groupby(['Season', ec]).ngroups}")


if __name__ == "__main__":
    main()
