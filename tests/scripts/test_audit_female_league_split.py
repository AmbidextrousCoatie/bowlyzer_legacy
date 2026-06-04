"""Audit for collapsed female league ids (BayL vs BayL (D), etc.)."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from scripts.audit_female_league_split import audit_league_csv, load_female_league_pairs


def _write_csv(path: Path, rows: list[dict]) -> None:
    headers = ["Season", "League", "Team", "Player", "Position"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _team_total(*, season: str, league: str, team: str) -> dict:
    return {
        "Season": season,
        "League": league,
        "Team": team,
        "Player": "Team Total",
        "Position": "0",
    }


def test_audit_detects_collapsed_bayl(tmp_path: Path) -> None:
    rows = [
        *[_team_total(season="08/09", league="BayL", team=f"Team {i} 1") for i in range(21)],
    ]
    path = tmp_path / "bad.csv"
    _write_csv(path, rows)
    issues = audit_league_csv(path, pairs=[("BayL", "BayL (D)")])
    assert len(issues) == 1
    assert issues[0].male_league == "BayL"
    assert issues[0].female_league == "BayL (D)"


def test_audit_ok_when_female_league_present(tmp_path: Path) -> None:
    rows = [
        *[_team_total(season="08/09", league="BayL", team=f"M {i} 1") for i in range(10)],
        *[_team_total(season="08/09", league="BayL (D)", team=f"F {i} 1") for i in range(10)],
    ]
    path = tmp_path / "good.csv"
    _write_csv(path, rows)
    issues = audit_league_csv(path, pairs=[("BayL", "BayL (D)")])
    assert issues == []


def test_load_pairs_from_mapping():
    pairs = load_female_league_pairs()
    assert ("BayL", "BayL (D)") in pairs
    assert ("LL N1", "LL N (D)") in pairs
