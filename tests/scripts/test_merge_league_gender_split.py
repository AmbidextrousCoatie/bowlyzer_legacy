"""Merge must keep male and female league ids separate (e.g. LL N1 vs LL N (D))."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from scripts.merge_league_sources import merge_sources


def _write_minimal_league_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "Season",
        "Week",
        "Date",
        "League",
        "Team",
        "Opponent",
        "Position",
        "Player",
        "Round Number",
        "Match Number",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _team_total_row(*, season: str, league: str, week: str, team: str) -> dict:
    return {
        "Season": season,
        "Week": week,
        "Date": "2009-10-01",
        "League": league,
        "Team": team,
        "Opponent": "Opponent FC 1",
        "Position": "0",
        "Player": "Team Total",
        "Round Number": "1",
        "Match Number": "1",
    }


def test_merge_preserves_female_league_id(tmp_path: Path) -> None:
    season = "09/10"
    male_bayl = [f"BayL Male {i} 1" for i in range(1, 11)]
    female_bayl = [f"BayL Female {i} 1" for i in range(1, 11)]
    male_teams = [f"Male Club {i} 1" for i in range(1, 9)]
    female_teams = [f"Female Club {i} 1" for i in range(1, 11)]

    legacy_rows = [
        *[_team_total_row(season=season, league="BayL", week="1", team=t) for t in male_bayl],
        *[_team_total_row(season=season, league="BayL (D)", week="1", team=t) for t in female_bayl],
        *[_team_total_row(season=season, league="LL N1", week="1", team=t) for t in male_teams],
        *[_team_total_row(season=season, league="LL N (D)", week="1", team=t) for t in female_teams],
    ]
    legacy_csv = tmp_path / "legacy.csv"
    gf_csv = tmp_path / "gf.csv"
    out_csv = tmp_path / "merged.csv"

    _write_minimal_league_csv(legacy_csv, legacy_rows)
    _write_minimal_league_csv(gf_csv, [_team_total_row(season="24/25", league="BayL", week="1", team="GF Only 1")])

    merge_sources(
        [legacy_csv, gf_csv],
        out_csv,
        key_names=["league", "season", "week", "round number", "match number", "team", "position", "player"],
        write_csv=True,
    )

    merged = pd.read_csv(out_csv, sep=";", dtype=str).fillna("")
    sub = merged[
        (merged["Season"] == season)
        & (merged["Player"].str.lower() == "team total")
        & (merged["Position"] == "0")
    ]
    counts = sub.groupby("League")["Team"].nunique().to_dict()
    assert counts.get("BayL") == 10
    assert counts.get("BayL (D)") == 10
    assert counts.get("LL N1") == 8
    assert counts.get("LL N (D)") == 10
