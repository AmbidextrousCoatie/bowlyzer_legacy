#!/usr/bin/env python3
"""One-off: correlate conflict groups with season years vs aktive registry coverage."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd

from data_access.aktive_mitglieder_registry import discover_local_aktive_workbooks
from data_access.players_registry import (
    load_players_registry_df,
    registry_accepts_all_names_for_id,
    registry_lookup_by_id,
)
from data_access.schema import Columns
from database.paths import legacy_scrape_dir


def season_start_year(season: str) -> int:
    part = str(season).strip().split("/")[0]
    if len(part) == 2:
        return 2000 + int(part)
    return int(part)


def season_summary(df: pd.DataFrame, name: str, season_col: str) -> dict:
    seasons = sorted(df[season_col].dropna().astype(str).unique().tolist())
    years = [season_start_year(s) for s in seasons]
    return {
        "rows": len(df),
        "seasons": seasons,
        "min_year": min(years) if years else None,
        "max_year": max(years) if years else None,
        "only_2020_plus": bool(years) and all(y >= 2020 for y in years),
        "any_pre_2020": any(y < 2020 for y in years),
        "any_2020_plus": any(y >= 2020 for y in years),
    }


def main() -> None:
    root = legacy_scrape_dir()
    print(f"legacy scrape root: {root} (exists={root.exists()})")
    if root.exists():
        workbooks = discover_local_aktive_workbooks(root)
        seasons = sorted({season for season, _ in workbooks})
        if seasons:
            print(f"aktive seasons: {seasons[0]} .. {seasons[-1]} ({len(seasons)} seasons)")
        else:
            print("aktive seasons: none found")

    league_path = Path("database/data/league_results_merged.csv")
    df = pd.read_csv(league_path, sep=";", dtype=str, low_memory=False)
    lookup = registry_lookup_by_id(load_players_registry_df())

    groups = [
        ("38397", ["Schwartz, Janin", "Theisen, Janin"], "marriage-like"),
        ("38539", ["Fischer, Stephanie", "Triebel, Stephanie"], "marriage-like"),
        ("38607", ["Jenke, Sandra", "Mattern, Sandra"], "marriage-like"),
        ("38555", ["Daffner, Regina", "Gahr, Regina", "Gahr Regina"], "marriage-like"),
        ("16270", ["Feuerlein, Andreas", "Feuerlein, Andy"], "nickname"),
        ("38114", ["Hoppe, Oscar", "Hoppe, Oswald"], "given-variant"),
        ("38309", ["Pafford, Mark", "Paffort, Marc", "Pfafford, Mark"], "typo"),
        ("7762", ["Giuseppe, Giorgini", "Windsheimer, Friedrich"], "not-marriage"),
        ("7883", ["Beck, Joseph", "Hofbauer, Karlheinz"], "not-marriage"),
        ("16056", ["Balkheimer, Jennifer", "Beck-Balkheimer, Jennifer", "Huber, Jennifer"], "resolved-marriage"),
        ("25822", ["Kammermeier, Max", "Kammermeier, Maximilian"], "substring"),
        ("38583", ["Iosbacker, Douglas", "Iosbaker, Douglas"], "typo"),
        ("38793", ["Sigl, Thomas", "Tom Sigl"], "format"),
        ("38892", ["Hermann, Max", "Herrmann, Maximilian", "Herrmann Maximilian"], "typo"),
    ]

    print()
    for pid, names, kind in groups:
        entry = lookup.get(pid)
        accepts = registry_accepts_all_names_for_id(pid, names, lookup) if entry else False
        print(f"=== {pid} ({kind}) registry_accepts={accepts} ===")
        sub = df[df[Columns.player_id].astype(str) == str(pid)]
        for name in names:
            rows = sub[sub[Columns.player_name].astype(str) == name]
            info = season_summary(rows, name, Columns.season)
            print(
                f"  {name!r}: rows={info['rows']} "
                f"years={info['min_year']}-{info['max_year']} "
                f"pre2020={info['any_pre_2020']} post2019={info['any_2020_plus']} "
                f"only2020+={info['only_2020_plus']}"
            )
            print(f"    seasons: {'; '.join(info['seasons'])}")

        if not accepts and entry and len(names) == 2:
            registered = {names[0]} if names[0] == entry["canonical_name"] else set()
            missing = [n for n in names if n not in entry.get("aliases", "") and n != entry["canonical_name"]]
            print(f"  missing from registry aliases: {missing}")


if __name__ == "__main__":
    main()
