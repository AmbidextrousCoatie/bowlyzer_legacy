"""Tournament per-event data quality audit."""

from __future__ import annotations

import pandas as pd

from data_access.tournament_data_quality import audit_tournament_data_quality


def test_audit_flags_same_name_different_ids() -> None:
    df = pd.DataFrame(
        [
            {
                "Season": "23/24",
                "Event Name": "Bayerische Meisterschaft Einzel 2024",
                "Player": "Test, Anna",
                "Player ID": "1",
                "Club": "Club A",
            },
            {
                "Season": "23/24",
                "Event Name": "Bayerische Meisterschaft Einzel 2024",
                "Player": "Test, Anna",
                "Player ID": "2",
                "Club": "Club A",
            },
        ]
    )
    rows = audit_tournament_data_quality(df)
    assert len(rows) == 1
    assert rows[0].status == "red"
    assert rows[0].same_name_different_ids == 1


def test_audit_uses_published_event_column() -> None:
    df = pd.DataFrame(
        [
            {
                "Season": "23/24",
                "Event": "Bayerische Meisterschaft Einzel 2024",
                "Event Type": "tournament",
                "Player": "Solo, Max",
                "Player ID": "99",
                "Club": "Club B",
            },
        ]
    )
    rows = audit_tournament_data_quality(df)
    assert len(rows) == 1
    assert rows[0].event_name == "Bayerische Meisterschaft Einzel 2024"
    assert rows[0].status == "green"


def test_audit_yellow_for_missing_player_id() -> None:
    df = pd.DataFrame(
        [
            {
                "Season": "23/24",
                "Event Name": "Südbayerische Meisterschaft 2024",
                "Player": "Solo, Max",
                "Player ID": "",
                "Club": "Club B",
            },
        ]
    )
    rows = audit_tournament_data_quality(df)
    assert rows[0].status == "yellow"
    assert rows[0].missing_player_id == 1
