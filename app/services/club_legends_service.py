"""Club player highlights (legends) from league game rows."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.services.league_service import LeagueService
from app.services.player_service import PlayerService
from app.utils.json_safe import to_json_float, to_json_int
from app.utils.league_player_sources import resolve_player_database_id
from data_access.schema import Columns
from data_access.score_utils import mean_scores
from data_access.text_norm import normalize_unicode_label

TOP_N = 5
MIN_GAMES_ALLTIME_AVG = 12
MIN_GAMES_SEASON_SPOTLIGHT = 6
MIN_TEAMS_REPRESENTED = 2
MIN_LEAGUES_SEEN = 2


def _split_club_from_team_label(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", raw)
    if not match:
        return raw
    return str(match.group(1) or "").strip()


def _normalize_club_label(value: Any) -> str:
    label = _split_club_from_team_label(str(value or "").strip())
    return normalize_unicode_label(label) if label else ""


def _team_slot_label(team_name: str) -> str:
    """Mannschaft number within a club (``2`` from ``Club Name 2``); ``base`` if unnumbered."""
    raw = str(team_name or "").strip()
    if not raw:
        return ""
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", raw)
    if not match:
        return "base"
    num = str(match.group(2) or "").strip()
    return num if num else "base"


def _format_team_slots(slots: List[str]) -> List[str]:
    uniq = sorted(
        {str(s).strip() for s in slots if str(s).strip()},
        key=lambda s: (s != "base", int(s) if str(s).isdigit() else 999, str(s)),
    )
    return ["Basis" if s == "base" else str(s) for s in uniq]


def _league_game_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Input player rows for league stats (exclude computed + tournaments)."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df
    if Columns.input_data in out.columns:
        from app.services.player_service import _csv_bool_is_true

        out = out[_csv_bool_is_true(out[Columns.input_data])]
    if Columns.computed_data in out.columns:
        from app.services.player_service import _csv_bool_is_false

        out = out[_csv_bool_is_false(out[Columns.computed_data])]
    if Columns.event_type in out.columns:
        et = out[Columns.event_type].fillna("").astype(str).str.strip().str.lower()
        out = out.loc[~et.eq("tournament")]
    elif Columns.league_name in out.columns:
        lg = out[Columns.league_name].fillna("").astype(str).str.strip()
        out = out.loc[lg.ne("")]
    if Columns.player_name in out.columns:
        names = out[Columns.player_name].fillna("").astype(str).str.strip()
        out = out.loc[names.ne("") & names.ne("Team Total")]
    if Columns.score in out.columns:
        out = out.copy()
        out[Columns.score] = pd.to_numeric(out[Columns.score], errors="coerce")
        out = out.dropna(subset=[Columns.score])
    return out


def _club_series(df: pd.DataFrame) -> pd.Series:
    if Columns.club in df.columns:
        raw = df[Columns.club].fillna("").astype(str).str.strip()
        return raw.map(_normalize_club_label)
    if Columns.team_name in df.columns:
        return df[Columns.team_name].fillna("").astype(str).map(_normalize_club_label)
    return pd.Series([""] * len(df), index=df.index)


def _player_keys(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    names = df[Columns.player_name].fillna("").astype(str).str.strip()
    if Columns.player_id in df.columns:
        pid = df[Columns.player_id].fillna("").astype(str).str.strip()
        pid = pid.where(~pid.str.lower().isin({"", "nan", "none"}), "")
        key = pid.where(pid.astype(bool), names)
    else:
        key = names
    return key, names


def _display_name(group_names: pd.Series) -> str:
    cleaned = [str(n).strip() for n in group_names.dropna().tolist() if str(n).strip()]
    if not cleaned:
        return ""
    return max(set(cleaned), key=lambda n: (cleaned.count(n), len(n), n.lower()))


def _canonical_display_name(
    player_id: str,
    group_names: pd.Series,
    registry_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> str:
    """Prefer ``players_registry`` canonical_name; fall back to majority spelling."""
    from data_access.player_id_name_normalization import normalize_player_id

    pid = normalize_player_id(player_id)
    if pid and registry_lookup:
        entry = registry_lookup.get(pid)
        if entry:
            canon = str(entry.get("canonical_name") or "").strip()
            if canon:
                return canon
    return _display_name(group_names)


def _legend_row(
    *,
    player_id: str,
    player_name: str,
    value: float | int,
    games: Optional[int] = None,
    average: Optional[float] = None,
    season: Optional[str] = None,
    teams: Optional[List[str]] = None,
    leagues: Optional[List[str]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "player_id": player_id or "",
        "player_name": player_name,
        "value": value,
    }
    if games is not None:
        row["games"] = to_json_int(games)
    if average is not None:
        row["average"] = to_json_float(average)
    if season:
        row["season"] = season
    if teams:
        row["teams"] = teams
    if leagues:
        row["leagues"] = leagues
    return row


def _empty_payload(club: str = "") -> Dict[str, Any]:
    return {
        "club": club,
        "most_seasons": [],
        "most_games": [],
        "highest_average": [],
        "best_seasons": [],
        "most_teams_represented": [],
        "most_leagues_seen": [],
    }


class ClubLegendsService:
    def __init__(self, league_database: str, player_database: Optional[str] = None):
        self.league_database = league_database
        self.player_database = player_database or resolve_player_database_id(league_database)
        self._league_service = LeagueService(database=league_database)
        self._player_service = PlayerService(database=self.player_database)
        self._league_games: Optional[pd.DataFrame] = None

    def _league_games_dataframe(self) -> pd.DataFrame:
        if self._league_games is not None:
            return self._league_games
        base = self._player_service.data_manager.df
        self._league_games = _league_game_rows(base if base is not None else pd.DataFrame())
        return self._league_games

    def _club_frame(self, club: str) -> pd.DataFrame:
        df = self._league_games_dataframe()
        if df.empty or not club:
            return df.iloc[0:0]
        club_norm = normalize_unicode_label(club)
        clubs = _club_series(df)
        return df.loc[clubs.eq(club_norm)].copy()

    def get_club_legends(self, club: str) -> Dict[str, Any]:
        clubs = self._league_service.get_available_clubs()
        resolved = self._league_service.resolve_club_name(club, clubs)
        if not resolved:
            return _empty_payload(str(club or "").strip())

        df = self._club_frame(resolved)
        if df.empty or Columns.player_name not in df.columns or Columns.season not in df.columns:
            return _empty_payload(resolved)

        keys, names = _player_keys(df)
        work = df.copy()
        work["_pk"] = keys
        work["_pname"] = names
        work = work.loc[work["_pk"].astype(str).str.strip().ne("")]
        if work.empty:
            return _empty_payload(resolved)

        registry_lookup: Dict[str, Dict[str, str]] = {}
        try:
            from data_access.players_registry import load_players_registry_df, registry_lookup_by_id

            registry_df = load_players_registry_df()
            if registry_df is not None and not registry_df.empty:
                registry_lookup = registry_lookup_by_id(registry_df)
        except Exception:
            registry_lookup = {}

        def pid_for_group(g: pd.DataFrame) -> str:
            if Columns.player_id not in g.columns:
                return ""
            vals = g[Columns.player_id].fillna("").astype(str).str.strip()
            vals = vals[~vals.str.lower().isin({"", "nan", "none"})]
            return str(vals.iloc[0]) if len(vals) else ""

        def display_for_group(g: pd.DataFrame) -> str:
            return _canonical_display_name(pid_for_group(g), g["_pname"], registry_lookup)

        # --- most seasons ---
        season_counts = (
            work.groupby("_pk", sort=False)
            .agg(
                seasons=(Columns.season, "nunique"),
                _pname=("_pname", lambda s: _display_name(s)),
            )
            .reset_index()
        )
        season_counts = season_counts.sort_values(
            by=["seasons", "_pname"],
            ascending=[False, True],
        ).head(TOP_N)
        most_seasons = [
            _legend_row(
                player_id=pid_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                player_name=display_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                value=int(row["seasons"]),
            )
            for _, row in season_counts.iterrows()
        ]

        # --- most games ---
        game_counts = (
            work.groupby("_pk", sort=False)
            .agg(
                games=("_pk", "size"),
                _pname=("_pname", lambda s: _display_name(s)),
            )
            .reset_index()
        )
        game_counts = game_counts.sort_values(by=["games", "_pname"], ascending=[False, True]).head(TOP_N)
        most_games = []
        for _, row in game_counts.iterrows():
            pk = row["_pk"]
            sub = work.loc[work["_pk"].eq(pk)]
            most_games.append(
                _legend_row(
                    player_id=pid_for_group(sub),
                    player_name=display_for_group(sub),
                    value=int(row["games"]),
                    games=int(row["games"]),
                    average=to_json_float(mean_scores(sub[Columns.score])),
                )
            )

        # --- highest all-time average ---
        player_avgs = (
            work.groupby("_pk", sort=False)
            .agg(
                average=(Columns.score, lambda s: mean_scores(s)),
                games=(Columns.score, "size"),
                _pname=("_pname", lambda s: _display_name(s)),
            )
            .reset_index()
        )
        player_avgs = player_avgs.loc[player_avgs["games"] >= MIN_GAMES_ALLTIME_AVG]
        player_avgs = player_avgs.sort_values(
            by=["average", "games", "_pname"],
            ascending=[False, False, True],
        ).head(TOP_N)
        highest_average = [
            _legend_row(
                player_id=pid_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                player_name=display_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                value=to_json_float(row["average"]),
                games=int(row["games"]),
                average=to_json_float(row["average"]),
            )
            for _, row in player_avgs.iterrows()
        ]

        # --- best single seasons ---
        season_avgs = (
            work.groupby(["_pk", Columns.season], sort=False)
            .agg(
                average=(Columns.score, lambda s: mean_scores(s)),
                games=(Columns.score, "size"),
                _pname=("_pname", lambda s: _display_name(s)),
            )
            .reset_index()
        )
        season_avgs = season_avgs.loc[season_avgs["games"] >= MIN_GAMES_SEASON_SPOTLIGHT]
        season_avgs = season_avgs.sort_values(
            by=["average", "games", Columns.season],
            ascending=[False, False, False],
        ).head(TOP_N)
        best_seasons = [
            _legend_row(
                player_id=pid_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                player_name=display_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                value=to_json_float(row["average"]),
                games=int(row["games"]),
                average=to_json_float(row["average"]),
                season=str(row[Columns.season]),
            )
            for _, row in season_avgs.iterrows()
        ]

        # --- most teams represented (Mannschaften within the club) ---
        most_teams_represented: List[Dict[str, Any]] = []
        if Columns.team_name in work.columns:
            slot_work = work.copy()
            slot_work["_team_slot"] = (
                slot_work[Columns.team_name].fillna("").astype(str).map(_team_slot_label)
            )
            slot_work = slot_work.loc[slot_work["_team_slot"].astype(str).ne("")]
            if not slot_work.empty:
                team_counts = (
                    slot_work.groupby("_pk", sort=False)
                    .agg(
                        teams=("_team_slot", lambda s: _format_team_slots(list(s))),
                        _pname=("_pname", lambda s: _display_name(s)),
                    )
                    .reset_index()
                )
                team_counts["team_count"] = team_counts["teams"].map(len)
                team_counts = team_counts.loc[team_counts["team_count"] >= MIN_TEAMS_REPRESENTED]
                team_counts = team_counts.sort_values(
                    by=["team_count", "_pname"],
                    ascending=[False, True],
                ).head(TOP_N)
                most_teams_represented = [
                    _legend_row(
                        player_id=pid_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                        player_name=display_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                        value=int(row["team_count"]),
                        teams=list(row["teams"]),
                    )
                    for _, row in team_counts.iterrows()
                ]

        # --- most leagues seen ---
        most_leagues_seen: List[Dict[str, Any]] = []
        if Columns.league_name in work.columns:
            league_work = work.copy()
            league_work["_league"] = (
                league_work[Columns.league_name].fillna("").astype(str).str.strip()
            )
            league_work = league_work.loc[league_work["_league"].astype(str).ne("")]
            if not league_work.empty:
                league_counts = (
                    league_work.groupby("_pk", sort=False)
                    .agg(
                        leagues=(
                            "_league",
                            lambda s: sorted({str(x).strip() for x in s if str(x).strip()}),
                        ),
                        _pname=("_pname", lambda s: _display_name(s)),
                    )
                    .reset_index()
                )
                league_counts["league_count"] = league_counts["leagues"].map(len)
                league_counts = league_counts.loc[league_counts["league_count"] >= MIN_LEAGUES_SEEN]
                league_counts = league_counts.sort_values(
                    by=["league_count", "_pname"],
                    ascending=[False, True],
                ).head(TOP_N)
                most_leagues_seen = [
                    _legend_row(
                        player_id=pid_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                        player_name=display_for_group(work.loc[work["_pk"].eq(row["_pk"])]),
                        value=int(row["league_count"]),
                        leagues=list(row["leagues"]),
                    )
                    for _, row in league_counts.iterrows()
                ]

        return {
            "club": resolved,
            "most_seasons": most_seasons,
            "most_games": most_games,
            "highest_average": highest_average,
            "best_seasons": best_seasons,
            "most_teams_represented": most_teams_represented,
            "most_leagues_seen": most_leagues_seen,
        }
