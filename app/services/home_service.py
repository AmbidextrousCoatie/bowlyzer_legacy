"""Aggregate counts for the landing page."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.config.database_config import database_config
from app.services.league_service import LeagueService
from app.services.tournament_service import TournamentService
from data_access.competition_schema import competition_event_column
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


def _unique_seasons(*frames: pd.DataFrame) -> int:
    seasons: set[str] = set()
    for frame in frames:
        if frame.empty or Columns.season not in frame.columns:
            continue
        for season in frame[Columns.season].dropna().astype(str):
            text = season.strip()
            if text:
                seasons.add(text)
    return len(seasons)


def _unique_season_event_combos(frame: pd.DataFrame, event_col: str | None) -> int:
    if frame.empty or not event_col or event_col not in frame.columns:
        return 0
    if Columns.season not in frame.columns:
        return 0
    season = frame[Columns.season].fillna("").astype(str).str.strip()
    event = frame[event_col].fillna("").astype(str).str.strip()
    valid = season.ne("") & event.ne("")
    if not valid.any():
        return 0
    return int(frame.loc[valid, [Columns.season, event_col]].drop_duplicates().shape[0])


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
    league_event_col = competition_event_column(league_df) or Columns.event

    tournament_db = _resolve_tournament_database()
    tournament_df = pd.DataFrame()
    tournament_games = 0
    tournament_event_col: str | None = None
    try:
        t_svc = TournamentService(database=tournament_db)
        raw_t = t_svc.adapter.get_filtered_data(filters={})
        tournament_df = _tournament_frame(raw_t)
        tournament_games = _count_scored_games(tournament_df)
        tournament_event_col = competition_event_column(tournament_df)
    except Exception:
        pass

    years = _unique_seasons(league_df, tournament_df)
    league_seasons = _unique_season_event_combos(league_df, league_event_col)
    tournaments = _unique_season_event_combos(tournament_df, tournament_event_col)

    return {
        "database": db,
        "tournament_database": tournament_db,
        "games": league_games + tournament_games,
        "league_games": league_games,
        "tournament_games": tournament_games,
        "years": years,
        "league_seasons": league_seasons,
        "tournaments": tournaments,
        "players": _unique_players(league_df, tournament_df),
    }
