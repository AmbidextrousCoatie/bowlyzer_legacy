from data_access.adapters.data_adapter import DataAdapter
from data_access.schema import Columns, ColumnsExtra
import pandas as pd
import pathlib
import operator
from typing import List, Dict, Any, Optional, Tuple, Callable, Union

from data_access.models.league_models import LeagueQuery
from data_access.models.league_models import TeamSeasonPerformance, TeamWeeklyPerformance
from data_access.models.raw_data_models import RawPlayerData, RawTeamData, RawLeagueData
from data_access.dtype_normalization import normalize_legacy_dataframe_types
from data_access.score_utils import league_points_cell
from data_access.text_norm import normalize_unicode_label



# Define comparison operators
OPERATORS = {
    "eq": operator.eq,  # Equal
    "ne": operator.ne,  # Not equal
    "lt": operator.lt,  # Less than
    "le": operator.le,  # Less than or equal
    "gt": operator.gt,  # Greater than
    "ge": operator.ge,  # Greater than or equal
    "in": lambda x, y: x in y,  # In list
    "not_in": lambda x, y: x not in y,  # Not in list
    "contains": lambda x, y: y in x if isinstance(x, str) else False,  # String contains
    "startswith": lambda x, y: x.startswith(y) if isinstance(x, str) else False,  # String starts with
    "endswith": lambda x, y: x.endswith(y) if isinstance(x, str) else False,  # String ends with
}

BOOL_TRUE_TOKENS = {"true", "1", "yes", "y", "on"}
BOOL_FALSE_TOKENS = {"false", "0", "no", "n", "off", ""}


def _safe_int_cell(value: Any, default: int = 0) -> int:
    """Coerce CSV/DataFrame cells to int; ``pd.NA`` / NaN / invalid -> ``default``."""
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num):
        return default
    try:
        return int(num)
    except (ValueError, TypeError, OverflowError):
        return default


def _safe_float_cell(value: Any, default: float = 0.0) -> float:
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num):
        return default
    try:
        return float(num)
    except (ValueError, TypeError, OverflowError):
        return default


def _row_ok_for_raw_player(row: pd.Series) -> bool:
    """Skip rows that cannot be keyed by week (common with bad imports / merged cells)."""
    if pd.isna(row.get(Columns.week)):
        return False
    if pd.isna(row.get(Columns.score)):
        return False
    return True


def _unique_clean_str_labels(series: pd.Series) -> List[str]:
    """Sorted unique non-empty labels; never returns float NaN (safe for ``jsonify``)."""
    out: List[str] = []
    for x in series.dropna().unique().tolist():
        s = normalize_unicode_label(str(x))
        if not s or s.lower() in ("nan", "none", "<na>", "nat"):
            continue
        out.append(s)
    return sorted(set(out))


