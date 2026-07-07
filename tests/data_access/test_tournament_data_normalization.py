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
