"""Tournament club resolution via Rangliste."""

from __future__ import annotations

import pandas as pd

from data_access.schema import Columns
from data_access.tournament_club_resolution import (
    AFFILIATION_SOURCE_EINZELMITGLIED,
    AFFILIATION_SOURCE_RANGLISTE_SAME,
    REPORTING_MODE_VEREIN,
    apply_tournament_affiliation_resolution,
)


def _lookup() -> dict:
    return {
        ("7879", "11/12"): {
            "club_raw": "Ratisbona Regensburg",
            "verein_raw": "BV 68 Regensburg",
            "club_canonical": "Ratisbona Regensburg",
            "verein_canonical": "BV 68 Regensburg",
            "is_einzelmitglied": False,
        },
        ("1234", "14/15"): {
            "club_raw": "Einzelmitglied",
            "verein_raw": "1. BBV Lindau",
            "club_canonical": "",
            "verein_canonical": "1. BBV Lindau",
            "is_einzelmitglied": True,
        },
    }


def test_rangliste_promotes_verein_tournament_label_to_club() -> None:
    frame = pd.DataFrame(
        [
            {
                Columns.season: "11/12",
                Columns.player_id: "7879",
                Columns.club: "BV 68 Regensburg",
                Columns.event_type: "tournament",
            }
        ]
    )
    out, stats = apply_tournament_affiliation_resolution(frame, affiliation_lookup=_lookup())
    assert out.iloc[0][Columns.club] == "Ratisbona Regensburg"
    assert out.iloc[0][Columns.history_club] == "Ratisbona Regensburg"
    assert out.iloc[0][Columns.verein] == "BV 68 Regensburg"
    assert out.iloc[0][Columns.affiliation_source] == AFFILIATION_SOURCE_RANGLISTE_SAME
    assert stats["rangliste_same_season"] == 1


def test_einzelmitglied_keeps_verein_for_history() -> None:
    frame = pd.DataFrame(
        [
            {
                Columns.season: "14/15",
                Columns.player_id: "1234",
                Columns.club: "Einzelmitglied",
                Columns.event_type: "tournament",
            }
        ]
    )
    out, stats = apply_tournament_affiliation_resolution(frame, affiliation_lookup=_lookup())
    assert out.iloc[0][Columns.club] == "1. BBV Lindau"
    assert out.iloc[0][Columns.history_club] == "1. BBV Lindau"
    assert out.iloc[0][Columns.affiliation_source] == AFFILIATION_SOURCE_EINZELMITGLIED
    assert stats["einzelmitglied_verein"] == 1


def test_verein_reporting_mode_uses_verein_for_club_column() -> None:
    frame = pd.DataFrame(
        [
            {
                Columns.season: "11/12",
                Columns.player_id: "7879",
                Columns.club: "BV 68 Regensburg",
                Columns.event_type: "tournament",
            }
        ]
    )
    out, _stats = apply_tournament_affiliation_resolution(
        frame,
        affiliation_lookup=_lookup(),
        reporting_mode=REPORTING_MODE_VEREIN,
    )
    assert out.iloc[0][Columns.club] == "BV 68 Regensburg"
    assert out.iloc[0][Columns.history_club] == "Ratisbona Regensburg"
