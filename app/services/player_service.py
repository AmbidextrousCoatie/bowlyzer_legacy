import pandas as pd
import re
from data_access.schema import Columns
from data_access.score_utils import mean_scores, sum_scores, sum_scores_float
from app.services.data_manager import DataManager
from app.config.database_config import database_config
from business_logic.statistics import calculate_score_average_player, calculate_games_count_player
from business_logic.server import Server
from app.services.statistics_service import StatisticsService
from app.models.statistics_models import PlayerStatistics
from app.utils.json_safe import to_json_int
from typing import Dict, List, Any, Optional, Tuple

OVERALL_CUMULATIVE_SCORE_COL = "Overall Cumulative Score"


def _csv_bool_is_true(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(("true", "1", "yes"))


def _csv_bool_is_false(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(("false", "0", "no", ""))


class PlayerService:
    _player_catalog_cache: Dict[str, List[Dict[str, str]]] = {}

    def __init__(self, database: str = None):
        self.database = database
        self.data_manager = DataManager(source=database) if database else DataManager()
        self.server = Server(database=database)
        self.stats_service = StatisticsService(database=database)

    @staticmethod
    def _normalize_player_id(value: Any) -> str:
        raw = str(value).strip() if value is not None else ""
        if not raw:
            return ""
        try:
            return str(int(float(raw)))
        except ValueError:
            return raw

    @staticmethod
    def _build_name_token_stats(df: pd.DataFrame) -> Tuple[Dict[str, int], Dict[str, int]]:
        first_counts: Dict[str, int] = {}
        last_counts: Dict[str, int] = {}
        if df is None or df.empty or Columns.player_name not in df.columns:
            return first_counts, last_counts

        for raw in df[Columns.player_name].dropna().astype(str).tolist():
            parts = raw.strip().split()
            if len(parts) < 2:
                continue
            first, last = parts[0], parts[-1]
            first_counts[first] = first_counts.get(first, 0) + 1
            last_counts[last] = last_counts.get(last, 0) + 1
        return first_counts, last_counts

    def _canonical_name_for_player_id(
        self,
        player_id: str,
        names: List[str],
        token_stats: Optional[Tuple[Dict[str, int], Dict[str, int]]] = None,
    ) -> str:
        """
        Pick one stable display name per player id.
        Heuristic for two-token reversals (A B vs B A):
        prefer orientation that matches global first/last token tendencies.
        """
        cleaned = [str(n).strip() for n in names if str(n).strip()]
        if not cleaned:
            return ""
        from data_access.players_registry import canonical_name_for_player_id

        registry_name = canonical_name_for_player_id(player_id)
        if registry_name:
            return registry_name
        if len(set(cleaned)) == 1:
            return cleaned[0]

        if token_stats is None:
            first_counts, last_counts = self._build_name_token_stats(self.data_manager.df)
        else:
            first_counts, last_counts = token_stats

        def score(name: str) -> int:
            parts = name.split()
            if len(parts) < 2:
                return 0
            first, last = parts[0], parts[-1]
            return (first_counts.get(first, 0) - last_counts.get(first, 0)) + (
                last_counts.get(last, 0) - first_counts.get(last, 0)
            )

        best = sorted(cleaned, key=lambda n: (-score(n), -len(n), n.lower()))[0]
        return best

    @staticmethod
    def _safe_player_rows(df: pd.DataFrame) -> pd.DataFrame:
        out = df
        if Columns.input_data in out.columns:
            out = out[_csv_bool_is_true(out[Columns.input_data])]
        if Columns.computed_data in out.columns:
            out = out[_csv_bool_is_false(out[Columns.computed_data])]
        return out

    def _player_catalog(self) -> List[Dict[str, str]]:
        df = self.data_manager.df
        if df is None or df.empty or Columns.player_name not in df.columns:
            return []
        source_id = str(self.data_manager.current_source or self.database or "")
        from data_access.shared_pandas_store import compute_database_revision

        cache_key = compute_database_revision(source_id) if source_id else source_id
        cached = self._player_catalog_cache.get(cache_key)
        if cached is not None:
            return cached

        sub = self._safe_player_rows(df)
        if Columns.player_id not in sub.columns:
            names = sorted({str(n).strip() for n in sub[Columns.player_name].dropna().tolist() if str(n).strip()})
            sorted_out = [{"id": n, "name": n} for n in names if n != "Team Total"]
            self._player_catalog_cache[cache_key] = sorted_out
            return sorted_out

        work = sub[[Columns.player_id, Columns.player_name]].dropna(subset=[Columns.player_name]).copy()
        work["name"] = work[Columns.player_name].astype(str).str.strip()
        work = work[work["name"].ne("") & work["name"].ne("Team Total")]
        work["pid"] = work[Columns.player_id].map(self._normalize_player_id)
        work["key"] = work["pid"].where(work["pid"].astype(bool), work["name"])

        grouped: Dict[str, List[str]] = {}
        for key, names in work.groupby("key", sort=False)["name"]:
            unique_names = list(dict.fromkeys(names.tolist()))
            grouped[str(key)] = unique_names

        out = []
        token_stats = self._build_name_token_stats(sub)
        for pid, names in grouped.items():
            canonical = self._canonical_name_for_player_id(pid, names, token_stats=token_stats)
            if canonical:
                out.append({"id": pid, "name": canonical})
        sorted_out = sorted(out, key=lambda x: x["name"].lower())
        self._player_catalog_cache[cache_key] = sorted_out
        return sorted_out

    def _subset_player_games(
        self,
        player_name: str,
        player_id: str = "",
        season: str | None = None,
    ) -> pd.DataFrame:
        """Player input rows for one player (optional season), without copying the full table."""
        base = self.data_manager.df
        if base is None or base.empty:
            return pd.DataFrame()

        pid = self._normalize_player_id(player_id)
        if pid and Columns.player_id in base.columns:
            id_series = base[Columns.player_id].astype(str).map(self._normalize_player_id)
            games_df = base.loc[id_series.eq(pid)]
        elif player_name:
            games_df = self.server.get_games_for_player(player_name)
            if games_df is None:
                games_df = base.iloc[0:0]
        else:
            games_df = base.iloc[0:0]

        if season and str(season).strip().lower() != "all":
            season_norm = str(season).strip()
            if Columns.season in games_df.columns:
                games_df = games_df.loc[games_df[Columns.season].astype(str).str.strip().eq(season_norm)]

        games_df = self._safe_player_rows(games_df)
        if Columns.score in games_df.columns:
            games_df = games_df.copy()
            games_df[Columns.score] = pd.to_numeric(games_df[Columns.score], errors="coerce")
            games_df = games_df.dropna(subset=[Columns.score])
        return games_df

    def _build_period_stats(
        self,
        games_df: pd.DataFrame,
        *,
        competition_name,
        row_team_name,
        row_club,
    ) -> List[Dict[str, Any]]:
        """Per matchday (league week) or tournament stage averages for highlight boxes."""
        if games_df is None or games_df.empty or Columns.score not in games_df.columns:
            return []

        from data_access.competition_schema import competition_event_column

        work = games_df.copy()
        if Columns.event_type in work.columns:
            is_tournament = (
                work[Columns.event_type].fillna("").astype(str).str.strip().str.lower().eq("tournament")
            )
        else:
            is_tournament = pd.Series(False, index=work.index)

        periods: List[Dict[str, Any]] = []

        def append_period(*, chunk: pd.DataFrame, is_tourn: bool, period_kind: str, period_value: str, period_number: Any) -> None:
            if chunk.empty:
                return
            games = len(chunk)
            if games <= 0:
                return
            avg = mean_scores(chunk[Columns.score])
            if avg is None:
                return
            season_val = ""
            if Columns.season in chunk.columns:
                seasons = [str(s).strip() for s in chunk[Columns.season].dropna().unique().tolist() if str(s).strip()]
                season_val = seasons[0] if seasons else ""
            comp = competition_name(chunk)
            team_num = None
            if Columns.team_name in chunk.columns:
                tn = row_team_name(chunk)
                if tn:
                    m = re.search(r"\s+(\d+)\s*$", tn)
                    if m:
                        team_num = int(m.group(1))
            periods.append(
                {
                    "season": season_val,
                    "competition": comp,
                    "is_tournament": bool(is_tourn),
                    "period_kind": period_kind,
                    "period_value": str(period_value).strip(),
                    "period_number": to_json_int(period_number) if period_number is not None else None,
                    "games": int(games),
                    "average": float(round(float(avg), 2)),
                    "club": row_club(chunk),
                    "team_name": row_team_name(chunk),
                    "team_number": team_num,
                    "row_type": "period",
                }
            )

        league_work = work.loc[~is_tournament]
        if not league_work.empty and Columns.week in league_work.columns:
            league_work = league_work.copy()
            league_work["_week"] = pd.to_numeric(league_work[Columns.week], errors="coerce")
            league_work = league_work.dropna(subset=["_week"])
            if not league_work.empty:
                comp_col = competition_event_column(league_work) or Columns.league_name
                if comp_col in league_work.columns:
                    group_cols = [Columns.season, comp_col, "_week"]
                    for keys, chunk in league_work.groupby(group_cols, dropna=False):
                        season_key, comp_key, week_key = keys
                        comp_label = str(comp_key).strip()
                        if not comp_label or pd.isna(week_key):
                            continue
                        append_period(
                            chunk=chunk,
                            is_tourn=False,
                            period_kind="week",
                            period_value=str(int(week_key)),
                            period_number=int(week_key),
                        )

        tourn_work = work.loc[is_tournament]
        if not tourn_work.empty:
            tourn_work = tourn_work.copy()
            if Columns.round_number in tourn_work.columns:
                tourn_work["_round"] = pd.to_numeric(tourn_work[Columns.round_number], errors="coerce")
            else:
                tourn_work["_round"] = pd.NA
            comp_col = competition_event_column(tourn_work) or Columns.event_name
            if comp_col in tourn_work.columns:
                group_cols = [Columns.season, comp_col, "_round"]
                if Columns.round_name in tourn_work.columns:
                    group_cols.append(Columns.round_name)
                for keys, chunk in tourn_work.groupby(group_cols, dropna=False):
                    season_key = keys[0]
                    comp_key = keys[1]
                    round_key = keys[2]
                    round_name = ""
                    if Columns.round_name in tourn_work.columns and len(keys) > 3:
                        round_name = str(keys[3]).strip()
                    comp_label = str(comp_key).strip()
                    if not comp_label or pd.isna(round_key):
                        continue
                    label = round_name or f"Round {int(round_key)}"
                    append_period(
                        chunk=chunk,
                        is_tourn=True,
                        period_kind="round",
                        period_value=label,
                        period_number=int(round_key),
                    )

        return periods

    def _subset_ranking_frame(
        self,
        season_value: Any,
        *,
        league_value: str | None = None,
        event_value: str | None = None,
        tournament_only: bool = False,
    ) -> pd.DataFrame:
        base = self.data_manager.df
        if base is None or base.empty:
            return pd.DataFrame()
        if Columns.season in base.columns:
            base = base.loc[base[Columns.season].astype(str).str.strip().eq(str(season_value).strip())]
        if league_value and Columns.league_name in base.columns:
            base = base.loc[
                base[Columns.league_name].astype(str).str.strip().eq(str(league_value).strip())
            ]
        if event_value:
            from data_access.competition_schema import competition_event_column

            event_col = competition_event_column(base)
            if event_col:
                base = base.loc[
                    base[event_col].astype(str).str.strip().eq(str(event_value).strip())
                ]
        if tournament_only and Columns.event_type in base.columns:
            base = base.loc[base[Columns.event_type].astype(str).str.strip().str.lower().eq("tournament")]
        return self._safe_player_rows(base)

    def get_all_players(self):
        """Get list of all players for selection"""
        return self._player_catalog()

    def get_player_statistics(self, player_name: str, season: str) -> PlayerStatistics:
        """Get comprehensive player statistics"""
        return self.stats_service.get_player_statistics(player_name, season)

    def get_personal_stats(self, player_name: str, season: str = 'all') -> Dict[str, Any]:
        """Get personal statistics for a player"""
        if season == 'all':
            # Get all seasons the player participated in
            player_data = self.data_manager.df[self.data_manager.df[Columns.player_name] == player_name]
            seasons = sorted(player_data[Columns.season].unique())
            
            # Get statistics for each season
            season_stats = []
            for season in seasons:
                stats = self.get_player_statistics(player_name, season)
                if stats:
                    season_stats.append({
                        'season': season,
                        'statistics': {
                            'total_score': stats.season_summary.total_score,
                            'total_points': stats.season_summary.total_points,
                            'average_score': stats.season_summary.average_score,
                            'games_played': stats.season_summary.games_played,
                            'best_score': stats.season_summary.best_score,
                            'worst_score': stats.season_summary.worst_score,
                            'team_contribution': stats.team_contribution
                        }
                    })
            
            return {
                'name': player_name,
                'seasons': season_stats
            }
        else:
            # Get statistics for specific season
            stats = self.get_player_statistics(player_name, season)
            if not stats:
                return None
                
            return {
                'name': player_name,
                'season': season,
                'statistics': {
                    'total_score': stats.season_summary.total_score,
                    'total_points': stats.season_summary.total_points,
                    'average_score': stats.season_summary.average_score,
                    'games_played': stats.season_summary.games_played,
                    'best_score': stats.season_summary.best_score,
                    'worst_score': stats.season_summary.worst_score,
                    'team_contribution': stats.team_contribution
                }
            }

    def get_team_comparison(self, player_name: str, season: str) -> Dict[str, Any]:
        """Compare player stats with team averages"""
        player_stats = self.get_player_statistics(player_name, season)
        if not player_stats:
            return None
            
        # Get team data
        team_data = self.data_manager.df[
            (self.data_manager.df[Columns.team_name] == player_stats.team_name) &
            (self.data_manager.df[Columns.season] == season)
        ]
        
        # Calculate team averages
        team_avg = mean_scores(team_data[Columns.score])
        team_total = sum_scores_float(team_data[Columns.score])
        
        return {
            'player': {
                'name': player_name,
                'average': player_stats.season_summary.average_score,
                'total_score': player_stats.season_summary.total_score,
                'contribution': player_stats.team_contribution
            },
            'team': {
                'name': player_stats.team_name,
                'average': team_avg,
                'total_score': team_total
            },
            'comparison': {
                'vs_team_avg': player_stats.season_summary.average_score - team_avg,
                'contribution_percentage': player_stats.team_contribution
            }
        }

    def search_players(self, search_term: str) -> List[Dict[str, str]]:
        """Search players by name"""
        # Get all players first
        all_players = self.get_all_players()
        
        # Filter players based on search term
        if search_term:
            search_term = search_term.lower()
            filtered_players = [
                player
                for player in all_players
                if search_term in str(player.get("name", "")).lower()
                or search_term in str(player.get("id", "")).lower()
            ]
            return filtered_players
        
        return all_players

    def get_player_seasons(self, player_name: str, player_id: str = "") -> List[str]:
        """Get sorted season list for a specific player."""
        if not player_name and not player_id:
            return []
        games_df = self._subset_player_games(player_name, player_id)
        if games_df.empty or Columns.season not in games_df.columns:
            return []
        seasons = [str(s).strip() for s in games_df[Columns.season].dropna().unique().tolist() if str(s).strip()]
        return sorted(seasons)

    def get_historical_data(self, player_id: str):
        """Get historical performance data"""
        pass

    def get_lifetime_stats(self, player_name, season: str = "all", player_id: str = ""):
        """Get lifetime statistics for a player."""
        pid = self._normalize_player_id(player_id)
        games_df = self._subset_player_games(player_name, player_id, season=season)
        if games_df.empty:
            return None

        overall_average = mean_scores(games_df[Columns.score])

        def normalize_club(value: Any) -> str:
            label = str(value).strip() if value is not None else ""
            if not label:
                return "-"
            # Strip trailing team number, e.g. "Clubname 1" -> "Clubname"
            return re.sub(r"\s+\d+$", "", label)

        def competition_name(df: pd.DataFrame) -> str:
            from data_access.competition_schema import competition_event_column

            event_col = competition_event_column(df)
            if event_col:
                vals = [str(x).strip() for x in df[event_col].dropna().tolist() if str(x).strip()]
                if vals:
                    return vals[0]
            if Columns.league_name in df.columns:
                vals = [str(x).strip() for x in df[Columns.league_name].dropna().tolist() if str(x).strip()]
                if vals:
                    return vals[0]
            return "Unknown Competition"

        def row_team_name(df: pd.DataFrame) -> str:
            if Columns.team_name in df.columns:
                vals = [str(x).strip() for x in df[Columns.team_name].dropna().tolist() if str(x).strip()]
                if vals:
                    return vals[0]
            return ""

        def row_club(df: pd.DataFrame) -> str:
            if Columns.club in df.columns:
                vals = [str(x).strip() for x in df[Columns.club].dropna().tolist() if str(x).strip()]
                if vals:
                    return normalize_club(vals[0])
            if Columns.team_name in df.columns:
                vals = [str(x).strip() for x in df[Columns.team_name].dropna().tolist() if str(x).strip()]
                if vals:
                    return normalize_club(vals[0])
            return "-"

        def event_label(row: pd.Series) -> str:
            event = ""
            if Columns.event in row.index and pd.notna(row.get(Columns.event)):
                event = str(row.get(Columns.event)).strip()
            elif Columns.event_name in row.index and pd.notna(row.get(Columns.event_name)):
                event = str(row.get(Columns.event_name)).strip()
            if not event and Columns.league_name in row and pd.notna(row.get(Columns.league_name)):
                event = str(row.get(Columns.league_name)).strip()
            if not event:
                event = "Event"
            week_part = ""
            if Columns.week in row and pd.notna(row.get(Columns.week)):
                week_part = f" Week {row.get(Columns.week)}"
            round_part = ""
            if Columns.round_name in row and pd.notna(row.get(Columns.round_name)):
                round_part = f" {row.get(Columns.round_name)}"
            return f"{event}{week_part}{round_part}".strip()

        def league_average_rank(
            season_value: Any,
            league_value: str,
            player_value: str,
            player_id_value: str = "",
        ) -> Tuple[Optional[int], int]:
            base = self._subset_ranking_frame(season_value, league_value=league_value)
            if base.empty or Columns.player_name not in base.columns or Columns.score not in base.columns:
                return None, 0
            base = base.copy()
            base[Columns.score] = pd.to_numeric(base[Columns.score], errors="coerce")
            base = base.dropna(subset=[Columns.score])
            if base.empty:
                return None, 0
            pid_norm = self._normalize_player_id(player_id_value)
            if pid_norm and Columns.player_id in base.columns:
                base[Columns.player_id] = base[Columns.player_id].astype(str).map(self._normalize_player_id)
                grouped = (
                    base.groupby(Columns.player_id, dropna=False)[Columns.score]
                    .apply(mean_scores)
                    .sort_values(ascending=False)
                )
                if pid_norm not in grouped.index:
                    return None, int(len(grouped))
                rank_series = grouped.rank(method="min", ascending=False)
                return int(rank_series[pid_norm]), int(len(grouped))
            grouped = (
                base.groupby(Columns.player_name, dropna=False)[Columns.score]
                .apply(mean_scores)
                .sort_values(ascending=False)
            )
            if player_value not in grouped.index:
                return None, int(len(grouped))
            rank_series = grouped.rank(method="min", ascending=False)
            return int(rank_series[player_value]), int(len(grouped))

        def tournament_final_rank(
            season_value: Any,
            event_value: str,
            player_value: str,
            player_id_value: str = "",
        ) -> Tuple[Optional[int], int]:
            base = self._subset_ranking_frame(
                season_value,
                event_value=event_value,
                tournament_only=True,
            )
            if base.empty or Columns.player_name not in base.columns:
                return None, 0

            # Rank all participants by their latest cumulative tournament total.
            # This keeps eliminated players in ranking (e.g. did not reach final round).
            if (
                OVERALL_CUMULATIVE_SCORE_COL in base.columns
                and Columns.round_number in base.columns
                and Columns.game_number in base.columns
            ):
                work = base.copy()
                work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
                work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce")
                work[OVERALL_CUMULATIVE_SCORE_COL] = pd.to_numeric(
                    work[OVERALL_CUMULATIVE_SCORE_COL], errors="coerce"
                )
                work = work.dropna(subset=[OVERALL_CUMULATIVE_SCORE_COL])
                if work.empty:
                    return None, 0
                sort_cols = [Columns.player_name, Columns.round_number, Columns.game_number]
                work = work.sort_values(by=sort_cols, ascending=[True, True, True])
                latest = work.groupby(Columns.player_name, dropna=False).tail(1)
                totals = (
                    latest.groupby(Columns.player_name, dropna=False)[OVERALL_CUMULATIVE_SCORE_COL]
                    .max()
                    .sort_values(ascending=False)
                )
            else:
                if Columns.score not in base.columns:
                    return None, 0
                work = base.copy()
                work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
                totals = (
                    work.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .sort_values(ascending=False)
                )

            pid_norm = self._normalize_player_id(player_id_value)
            if pid_norm and Columns.player_id in base.columns:
                work = base.copy()
                work[Columns.player_id] = work[Columns.player_id].astype(str).map(self._normalize_player_id)
                if (
                    OVERALL_CUMULATIVE_SCORE_COL in work.columns
                    and Columns.round_number in work.columns
                    and Columns.game_number in work.columns
                ):
                    work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
                    work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce")
                    work[OVERALL_CUMULATIVE_SCORE_COL] = pd.to_numeric(work[OVERALL_CUMULATIVE_SCORE_COL], errors="coerce")
                    work = work.dropna(subset=[OVERALL_CUMULATIVE_SCORE_COL])
                    work = work.sort_values(by=[Columns.player_id, Columns.round_number, Columns.game_number], ascending=[True, True, True])
                    latest = work.groupby(Columns.player_id, dropna=False).tail(1)
                    totals_by_id = latest.groupby(Columns.player_id, dropna=False)[OVERALL_CUMULATIVE_SCORE_COL].max().sort_values(ascending=False)
                else:
                    work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
                    totals_by_id = (
                        work.groupby(Columns.player_id, dropna=False)[Columns.score]
                        .apply(sum_scores)
                        .sort_values(ascending=False)
                    )
                if pid_norm not in totals_by_id.index:
                    return None, int(len(totals_by_id))
                rank_series = totals_by_id.rank(method="min", ascending=False)
                return int(rank_series[pid_norm]), int(len(totals_by_id))

            if player_value not in totals.index:
                return None, int(len(totals))
            rank_series = totals.rank(method="min", ascending=False)
            return int(rank_series[player_value]), int(len(totals))

        # first handle the seasons stats
        data_grouped = games_df.groupby(Columns.season)
        season_stats = []
        last_seasons_average = None
        for i, (season, data) in enumerate(data_grouped):
            
            total_games = len(data)
            total_pins = sum_scores_float(data[Columns.score])
            average = total_pins / total_games
            
            # Calculate deviation from overall average
            dev_from_avg = average - overall_average
            
            # Calculate change from previous season
            if last_seasons_average is not None:
                vs_last_season = average - last_seasons_average
            else:
                vs_last_season = None  # Use None instead of 0.0 for first season
            
            last_seasons_average = average

            # Find best and worst games
            best_game = data[data[Columns.score] == data[Columns.score].max()].iloc[0]   
            worst_game = data[data[Columns.score] == data[Columns.score].min()].iloc[0]
            
            season_stats.append({
                'season': season,
                'competition': 'All Events',
                'club': '',
                'games': int(total_games),
                'total_pins': int(total_pins),
                'average': float(round(average, 2)),
                'vs_last_season': float(round(vs_last_season, 2)) if vs_last_season is not None else None,
                'rank': None,
                'is_tournament': False,
                'row_type': 'season_total',

                'best_game': {
                    'score': int(best_game.at[Columns.score]),
                    'date': 'tbd',
                    'event': event_label(best_game)
                },

                'worst_game': {
                    'score': int(worst_game.at[Columns.score]),
                    'date': 'tbd',
                    'event': event_label(worst_game)
                }
            })

            # Add competition-specific rows inside the selected season timeframe.
            if Columns.event in data.columns:
                comp_group_col = Columns.event
            elif Columns.event_name in data.columns:
                comp_group_col = Columns.event_name
            else:
                comp_group_col = Columns.league_name
            if comp_group_col in data.columns:
                group_cols = [comp_group_col]
                if Columns.team_name in data.columns:
                    group_cols.append(Columns.team_name)
                comp_groups = data.groupby(group_cols, dropna=False)
                for comp_key, cdf in comp_groups:
                    if isinstance(comp_key, tuple):
                        comp_name, _team_name = comp_key
                    else:
                        comp_name, _team_name = comp_key, ""
                    if pd.isna(comp_name):
                        continue
                    comp_games = len(cdf)
                    if comp_games == 0:
                        continue
                    comp_pins = sum_scores_float(cdf[Columns.score])
                    comp_avg = comp_pins / comp_games
                    comp_best = cdf[cdf[Columns.score] == cdf[Columns.score].max()].iloc[0]
                    comp_worst = cdf[cdf[Columns.score] == cdf[Columns.score].min()].iloc[0]
                    rank_value, competitors = (
                        tournament_final_rank(season, str(comp_name), player_name, pid)
                        if (
                            Columns.event_type in cdf.columns
                            and cdf[Columns.event_type].astype(str).str.lower().eq("tournament").any()
                        )
                        else league_average_rank(season, str(comp_name), player_name, pid)
                    )
                    season_stats.append({
                        'is_tournament': bool(
                            Columns.event_type in cdf.columns
                            and cdf[Columns.event_type].astype(str).str.lower().eq("tournament").any()
                        ),
                        'season': season,
                        'competition': str(comp_name).strip() or competition_name(cdf),
                        'club': row_club(cdf),
                        'team_name': row_team_name(cdf),
                        'team_number': (
                            int(m.group(1))
                            if (m := re.search(r"\s+(\d+)\s*$", row_team_name(cdf)))
                            else None
                        ),
                        'games': int(comp_games),
                        'total_pins': int(comp_pins),
                        'average': float(round(comp_avg, 2)),
                        'vs_last_season': None,
                        'rank': rank_value,
                        'competitors': competitors,
                        'row_type': 'competition',
                        'best_game': {
                            'score': int(comp_best.at[Columns.score]),
                            'date': 'tbd',
                            'event': event_label(comp_best)
                        },
                        'worst_game': {
                            'score': int(comp_worst.at[Columns.score]),
                            'date': 'tbd',
                            'event': event_label(comp_worst)
                        }
                    })

        collected_data = dict(seasons=season_stats)
        collected_data["periods"] = self._build_period_stats(
            games_df,
            competition_name=competition_name,
            row_team_name=row_team_name,
            row_club=row_club,
        )

        # calculate the lifetime stats
        
        # Calculate basic stats
        total_games = len(games_df)
        total_pins = sum_scores_float(games_df[Columns.score])
        avg_score = total_pins / total_games if total_games > 0 else 0
        
        # Find best and worst games
        best_game = games_df[games_df[Columns.score] == games_df[Columns.score].max()].iloc[0]
        worst_game = games_df[games_df[Columns.score] == games_df[Columns.score].min()].iloc[0]
        
        season_means = data_grouped[Columns.score].apply(mean_scores)

        # Find season with best mean
        best_season = season_means.idxmax()  # Gets the season name
        best_season_avg = season_means.max()  # Gets the actual average

        # For most improved, calculate differences between consecutive seasons
        season_improvements = season_means.diff()  # Calculates difference to previous season
        
        # Handle NaN values in improvements
        if season_improvements.empty or season_improvements.isna().all():
            most_improved_season = None
            most_improved_improvement = None
        else:
            # Filter out NaN values and find the maximum improvement
            valid_improvements = season_improvements.dropna()
            if valid_improvements.empty:
                most_improved_season = None
                most_improved_improvement = None
            else:
                most_improved_season = valid_improvements.idxmax()  # Gets the season name
                most_improved_improvement = valid_improvements.max()

        collected_data['lifetime'] = {
            'total_games': int(total_games),
            'total_pins': int(total_pins),
            'average_score': float(round(avg_score, 2)),

            'best_game': {
                'score': int(best_game.at[Columns.score]),
                'date': 'tbd',
                'event': f"{best_game.at[Columns.season]} {event_label(best_game)}"
            },
            'worst_game': {
                'score': int(worst_game.at[Columns.score]),
                'date': 'tbd',
                'event': f"{worst_game.at[Columns.season]} {event_label(worst_game)}"
            },
            'best_season': {
                'season': best_season,
                'average': float(round(best_season_avg, 2))    
            },
            'most_improved': {
                'season': most_improved_season,
                'improvement': float(round(most_improved_improvement, 2)) if most_improved_improvement is not None else None
            }
        }

        return collected_data
