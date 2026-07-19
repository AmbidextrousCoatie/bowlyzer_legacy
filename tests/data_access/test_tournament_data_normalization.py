"""Tournament data normalization."""

from __future__ import annotations

import pandas as pd

from data_access.schema import Columns
from data_access.tournament_data_normalization import normalize_tournament_dataframe


def test_normalize_tournament_club_names() -> None:
    df = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "Event Name": "Clubmeisterschaft Donaubowler 2026",
                "Player": "Müller, Hans",
                "Player ID": "123",
                "Club": "Donaubowler Regensburg",
            }
        ]
    )
    out, stats = normalize_tournament_dataframe(df, normalize_player_ids=False)
    assert Columns.club in out.columns
    assert int(stats.get("club_cells_normalized") or 0) >= 0


def test_normalize_collapses_affiliation_sourced_club_aliases() -> None:
    """Index hits must still fold club_mapping aliases (Spiele nach Club vs Clubzugehörigkeit)."""
    df = pd.DataFrame(
        [
            {
                Columns.season: "15/16",
                Columns.player_id: "7830",
                Columns.club: "BC Donau - Bowler",
                Columns.history_club: "BC Donau - Bowler",
                Columns.affiliation_source: "index_same_season",
                Columns.event_type: "tournament",
            }
        ]
    )
    out, stats = normalize_tournament_dataframe(
        df,
        normalize_player_ids=False,
        resolve_affiliations=False,
    )
    assert out.iloc[0][Columns.club] == "Donaubowler Regensburg"
    assert out.iloc[0][Columns.history_club] == "Donaubowler Regensburg"
    assert int(stats.get("club_registry_rows_changed") or 0) >= 1
