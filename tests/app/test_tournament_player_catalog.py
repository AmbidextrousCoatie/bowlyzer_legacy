"""Tournament player catalog for PlayerSearch ({id, name})."""

from __future__ import annotations

import pandas as pd

from app.services.tournament_service import TournamentService
from data_access.schema import Columns


def test_tournament_player_search_entries_dedupes_by_id() -> None:
    svc = TournamentService.__new__(TournamentService)
    df = pd.DataFrame(
        {
            Columns.player_name: ["Feller, Christian", "Feller, Christian", "Schmidt, Alex"],
            Columns.player_id: ["42", "42", "99"],
        }
    )
    out = svc._tournament_player_search_entries(df)
    assert out == [
        {"id": "42", "name": "Feller, Christian"},
        {"id": "99", "name": "Schmidt, Alex"},
    ]


def test_tournament_player_search_entries_falls_back_to_name_key() -> None:
    svc = TournamentService.__new__(TournamentService)
    df = pd.DataFrame({Columns.player_name: ["Solo, Player"], Columns.player_id: [""]})
    out = svc._tournament_player_search_entries(df)
    assert out == [{"id": "Solo, Player", "name": "Solo, Player"}]
