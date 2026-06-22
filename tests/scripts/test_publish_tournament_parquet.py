"""VPS tournament publish script matches build_published_dataset merge behavior."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from scripts.publish_tournament_parquet import merge_tournament_sources


def _write_tournament_csv(path: Path, rows: list[dict]) -> None:
    headers = ["Season", "Event Type", "Event Name", "Player", "Club", "Score"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_merge_tournament_sources_emits_event_column(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    out = tmp_path / "merged.csv"
    _write_tournament_csv(
        a,
        [
            {
                "Season": "25/26",
                "Event Type": "tournament",
                "Event Name": "Event A",
                "Player": "P1",
                "Club": "Club A",
                "Score": "200",
            }
        ],
    )
    _write_tournament_csv(
        b,
        [
            {
                "Season": "25/26",
                "Event Type": "tournament",
                "Event Name": "Event B",
                "Player": "P2",
                "Club": "Club B",
                "Score": "210",
            }
        ],
    )

    merge_tournament_sources([a, b], out, write_csv=True)
    merged = pd.read_csv(out, sep=";", dtype=str).fillna("")
    assert "Event Name" not in merged.columns
    assert set(merged["Event"].tolist()) == {"Event A", "Event B"}
    assert (merged["Event Type"] == "tournament").all()
