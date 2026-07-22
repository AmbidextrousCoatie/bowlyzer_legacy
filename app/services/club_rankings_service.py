"""Cross-club leaderboard metrics for the club page empty state."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.club_legends_service import (
    _club_series,
    _league_game_rows,
    _player_keys,
)
from app.services.league_service import LeagueService
from app.services.tournament_service import TournamentService
from app.utils.json_safe import to_json_float, to_json_int
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label

TOP_N = 5


def _club_entries(series: pd.Series, top_n: int) -> List[Dict[str, Any]]:
    if series is None or series.empty:
        return []
    ranked = series.sort_values(ascending=False).head(top_n)
    out: List[Dict[str, Any]] = []
    for club, value in ranked.items():
        label = str(club or "").strip()
        if not label:
            continue
        out.append({"club": label, "value": to_json_int(value)})
    return out


def _detail_entry(
    row: pd.Series,
    value: float,
    *,
    match_total: Optional[float] = None,
) -> Dict[str, Any]:
    week_val = row.get(Columns.week)
    round_val = row.get("_round")
    entry: Dict[str, Any] = {
        "club": str(row["_club"]),
        "value": to_json_float(value),
        "team": str(row.get(Columns.team_name) or "").strip(),
        "season": str(row.get(Columns.season) or "").strip(),
        "league": str(row.get(Columns.league_name) or "").strip(),
        "week": str(week_val).strip() if pd.notna(week_val) else "",
    }
    if round_val is not None and pd.notna(round_val):
        entry["round"] = str(int(round_val))
    total = match_total
    if total is None and "match_total" in row.index and pd.notna(row.get("match_total")):
        total = float(row["match_total"])
    if total is not None:
        entry["match_total"] = to_json_int(total)
    return entry


class ClubRankingsService:
    def __init__(
        self,
        league_database: str,
        tournament_database: Optional[str] = None,
    ):
        self.league_database = league_database
        self._league_service = LeagueService(database=league_database)
        self._tournament_database = tournament_database

    def _resolve_tournament_database(self) -> Optional[str]:
        if self._tournament_database:
            return self._tournament_database
        try:
            from app.routes.tournament_routes import _resolve_default_tournament_source

            return _resolve_default_tournament_source()
        except Exception:
            return None

    def _canonical_clubs(self) -> List[str]:
        return self._league_service.get_available_clubs()

    def _resolve_club(self, label: str, clubs: List[str]) -> str:
        resolved = self._league_service.resolve_club_name(label, clubs)
        return resolved or str(label or "").strip()

    def _player_league_frame(self) -> pd.DataFrame:
        from app.services.player_service import PlayerService

        base = PlayerService(database=self.league_database).data_manager.df
        df = _league_game_rows(base if base is not None else pd.DataFrame())
        if df.empty:
            return df
        work = df.copy()
        work["_club"] = _club_series(work)
        return work.loc[work["_club"].astype(str).str.strip().ne("")]

    def _pins_and_members(self, top_n: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        work = self._player_league_frame()
        if work.empty:
            return [], []

        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce")
        pins = work.groupby("_club", sort=False)[Columns.score].sum()

        keys, _ = _player_keys(work)
        members_work = work.copy()
        members_work["_pk"] = keys
        members_work = members_work.loc[members_work["_pk"].astype(str).str.strip().ne("")]
        members = (
            members_work.groupby("_club", sort=False)["_pk"].nunique()
            if not members_work.empty
            else pd.Series(dtype=int)
        )

        return _club_entries(pins, top_n), _club_entries(members, top_n)

    def _team_match_frame(self) -> pd.DataFrame:
        """One row per team match (round > 0) with scratch team average."""
        df = self._league_service.adapter.get_filtered_data(
            filters={Columns.computed_data: {"value": False, "operator": "eq"}},
            columns=[
                Columns.team_name,
                Columns.score,
                Columns.season,
                Columns.league_name,
                Columns.week,
                Columns.round_number,
                Columns.player_name,
            ],
        )
        if df is None or df.empty:
            return pd.DataFrame()

        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce")
        work = work.dropna(subset=[Columns.score])
        names = work[Columns.player_name].fillna("").astype(str).str.strip()
        work = work.loc[names.ne("") & names.ne("Team Total")]
        if work.empty:
            return pd.DataFrame()

        work["_round"] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        work = work.dropna(subset=["_round"])
        work = work.loc[work["_round"] > 0]
        if work.empty:
            return pd.DataFrame()

        match_keys = [
            Columns.season,
            Columns.league_name,
            Columns.week,
            Columns.team_name,
            "_round",
        ]
        matches = (
            work.groupby(match_keys, sort=False)[Columns.score]
            .agg(match_average="mean", match_total="sum", players="count")
            .reset_index()
        )
        return matches

    def _team_average_rankings(
        self,
        clubs: List[str],
        top_n: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        matches = self._team_match_frame()
        if matches.empty:
            return [], []

        resolved_clubs: List[str] = []
        for team_name in matches[Columns.team_name].astype(str):
            club, _ = self._league_service._split_club_and_team_number(team_name)
            resolved_clubs.append(self._resolve_club(club, clubs))
        matches = matches.copy()
        matches["_club"] = resolved_clubs
        matches = matches.loc[matches["_club"].astype(str).str.strip().ne("")]
        if matches.empty:
            return [], []

        week_keys = [Columns.season, Columns.league_name, Columns.week, Columns.team_name, "_club"]
        weekly = (
            matches.groupby(week_keys, sort=False)["match_average"]
            .mean()
            .reset_index(name="week_average")
        )

        weekly_idx = weekly.groupby("_club", sort=False)["week_average"].idxmax()
        weekly_best = weekly.loc[weekly_idx].sort_values("week_average", ascending=False).head(top_n)

        match_idx = matches.groupby("_club", sort=False)["match_average"].idxmax()
        match_best = matches.loc[match_idx].sort_values("match_average", ascending=False).head(top_n)

        weekly_out = [
            _detail_entry(row, float(row["week_average"])) for _, row in weekly_best.iterrows()
        ]
        match_out = [
            _detail_entry(row, float(row["match_average"])) for _, row in match_best.iterrows()
        ]
        return weekly_out, match_out

    def _league_wins(self, clubs: List[str], top_n: int) -> List[Dict[str, Any]]:
        df = self._league_service.adapter.get_filtered_data(
            columns=[Columns.season, Columns.league_name, Columns.team_name, Columns.points],
            filters={},
        )
        if df is None or df.empty:
            return []

        work = df.dropna(subset=[Columns.season, Columns.league_name, Columns.team_name]).copy()
        if work.empty or Columns.points not in work.columns:
            return []

        work[Columns.points] = pd.to_numeric(work[Columns.points], errors="coerce").fillna(0)
        totals = (
            work.groupby([Columns.season, Columns.league_name, Columns.team_name], sort=False)[
                Columns.points
            ]
            .sum()
            .reset_index()
        )
        totals["rank"] = totals.groupby([Columns.season, Columns.league_name], sort=False)[
            Columns.points
        ].rank(ascending=False, method="min")
        winners = totals.loc[totals["rank"] == 1]
        if winners.empty:
            return []

        counts: Counter[str] = Counter()
        for _, row in winners.iterrows():
            club, _ = self._league_service._split_club_and_team_number(row[Columns.team_name])
            resolved = self._resolve_club(club, clubs)
            if resolved:
                counts[resolved] += 1

        series = pd.Series(dict(counts), dtype=int)
        return _club_entries(series, top_n)

    def _tournament_wins(self, clubs: List[str], top_n: int) -> List[Dict[str, Any]]:
        tournament_db = self._resolve_tournament_database()
        if not tournament_db:
            return []

        try:
            tournament_svc = TournamentService(database=tournament_db)
            events = tournament_svc.list_tournament_events()
        except Exception:
            return []

        counts: Counter[str] = Counter()
        for event in events:
            season = str(event.get("season") or "").strip()
            tournament = str(event.get("tournament") or "").strip()
            if not season or not tournament:
                continue
            finishers, _ = tournament_svc._leaderboard_top_finishers(
                season,
                tournament,
                top_n=1,
            )
            if not finishers:
                continue
            winner = finishers[0]
            if winner.get("rank") != 1:
                continue
            club_label = str(winner.get("club") or "").strip()
            if not club_label:
                continue
            resolved = self._resolve_club(club_label, clubs)
            if not resolved:
                continue
            norm = normalize_unicode_label(resolved)
            if norm:
                counts[resolved] += 1

        if not counts:
            return []
        series = pd.Series(dict(counts), dtype=int)
        return _club_entries(series, top_n)

    def get_club_rankings(self, top_n: int = TOP_N) -> Dict[str, Any]:
        limit = max(1, min(int(top_n or TOP_N), 20))
        clubs = self._canonical_clubs()

        highest_total_pinfall, most_members = self._pins_and_members(limit)
        highest_weekly_team_average, highest_team_game_average = self._team_average_rankings(
            clubs,
            limit,
        )

        return {
            "top_n": limit,
            "highest_total_pinfall": highest_total_pinfall,
            "most_members": most_members,
            "highest_weekly_team_average": highest_weekly_team_average,
            "highest_team_game_average": highest_team_game_average,
            "most_tournament_wins": self._tournament_wins(clubs, limit),
            "most_league_wins": self._league_wins(clubs, limit),
        }