class DataAdapterPandas(DataAdapter):
    def __init__(self, path_to_csv_data: pathlib.Path=None, df: pd.DataFrame=None, database: str=None):
        self.data_path = path_to_csv_data
        self.df = None
        self.database = database
        
        if path_to_csv_data is not None and path_to_csv_data.exists():
            self._load_data()
        elif df is not None:
            work = df.copy()
            if work.columns.duplicated().any():
                work = work.loc[:, ~work.columns.duplicated()].copy()
            self.df = normalize_legacy_dataframe_types(work)
            self._normalize_week_column()
        elif database is not None:
            # Load from database parameter
            self._load_data_from_database()
        else:
            print(type(path_to_csv_data))
            print(type(df))
            print(type(database))
            raise ValueError("Either path_to_csv_data, df, or database must be provided")
    
    def _load_data_from_database(self):
        """Load data from database parameter"""
        if self.database is None:
            raise ValueError("Database parameter is required")
        
        # Get the full path from database_config
        try:
            from app.config.database_config import database_config, DATABASE_DATA_DIR
            config = database_config.get_source_config(self.database)
            if config and config.file_path:
                database_path = pathlib.Path(config.file_path)
            else:
                # Fallback: construct path from filename
                filename = database_config.get_filename_for_source(self.database)
                database_path = pathlib.Path(DATABASE_DATA_DIR) / filename
        except ImportError:
            # Fallback if config not available
            database_path = pathlib.Path("database", "data", self.database).absolute()
        
        if not database_path.exists():
            raise ValueError(f"Database file not found: {database_path}")
        
        self.data_path = database_path
        self._load_data()

    def _normalize_week_column(self) -> None:
        """Coerce Week to nullable integers so filters and UI week tokens match (1 not 1.0)."""
        if self.df is None or Columns.week not in self.df.columns:
            return
        w = pd.to_numeric(self.df[Columns.week], errors="coerce")
        self.df[Columns.week] = w.round(0).astype("Int64")

    def _load_data(self):
        """Load data from CSV file"""

        self.df = pd.read_csv(self.data_path, sep=";", dtype=str, low_memory=False)
        if self.df.columns.duplicated().any():
            self.df = self.df.loc[:, ~self.df.columns.duplicated()].copy()
        self.df = normalize_legacy_dataframe_types(self.df)
        self._normalize_week_column()

    @staticmethod
    def _bool_mask(series: pd.Series, value: bool) -> pd.Series:
        normalized = series.fillna("").astype(str).str.strip().str.lower()
        return normalized.isin(BOOL_TRUE_TOKENS if value else BOOL_FALSE_TOKENS)

    def set_dataframe(self, df):
        """Set the dataframe directly (for testing or in-memory operations)"""
        self.df = df
        self._normalize_week_column()

    def get_filtered_data(self, 
                          filters: Optional[Dict[str, Dict[str, Any]]] = None, 
                          columns: Optional[List[str]] = None,
                          sort_by: Optional[Union[str, List[str]]] = None,
                          ascending: bool = True,
                          limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get filtered data from the dataframe with enhanced filtering capabilities.
        
        Args:
            filters: Dictionary of column names to filter dictionaries
                   Each filter dictionary should have:
                   - 'value': The value to filter by
                   - 'operator': The operator to use (must be one of OPERATORS keys)
            columns: List of columns to include in the result
            sort_by: Column(s) to sort by
            ascending: Sort direction (True for ascending, False for descending)
            limit: Maximum number of rows to return
            
        Returns:
            Filtered pandas DataFrame
        """
        if self.df is None:
            return pd.DataFrame()
        
        # Start with the full dataframe
        result = self.df
        
        # Apply filters
        if filters:
            for column, filter_dict in filters.items():
                if column in result.columns:
                    value = filter_dict.get('value')
                    operator_name = filter_dict.get('operator')
                    
                    if value is not None and operator_name in OPERATORS:
                        op_func = OPERATORS[operator_name]
                        
                        # Apply the filter using a vectorized operation if possible
                        if operator_name in ["in", "not_in"]:
                            if operator_name == "in":
                                result = result[result[column].isin(value)]
                            else:
                                result = result[~result[column].isin(value)]
                        elif operator_name in ["contains", "startswith", "endswith"]:
                            # String operations
                            if operator_name == "contains":
                                result = result[result[column].str.contains(value, na=False)]
                            elif operator_name == "startswith":
                                result = result[result[column].str.startswith(value, na=False)]
                            elif operator_name == "endswith":
                                result = result[result[column].str.endswith(value, na=False)]
                        else:
                            # Type-aware comparisons for string-loaded CSVs.
                            col_series = result[column]
                            if operator_name in ["eq", "ne"]:
                                if isinstance(value, bool):
                                    mask = self._bool_mask(col_series, value)
                                    result = result[mask] if operator_name == "eq" else result[~mask]
                                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                                    numeric = pd.to_numeric(col_series, errors="coerce")
                                    target = float(value)
                                    mask = numeric.eq(target)
                                    result = result[mask] if operator_name == "eq" else result[~mask]
                                else:
                                    left = col_series.fillna("").astype(str).str.strip().map(
                                        normalize_unicode_label
                                    )
                                    right = normalize_unicode_label(str(value))
                                    mask = left.eq(right)
                                    result = result[mask] if operator_name == "eq" else result[~mask]
                            elif operator_name in ["lt", "le", "gt", "ge"] and isinstance(value, (int, float)):
                                numeric = pd.to_numeric(col_series, errors="coerce")
                                target = float(value)
                                if operator_name == "lt":
                                    result = result[numeric.lt(target)]
                                elif operator_name == "le":
                                    result = result[numeric.le(target)]
                                elif operator_name == "gt":
                                    result = result[numeric.gt(target)]
                                elif operator_name == "ge":
                                    result = result[numeric.ge(target)]
                            else:
                                # Fallback generic comparator
                                mask = col_series.apply(lambda x: op_func(x, value))
                                result = result[mask]
        
        # Select columns
        if columns:
            # Only include columns that exist in the dataframe
            valid_columns = [col for col in columns if col in result.columns]
            if valid_columns:
                result = result[valid_columns]
        
        # Sort the results
        if sort_by:
            if isinstance(sort_by, str):
                sort_by = [sort_by]
            
            # Only sort by columns that exist in the dataframe
            valid_sort_columns = [col for col in sort_by if col in result.columns]
            if valid_sort_columns:
                result = result.sort_values(by=valid_sort_columns, ascending=ascending)
        
        # Apply limit
        if limit is not None and limit > 0:
            result = result.head(limit)
        
        return result


    
    def get_weeks(self, season: str, league: str) -> List[int]:
        """Get available weeks for a season and league"""
        filters = {"Season": season, "League": league}
        result = self.get_filtered_data__deprecated(filters_eq=filters)
        
        if result.empty:
            return []
        
        if "Week" in result.columns:
            weeks: List[int] = []
            for w in result["Week"].dropna().unique():
                try:
                    w_str = str(w).strip()
                    if not w_str or w_str.lower() == "nan":
                        continue
                    weeks.append(int(float(w_str)))
                except (ValueError, TypeError):
                    continue
            return sorted(set(weeks))

        return []

    def get_league_week_data(self, query: LeagueQuery) -> pd.DataFrame:
        """Get league data for specific weeks"""
        # Convert query to filters
        filters = {}
        
        if query.season:
            filters["Season"] = query.season
        
        if query.league:
            filters["League"] = query.league
        
        if query.week is not None:
            filters["Week"] = query.week
        
        if query.team:
            filters["Team"] = query.team
        
        # Get filtered data
        result = self.get_filtered_data__deprecated(filters_eq=filters)
        
        return result

    def get_player_data(self, player_name: str) -> pd.DataFrame:
        return self.df[self.df[Columns.player_name] == player_name]
    
    def get_all_players(self) -> List[str]:
        return self.df[Columns.player_name].unique().tolist()
    
    def get_filtered_data__deprecated(self, columns: List[Columns]=None, filters_eq: dict=None, filters_lt: dict=None, filters_gt: dict=None, print_debug: bool=False) -> pd.DataFrame:
        filtered_df = self.df.copy()

        if print_debug:
            print("Initial DataFrame shape:", filtered_df.shape)
            print("Available columns:", filtered_df.columns.tolist())

        if filters_eq is not None:
            for column, value in filters_eq.items():
                if print_debug:
                    print(column + " == " + str(value))
                if value is not None:
                    if isinstance(value, list):
                        filtered_df = filtered_df[filtered_df[column].isin(value)]
                    else:
                        filtered_df = filtered_df[filtered_df[column] == value]
            if print_debug:
                print(f"DataFrame shape after filtering: {filtered_df.shape}")  

        if filters_lt is not None:
            for column, value in filters_lt.items():
                if print_debug:
                    print(column + " < " + str(value))
                if value is not None:
                    filtered_df = filtered_df[filtered_df[column] < value]
            if print_debug:
                print(f"DataFrame shape after filtering: {filtered_df.shape}")  

        if filters_gt is not None:
            for column, value in filters_gt.items():
                if print_debug:
                    print(column + " > " + str(value))
                if value is not None:
                    filtered_df = filtered_df[filtered_df[column] > value]
            if print_debug:
                print(f"DataFrame shape after filtering: {filtered_df.shape}")  

        # extract columns
        if columns is not None:
            filtered_df = filtered_df[columns] 
            if print_debug:
                print("extracting columns: " + str(columns))
                print(f"DataFrame shape after extracting columns: {filtered_df.shape}")  
        return filtered_df
    
    def get_seasons(self, league_name: str=None, team_name: str=None) -> List[str]:
        filters_eq = dict()
        print(f"## DA - Pandas - get_seasons - Getting seasons for league_name: {league_name} and team_name: {team_name}")
        if league_name is not None:
            filters_eq[Columns.league_name] = league_name
        if team_name is not None:
            filters_eq[Columns.team_name] = team_name
        series = self.get_filtered_data__deprecated(columns=[Columns.season], filters_eq=filters_eq)[Columns.season]
        cleaned = _unique_clean_str_labels(series)
        print(f"## DA - Pandas - get_seasons - Seasons: {cleaned}")
        return cleaned
    
    def get_leagues(self, season: str=None, team_name: str=None) -> List[str]:
        filters_eq = dict()
        if season is not None:
            filters_eq[Columns.season] = season
        if team_name is not None:
            filters_eq[Columns.team_name] = team_name
        series = self.get_filtered_data__deprecated(columns=[Columns.league_name], filters_eq=filters_eq)[
            Columns.league_name
        ]
        return _unique_clean_str_labels(series)
    
    def get_weeks__deprecated(self, league_name: str=None, season: str=None, team_name: str=None) -> List[int]:
        """
        Fetches the weeks all available weeks in the database, filtered by league_name and season if provided.
        If league_name and season are provided, the weeks are fetched for the given league and season.
        If only one of the two is provided, the weeks are fetched for all leagues or seasons respectively.

        Args:
            league_name (str): The name of the league.
            season (str): The season.

        Returns:
            List[int]: The weeks.
        """
        filters_eq = dict()

        if league_name is not None:
            filters_eq[Columns.league_name] = league_name

        if season is not None:
            filters_eq[Columns.season] = season

        if team_name is not None:
            filters_eq[Columns.team_name] = team_name

        if filters_eq is not None:
            filtered_df = self.get_filtered_data__deprecated(columns=[Columns.week], filters_eq=filters_eq)
        
        try:
            # Get unique weeks, sort them, and convert to list
            weeks = sorted(filtered_df[Columns.week].unique().tolist())
            # Filter out None/NaN values if any
            weeks = [week for week in weeks if week is not None]
            #print(f"Available weeks: {weeks}")  # Debug output
            return weeks
        except Exception as e:
            print(f"Error getting weeks: {str(e)}")
            return []
    
    def get_league_match_day(self, league_name: str, season: str, week: int) -> pd.DataFrame:
        return self.df[(self.df[Columns.league_name] == league_name) & (self.df[Columns.season] == season) & (self.df[Columns.week] == week)]
    
    def get_league_season(self, league_name: str, season: str, week: int=None) -> pd.DataFrame:
        if week is None:
            return self.df[self.df[Columns.league_name] == league_name][self.df[Columns.season] == season]
        else:
            return self.df[self.df[Columns.league_name] == league_name][self.df[Columns.season] == season][self.df[Columns.week] <= week]

    def get_latest_events(self, limit=5):
        """Get the latest league events based on date."""
        # Get unique combinations of season, league, week, and date
        events = self.df[[Columns.season, Columns.league_name, Columns.week, Columns.date]].drop_duplicates()

        # Sort by date in descending order and get the latest events
        latest_events = events.sort_values(by=Columns.date, ascending=False).head(limit)

        return latest_events    

    def get_league_standings(self, season: str, league: str, week: Optional[int] = None) -> List[TeamSeasonPerformance]:
        """
        Get league standings for a specific season, league, and week.
        
        Args:
            season: The season identifier
            league: The league name
            week: The week number (if None, gets all weeks)
            
        Returns:
            List of TeamSeasonPerformance objects
        """
        # Create a query object
        query = LeagueQuery(
            season=season,
            league=league,
            max_week=week
        )
        
        print(query)
        # Get filtered data
        filters = query.to_filter_dict()
        league_data = self.get_filtered_data(filters=filters)
        
        if league_data.empty:
            return []
        
        # Group by team and week to get team performances
        team_performances = {}
        
        # Process each row in the dataframe
        for _, row in league_data.iterrows():
            team_id = row[Columns.team_name]  # Using team name as ID for now
            team_name = row[Columns.team_name]
            week_num = row[Columns.week]
            score = row[Columns.score]
            points = league_points_cell(row)
            players_per_team = row.get(Columns.players_per_team, 4)  # Get players per team or default to 4
            
            # Initialize team data if not exists
            if team_id not in team_performances:
                team_performances[team_id] = {
                    'team_id': team_id,
                    'team_name': team_name,
                    'total_score': 0,
                    'total_points': 0,
                    'total_number_of_games': 0,
                    'weekly_performances': {}
                }
            
            # Initialize week data if not exists
            if week_num not in team_performances[team_id]['weekly_performances']:
                team_performances[team_id]['weekly_performances'][week_num] = {
                    'score': 0,
                    'points': 0,
                    'number_of_games': 0,
                    'players_per_team': players_per_team
                }
            
            # Add score and points
            team_performances[team_id]['weekly_performances'][week_num]['score'] += score
            team_performances[team_id]['weekly_performances'][week_num]['points'] += points
            team_performances[team_id]['weekly_performances'][week_num]['number_of_games'] += 1
            # Update team totals
            team_performances[team_id]['total_score'] += score
            team_performances[team_id]['total_points'] += points
            team_performances[team_id]['total_number_of_games'] += 1
        # Convert to TeamSeasonPerformance objects
        result = []
        for team_id, data in team_performances.items():
            # Calculate average (using players_per_team from each week)
            total_games = 0
            for week_num, week_data in data['weekly_performances'].items():
                # Each player plays one game per week
                total_games += week_data['players_per_team']
            
            # @todo: this is a hack to normalize the score, the factor 2.5 is arbitrary, fix it in the structure
            average = data['total_score'] / (total_games) if total_games > 0 else 0
            
            # Create weekly performance objects
            weekly_performances = []
            for week_num, week_data in data['weekly_performances'].items():
                
                weekly_performances.append( 
                    TeamWeeklyPerformance(
                        team_id=data['team_id'],
                        team_name=data['team_name'],
                        week=week_num,
                        score=week_data['score'],
                        points=week_data['points'],
                        number_of_games=week_data['number_of_games'],
                        players_per_team=week_data['players_per_team']
                    )
                )
            
            # Sort weekly performances by week
            weekly_performances.sort(key=lambda x: x.week)
            
            # Create the TeamSeasonPerformance
            result.append(
                TeamSeasonPerformance(
                    team_id=data['team_id'],
                    team_name=data['team_name'],
                    total_score=data['total_score'],
                    total_points=data['total_points'],
                    average=round(average, 2),
                    weekly_performances=weekly_performances
                )
            )
        
        return result
    
    def _convert_to_raw_player_data(self, row: pd.Series) -> RawPlayerData:
        """Convert a pandas Series to RawPlayerData"""
        return RawPlayerData(
            player_name=str(row[Columns.player_name]),
            team_name=str(row[Columns.team_name]),
            week=_safe_int_cell(row[Columns.week], 0),
            round_number=_safe_int_cell(row.get(Columns.round_number), 0),
            score=_safe_int_cell(row[Columns.score], 0),
            points=_safe_float_cell(row.get(Columns.points), 0.0),
            calculated_score=bool(not pd.isna(row[Columns.input_data])),
        )

    def _convert_to_raw_team_data(self, team_df: pd.DataFrame) -> RawTeamData:
        """Convert team DataFrame to RawTeamData"""
        players = [
            self._convert_to_raw_player_data(row)
            for _, row in team_df.iterrows()
            if _row_ok_for_raw_player(row)
        ]
        return RawTeamData(
            team_name=str(team_df[Columns.team_name].iloc[0]),
            season=str(team_df[Columns.season].iloc[0]),
            players=players
        )

    def get_raw_team_data(self, team: str, season: str) -> RawTeamData:
        """Get raw team data as DTO"""
        filters = {
            Columns.team_name: {'value': team, 'operator': 'eq'},
            Columns.season: {'value': season, 'operator': 'eq'}
        }
        team_df = self.get_filtered_data(filters=filters)
        if team_df.empty:
            return None
        raw = self._convert_to_raw_team_data(team_df)
        if not raw.players:
            return None
        return raw

    def get_raw_league_data(self, league: str, season: str) -> RawLeagueData:
        """Get raw league data as DTO"""
        filters = {
            Columns.league_name: {'value': league, 'operator': 'eq'},
            Columns.season: {'value': season, 'operator': 'eq'}
        }
        league_df = self.get_filtered_data(filters=filters)
        if league_df.empty:
            return None
            
        teams = []
        for team in league_df[Columns.team_name].unique():
            team_df = league_df[league_df[Columns.team_name] == team]
            teams.append(self._convert_to_raw_team_data(team_df))
            
        return RawLeagueData(
            league_name=league,
            season=season,
            teams=teams
        )
    
    def get_matches(self, team: str = None, season: str = None, league: str = None, opponent_team_name: str = None) -> pd.DataFrame:
        """Get matches data with team and opponent scores
        
        Args:
            team: Team name to filter by
            season: Season to filter by
            league: League to filter by
            opponent_team_name: Opponent team name to filter by
            
        Returns:
            DataFrame with columns: league, season, week, team_name, round_number, 
            score (team score), opponent_team_name, opponent_score (opponent team score)
        """
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        # Build filters for team data
        team_filters = {
            Columns.computed_data: {'value': True, 'operator': 'eq'}
        }
        
        if team:
            team_filters[Columns.team_name] = {'value': team, 'operator': 'eq'}
        if season:
            team_filters[Columns.season] = {'value': season, 'operator': 'eq'}
        if league:
            team_filters[Columns.league_name] = {'value': league, 'operator': 'eq'}
        if opponent_team_name:
            team_filters[Columns.team_name_opponent] = {'value': opponent_team_name, 'operator': 'eq'}
        
        # Get team data
        team_data = self.get_filtered_data(filters=team_filters)
        
        if team_data.empty:
            return pd.DataFrame()
        
        # Create result DataFrame with required columns
        result_columns = [
            Columns.league_name, Columns.season, Columns.week, 
            Columns.team_name, Columns.round_number, Columns.score, 
            Columns.team_name_opponent
        ]
        
        result_df = team_data[result_columns].copy()
        
        # Get all computed data for the same matches to find opponent scores
        # We need to get all teams that played in the same matches as our team
        all_match_filters = {
            Columns.computed_data: {'value': True, 'operator': 'eq'}
        }
        
        # Add season filter if specified
        if season:
            all_match_filters[Columns.season] = {'value': season, 'operator': 'eq'}
        if league:
            all_match_filters[Columns.league_name] = {'value': league, 'operator': 'eq'}
        
        # Get all computed data for these matches
        all_match_data = self.get_filtered_data(filters=all_match_filters)
        
        if all_match_data.empty:
            return result_df
        
        # Create opponent data by filtering for the opponent teams
        opponent_data = all_match_data[all_match_data[Columns.team_name].isin(result_df[Columns.team_name_opponent].unique())].copy()
        
        # Merge result_df with opponent_data to get opponent scores
        # We'll merge on season, league, week, round_number, and match the team_name with team_name_opponent
        merge_columns = [Columns.season, Columns.league_name, Columns.week, Columns.round_number]
        
        # Select only the columns we need from opponent_data and rename them
        opponent_data_for_merge = opponent_data[merge_columns + [Columns.team_name, Columns.score]].copy()
        opponent_data_for_merge = opponent_data_for_merge.rename(columns={
            Columns.team_name: Columns.team_name_opponent,
            Columns.score: 'opponent_score'
        })
        
        # Merge the dataframes
        result_df = result_df.merge(
            opponent_data_for_merge,
            on=merge_columns + [Columns.team_name_opponent],
            how='left'
        )
        
        # Fill any missing opponent scores with 0
        result_df['opponent_score'] = result_df['opponent_score'].fillna(0)
        
        return result_df
    