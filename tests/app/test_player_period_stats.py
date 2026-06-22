"""Player period stats (best days) aggregation."""

from __future__ import annotations

import pandas as pd

from app.services.player_service import PlayerService
from data_access.schema import Columns


def _service() -> PlayerService:
    return PlayerService(database=None)


def test_build_period_stats_league_week_and_tournament_round():
    svc = _service()
    df = pd.DataFrame(
        {
            Columns.season: ["25/26", "25/26", "25/26", "25/26", "24/25", "24/25"],
            Columns.event_type: ["league", "league", "league", "league", "tournament", "tournament"],
            "League": ["LL N1", "LL N1", "LL N1", "LL N1", "", ""],
            Columns.event_name: ["LL N1", "LL N1", "LL N1", "LL N1", "Nordbayerische Meisterschaft", "Nordbayerische Meisterschaft"],
            Columns.week: [2, 2, 2, 3, pd.NA, pd.NA],
            Columns.round_number: [pd.NA, pd.NA, pd.NA, pd.NA, 1, 1],
            Columns.round_name: ["", "", "", "", "Vorlauf", "Vorlauf"],
            Columns.team_name: ["Club 1", "Club 1", "Club 1", "Club 1", "", ""],
            Columns.club: ["Club", "Club", "Club", "Club", "", ""],
            Columns.score: [200, 210, 220, 180, 205, 215],
            Columns.input_data: ["True"] * 6,
            Columns.computed_data: ["False"] * 6,
        }
    )

    def competition_name(chunk: pd.DataFrame) -> str:
        from data_access.competition_schema import competition_event_column

        col = competition_event_column(chunk)
        if col and col in chunk.columns:
            vals = [str(x).strip() for x in chunk[col].dropna().tolist() if str(x).strip()]
            if vals:
                return vals[0]
        return "Unknown"

    def row_team_name(chunk: pd.DataFrame) -> str:
        if Columns.team_name in chunk.columns:
            vals = [str(x).strip() for x in chunk[Columns.team_name].dropna().tolist() if str(x).strip()]
            if vals:
                return vals[0]
        return ""

    def row_club(chunk: pd.DataFrame) -> str:
        if Columns.club in chunk.columns:
            vals = [str(x).strip() for x in chunk[Columns.club].dropna().tolist() if str(x).strip()]
            if vals:
                return vals[0]
        return "-"

    periods = svc._build_period_stats(
        df,
        competition_name=competition_name,
        row_team_name=row_team_name,
        row_club=row_club,
    )

    league_week2 = next(p for p in periods if p["period_kind"] == "week" and p["period_number"] == 2)
    assert league_week2["competition"] == "LL N1"
    assert league_week2["average"] == 210.0
    assert league_week2["games"] == 3

    tourn = next(p for p in periods if p["period_kind"] == "round")
    assert tourn["competition"] == "Nordbayerische Meisterschaft"
    assert tourn["period_value"] == "Vorlauf"
    assert tourn["average"] == 210.0
