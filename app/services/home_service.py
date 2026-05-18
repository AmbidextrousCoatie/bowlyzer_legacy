"""Aggregate counts for the landing page."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.config.database_config import database_config
from app.services.league_service import LeagueService
from app.services.tournament_service import TournamentService
from data_access.schema import Columns


def _league_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or Columns.event_type not in df.columns:
        return df
    et = df[Columns.event_type].fillna("league").astype(str).str.strip().str.lower()
    mask = et.eq("league") | et.eq("")
    return df[mask] if mask.any() else df


def _tournament_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or Columns.event_type not in df.columns:
        return df
    et = df[Columns.event_type].fillna("").astype(str).str.strip().str.lower()
    mask = et.eq("tournament")
    return df[mask] if mask.any() else pd.DataFrame()


def _count_scored_games(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    if Columns.score in frame.columns:
        return int(frame[Columns.score].notna().sum())
    return int(len(frame))


def _unique_players(*frames: pd.DataFrame) -> int:
    names: set[str] = set()
    for frame in frames:
        if frame.empty or Columns.player_name not in frame.columns:
            continue
        for name in frame[Columns.player_name].dropna().astype(str):
            if name.strip():
                names.add(name.strip())
    return len(names)


def _resolve_tournament_database() -> str:
    from app.routes.tournament_routes import _resolve_default_tournament_source

    return _resolve_default_tournament_source()


def get_home_stats(database: str | None = None) -> dict[str, Any]:
    db = database or database_config.get_default_source()
    if not database_config.validate_source(db):
        db = database_config.get_default_source()

    league_svc = LeagueService(database=db)
    league_df = _league_frame(league_svc.adapter.get_filtered_data(filters={}))

    league_games = _count_scored_games(league_df)
    leagues = (
        int(league_df[Columns.league_name].dropna().nunique()) if not league_df.empty else 0
    )
    league_seasons = (
        int(league_df[Columns.season].dropna().nunique()) if not league_df.empty else 0
    )

    tournament_db = _resolve_tournament_database()
    tournament_df = pd.DataFrame()
    tournaments = 0
    tournament_games = 0
    tournament_seasons = 0
    try:
        t_svc = TournamentService(database=tournament_db)
        raw_t = t_svc.adapter.get_filtered_data(filters={})
        tournament_df = _tournament_frame(raw_t)
        tournament_games = _count_scored_games(tournament_df)
        if not tournament_df.empty and Columns.event_name in tournament_df.columns:
            tournaments = int(tournament_df[Columns.event_name].dropna().nunique())
        if not tournament_df.empty and Columns.season in tournament_df.columns:
            tournament_seasons = int(tournament_df[Columns.season].dropna().nunique())
    except Exception:
        pass

    seasons = len(
        set(league_df[Columns.season].dropna().astype(str).tolist())
        | set(tournament_df[Columns.season].dropna().astype(str).tolist())
        if not league_df.empty or not tournament_df.empty
        else set()
    )

    return {
        "database": db,
        "tournament_database": tournament_db,
        "games": league_games + tournament_games,
        "league_games": league_games,
        "tournament_games": tournament_games,
        "leagues": leagues,
        "seasons": seasons or max(league_seasons, tournament_seasons),
        "tournaments": tournaments,
        "players": _unique_players(league_df, tournament_df),
    }
