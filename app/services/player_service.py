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
from dataclasses import dataclass

OVERALL_CUMULATIVE_SCORE_COL = "Overall Cumulative Score"


@dataclass(frozen=True)
class _CompetitionRankTable:
    by_id: Dict[str, int]
    by_name: Dict[str, int]
    competitors: int


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
    def _player_name_from_chunk(chunk: pd.DataFrame) -> str:
        if chunk is None or chunk.empty or Columns.player_name not in chunk.columns:
            return ""
        vals = [str(x).strip() for x in chunk[Columns.player_name].dropna().tolist() if str(x).strip()]
        return vals[0] if vals else ""

    def _player_id_from_chunk(self, chunk: pd.DataFrame) -> str:
        if chunk is None or chunk.empty or Columns.player_id not in chunk.columns:
            return ""
        vals = [
            self._normalize_player_id(x)
            for x in chunk[Columns.player_id].dropna().tolist()
            if self._normalize_player_id(x)
        ]
        return vals[0] if vals else ""

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
        registry_lookup: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> str:
        """
        Pick one stable display name per player id.
        Heuristic for two-token reversals (A B vs B A):
        prefer orientation that matches global first/last token tendencies.
        """
        cleaned = [str(n).strip() for n in names if str(n).strip()]
        if not cleaned:
            return ""
        if registry_lookup is not None:
            entry = registry_lookup.get(self._normalize_player_id(player_id))
            registry_name = entry["canonical_name"] if entry else ""
        else:
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
        per_player: bool = False,
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
                    **(
                        {
                            "player_name": self._player_name_from_chunk(chunk),
                            "player_id": self._player_id_from_chunk(chunk),
                        }
                        if per_player
                        else {}
                    ),
                }
            )

        player_group_cols: List[str] = []
        if per_player:
            if Columns.player_id in work.columns:
                player_group_cols.append(Columns.player_id)
            if Columns.player_name in work.columns:
                player_group_cols.append(Columns.player_name)

        league_work = work.loc[~is_tournament]
        if not league_work.empty and Columns.week in league_work.columns:
            league_work = league_work.copy()
            league_work["_week"] = pd.to_numeric(league_work[Columns.week], errors="coerce")
            league_work = league_work.dropna(subset=["_week"])
            if not league_work.empty:
                comp_col = competition_event_column(league_work) or Columns.league_name
                if comp_col in league_work.columns:
                    group_cols = [*player_group_cols, Columns.season, comp_col, "_week"]
                    for keys, chunk in league_work.groupby(group_cols, dropna=False):
                        key_tuple = keys if isinstance(keys, tuple) else (keys,)
                        offset = len(player_group_cols)
                        season_key = key_tuple[offset]
                        comp_key = key_tuple[offset + 1]
                        week_key = key_tuple[offset + 2]
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
                group_cols = [*player_group_cols, Columns.season, comp_col, "_round"]
                if Columns.round_name in tourn_work.columns:
                    group_cols.append(Columns.round_name)
                for keys, chunk in tourn_work.groupby(group_cols, dropna=False):
                    key_tuple = keys if isinstance(keys, tuple) else (keys,)
                    offset = len(player_group_cols)
                    season_key = key_tuple[offset]
                    comp_key = key_tuple[offset + 1]
                    round_key = key_tuple[offset + 2]
                    round_name = ""
                    if Columns.round_name in tourn_work.columns and len(key_tuple) > offset + 3:
                        round_name = str(key_tuple[offset + 3]).strip()
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

    def _league_competition_rank_table(self, season_value: Any, league_value: str) -> _CompetitionRankTable:
        base = self._subset_ranking_frame(season_value, league_value=league_value)
        if base.empty or Columns.player_name not in base.columns or Columns.score not in base.columns:
            return _CompetitionRankTable({}, {}, 0)
        work = base.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce")
        work = work.dropna(subset=[Columns.score])
        if work.empty:
            return _CompetitionRankTable({}, {}, 0)

        by_id: Dict[str, int] = {}
        competitors = 0
        if Columns.player_id in work.columns:
            work[Columns.player_id] = work[Columns.player_id].astype(str).map(self._normalize_player_id)
            grouped = (
                work.groupby(Columns.player_id, dropna=False)[Columns.score]
                .apply(mean_scores)
                .sort_values(ascending=False)
            )
            competitors = int(len(grouped))
            rank_series = grouped.rank(method="min", ascending=False)
            by_id = {str(k): int(v) for k, v in rank_series.items() if str(k).strip()}

        grouped_name = (
            work.groupby(Columns.player_name, dropna=False)[Columns.score]
            .apply(mean_scores)
            .sort_values(ascending=False)
        )
        if not competitors:
            competitors = int(len(grouped_name))
        rank_name = grouped_name.rank(method="min", ascending=False)
        by_name = {str(k): int(v) for k, v in rank_name.items() if str(k).strip()}
        return _CompetitionRankTable(by_id, by_name, competitors)

    def _tournament_competition_rank_table(self, season_value: Any, event_value: str) -> _CompetitionRankTable:
        base = self._subset_ranking_frame(
            season_value,
            event_value=event_value,
            tournament_only=True,
        )
        if base.empty or Columns.player_name not in base.columns:
            return _CompetitionRankTable({}, {}, 0)

        totals = None
        totals_by_id: Optional[pd.Series] = None
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
            if not work.empty:
                sort_cols = [Columns.player_name, Columns.round_number, Columns.game_number]
                work = work.sort_values(by=sort_cols, ascending=[True, True, True])
                latest = work.groupby(Columns.player_name, dropna=False).tail(1)
                totals = (
                    latest.groupby(Columns.player_name, dropna=False)[OVERALL_CUMULATIVE_SCORE_COL]
                    .max()
                    .sort_values(ascending=False)
                )
                if Columns.player_id in base.columns:
                    work_id = base.copy()
                    work_id[Columns.player_id] = work_id[Columns.player_id].astype(str).map(self._normalize_player_id)
                    work_id[Columns.round_number] = pd.to_numeric(work_id[Columns.round_number], errors="coerce")
                    work_id[Columns.game_number] = pd.to_numeric(work_id[Columns.game_number], errors="coerce")
                    work_id[OVERALL_CUMULATIVE_SCORE_COL] = pd.to_numeric(
                        work_id[OVERALL_CUMULATIVE_SCORE_COL], errors="coerce"
                    )
                    work_id = work_id.dropna(subset=[OVERALL_CUMULATIVE_SCORE_COL])
                    work_id = work_id.sort_values(
                        by=[Columns.player_id, Columns.round_number, Columns.game_number],
                        ascending=[True, True, True],
                    )
                    latest_id = work_id.groupby(Columns.player_id, dropna=False).tail(1)
                    totals_by_id = (
                        latest_id.groupby(Columns.player_id, dropna=False)[OVERALL_CUMULATIVE_SCORE_COL]
                        .max()
                        .sort_values(ascending=False)
                    )
        elif Columns.score in base.columns:
            work = base.copy()
            work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
            totals = (
                work.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
            )
            if Columns.player_id in base.columns:
                work_id = base.copy()
                work_id[Columns.player_id] = work_id[Columns.player_id].astype(str).map(self._normalize_player_id)
                work_id[Columns.score] = pd.to_numeric(work_id[Columns.score], errors="coerce").fillna(0)
                totals_by_id = (
                    work_id.groupby(Columns.player_id, dropna=False)[Columns.score]
                    .apply(sum_scores)
                    .sort_values(ascending=False)
                )

        if totals is None and totals_by_id is None:
            return _CompetitionRankTable({}, {}, 0)

        by_name: Dict[str, int] = {}
        competitors = 0
        if totals is not None:
            competitors = int(len(totals))
            rank_name = totals.rank(method="min", ascending=False)
            by_name = {str(k): int(v) for k, v in rank_name.items() if str(k).strip()}

        by_id: Dict[str, int] = {}
        if totals_by_id is not None:
            if not competitors:
                competitors = int(len(totals_by_id))
            rank_id = totals_by_id.rank(method="min", ascending=False)
            by_id = {str(k): int(v) for k, v in rank_id.items() if str(k).strip()}

        return _CompetitionRankTable(by_id, by_name, competitors)

    @staticmethod
    def _lookup_competition_rank(
        table: _CompetitionRankTable,
        player_value: str,
        player_id_value: str,
        *,
        normalize_player_id: Any,
    ) -> Tuple[Optional[int], int]:
        pid_norm = normalize_player_id(player_id_value)
        if pid_norm and pid_norm in table.by_id:
            return table.by_id[pid_norm], table.competitors
        if player_value and player_value in table.by_name:
            return table.by_name[player_value], table.competitors
        return None, table.competitors

    @staticmethod
    def _is_tournament_chunk(cdf: pd.DataFrame) -> bool:
        return bool(
            Columns.event_type in cdf.columns
            and cdf[Columns.event_type].astype(str).str.lower().eq("tournament").any()
        )

    def _build_competition_rank_cache(
        self,
        games_df: pd.DataFrame,
        *,
        comp_group_col: str,
    ) -> Dict[Tuple[Any, str, bool], _CompetitionRankTable]:
        keys: set[Tuple[Any, str, bool]] = set()
        if comp_group_col not in games_df.columns:
            return {}
        for season_value, season_data in games_df.groupby(Columns.season, dropna=False):
            group_cols = [comp_group_col]
            if Columns.team_name in season_data.columns:
                group_cols.append(Columns.team_name)
            for comp_key, cdf in season_data.groupby(group_cols, dropna=False):
                comp_name = comp_key[0] if isinstance(comp_key, tuple) else comp_key
                if pd.isna(comp_name):
                    continue
                keys.add((season_value, str(comp_name).strip(), self._is_tournament_chunk(cdf)))

        cache: Dict[Tuple[Any, str, bool], _CompetitionRankTable] = {}
        for season_value, comp_name, is_tournament in keys:
            key = (season_value, comp_name, is_tournament)
            if is_tournament:
                cache[key] = self._tournament_competition_rank_table(season_value, comp_name)
            else:
                cache[key] = self._league_competition_rank_table(season_value, comp_name)
        return cache

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
            return self.get_all_seasons()
        games_df = self._subset_player_games(player_name, player_id)
        if games_df.empty or Columns.season not in games_df.columns:
            return []
        seasons = [str(s).strip() for s in games_df[Columns.season].dropna().unique().tolist() if str(s).strip()]
        return sorted(seasons)

    def get_all_seasons(self) -> List[str]:
        """Sorted season list across all players in the current database."""
        base = self.data_manager.df
        if base is None or base.empty or Columns.season not in base.columns:
            return []
        seasons = [
            str(s).strip()
            for s in base[Columns.season].dropna().unique().tolist()
            if str(s).strip()
        ]
        return sorted(seasons)

    def _subset_all_player_games(self, season: str | None = None) -> pd.DataFrame:
        """All player game rows (optional season filter), without copying unrelated tables."""
        base = self.data_manager.df
        if base is None or base.empty:
            return pd.DataFrame()

        games_df = self._safe_player_rows(base)
        if season and str(season).strip().lower() != "all":
            season_norm = str(season).strip()
            if Columns.season in games_df.columns:
                games_df = games_df.loc[games_df[Columns.season].astype(str).str.strip().eq(season_norm)]

        if Columns.score in games_df.columns:
            games_df = games_df.copy()
            games_df[Columns.score] = pd.to_numeric(games_df[Columns.score], errors="coerce")
            games_df = games_df.dropna(subset=[Columns.score])
        return games_df

    @staticmethod
    def _game_row_competition(row: pd.Series) -> str:
        from data_access.competition_schema import competition_event_column

        if Columns.event in row.index and pd.notna(row.get(Columns.event)):
            label = str(row.get(Columns.event)).strip()
            if label:
                return label
        if Columns.event_name in row.index and pd.notna(row.get(Columns.event_name)):
            label = str(row.get(Columns.event_name)).strip()
            if label:
                return label
        if Columns.league_name in row.index and pd.notna(row.get(Columns.league_name)):
            return str(row.get(Columns.league_name)).strip()
        return ""

    @staticmethod
    def _game_row_is_tournament(row: pd.Series) -> bool:
        if Columns.event_type not in row.index:
            return False
        return str(row.get(Columns.event_type) or "").strip().lower() == "tournament"

    @staticmethod
    def _game_row_date_label(row: pd.Series) -> str:
        if Columns.date not in row.index or pd.isna(row.get(Columns.date)):
            return ""
        return str(row.get(Columns.date)).strip()

    @staticmethod
    def _game_row_date_sort_value(row: pd.Series) -> float:
        if Columns.date not in row.index:
            return float("-inf")
        raw = row.get(Columns.date)
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return float("-inf")
        text = str(raw).strip()
        if not text:
            return float("-inf")
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            parsed = pd.to_datetime(text, errors="coerce")
        else:
            parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return float("-inf")
        return float(parsed.value)

    def _individual_game_record(self, row: pd.Series) -> Dict[str, Any]:
        from app.utils.json_safe import to_json_int

        team_name = ""
        if Columns.team_name in row.index and pd.notna(row.get(Columns.team_name)):
            team_name = str(row.get(Columns.team_name)).strip()
        team_number = None
        if team_name:
            match = re.search(r"\s+(\d+)\s*$", team_name)
            if match:
                team_number = int(match.group(1))
        club = ""
        if Columns.club in row.index and pd.notna(row.get(Columns.club)):
            club = str(row.get(Columns.club)).strip()
        elif team_name:
            club = re.sub(r"\s+\d+$", "", team_name).strip()

        week = None
        if Columns.week in row.index and pd.notna(row.get(Columns.week)):
            week = to_json_int(pd.to_numeric(row.get(Columns.week), errors="coerce"))
        round_number = None
        if Columns.round_number in row.index and pd.notna(row.get(Columns.round_number)):
            round_number = to_json_int(pd.to_numeric(row.get(Columns.round_number), errors="coerce"))

        player_name = ""
        if Columns.player_name in row.index and pd.notna(row.get(Columns.player_name)):
            player_name = str(row.get(Columns.player_name)).strip()
        player_id = ""
        if Columns.player_id in row.index and pd.notna(row.get(Columns.player_id)):
            player_id = self._normalize_player_id(row.get(Columns.player_id))

        score_val = pd.to_numeric(row.get(Columns.score), errors="coerce")
        score = int(score_val) if pd.notna(score_val) else None
        season = str(row.get(Columns.season)).strip() if Columns.season in row.index else ""

        return {
            "player_name": player_name,
            "player_id": player_id,
            "score": score,
            "date": self._game_row_date_label(row) or None,
            "season": season or None,
            "competition": self._game_row_competition(row) or None,
            "is_tournament": self._game_row_is_tournament(row),
            "club": club or None,
            "team_name": team_name or None,
            "team_number": team_number,
            "week": week,
            "round_number": round_number,
        }

    def get_highest_individual_games(
        self,
        limit: int = 10,
        player_name: str = "",
        player_id: str = "",
        season: str = "all",
    ) -> List[Dict[str, Any]]:
        """Top single-game scores (all players or one player, optional season)."""
        if player_name or player_id:
            games_df = self._subset_player_games(player_name, player_id, season=season)
        else:
            season_filter = season if str(season).strip().lower() != "all" else None
            games_df = self._subset_all_player_games(season=season_filter)
        if games_df.empty:
            return []
        work = games_df.copy()
        work["_date_sort"] = work.apply(self._game_row_date_sort_value, axis=1)
        work = work.sort_values(
            by=[Columns.score, "_date_sort"],
            ascending=[False, False],
            kind="mergesort",
        )
        out: List[Dict[str, Any]] = []
        for _, row in work.head(max(1, int(limit))).iterrows():
            out.append(self._individual_game_record(row))
        return out

    def get_club_300_games(self) -> List[Dict[str, Any]]:
        """All perfect 300 games, newest first."""
        games_df = self._subset_all_player_games()
        if games_df.empty:
            return []
        perfect = games_df[games_df[Columns.score] == 300].copy()
        if perfect.empty:
            return []
        perfect["_date_sort"] = perfect.apply(self._game_row_date_sort_value, axis=1)
        perfect = perfect.sort_values(by=["_date_sort"], ascending=[False], kind="mergesort")
        return [self._individual_game_record(row) for _, row in perfect.iterrows()]

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

    @staticmethod
    def merge_aggregate_lifetime_payloads(parts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Merge per-season aggregate payloads into one career-wide ``scope=all`` response."""
        clean = [p for p in parts if p]
        if not clean:
            return None
        if len(clean) == 1:
            return clean[0]

        merged: Dict[str, Any] = {
            "scope": "all",
            "seasons": [],
            "player_competitions": [],
            "player_season_totals": [],
            "periods": [],
        }
        part_lifetimes: List[Dict[str, Any]] = []
        for part in clean:
            merged["seasons"].extend(part.get("seasons") or [])
            merged["player_competitions"].extend(part.get("player_competitions") or [])
            merged["player_season_totals"].extend(part.get("player_season_totals") or [])
            merged["periods"].extend(part.get("periods") or [])
            lifetime = part.get("lifetime")
            if isinstance(lifetime, dict):
                part_lifetimes.append(lifetime)

        merged["lifetime"] = PlayerService._lifetime_summary_from_merged_aggregate(
            merged["player_season_totals"],
            part_lifetimes,
        )
        return merged

    @staticmethod
    def _lifetime_summary_from_merged_aggregate(
        player_season_totals: List[Dict[str, Any]],
        part_lifetimes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        total_games = sum(int(r.get("games") or 0) for r in player_season_totals)
        total_pins = sum(int(r.get("total_pins") or 0) for r in player_season_totals)
        avg_score = total_pins / total_games if total_games > 0 else 0.0

        best_game = None
        worst_game = None
        for lifetime in part_lifetimes:
            bg = lifetime.get("best_game") if isinstance(lifetime, dict) else None
            wg = lifetime.get("worst_game") if isinstance(lifetime, dict) else None
            if isinstance(bg, dict) and bg.get("score") is not None:
                if best_game is None or int(bg["score"]) > int(best_game["score"]):
                    best_game = bg
            if isinstance(wg, dict) and wg.get("score") is not None:
                if worst_game is None or int(wg["score"]) < int(worst_game["score"]):
                    worst_game = wg

        best_season_row = max(
            player_season_totals,
            key=lambda r: float(r.get("average") or 0),
            default=None,
        )
        best_season = best_season_row.get("season") if best_season_row else None
        best_season_avg = best_season_row.get("average") if best_season_row else None
        best_season_player = best_season_row.get("player_name") if best_season_row else None

        most_improved_player = None
        most_improved_season = None
        most_improved_improvement = None
        best_delta = None
        by_player: Dict[str, List[Dict[str, Any]]] = {}
        for row in player_season_totals:
            player_key = str(row.get("player_id") or row.get("player_name") or "").strip()
            if not player_key:
                continue
            by_player.setdefault(player_key, []).append(row)

        for rows in by_player.values():
            ordered = sorted(rows, key=lambda r: str(r.get("season") or ""))
            last_avg = None
            for row in ordered:
                avg = row.get("average")
                if avg is None:
                    continue
                if last_avg is not None:
                    delta = float(avg) - float(last_avg)
                    if best_delta is None or delta > best_delta:
                        best_delta = delta
                        most_improved_season = row.get("season")
                        most_improved_improvement = delta
                        most_improved_player = row.get("player_name")
                last_avg = float(avg)

        return {
            "total_games": int(total_games),
            "total_pins": int(total_pins),
            "average_score": float(round(avg_score, 2)),
            "best_game": best_game or {"score": None, "date": "tbd", "event": "Event"},
            "worst_game": worst_game or {"score": None, "date": "tbd", "event": "Event"},
            "best_season": {
                "season": best_season,
                "average": float(round(float(best_season_avg), 2)) if best_season_avg is not None else None,
                "player_name": best_season_player,
            },
            "most_improved": {
                "season": most_improved_season,
                "improvement": float(round(float(most_improved_improvement), 2))
                if most_improved_improvement is not None
                else None,
                "player_name": most_improved_player,
            },
        }

    def get_aggregate_lifetime_stats(self, season: str = "all"):
        """Lifetime stats across all players (``all`` merges per-season payloads)."""
        season_norm = str(season).strip() if season is not None else "all"
        if str(season_norm).lower() == "all":
            parts = []
            for season_value in self.get_all_seasons():
                part = self._aggregate_lifetime_stats_for_season(season_value)
                if part:
                    parts.append(part)
            return self.merge_aggregate_lifetime_payloads(parts)
        return self._aggregate_lifetime_stats_for_season(season_norm)

    def _aggregate_lifetime_stats_for_season(self, season: str) -> Optional[Dict[str, Any]]:
        games_df = self._subset_all_player_games(season=season)
        if games_df.empty:
            return None
        return self._build_aggregate_lifetime_stats_from_games(games_df)

    def _build_aggregate_lifetime_stats_from_games(self, games_df: pd.DataFrame) -> Dict[str, Any]:
        """Aggregate all-player stats for the rows in *games_df* (one season or scoped slice)."""

        def normalize_club(value: Any) -> str:
            label = str(value).strip() if value is not None else ""
            if not label:
                return "-"
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

        def comp_group_col(df: pd.DataFrame) -> str:
            from data_access.competition_schema import competition_event_column

            if Columns.event in df.columns:
                return Columns.event
            if Columns.event_name in df.columns:
                return Columns.event_name
            return Columns.league_name

        comp_col = comp_group_col(games_df)

        registry_lookup: Dict[str, Dict[str, str]] = {}
        try:
            from data_access.players_registry import load_players_registry_df, registry_lookup_by_id

            registry_df = load_players_registry_df()
            if registry_df is not None and not registry_df.empty:
                registry_lookup = registry_lookup_by_id(registry_df)
        except Exception:
            registry_lookup = {}

        def append_competition_row(
            *,
            target: List[Dict[str, Any]],
            season_value: Any,
            cdf: pd.DataFrame,
            comp_name: str,
            player_value: str,
            player_id_value: str,
            include_player: bool,
        ) -> None:
            comp_games = len(cdf)
            if comp_games == 0:
                return
            comp_pins = sum_scores_float(cdf[Columns.score])
            comp_avg = comp_pins / comp_games
            comp_best = cdf[cdf[Columns.score] == cdf[Columns.score].max()].iloc[0]
            comp_worst = cdf[cdf[Columns.score] == cdf[Columns.score].min()].iloc[0]
            is_tournament = self._is_tournament_chunk(cdf)
            rank_value, competitors = None, None
            row = {
                "is_tournament": is_tournament,
                "season": season_value,
                "competition": str(comp_name).strip() or competition_name(cdf),
                "club": row_club(cdf),
                "team_name": row_team_name(cdf),
                "team_number": (
                    int(m.group(1))
                    if (m := re.search(r"\s+(\d+)\s*$", row_team_name(cdf)))
                    else None
                ),
                "games": int(comp_games),
                "total_pins": int(comp_pins),
                "average": float(round(comp_avg, 2)),
                "vs_last_season": None,
                "rank": rank_value,
                "competitors": competitors,
                "row_type": "competition",
                "best_game": {
                    "score": int(comp_best.at[Columns.score]),
                    "date": "tbd",
                    "event": event_label(comp_best),
                },
                "worst_game": {
                    "score": int(comp_worst.at[Columns.score]),
                    "date": "tbd",
                    "event": event_label(comp_worst),
                },
            }
            if include_player:
                row["player_name"] = player_value
                row["player_id"] = player_id_value
            target.append(row)

        season_stats: List[Dict[str, Any]] = []
        player_competitions: List[Dict[str, Any]] = []
        player_season_totals: List[Dict[str, Any]] = []
        token_stats = self._build_name_token_stats(games_df)

        player_group_col = Columns.player_id if Columns.player_id in games_df.columns else Columns.player_name

        for season_value, season_data in games_df.groupby(Columns.season, dropna=False):
            total_games = len(season_data)
            total_pins = sum_scores_float(season_data[Columns.score])
            average = total_pins / total_games if total_games else 0.0
            best_game = season_data[season_data[Columns.score] == season_data[Columns.score].max()].iloc[0]
            worst_game = season_data[season_data[Columns.score] == season_data[Columns.score].min()].iloc[0]
            season_stats.append(
                {
                    "season": season_value,
                    "competition": "All Events",
                    "club": "",
                    "games": int(total_games),
                    "total_pins": int(total_pins),
                    "average": float(round(average, 2)),
                    "vs_last_season": None,
                    "rank": None,
                    "is_tournament": False,
                    "row_type": "season_total",
                    "best_game": {
                        "score": int(best_game.at[Columns.score]),
                        "date": "tbd",
                        "event": event_label(best_game),
                    },
                    "worst_game": {
                        "score": int(worst_game.at[Columns.score]),
                        "date": "tbd",
                        "event": event_label(worst_game),
                    },
                }
            )

            comp_col = comp_group_col(season_data)
            if comp_col in season_data.columns:
                group_cols = [comp_col]
                if Columns.team_name in season_data.columns:
                    group_cols.append(Columns.team_name)
                for comp_key, cdf in season_data.groupby(group_cols, dropna=False):
                    comp_name = comp_key[0] if isinstance(comp_key, tuple) else comp_key
                    if pd.isna(comp_name):
                        continue
                    append_competition_row(
                        target=season_stats,
                        season_value=season_value,
                        cdf=cdf,
                        comp_name=str(comp_name),
                        player_value="",
                        player_id_value="",
                        include_player=False,
                    )

            for player_key, pdata in season_data.groupby(player_group_col, dropna=False):
                if Columns.player_id in games_df.columns:
                    pid = self._normalize_player_id(player_key)
                    names = pdata[Columns.player_name].dropna().astype(str).tolist()
                    pname = self._canonical_name_for_player_id(
                        pid, names, token_stats=token_stats, registry_lookup=registry_lookup
                    ) or (
                        names[0] if names else ""
                    )
                else:
                    pname = str(player_key).strip()
                    pid = ""

                p_games = len(pdata)
                p_pins = sum_scores_float(pdata[Columns.score])
                p_avg = p_pins / p_games if p_games else 0.0
                player_season_totals.append(
                    {
                        "season": season_value,
                        "competition": "All Events",
                        "club": row_club(pdata),
                        "games": int(p_games),
                        "total_pins": int(p_pins),
                        "average": float(round(p_avg, 2)),
                        "vs_last_season": None,
                        "rank": None,
                        "is_tournament": False,
                        "row_type": "season_total",
                        "player_name": pname,
                        "player_id": pid,
                    }
                )

                if comp_col in pdata.columns:
                    p_group_cols = [comp_col]
                    if Columns.team_name in pdata.columns:
                        p_group_cols.append(Columns.team_name)
                    for comp_key, cdf in pdata.groupby(p_group_cols, dropna=False):
                        comp_name = comp_key[0] if isinstance(comp_key, tuple) else comp_key
                        if pd.isna(comp_name):
                            continue
                        append_competition_row(
                            target=player_competitions,
                            season_value=season_value,
                            cdf=cdf,
                            comp_name=str(comp_name),
                            player_value=pname,
                            player_id_value=pid,
                            include_player=True,
                        )

        periods = self._build_period_stats(
            games_df,
            competition_name=competition_name,
            row_team_name=row_team_name,
            row_club=row_club,
            per_player=True,
        )

        total_games = len(games_df)
        total_pins = sum_scores_float(games_df[Columns.score])
        avg_score = total_pins / total_games if total_games > 0 else 0
        best_game = games_df[games_df[Columns.score] == games_df[Columns.score].max()].iloc[0]
        worst_game = games_df[games_df[Columns.score] == games_df[Columns.score].min()].iloc[0]

        best_season_row = max(player_season_totals, key=lambda r: r.get("average") or 0, default=None)
        best_season = best_season_row.get("season") if best_season_row else None
        best_season_avg = best_season_row.get("average") if best_season_row else None
        best_season_player = best_season_row.get("player_name") if best_season_row else None

        most_improved_player = None
        most_improved_season = None
        most_improved_improvement = None
        if Columns.season in games_df.columns:
            best_delta = None
            for _player_key, pdata in games_df.groupby(player_group_col, dropna=False):
                if Columns.player_id in games_df.columns:
                    pid = self._normalize_player_id(_player_key)
                    names = pdata[Columns.player_name].dropna().astype(str).tolist()
                    pname = self._canonical_name_for_player_id(
                        pid, names, token_stats=token_stats, registry_lookup=registry_lookup
                    ) or (
                        names[0] if names else ""
                    )
                else:
                    pname = str(_player_key).strip()
                season_means = pdata.groupby(Columns.season)[Columns.score].apply(mean_scores)
                improvements = season_means.diff().dropna()
                if improvements.empty:
                    continue
                delta = float(improvements.max())
                if best_delta is None or delta > best_delta:
                    best_delta = delta
                    most_improved_season = improvements.idxmax()
                    most_improved_improvement = delta
                    most_improved_player = pname

        best_game_player = self._player_name_from_chunk(best_game.to_frame().T)
        worst_game_player = self._player_name_from_chunk(worst_game.to_frame().T)

        return {
            "scope": "all",
            "seasons": season_stats,
            "player_competitions": player_competitions,
            "player_season_totals": player_season_totals,
            "periods": periods,
            "lifetime": {
                "total_games": int(total_games),
                "total_pins": int(total_pins),
                "average_score": float(round(avg_score, 2)),
                "best_game": {
                    "score": int(best_game.at[Columns.score]),
                    "date": "tbd",
                    "event": f"{best_game_player} · {best_game.at[Columns.season]} {event_label(best_game)}".strip(" ·"),
                },
                "worst_game": {
                    "score": int(worst_game.at[Columns.score]),
                    "date": "tbd",
                    "event": f"{worst_game_player} · {worst_game.at[Columns.season]} {event_label(worst_game)}".strip(" ·"),
                },
                "best_season": {
                    "season": best_season,
                    "average": float(round(best_season_avg, 2)) if best_season_avg is not None else None,
                    "player_name": best_season_player,
                },
                "most_improved": {
                    "season": most_improved_season,
                    "improvement": float(round(most_improved_improvement, 2))
                    if most_improved_improvement is not None
                    else None,
                    "player_name": most_improved_player,
                },
            },
        }
