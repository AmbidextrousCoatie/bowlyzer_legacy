import pandas as pd
import re
from data_access.schema import Columns
from app.services.data_manager import DataManager
from business_logic.statistics import calculate_score_average_player, calculate_games_count_player
from business_logic.server import Server
from app.services.statistics_service import StatisticsService
from app.models.statistics_models import PlayerStatistics
from typing import Dict, List, Any, Optional

OVERALL_CUMULATIVE_SCORE_COL = "Overall Cumulative Score"


def _csv_bool_is_true(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(("true", "1", "yes"))


def _csv_bool_is_false(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(("false", "0", "no", ""))


class PlayerService:
    def __init__(self, database: str = None):
        self.database = database
        self.data_manager = DataManager(source=database) if database else DataManager()
        self.server = Server(database=database)
        self.stats_service = StatisticsService(database=database)

    def get_all_players(self):
        """Get list of all players for selection"""
        df = self.data_manager.df
        if df is None or df.empty or Columns.player_name not in df.columns:
            return []
        sub = df
        if Columns.input_data in df.columns and Columns.computed_data in df.columns:
            sub = df[
                _csv_bool_is_true(df[Columns.input_data])
                & _csv_bool_is_false(df[Columns.computed_data])
            ]
        names = sub[Columns.player_name].dropna()
        cleaned: List[str] = []
        seen: set = set()
        for raw in names.unique():
            label = str(raw).strip()
            low = label.lower()
            if not label or low in ("nan", "none", "<na>", "nat", "#n/a"):
                continue
            if label == "Team Total":
                continue
            if label not in seen:
                seen.add(label)
                cleaned.append(label)
        return [{"id": n, "name": n} for n in sorted(cleaned)]

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
        team_avg = team_data[Columns.score].mean()
        team_total = team_data[Columns.score].sum()
        
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
                player for player in all_players
                if search_term in str(player.get("name", "")).lower()
            ]
            return filtered_players
        
        return all_players

    def get_player_seasons(self, player_name: str) -> List[str]:
        """Get sorted season list for a specific player."""
        if not player_name:
            return []
        games_df = self.server.get_games_for_player(player_name)
        if games_df is None or games_df.empty or Columns.season not in games_df.columns:
            return []
        seasons = [str(s).strip() for s in games_df[Columns.season].dropna().unique().tolist() if str(s).strip()]
        return sorted(seasons)

    def get_historical_data(self, player_id: str):
        """Get historical performance data"""
        pass

    def get_lifetime_stats(self, player_name, season: str = "all"):
        """Get lifetime statistics for a player."""

        
        # Get all games for the player
        games_df = self.server.get_games_for_player(player_name)
        if season and str(season).strip().lower() != "all":
            season_norm = str(season).strip()
            if Columns.season in games_df.columns:
                games_df = games_df[games_df[Columns.season].astype(str).str.strip().eq(season_norm)]
        
        if games_df.empty:
            return None
 
        overall_average = games_df[Columns.score].mean()

        def normalize_club(value: Any) -> str:
            label = str(value).strip() if value is not None else ""
            if not label:
                return "-"
            # Strip trailing team number, e.g. "Clubname 1" -> "Clubname"
            return re.sub(r"\s+\d+$", "", label)

        def competition_name(df: pd.DataFrame) -> str:
            if Columns.event_name in df.columns:
                vals = [str(x).strip() for x in df[Columns.event_name].dropna().tolist() if str(x).strip()]
                if vals:
                    return vals[0]
            if Columns.league_name in df.columns:
                vals = [str(x).strip() for x in df[Columns.league_name].dropna().tolist() if str(x).strip()]
                if vals:
                    return vals[0]
            return "Unknown Competition"

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
            if Columns.event_name in row and pd.notna(row.get(Columns.event_name)):
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

        def _safe_player_rows(df: pd.DataFrame) -> pd.DataFrame:
            out = df.copy()
            if Columns.input_data in out.columns:
                out = out[_csv_bool_is_true(out[Columns.input_data])]
            if Columns.computed_data in out.columns:
                out = out[_csv_bool_is_false(out[Columns.computed_data])]
            return out

        def league_average_rank(season_value: Any, league_value: str, player_value: str) -> Optional[int]:
            base = self.data_manager.df.copy()
            if base.empty:
                return None
            if Columns.season in base.columns:
                base = base[base[Columns.season].astype(str).str.strip().eq(str(season_value).strip())]
            if Columns.league_name in base.columns:
                base = base[base[Columns.league_name].astype(str).str.strip().eq(str(league_value).strip())]
            base = _safe_player_rows(base)
            if base.empty or Columns.player_name not in base.columns or Columns.score not in base.columns:
                return None
            grouped = (
                base.groupby(Columns.player_name, dropna=False)[Columns.score]
                .mean()
                .sort_values(ascending=False)
            )
            if player_value not in grouped.index:
                return None
            rank_series = grouped.rank(method="min", ascending=False)
            return int(rank_series[player_value])

        def tournament_final_rank(season_value: Any, event_value: str, player_value: str) -> Optional[int]:
            base = self.data_manager.df.copy()
            if base.empty:
                return None
            if Columns.season in base.columns:
                base = base[base[Columns.season].astype(str).str.strip().eq(str(season_value).strip())]
            if Columns.event_name in base.columns:
                base = base[base[Columns.event_name].astype(str).str.strip().eq(str(event_value).strip())]
            if Columns.event_type in base.columns:
                base = base[base[Columns.event_type].astype(str).str.strip().str.lower().eq("tournament")]
            if base.empty or Columns.player_name not in base.columns:
                return None

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
                    return None
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
                    return None
                work = base.copy()
                work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
                totals = (
                    work.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .sort_values(ascending=False)
                )

            if player_value not in totals.index:
                return None
            rank_series = totals.rank(method="min", ascending=False)
            return int(rank_series[player_value])

        # first handle the seasons stats
        data_grouped = games_df.groupby(Columns.season)
        season_stats = []
        last_seasons_average = None
        for i, (season, data) in enumerate(data_grouped):
            
            total_games = len(data)
            total_pins = data[Columns.score].sum()
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
                'club': row_club(data),
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
            comp_group_col = Columns.event_name if Columns.event_name in data.columns else Columns.league_name
            if comp_group_col in data.columns:
                comp_groups = data.groupby(comp_group_col)
                for comp_name, cdf in comp_groups:
                    if pd.isna(comp_name):
                        continue
                    comp_games = len(cdf)
                    if comp_games == 0:
                        continue
                    comp_pins = cdf[Columns.score].sum()
                    comp_avg = comp_pins / comp_games
                    comp_best = cdf[cdf[Columns.score] == cdf[Columns.score].max()].iloc[0]
                    comp_worst = cdf[cdf[Columns.score] == cdf[Columns.score].min()].iloc[0]
                    season_stats.append({
                        'is_tournament': bool(
                            Columns.event_type in cdf.columns
                            and cdf[Columns.event_type].astype(str).str.lower().eq("tournament").any()
                        ),
                        'season': season,
                        'competition': str(comp_name).strip() or competition_name(cdf),
                        'club': row_club(cdf),
                        'games': int(comp_games),
                        'total_pins': int(comp_pins),
                        'average': float(round(comp_avg, 2)),
                        'vs_last_season': None,
                        'rank': (
                            tournament_final_rank(season, str(comp_name), player_name)
                            if (Columns.event_type in cdf.columns and cdf[Columns.event_type].astype(str).str.lower().eq("tournament").any())
                            else league_average_rank(season, str(comp_name), player_name)
                        ),
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

        # calculate the lifetime stats
        
        # Calculate basic stats
        total_games = len(games_df)
        total_pins = games_df[Columns.score].sum()
        avg_score = total_pins / total_games if total_games > 0 else 0
        
        # Find best and worst games
        best_game = games_df[games_df[Columns.score] == games_df[Columns.score].max()].iloc[0]
        worst_game = games_df[games_df[Columns.score] == games_df[Columns.score].min()].iloc[0]
        
        season_means = data_grouped[Columns.score].mean()

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
