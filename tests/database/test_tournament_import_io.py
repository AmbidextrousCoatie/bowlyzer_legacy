"""Tournament import CSV merge helpers."""

from __future__ import annotations

from pathlib import Path

from database.tournament_import.io import (
    merge_rows_by_season_events,
    read_csv_rows,
    strip_rows_for_season_tournament,
    write_csv_rows,
)


def test_merge_rows_by_season_events_keeps_other_seasons(tmp_path: Path) -> None:
    target = tmp_path / "manual.csv"
    write_csv_rows(
        target,
        [
            {
                "Season": "08/09",
                "Event Name": "Südbayerische Meisterschaft 2009 Herren",
                "Date": "2009-01-01",
                "Round Number": "1",
                "Game Number": "0",
                "Player": "A",
                "Player ID": "1",
            },
            {
                "Season": "09/10",
                "Event Name": "Südbayerische Meisterschaft",
                "Date": "2010-01-01",
                "Round Number": "1",
                "Game Number": "0",
                "Player": "B",
                "Player ID": "2",
            },
        ],
    )
    new_rows = [
        {
            "Season": "08/09",
            "Event Name": "Südbayerische Meisterschaft",
            "Date": "2009-01-01",
            "Round Number": "1",
            "Game Number": "0",
            "Player": "A",
            "Player ID": "1",
        }
    ]
    before, after = merge_rows_by_season_events(target, new_rows)
    rows = read_csv_rows(target)
    assert before == 2
    assert after == 3
    assert {row["Event Name"] for row in rows if row["Season"] == "08/09"} == {
        "Südbayerische Meisterschaft 2009 Herren",
        "Südbayerische Meisterschaft",
    }
    assert any(row["Season"] == "09/10" for row in rows)


def test_strip_rows_for_season_tournament_removes_legacy_names(tmp_path: Path) -> None:
    target = tmp_path / "manual.csv"
    write_csv_rows(
        target,
        [
            {
                "Season": "08/09",
                "Event Name": "Südbayerische Meisterschaft 2009 Herren",
                "Date": "2009-01-01",
                "Round Number": "1",
                "Game Number": "0",
                "Player": "A",
                "Player ID": "1",
            },
            {
                "Season": "08/09",
                "Event Name": "Bayerische Meisterschaft Einzel 2009",
                "Date": "2009-01-01",
                "Round Number": "1",
                "Game Number": "0",
                "Player": "C",
                "Player ID": "3",
            },
        ],
    )
    removed = strip_rows_for_season_tournament(
        target,
        season="08/09",
        tournament_id="SBM M",
        legacy_event_names=("Südbayerische Meisterschaft 2009 Herren",),
    )
    rows = read_csv_rows(target)
    assert removed == 1
    assert len(rows) == 1
    assert rows[0]["Event Name"] == "Bayerische Meisterschaft Einzel 2009"
