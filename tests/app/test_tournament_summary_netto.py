"""Summary cards use net pins (scratch + handicap) when the event has handicap data."""

from __future__ import annotations

import pandas as pd

from app.services.tournament_service import TournamentService
from data_access.schema import Columns


def _clubmeisterschaft_df() -> pd.DataFrame:
    path = "database/data/tournament_manual_postprocessed.csv"
    df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False)
    mask = df[Columns.event_name].astype(str).str.strip().eq("Clubmeisterschaft Donaubowler 2026")
    return df.loc[mask].copy()


def test_summary_cards_use_net_pins_for_clubmeisterschaft_round_2():
    df = _clubmeisterschaft_df()
    svc = TournamentService()
    cards = svc.get_summary_cards(
        "25/26",
        "Clubmeisterschaft Donaubowler 2026",
        round_number=2,
        df=df,
    ).get("cards", [])

    by_title = {c["title"]: c for c in cards}
    leader = by_title.get("Tournament Leader")
    assert leader is not None
    assert leader["subtitle"].startswith("\u2300")
    ranked = svc._avg_net_standings_from_gesamt_pivot(df, through_round=2, include_club=False)
    assert leader["value"] == str(ranked.iloc[0][Columns.player_name])

    stage = by_title.get("Stage Winner")
    assert stage is not None
    assert stage["value"] == "Peter Holten"
    assert "netto" in (stage.get("subtitle") or "").lower()

    # Set 2 scratch leader would be Christian Feller — net leader is Peter Holten.
    sub = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(2.0)]
    scratch = (
        pd.to_numeric(sub[Columns.score], errors="coerce").fillna(0)
        .groupby(sub[Columns.player_name].astype(str))
        .sum()
    )
    assert scratch.idxmax() == "Christian Feller"


def test_round_results_sorted_by_cumulative_net_after_stage():
    df = _clubmeisterschaft_df()
    svc = TournamentService()
    tbl = svc.get_round_results_table(
        "25/26",
        "Clubmeisterschaft Donaubowler 2026",
        round_number=2,
        df=df,
    )
    assert tbl.data
    assert tbl.data[0][1] == "Marco Hürdler"
    assert tbl.default_sort == {"field": "overall_net", "dir": "desc"}


def test_stage_leaderboard_sorted_by_cumulative_net_after_stage():
    df = _clubmeisterschaft_df()
    svc = TournamentService()
    lb = svc.get_leaderboard_table(
        "25/26",
        "Clubmeisterschaft Donaubowler 2026",
        round_number=2,
        df=df,
    )
    assert lb.data
    assert lb.data[0][1] == "Marco Hürdler"
    assert lb.default_sort == {"field": "total_net", "dir": "desc"}


def test_cut_line_uses_average_rank_for_clubmeisterschaft():
    df = _clubmeisterschaft_df()
    svc = TournamentService()
    season, tournament = "25/26", "Clubmeisterschaft Donaubowler 2026"
    cards = svc.get_summary_cards(season, tournament, round_number=2, df=df)
    cut = next(c for c in cards["cards"] if c.get("title") == "Cut Line")
    cut_pos = svc._resolved_cut_position_for_round(df, 2, season, tournament)
    assert cut_pos is not None
    ranked = svc._avg_net_standings_from_gesamt_pivot(df, through_round=2, include_club=False)
    expected = str(ranked.loc[ranked["rank"].eq(int(cut_pos)), Columns.player_name].iloc[0])
    assert cut["value"] == expected
    assert cut["subtitle"].startswith("\u2300")


def test_gesamt_cut_line_matches_leaderboard_average_sort():
    """Gesamt overview: cut-line card follows avg_net sort (Ernest @ 6, not Volkmar by total pins)."""
    df = _clubmeisterschaft_df()
    svc = TournamentService()
    season, tournament = "25/26", "Clubmeisterschaft Donaubowler 2026"
    cards = svc.get_summary_cards(season, tournament, df=df).get("cards", [])
    cut = next(c for c in cards if c.get("title") == "Cut Line")
    assert cut["value"] == "Ernest Roth"
    assert "201.9" in cut["subtitle"]
    assert "4038" in cut["subtitle"]
    leader = next(c for c in cards if c.get("title") == "Tournament Leader")
    standings = svc._avg_net_standings_from_gesamt_pivot(df, through_round=None, include_club=False)
    assert leader["value"] == str(standings.iloc[0][Columns.player_name])
    volkmar = standings.loc[standings[Columns.player_name].eq("Volkmar Hartfeil")].iloc[0]
    assert int(volkmar["rank"]) == 3
    assert float(volkmar["avg_net"]) == 210.4
