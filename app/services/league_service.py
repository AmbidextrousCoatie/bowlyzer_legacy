from typing import List, Dict, Any, Optional, Tuple, Union
import datetime
import pandas as pd
import re
  

from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.models.league_models import LeagueQuery, TeamSeasonPerformance, LeagueStandings, TeamWeeklyPerformance
from app.services.i18n_service import i18n_service
from app.models.table_data import TableData, ColumnGroup, Column, PlotData, TileData
from app.services.statistics_service import StatisticsService
from app.models.statistics_models import LeagueStatistics, LeagueResults
from app.models.series_data import SeriesData
from data_access.dtype_normalization import BOOL_FALSE_TOKENS, BOOL_TRUE_TOKENS
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label, safe_rank_int
from data_access.score_utils import (
    mean_scores,
    pinfall_display,
    pinfall_for_total,
    scores_for_totals,
    sum_league_points,
    sum_scores,
    sum_scores_float,
)
from itertools import accumulate
from app.config.debug_config import debug_config
from app.utils.color_constants import get_theme_color, get_heat_map_color
from app.utils.league_utils import (
    format_float_one_decimal,
    get_league_level,
    get_league_division_map,
    convert_to_simple_types,
    apply_heat_map_to_columns,
    resolve_league_long_name,
)
from app.utils.json_safe import json_safe
from app.utils.league_level5_merge import (
    get_level5_merge_registry,
    merge_key_for_league,
    merged_league_label,
    resolve_league_id_for_season,
)
from app.utils.league_week_expectations import expected_weeks_for_league_season, schema_rule_summary
# from data_access.series_data import calculate_series_data, get_player_series_data, get_team_series_data


class ColumnWidths:
    """Class to store column widths for the league service"""
    player = "120px"
    team = "120px"
    points = "70px"
    pins = "70px"
    average = "70px"
    season = "90px"
    league = "90px"
    games = "70px"  
    position = "60px"
    week = "80px"
    date = "120px"
    misc = "80px"
    location = "120px"


def _lineup_base(positions: set[int]) -> int:
    """Offset to convert stored Position values to 0-based lineup slots."""
    if not positions:
        return 0
    return 1 if 0 not in positions and min(positions) >= 1 else 0


def _lineup_slot_lookup(df: pd.DataFrame) -> dict[int, pd.Series]:
    """Map 0-based lineup slot index to the player row for that slot."""
    if df.empty or Columns.position not in df.columns:
        return {}
    positions = {
        int(p)
        for p in pd.to_numeric(df[Columns.position], errors="coerce").dropna()
    }
    base = _lineup_base(positions)
    lookup: dict[int, pd.Series] = {}
    for _, row in df.iterrows():
        pos_raw = row.get(Columns.position)
        if pd.isna(pos_raw):
            continue
        slot = int(pos_raw) - base
        lookup[slot] = row
    return lookup


class LeagueService:
    def __init__(self, adapter_type=DataAdapterSelector.PANDAS, database: str = None):
        self.database = database
        self.adapter = DataAdapterFactory.create_adapter(adapter_type, database=database)
        self.stats_service = StatisticsService(database=database)
        self._warm_slice_cache: Optional[Dict[Tuple[str, str, bool], pd.DataFrame]] = None
        
        # Register this adapter with DataManager for automatic refresh
        try:
            from app.services.data_manager import DataManager
            data_manager = DataManager()
            data_manager.register_server_instance(self)
        except ImportError:
            # DataManager not available, continue without registration
            pass

    def warm_slice_cache_begin(self) -> None:
        """Enable per-(season, league) dataframe memoization for cache warm workers."""
        self._warm_slice_cache = {}

    def warm_slice_cache_end(self) -> None:
        self._warm_slice_cache = None

    def _season_league_dataframe(self, league_name: str, season: str, *, computed_data: bool) -> pd.DataFrame:
        """All rows for (season, league, computed_data); cached during warm when enabled."""
        season_key = str(season).strip()
        league_key = str(league_name).strip()
        cache_key = (season_key, league_key, bool(computed_data))
        cache = self._warm_slice_cache
        if cache is not None:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached.copy()

        filters = {
            Columns.league_name: {"value": league_name, "operator": "eq"},
            Columns.season: {"value": season, "operator": "eq"},
            Columns.computed_data: {"value": computed_data, "operator": "eq"},
        }
        df = self.adapter.get_filtered_data(filters=filters)
        if df is None or df.empty:
            df = pd.DataFrame()
        if cache is not None:
            cache[cache_key] = df
        return df.copy()

    @staticmethod
    def _filter_dataframe_week(df: pd.DataFrame, week: Optional[int]) -> pd.DataFrame:
        if df.empty or week is None or Columns.week not in df.columns:
            return df
        weeks = pd.to_numeric(df[Columns.week], errors="coerce")
        return df.loc[weeks == int(week)].copy()

    def refresh_data_adapter(self, database: str = None):
        """Refresh the data adapter with the current data source"""
        if database:
            self.database = database
        debug_config.log_service('LeagueService', 'refresh_adapter', f"database={self.database}")
        self.adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=self.database)

    def get_available_weeks(self, season: str, league: str) -> List[int]:
        """Get available weeks for a season and league"""
        return self.adapter.get_weeks(season, league)
    
    def get_latest_week(self, season: str, league: str) -> int:
        """Get the latest week number for a season and league"""
        weeks = self.get_available_weeks(season, league)
        return max(weeks) if weeks else 1
    
    def get_seasons(self, league_name: str=None, team_name: str=None) -> List[str]:
        """Get all available seasons"""
        # print(f"####################### Getting seasons for league_name: {league_name} and team_name: {team_name}")
        return self.adapter.get_seasons(league_name=league_name, team_name=team_name)

    def get_leagues(self, season: Optional[str] = None, division: Optional[str] = None) -> List[str]:
        """Get all available leagues, optionally restricted to a season and/or division."""
        leagues = self.adapter.get_leagues(season=season)
        if not division:
            return leagues

        from app.utils.league_utils import get_league_division_map

        division_map = get_league_division_map()
        return [lg for lg in leagues if division_map.get(lg) == division]

    def _split_club_and_team_number(self, team_name: str):
        """Split trailing team number from team name if present."""
        text = str(team_name or "").strip()
        if not text:
            return "", ""
        match = re.match(r"^(.*?)(?:\s+(\d+))?$", text)
        if not match:
            return text, ""
        club_name = str(match.group(1) or "").strip()
        team_number = str(match.group(2) or "").strip()
        return club_name, team_number

    def _club_team_full_name(self, club: str, team_number: str) -> str:
        club = str(club or "").strip()
        team_number = str(team_number or "").strip()
        if not team_number or team_number == "base":
            return club
        if team_number.isdigit():
            return f"{club} {team_number}"
        return f"{club} {team_number}"

    @staticmethod
    def _computed_data_mask(series: pd.Series, *, want_true: bool) -> pd.Series:
        normalized = series.fillna("").astype(str).str.strip().str.lower()
        tokens = BOOL_TRUE_TOKENS if want_true else BOOL_FALSE_TOKENS
        return normalized.isin(tokens)

    def _league_team_count(self, league_name: str, season: str) -> int:
        filters = {
            Columns.league_name: {"value": league_name, "operator": "eq"},
            Columns.season: {"value": season, "operator": "eq"},
            Columns.computed_data: {"value": False, "operator": "eq"},
        }
        df = self.adapter.get_filtered_data(filters=filters, columns=[Columns.team_name])
        if df is None or df.empty:
            return 0
        return int(df[Columns.team_name].nunique())

    def _league_final_position(self, team_name: str, league_name: str, season: str) -> int:
        filters = {
            Columns.season: {"value": season, "operator": "eq"},
            Columns.league_name: {"value": league_name, "operator": "eq"},
        }
        df = self.adapter.get_filtered_data(
            columns=[Columns.team_name, Columns.points],
            filters=filters,
        )
        if df is None or df.empty or Columns.team_name not in df.columns:
            return 0
        needle = normalize_unicode_label(team_name)
        if needle not in set(df[Columns.team_name].astype(str).map(normalize_unicode_label)):
            return 0
        team_rank = df.groupby(Columns.team_name)[Columns.points].sum().rank(ascending=False)
        for idx in team_rank.index:
            if normalize_unicode_label(str(idx)) == needle:
                return safe_rank_int(team_rank.loc[idx])
        return 0

    def _get_club_source_dataframe(self) -> pd.DataFrame:
        """Return base dataframe used for club matrix computations."""
        filters = {
            Columns.computed_data: {'value': True, 'operator': 'eq'},
        }
        df = self.adapter.get_filtered_data(filters=filters)
        if df is None or df.empty:
            return pd.DataFrame(columns=[Columns.season, Columns.league_name, Columns.team_name, Columns.team_name_opponent])
        return df

    def resolve_club_name(self, club: str, clubs: Optional[List[str]] = None) -> str:
        """Map URL/user input to the canonical club label from data (NFC-aware)."""
        needle = normalize_unicode_label(club)
        if not needle:
            return ""
        if clubs is None:
            clubs = self.get_available_clubs()
        for candidate in clubs:
            if normalize_unicode_label(candidate) == needle:
                return candidate
        return str(club or "").strip()

    def get_available_clubs(self, only_with_unnumbered_team: bool = False) -> List[str]:
        """Get distinct club base names from Team/Opponent columns."""
        df = self._get_club_source_dataframe()
        clubs = set()
        clubs_with_unnumbered = set()
        clubs_with_numbered = set()
        for col in [Columns.team_name, Columns.team_name_opponent]:
            if col not in df.columns:
                continue
            for value in df[col].dropna().astype(str):
                club_name, _team_number = self._split_club_and_team_number(value)
                if club_name:
                    clubs.add(club_name)
                    if not _team_number:
                        clubs_with_unnumbered.add(club_name)
                    else:
                        clubs_with_numbered.add(club_name)
        if only_with_unnumbered_team:
            return sorted(clubs_with_unnumbered.intersection(clubs_with_numbered))
        return sorted(clubs)

    def get_club_team_season_matrix(self, club: str) -> Dict[str, Any]:
        """Build team-vs-season matrix for one club with league values in cells."""
        club = str(club or "").strip()
        if not club:
            return {"club": "", "seasons": [], "rows": []}

        df = self._get_club_source_dataframe()
        if df.empty:
            return {"club": club, "seasons": [], "rows": []}

        long_rows = []
        for col in [Columns.team_name, Columns.team_name_opponent]:
            if col not in df.columns:
                continue
            subset = df[[Columns.season, Columns.league_name, col]].copy()
            subset = subset.rename(columns={col: "TeamRaw"})
            long_rows.append(subset)
        if not long_rows:
            return {"club": club, "seasons": [], "rows": []}

        long_df = pd.concat(long_rows, ignore_index=True)
        long_df = long_df.dropna(subset=["TeamRaw", Columns.season, Columns.league_name])
        if long_df.empty:
            return {"club": club, "seasons": [], "rows": []}

        long_df["TeamRaw"] = long_df["TeamRaw"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        split_values = long_df["TeamRaw"].apply(self._split_club_and_team_number)
        long_df["club_name"] = split_values.apply(lambda item: item[0])
        long_df["team_number"] = split_values.apply(lambda item: item[1] if item[1] else "base")

        club_norm = normalize_unicode_label(club)
        club_df = long_df[long_df["club_name"].map(normalize_unicode_label) == club_norm].copy()
        if club_df.empty:
            return {"club": club, "seasons": [], "rows": []}
        club = str(club_df["club_name"].iloc[0])

        seasons = sorted(club_df[Columns.season].astype(str).unique())
        grouped = (
            club_df.groupby(["team_number", Columns.season])[Columns.league_name]
            .apply(lambda s: ", ".join(sorted({str(v).strip() for v in s if str(v).strip()})))
            .reset_index(name="leagues")
        )

        def _team_sort_key(team_label: str):
            return (0, int(team_label)) if str(team_label).isdigit() else (1, str(team_label))

        team_rows = []
        for team_number in sorted(grouped["team_number"].unique(), key=_team_sort_key):
            season_cells = {season: "" for season in seasons}
            sub = grouped[grouped["team_number"] == team_number]
            full_team_name = self._club_team_full_name(club, str(team_number))
            for row in sub.itertuples(index=False):
                season_key = str(getattr(row, Columns.season))
                leagues_str = getattr(row, "leagues")
                items = []
                for league_name in [p.strip() for p in str(leagues_str).split(",") if p.strip()]:
                    final_position = self._league_final_position(
                        full_team_name, league_name, season_key
                    )
                    team_count = self._league_team_count(league_name, season_key)
                    items.append({
                        "league": league_name,
                        "final_position": int(final_position) if final_position > 0 else None,
                        "team_count": int(team_count) if team_count > 0 else None,
                        "league_level": get_league_level(league_name),
                    })
                season_cells[season_key] = {
                    "leagues": leagues_str,
                    "items": items,
                }
            team_rows.append({
                "team_number": team_number,
                "seasons": season_cells,
            })

        return {
            "club": club,
            "seasons": seasons,
            "rows": team_rows,
        }

    def get_league_week_matrix(self, expected_weeks: int = None) -> Dict[str, Any]:
        """
        Build a league-vs-season matrix with missing week information.

        Expected matchdays per cell:
        - Bayernliga (``BayL``, ``BayL (D)``): always 6
        - all other leagues: number of teams in that league/season

        ``expected_weeks`` is ignored (kept for API compatibility).

        Cell semantics:
        - all expected weeks available -> checkmark
        - missing weeks -> comma-separated week numbers
        """
        _ = expected_weeks  # deprecated global override
        empty = {"seasons": [], "rows": [], "expected_weeks_rule": schema_rule_summary()}

        matrix_cols = [
            Columns.season,
            Columns.league_name,
            Columns.week,
            Columns.team_name,
            Columns.computed_data,
        ]
        df = self.adapter.get_filtered_data(filters={}, columns=matrix_cols)
        if df is None or df.empty:
            return empty

        for col in matrix_cols:
            if col not in df.columns:
                return empty

        df = df.copy()
        df[Columns.season] = df[Columns.season].astype(str).str.strip()
        df[Columns.league_name] = df[Columns.league_name].astype(str).str.strip()

        computed_mask = self._computed_data_mask(df[Columns.computed_data], want_true=True)
        raw_mask = self._computed_data_mask(df[Columns.computed_data], want_true=False)

        matrix_df = df.loc[computed_mask, [Columns.season, Columns.league_name, Columns.week]].copy()
        matrix_df[Columns.week] = pd.to_numeric(matrix_df[Columns.week], errors="coerce")
        matrix_df = matrix_df.dropna(subset=[Columns.week])
        matrix_df[Columns.week] = matrix_df[Columns.week].astype(int)
        matrix_df = matrix_df[matrix_df[Columns.week] > 0]
        matrix_df = matrix_df.drop_duplicates(
            subset=[Columns.season, Columns.league_name, Columns.week]
        )

        if matrix_df.empty:
            return empty

        seasons = sorted(matrix_df[Columns.season].unique())

        grouped = (
            matrix_df.groupby([Columns.league_name, Columns.season])[Columns.week]
            .apply(lambda s: sorted({int(v) for v in s if int(v) > 0}))
            .to_dict()
        )

        team_counts = (
            df.loc[raw_mask, [Columns.league_name, Columns.season, Columns.team_name]]
            .groupby([Columns.league_name, Columns.season])[Columns.team_name]
            .nunique()
            .to_dict()
        )

        _, merge_members = get_level5_merge_registry()
        merge_groups: Dict[str, Dict[str, Any]] = {}
        for league in sorted(matrix_df[Columns.league_name].unique()):
            merge_key = merge_key_for_league(league)
            bucket = merge_groups.setdefault(
                merge_key,
                {"members": merge_members.get(merge_key, [league])},
            )
            if league not in bucket["members"]:
                bucket["members"] = sorted(set(bucket["members"]) | {league})

        rows: List[Dict[str, Any]] = []
        def _merge_row_sort_key(item: Tuple[str, Dict[str, Any]]) -> Tuple[int, str]:
            key, bucket = item
            members = bucket["members"]
            level = min(get_league_level(member) for member in members)
            return level, merged_league_label(members)

        for merge_key, _bucket in sorted(merge_groups.items(), key=_merge_row_sort_key):
            members: List[str] = _bucket["members"]
            row_label = merged_league_label(members)
            season_cells: Dict[str, Dict[str, Any]] = {}
            for season in seasons:
                available_weeks = sorted(
                    {
                        int(w)
                        for member in members
                        for w in grouped.get((member, season), [])
                        if int(w) > 0
                    }
                )
                available_set = set(available_weeks)
                team_count = max(
                    (int(team_counts.get((member, season), 0)) for member in members),
                    default=0,
                )
                link_league = resolve_league_id_for_season(
                    members,
                    season,
                    weeks_by_league_season=grouped,
                    team_counts_by_league_season=team_counts,
                )
                expected_count = expected_weeks_for_league_season(
                    link_league or row_label,
                    season,
                    team_count=team_count,
                )
                if team_count == 0 and not available_weeks:
                    season_cells[season] = {
                        "label": "",
                        "status": "",
                        "missing_weeks": [],
                        "available_weeks": [],
                        "expected_weeks": 0,
                        "team_count": 0,
                        "league_id": link_league,
                    }
                    continue

                expected_set = set(range(1, expected_count + 1))
                missing_weeks = sorted(expected_set - available_set)
                coverage_ratio = (
                    len(available_set.intersection(expected_set)) / expected_count
                    if expected_count > 0
                    else 0.0
                )

                if not missing_weeks:
                    label = "✓"
                    status = "ok"
                else:
                    label = ", ".join(str(w) for w in missing_weeks)
                    if coverage_ratio >= 0.67:
                        status = "warn"
                    elif coverage_ratio >= 0.34:
                        status = "bad"
                    else:
                        status = "critical"

                season_cells[season] = {
                    "label": label,
                    "status": status,
                    "missing_weeks": missing_weeks,
                    "available_weeks": available_weeks,
                    "expected_weeks": expected_count,
                    "team_count": team_count,
                    "league_id": link_league,
                }

            rows.append({"league": row_label, "seasons": season_cells})

        return {
            "seasons": seasons,
            "rows": rows,
            "expected_weeks_rule": schema_rule_summary(),
        }

    def _liga_deep_link_params(
        self,
        *,
        season: str,
        league: str,
        week: Optional[Union[int, str]] = None,
        team: Optional[str] = None,
        round_number: Optional[Union[int, str]] = None,
    ) -> Dict[str, str]:
        params: Dict[str, str] = {
            "season": str(season or "").strip(),
            "league": str(league or "").strip(),
        }
        if week is not None and str(week).strip() != "":
            params["week"] = str(int(float(week))) if str(week).replace(".", "", 1).isdigit() else str(week).strip()
        if team and str(team).strip():
            params["team"] = str(team).strip()
        if round_number is not None and str(round_number).strip() != "":
            params["round"] = str(int(float(round_number))) if str(round_number).replace(".", "", 1).isdigit() else str(round_number).strip()
        return params

    def get_data_oddities(
        self,
        types: Optional[List[str]] = None,
        limit: int = 2000,
    ) -> Dict[str, Any]:
        """
        Scan league input rows for data-quality oddities with Liga deep-link context.

        Supported types: unnumbered_team, low_score, incomplete_row
        """
        allowed_types = {"unnumbered_team", "low_score", "incomplete_row"}
        selected_types = (
            {t for t in (types or []) if t in allowed_types} or allowed_types
        )
        limit = max(1, min(int(limit or 2000), 10_000))

        filters: Dict[str, Dict[str, Any]] = {
            Columns.computed_data: {"value": False, "operator": "eq"},
        }
        adapter_df = getattr(self.adapter, "df", None)
        if isinstance(adapter_df, pd.DataFrame) and Columns.input_data in adapter_df.columns:
            filters[Columns.input_data] = {"value": True, "operator": "eq"}

        columns = [
            Columns.season,
            Columns.league_name,
            Columns.week,
            Columns.round_number,
            Columns.match_number,
            Columns.team_name,
            Columns.team_name_opponent,
            Columns.player_name,
            Columns.position,
            Columns.score,
        ]
        df = self.adapter.get_filtered_data(filters=filters, columns=columns)
        if df is None or df.empty:
            return {
                "oddities": [],
                "summary": {"total": 0, "by_type": {}},
                "limit": limit,
                "truncated": False,
            }

        oddities: List[Dict[str, Any]] = []
        summary_counts: Dict[str, int] = {key: 0 for key in allowed_types}

        def _append(oddity: Dict[str, Any]) -> bool:
            if len(oddities) >= limit:
                return False
            oddities.append(oddity)
            summary_counts[oddity["type"]] = summary_counts.get(oddity["type"], 0) + 1
            return True

        if "unnumbered_team" in selected_types:
            unnumbered: Dict[str, Dict[str, Any]] = {}
            team_cols = [c for c in [Columns.team_name, Columns.team_name_opponent] if c in df.columns]
            for col in team_cols:
                for _, row in df.iterrows():
                    team_raw = str(row.get(col) or "").strip()
                    if not team_raw:
                        continue
                    _club, team_number = self._split_club_and_team_number(team_raw)
                    if team_number:
                        continue
                    bucket = unnumbered.get(team_raw)
                    if bucket is None:
                        season = str(row.get(Columns.season) or "").strip()
                        league = str(row.get(Columns.league_name) or "").strip()
                        week = row.get(Columns.week)
                        link_params = self._liga_deep_link_params(
                            season=season,
                            league=league,
                            week=week,
                            team=team_raw,
                        )
                        bucket = {
                            "team": team_raw,
                            "occurrences": 0,
                            "season": season,
                            "league": league,
                            "week": week,
                            "deep_link": {"path": "/liga", "params": link_params},
                        }
                        unnumbered[team_raw] = bucket
                    bucket["occurrences"] = int(bucket["occurrences"]) + 1

            for team_raw, bucket in sorted(unnumbered.items(), key=lambda item: item[0].lower()):
                occ = int(bucket["occurrences"])
                season = str(bucket.get("season") or "")
                league = str(bucket.get("league") or "")
                message = f'Mannschaft ohne Nummer: "{team_raw}"'
                if season or league:
                    message += f" ({league or '—'} · {season or '—'}, {occ}×)"
                else:
                    message += f" ({occ}×)"
                if not _append(
                    {
                        "id": f"unnumbered_team:{team_raw}",
                        "type": "unnumbered_team",
                        "severity": "warn",
                        "message": message,
                        "context": {
                            "team": team_raw,
                            "occurrences": occ,
                            "season": season,
                            "league": league,
                        },
                        "deep_link": bucket["deep_link"],
                    }
                ):
                    break

        if "low_score" in selected_types and len(oddities) < limit:
            player_mask = pd.Series(True, index=df.index)
            if Columns.player_name in df.columns:
                players = df[Columns.player_name].fillna("").astype(str).str.strip()
                player_mask &= players.ne("") & players.ne("Team Total")
            if Columns.position in df.columns:
                positions = pd.to_numeric(df[Columns.position], errors="coerce").fillna(0)
                player_mask &= positions.gt(0)

            scores = pd.to_numeric(df[Columns.score], errors="coerce")
            low_df = df[player_mask & scores.lt(1)].copy()
            low_df = low_df.sort_values(
                by=[Columns.season, Columns.league_name, Columns.week, Columns.player_name],
                na_position="last",
            )

            for _, row in low_df.iterrows():
                season = str(row.get(Columns.season) or "").strip()
                league = str(row.get(Columns.league_name) or "").strip()
                team = str(row.get(Columns.team_name) or "").strip()
                player = str(row.get(Columns.player_name) or "").strip()
                opponent = str(row.get(Columns.team_name_opponent) or "").strip()
                week = row.get(Columns.week)
                round_number = row.get(Columns.round_number)
                match_number = row.get(Columns.match_number)
                score_val = float(pd.to_numeric(row.get(Columns.score), errors="coerce"))
                if score_val < 0:
                    severity = "critical"
                elif score_val == 0:
                    severity = "bad"
                else:
                    severity = "warn"
                week_label = ""
                if week is not None and str(week).strip() not in {"", "nan"}:
                    week_label = f" · Spieltag {int(float(week))}" if str(week).replace(".", "", 1).isdigit() else f" · Spieltag {week}"
                message = f"{player}: Ergebnis {score_val:g}{week_label}"
                link_params = self._liga_deep_link_params(
                    season=season,
                    league=league,
                    week=week,
                    team=team,
                    round_number=round_number,
                )
                oddity_id = "|".join(
                    [
                        "low_score",
                        season,
                        league,
                        str(week),
                        str(round_number),
                        str(match_number),
                        team,
                        player,
                    ]
                )
                if not _append(
                    {
                        "id": oddity_id,
                        "type": "low_score",
                        "severity": severity,
                        "message": message,
                        "context": {
                            "season": season,
                            "league": league,
                            "week": week,
                            "round": round_number,
                            "match_number": match_number,
                            "team": team,
                            "opponent": opponent,
                            "player": player,
                            "score": score_val,
                        },
                        "deep_link": {"path": "/liga", "params": link_params},
                    }
                ):
                    break

        if "incomplete_row" in selected_types and len(oddities) < limit:
            # Einzelspieler-Zeilen ohne Spieltag und/oder ohne gültiges Ergebnis (z. B. pd.NA in Import)
            if Columns.week in df.columns and Columns.score in df.columns:
                player_mask = pd.Series(True, index=df.index)
                if Columns.player_name in df.columns:
                    players = df[Columns.player_name].fillna("").astype(str).str.strip()
                    player_mask &= players.ne("") & players.ne("Team Total")
                if Columns.position in df.columns:
                    positions = pd.to_numeric(df[Columns.position], errors="coerce").fillna(0)
                    player_mask &= positions.gt(0)

                wcol = df[Columns.week]
                week_bad = wcol.isna()
                try:
                    wstr = wcol.astype(str).str.strip()
                    week_bad = week_bad | wstr.isin(["", "nan", "None", "<NA>", "NaT", "<nat>"])
                except Exception:
                    pass

                scores_num = pd.to_numeric(df[Columns.score], errors="coerce")
                score_bad = scores_num.isna()

                bad_df = df.loc[player_mask & (week_bad | score_bad)].copy()
                bad_df = bad_df.sort_values(
                    by=[Columns.season, Columns.league_name, Columns.week, Columns.player_name],
                    na_position="last",
                )

                for idx, row in bad_df.iterrows():
                    season = str(row.get(Columns.season) or "").strip()
                    league = str(row.get(Columns.league_name) or "").strip()
                    team = str(row.get(Columns.team_name) or "").strip()
                    player = str(row.get(Columns.player_name) or "").strip()
                    week = row.get(Columns.week)
                    round_number = row.get(Columns.round_number)
                    match_number = row.get(Columns.match_number)

                    wm = bool(week_bad.loc[idx]) if idx in week_bad.index else True
                    sm = bool(score_bad.loc[idx]) if idx in score_bad.index else True

                    missing_bits: List[str] = []
                    if wm:
                        missing_bits.append("Spieltag fehlt")
                    if sm:
                        missing_bits.append("Ergebnis fehlt oder ungültig")
                    gap = ", ".join(missing_bits) if missing_bits else "unvollständige Zeile"

                    if season or league:
                        message = f"{player} ({team}): {gap} — {league or '—'} · {season or '—'}"
                    else:
                        message = f"{player} ({team}): {gap}"

                    link_week = week if not wm else None
                    link_params = self._liga_deep_link_params(
                        season=season,
                        league=league,
                        week=link_week,
                        team=team,
                        round_number=round_number,
                    )
                    oddity_id = "|".join(
                        [
                            "incomplete_row",
                            str(idx),
                            season,
                            league,
                            str(week),
                            str(match_number),
                            team,
                            player,
                        ]
                    )
                    severity = "critical" if (wm and sm) else "bad"
                    if not _append(
                        {
                            "id": oddity_id,
                            "type": "incomplete_row",
                            "severity": severity,
                            "message": message,
                            "context": {
                                "season": season,
                                "league": league,
                                "week": week,
                                "round": round_number,
                                "match_number": match_number,
                                "team": team,
                                "player": player,
                                "missing_week": 1 if wm else 0,
                                "missing_score": 1 if sm else 0,
                            },
                            "deep_link": {"path": "/liga", "params": link_params},
                        }
                    ):
                        break

        truncated = len(oddities) >= limit
        by_type = {key: summary_counts.get(key, 0) for key in sorted(selected_types)}
        return {
            "oddities": oddities,
            "summary": {"total": len(oddities), "by_type": by_type},
            "limit": limit,
            "truncated": truncated,
        }
    
    def get_available_rounds(self, season: str, league: str, week: int) -> List[int]:
        """Get available rounds (games) for a season, league, and week"""
        filters = {
            Columns.season: {'value': season, 'operator': 'eq'},
            Columns.league_name: {'value': league, 'operator': 'eq'},
            Columns.week: {'value': week, 'operator': 'eq'}
        }
        
        data = self.adapter.get_filtered_data(filters=filters)
        
        if data.empty or Columns.round_number not in data.columns:
            return []
        
        # Get unique round numbers, filter out empty/NaN values, and sort
        rounds_series = data[Columns.round_number].dropna()
        # Filter out empty strings and convert to int
        rounds = []
        for r in rounds_series.unique():
            try:
                r_str = str(r).strip()
                if r_str != '' and r_str.lower() != 'nan':
                    rounds.append(int(float(r_str)))  # Use float first to handle "1.0" strings
            except (ValueError, TypeError):
                continue
        
        return sorted(set(rounds))  # Remove duplicates and sort

    def get_game_overview_data(self, season: str, league: str, week: int, round_number: int) -> TableData:
        """
        Get game overview data for a specific round.
        Shows all matches with team vs opponent: team name, team pins, team points | opponent points, opponent pins, opponent name
        
        Args:
            season: Season identifier
            league: League name
            week: Week number
            round_number: Round/Game number
            
        Returns:
            TableData with column groups for Team and Opponent
        """
        try:
            # Get team totals for this round
            filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}  # Team totals
            }
            
            team_totals = self.adapter.get_filtered_data(filters=filters)
            
            if team_totals.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available')} - {i18n_service.get_text('game')} {round_number}"
                )
            
            # Get league standings to determine team positions
            standings = self.get_league_standings(season, league, week)
            team_positions = {}
            if standings and standings.teams:
                for team in standings.teams:
                    team_positions[team.team_name] = team.position
            
            # Create column groups
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("team"),
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=[
                        Column(title=i18n_service.get_text("position"), field="team_position", width=ColumnWidths.position, align="center", tooltip=i18n_service.get_text("position"), decimal_places=0),
                        Column(title=i18n_service.get_text("team"), field="team_name", width=ColumnWidths.team, align="left"),
                        Column(title=i18n_service.get_text("pins"), field="team_pins", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("points"), field="team_points", width=ColumnWidths.points, align="center", decimal_places=0)
                    ]
                ),
                ColumnGroup(
                    title=i18n_service.get_text("opponent"),
                    style={"backgroundColor": get_theme_color("surface_light")},
                    columns=[
                        Column(title=i18n_service.get_text("points"), field="opponent_points", width=ColumnWidths.points, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("pins"), field="opponent_pins", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("position"), field="opponent_position", width=ColumnWidths.position, align="center", tooltip=i18n_service.get_text("position"), decimal_places=0),
                        Column(title=i18n_service.get_text("opponent"), field="opponent_name", width=ColumnWidths.team, align="left")
                    ]
                )
            ]
            
            # Get individual player points for this round to add to team points
            individual_filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual player data
            }
            
            individual_data = self.adapter.get_filtered_data(filters=individual_filters)
            
            # Calculate individual points per team
            individual_points_by_team = {}
            if not individual_data.empty:
                for team in individual_data[Columns.team_name].unique():
                    team_individual = individual_data[individual_data[Columns.team_name] == team]
                    individual_points_by_team[team] = float(team_individual[Columns.points].sum()) if pd.notna(team_individual[Columns.points].sum()) else 0.0
            
            # Build data rows - group by team to find their opponent
            data = []
            processed_teams = set()
            
            for _, row in team_totals.iterrows():
                team_name = row[Columns.team_name]
                if team_name in processed_teams:
                    continue
                    
                opponent_name = row[Columns.team_name_opponent]
                team_pins = int(row[Columns.score]) if pd.notna(row[Columns.score]) else 0
                team_points = float(row[Columns.points]) if pd.notna(row[Columns.points]) else 0.0
                
                # Add individual points to team points
                individual_points = individual_points_by_team.get(team_name, 0.0)
                total_team_points = team_points + individual_points
                
                # Find opponent's totals
                opponent_row = team_totals[
                    (team_totals[Columns.team_name] == opponent_name) &
                    (team_totals[Columns.team_name_opponent] == team_name)
                ]
                
                if not opponent_row.empty:
                    opponent_pins = int(opponent_row[Columns.score].iloc[0]) if pd.notna(opponent_row[Columns.score].iloc[0]) else 0
                    opponent_team_points = float(opponent_row[Columns.points].iloc[0]) if pd.notna(opponent_row[Columns.points].iloc[0]) else 0.0
                    # Add opponent individual points
                    opponent_individual_points = individual_points_by_team.get(opponent_name, 0.0)
                    total_opponent_points = opponent_team_points + opponent_individual_points
                else:
                    opponent_pins = 0
                    total_opponent_points = 0.0
                
                # Get positions for both teams
                team_position = team_positions.get(team_name, None)
                opponent_position = team_positions.get(opponent_name, None)
                
                data.append([
                    team_position if team_position is not None else '',
                    team_name,
                    team_pins,
                    total_team_points,
                    total_opponent_points,
                    opponent_pins,
                    opponent_position if opponent_position is not None else '',
                    opponent_name
                ])
                
                processed_teams.add(team_name)
                processed_teams.add(opponent_name)
            
            # Heatmap coloring is now handled in the frontend
            return TableData(
                columns=columns,
                data=data,
                title=f"{league} - {i18n_service.get_text('week')} {week}, {i18n_service.get_text('game')} {round_number}",
                description=f"{i18n_service.get_text('match_results')} {season}",
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False,
                    "stripedColGroups": True
                }
            )
            
        except Exception as e:
            print(f"Error in get_game_overview_data: {e}")
            import traceback
            traceback.print_exc()
            return TableData(
                columns=[],
                data=[],
                title=f"Error loading game overview data"
            )

    def get_game_team_details_data(self, season: str, league: str, week: int, team: str, round_number: int) -> TableData:
        """
        Get game team details data for a specific team in a specific round.
        Shows individual player scores: Points, Player Name, Player Pins, Opponent Pins, Opponent Name
        Last row contains accumulated totals.
        
        Args:
            season: Season identifier
            league: League name
            week: Week number
            team: Team name
            round_number: Round/Game number
            
        Returns:
            TableData with player rows and totals row
        """
        try:
            print(f"get_game_team_details_data: season={season}, league={league}, week={week}, team={team}, round={round_number}")
            # Get individual player data for this team and round
            player_filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual player data
            }
            
            player_data = self.adapter.get_filtered_data(filters=player_filters)
            print(f"get_game_team_details_data: Found {len(player_data)} player rows")
            
            if player_data.empty:
                print(f"get_game_team_details_data: No player data found")
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available')} - {team}, {i18n_service.get_text('game')} {round_number}"
                )
            
            # Get opponent team name from first row
            if Columns.team_name_opponent not in player_data.columns:
                print(f"get_game_team_details_data: Column {Columns.team_name_opponent} not found in player_data")
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available')} - {team}, {i18n_service.get_text('game')} {round_number} (missing opponent column)"
                )
            
            # Extract opponent name and handle various edge cases
            opponent_name_raw = player_data[Columns.team_name_opponent].iloc[0] if not player_data.empty else ""
            # Convert to string and handle NaN/None values
            if pd.isna(opponent_name_raw) or opponent_name_raw is None:
                opponent_name = ""
            else:
                opponent_name = str(opponent_name_raw).strip()
            
            print(f"get_game_team_details_data: Opponent name = '{opponent_name}' (raw: {opponent_name_raw}, type: {type(opponent_name_raw)})")
            
            if not opponent_name or opponent_name == '' or opponent_name.lower() == 'nan':
                print(f"get_game_team_details_data: No opponent name found")
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available')} - {team}, {i18n_service.get_text('game')} {round_number} (no opponent found)"
                )
            
            # Get opponent player data
            opponent_filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.team_name: {'value': opponent_name, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}
            }
            
            print(f"get_game_team_details_data: Fetching opponent data for '{opponent_name}'")
            opponent_data = self.adapter.get_filtered_data(filters=opponent_filters)
            print(f"get_game_team_details_data: Found {len(opponent_data)} opponent rows")
            
            # Get team match points (Team Total row)
            team_total_filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}  # Team totals
            }
            team_total_data = self.adapter.get_filtered_data(filters=team_total_filters)
            team_match_points = 0.0
            if not team_total_data.empty and Columns.points in team_total_data.columns:
                team_match_points = float(team_total_data[Columns.points].iloc[0]) if pd.notna(team_total_data[Columns.points].iloc[0]) else 0.0
            
            # Get opponent team match points
            opponent_total_filters = {
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.team_name: {'value': opponent_name, 'operator': 'eq'},
                Columns.round_number: {'value': round_number, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}  # Team totals
            }
            opponent_total_data = self.adapter.get_filtered_data(filters=opponent_total_filters)
            opponent_match_points = 0.0
            if not opponent_total_data.empty and Columns.points in opponent_total_data.columns:
                opponent_match_points = float(opponent_total_data[Columns.points].iloc[0]) if pd.notna(opponent_total_data[Columns.points].iloc[0]) else 0.0
            
            # Create columns - two column groups: selected team and opposing team
            # Order: Player name, Pins, Points | Points, Pins, Player name
            columns = [
                ColumnGroup(
                    title=team,  # Selected team name
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=[
                        Column(title=i18n_service.get_text("player"), field="player_name", width=ColumnWidths.player, align="left"),
                        Column(title=i18n_service.get_text("pins"), field="player_pins", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("points"), field="points", width=ColumnWidths.points, align="center", decimal_places=0)
                    ]
                ),
                ColumnGroup(
                    title=opponent_name,  # Opposing team name
                    style={"backgroundColor": get_theme_color("surface_light")},
                    columns=[
                        Column(title=i18n_service.get_text("points"), field="opponent_points", width=ColumnWidths.points, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("pins"), field="opponent_pins", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("player"), field="opponent_player_name", width=ColumnWidths.player, align="left")
                    ]
                )
            ]
            
            # Build data rows - sort by position
            data = []
            if Columns.position not in player_data.columns:
                print(f"get_game_team_details_data: Column {Columns.position} not found in player_data")
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available')} - {team}, {i18n_service.get_text('game')} {round_number} (missing position column)"
                )
            
            player_data_sorted = player_data.sort_values(by=Columns.position)
            team_positions = {
                int(p)
                for p in pd.to_numeric(player_data[Columns.position], errors="coerce").dropna()
            }
            team_base = _lineup_base(team_positions)
            opponent_by_slot = _lineup_slot_lookup(opponent_data)
            
            total_points = 0.0
            total_player_pins = 0
            total_opponent_pins = 0
            
            total_opponent_points = 0.0
            
            for _, row in player_data_sorted.iterrows():
                try:
                    player_name = str(row[Columns.player_name]) if pd.notna(row[Columns.player_name]) else ""
                    player_pins = pinfall_display(row[Columns.score])
                    points = float(row[Columns.points]) if pd.notna(row[Columns.points]) else 0.0
                    position = int(row[Columns.position]) if pd.notna(row[Columns.position]) else 0
                    slot = position - team_base
                    
                    # Match opponent player at the same 0-based lineup slot
                    opponent_pins = 0
                    opponent_player_name = ""
                    opponent_points = 0.0
                    opponent_player = opponent_by_slot.get(slot)
                    if opponent_player is not None:
                        try:
                            if Columns.score in opponent_player.index:
                                opponent_pins = pinfall_display(opponent_player[Columns.score])
                            if Columns.player_name in opponent_player.index:
                                opponent_player_name = (
                                    str(opponent_player[Columns.player_name])
                                    if pd.notna(opponent_player[Columns.player_name])
                                    else ""
                                )
                            if Columns.points in opponent_player.index:
                                opponent_points = (
                                    float(opponent_player[Columns.points])
                                    if pd.notna(opponent_player[Columns.points])
                                    else 0.0
                                )
                        except (IndexError, KeyError, ValueError) as e:
                            print(f"get_game_team_details_data: Error getting opponent data for slot {slot}: {e}")
                    
                    data.append([
                        player_name,
                        player_pins,
                        points,
                        opponent_points,
                        opponent_pins,
                        opponent_player_name
                    ])
                    
                    total_points += points
                    total_player_pins += int(pinfall_for_total(row[Columns.score]))
                    if opponent_player is not None and Columns.score in opponent_player.index:
                        total_opponent_pins += int(pinfall_for_total(opponent_player[Columns.score]))
                    total_opponent_points += opponent_points
                except Exception as e:
                    print(f"get_game_team_details_data: Error processing player row: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Add team totals row (shows team name and team match points)
            data.append([
                team,  # Team name instead of "Total"
                total_player_pins,
                team_match_points,  # Team match points (0/3)
                opponent_match_points,  # Opponent team match points
                total_opponent_pins,
                opponent_name  # Opponent team name
            ])
            
            # Add final row with sum of all points (individual + team) for both teams
            total_all_points_team = total_points + team_match_points
            total_all_points_opponent = total_opponent_points + opponent_match_points
            data.append([
                "",  # Empty (player name column)
                "",  # Empty (pins column)
                total_all_points_team,  # Sum of individual + team points for team
                total_all_points_opponent,  # Sum of individual + team points for opponent
                "",  # Empty (pins column)
                ""  # Empty (player name column)
            ])
            
            return TableData(
                columns=columns,
                data=data,
                title=f"{team} - {i18n_service.get_text('week')} {week}, {i18n_service.get_text('game')} {round_number}",
                description=f"{i18n_service.get_text('individual_scores')} vs {opponent_name}",
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False,
                    "highlightLastRow": True
                }
            )
            
        except Exception as e:
            print(f"Error in get_game_team_details_data: {e}")
            import traceback
            traceback.print_exc()
            return TableData(
                columns=[],
                data=[],
                title=f"Error loading game team details data"
            )

    def get_league_standings(self, season: str, league: str, week: Optional[int] = None) -> LeagueStandings:
        """
        Get league standings for a specific season, league, and week.
        
        Args:
            season: The season identifier
            league: The league name
            week: The week number (if None, gets the latest week)
            
        Returns:
            LeagueStandings object with team performances
        """
        # If week is not specified, get the latest week
        if week is None:
            week = self.get_latest_week(season, league)
        
        print("week: ", week)

        # Get league statistics
        stats = self.stats_service.get_league_statistics(league, season)
        if not stats:
            return LeagueStandings(
                season=season,
                league_name=league,
                week=week,
                teams=[],
                last_updated=datetime.datetime.now().isoformat()
            )
        
        # Convert statistics to team performances
        team_performances = []
        for team_name, team_stats in stats.team_stats.items():
            # Get the latest weekly performance
            latest_week = max(team_stats.weekly_performances.keys())
            week_perf = team_stats.weekly_performances[latest_week]
            
            # Create weekly performances list
            weekly_performances = []
            for week_num, perf in team_stats.weekly_performances.items():
                weekly_performances.append(
                    TeamWeeklyPerformance(
                        team_id=perf.team_id,
                        team_name=perf.team_name,
                        week=week_num,
                        score=perf.total_score,
                        number_of_games=perf.number_of_games,
                        points=perf.points
                    )
                )
            
            # Sort weekly performances by week
            weekly_performances.sort(key=lambda x: x.week)
            
            # Create team performance
            team_performances.append(
                TeamSeasonPerformance(
                    team_id=week_perf.team_id,
                    team_name=team_name,
                    total_score=team_stats.season_summary.total_score,
                    total_points=team_stats.season_summary.total_points,
                    average=team_stats.season_summary.average_score,
                    weekly_performances=weekly_performances
                )
            )
        
        # Sort by total points (descending) and assign positions
        team_performances.sort(key=lambda x: (x.total_points, x.total_score), reverse=True)
        for i, perf in enumerate(team_performances, 1):
            perf.position = i
        
        # Create and return the LeagueStandings
        return LeagueStandings(
            season=season,
            league_name=league,
            week=week,
            teams=team_performances,
            last_updated=datetime.datetime.now().isoformat()
        )

    def _get_league_level(self, league: str) -> int:
        """Get the level of a league (delegates to utility function)"""
        return get_league_level(league)

    def get_league_performance_chart(self, season: str, league: str, team_id: Optional[str] = None) -> PlotData:
        """
        Get a chart showing team performance over time.
        
        Args:
            season: The season identifier
            league: The league name
            team_id: Optional team ID to highlight (if None, shows all teams)
            
        Returns:
            PlotData object with team performance data
        """
        # Get league standings
        standings = self.get_league_standings(season, league)
        
        if not standings.teams:
            return PlotData(
                title=f"{i18n_service.get_text('no_data_available_for')} {league} - {season}",
                series=[]
            )
        
        # Get all weeks in the season
        weeks = sorted(set(
            perf.week for team in standings.teams 
            for perf in team.weekly_performances
        ))
        
        # Prepare series data for each team
        series = []
        for team in standings.teams:
            # Skip teams that aren't the highlighted team (if specified)
            if team_id and team.team_id != team_id:
                continue
                
            # Create a map of week to points for this team
            week_to_points = {p.week: p.points for p in team.weekly_performances}
            
            # Calculate cumulative points for each week
            cumulative_points = []
            total = 0
            for week in weeks:
                total += week_to_points.get(week, 0)
                cumulative_points.append(total)
            
            # Add this team's series
            series.append({
                "name": team.team_name,
                "data": cumulative_points
            })
        
        # Create and return the PlotData
        return PlotData(
            title=f"{league} {i18n_service.get_text('team_performance')} - {season}",
            series=series,
            x_axis=weeks,
            y_axis_label=i18n_service.get_text("cumulative_points"),
            x_axis_label=i18n_service.get_text("week"),
            plot_type="line"
        )
    
    def get_league_summary_tiles(self, season: str, league: str) -> List[TileData]:
        """
        Get summary tiles for a league dashboard.
        
        Args:
            season: The season identifier
            league: The league name
            
        Returns:
            List of TileData objects with league summary information
        """
        # Get league standings
        standings = self.get_league_standings(season, league)
        
        if not standings.teams:
            return [
                TileData(
                    title=i18n_service.get_text("no_data"),
                    value=i18n_service.get_text("no_league_data_available"),
                    type="info"
                )
            ]
        
        # Create tiles
        tiles = []
        
        # League leader tile
        if standings.teams:
            leader = standings.teams[0]  # First team (highest points)
            tiles.append(
                TileData(
                    title=i18n_service.get_text("league_leader"),
                    value=leader.team_name,
                    subtitle=f"{leader.total_points} {i18n_service.get_text('points')}",
                    type="stat",
                    color="#28a745"  # Green
                )
            )
        
        # Average score tile
        if standings.teams:
            all_averages = [team.average for team in standings.teams]
            league_avg = sum(all_averages) / len(all_averages) if all_averages else 0
            tiles.append(
                TileData(
                    title=i18n_service.get_text("league_average"),
                    value=f"{league_avg:.1f}",
                    subtitle=i18n_service.get_text("pins_per_game"),
                    type="stat"
                )
            )
        
        # Weeks completed tile
        if standings.teams and standings.teams[0].weekly_performances:
            completed_weeks = len(set(p.week for p in standings.teams[0].weekly_performances))
            tiles.append(
                TileData(
                    title=i18n_service.get_text("weeks_completed"),
                    value=str(completed_weeks),
                    subtitle=f"of {completed_weeks + 2}",  # Assuming 2 more weeks to go
                    type="progress",
                    chart_data=[completed_weeks, completed_weeks + 2]
                )
            )
        
        return tiles
    
    def get_latest_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get the latest league events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of event dictionaries
        """
        # Import Columns dataclass
        from data_access.schema import Columns
        
        # Get all events from the adapter
        events_df = self.adapter.get_filtered_data(
            filters={},
            columns=[Columns.season, Columns.league_name, Columns.week, Columns.date]
        )
        
        # If no events, return empty list
        if events_df.empty:
            return []
        
        # Group by league, season, and week to get unique events
        # Take the first occurrence of each group (which will have the date)
        unique_events_df = events_df.groupby([Columns.league_name, Columns.season, Columns.week]).first().reset_index()
        
        # Sort by date (descending) to get the latest events
        unique_events_df = unique_events_df.sort_values(by=Columns.date, ascending=False)
        
        # Limit the results
        if limit is not None and limit > 0:
            unique_events_df = unique_events_df.head(limit)
        
        # Convert to list of dictionaries
        events = []
        for _, row in unique_events_df.iterrows():
            event = {
                "Season": row[Columns.season],
                "League": row[Columns.league_name],
                "Week": row[Columns.week],
                "Date": row[Columns.date]
            }
            events.append(event)
        
        return events

    def get_weeks(self, league_name: str = None, season: str = None) -> List[int]:
        """Get available weeks for a league and season"""
        #if not league_name or not season:
            # Return empty list if parameters are missing
        #    return []
        return self.adapter.get_weeks(season, league_name)

    def get_teams_in_league_season(self, league: str, season: str) -> List[str]:
        """Get teams in a specific league and season"""
        # Create a query to get all teams in this league and season
        query = LeagueQuery(season=season, league=league)
        
        # Get the data
        league_data = self.adapter.get_filtered_data(query.to_filter_dict())
        
        if league_data.empty:
            return []
        
        # Extract unique team names
        if 'Team' in league_data.columns:
            teams = sorted(league_data['Team'].unique().tolist())
            return teams
        
        return []

    def get_team_week_details_table_data(self, league: str, season: str, team: str, week: int) -> TableData:
        """Get team week details as a TableData object for rendering"""
        try:
            # Get individual player results for the team
            player_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}
            }
            
            player_data = self.adapter.get_filtered_data(filters=player_filters)
            
            if player_data.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available_for_team_week')} {team} - {i18n_service.get_text('week')} {week}"
                )
            
            # Get team totals (computed data)
            team_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}
            }
            
            team_data = self.adapter.get_filtered_data(filters=team_filters)
            
            # Get opponent team totals
            opponent_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name_opponent: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}
            }
            
            opponent_data = self.adapter.get_filtered_data(filters=opponent_filters)
            
            # Get individual opponent data to calculate average based on individual results
            opponent_individual_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name_opponent: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual data, not computed
            }
            
            opponent_individual_data = self.adapter.get_filtered_data(filters=opponent_individual_filters)
            
            # Round numbers: coerce to int for stable column field keys. Pipeline CSV often has
            # floats (1.0); Tabulator's nestedFieldSeparator is ".", so fields like "game1.0_score"
            # resolve as nested paths and cells render empty. Use integer game keys: game1_score, …
            rn = Columns.round_number

            def _matches_round(df: pd.DataFrame, game_int: int) -> pd.Series:
                return pd.to_numeric(df[rn], errors="coerce").eq(float(game_int))

            games = sorted(
                int(x) for x in pd.to_numeric(player_data[rn], errors="coerce").dropna().unique()
            )

            # Create a mapping of round_number to opponent team name
            game_to_opponent = {}
            for game in games:
                game_data = player_data[_matches_round(player_data, game)]
                if not game_data.empty:
                    opponent_name = game_data[Columns.team_name_opponent].iloc[0]
                    game_to_opponent[game] = opponent_name
            
            # Create column groups
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("player"),
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=[
                        Column(title=i18n_service.get_text("position"), field="position", width=ColumnWidths.position, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("name"), field="name", width=ColumnWidths.player, align="left")
                    ]
                )
            ]
            
            # Add game column groups with opponent team names
            for game in games:
                opponent_name = game_to_opponent.get(game, f"{i18n_service.get_text('game')} {game}")
                columns.append(
                    ColumnGroup(
                        title=opponent_name,
                        columns=[
                            Column(title=i18n_service.get_text("pins"), field=f"game{game}_score", width=ColumnWidths.pins, align="center", decimal_places=0),
                            Column(title=i18n_service.get_text("points"), field=f"game{game}_points", width=ColumnWidths.points, align="center", decimal_places=0)
                        ]
                    )
                )
            
            # Add totals column group
            columns.append(
                ColumnGroup(
                    title=i18n_service.get_text("total"),
                    style={"backgroundColor": get_theme_color("surface_alt")},
                    header_style={"fontWeight": "bold"},
                    columns=[
                        Column(title=i18n_service.get_text("points"), field="total_points", width=ColumnWidths.points, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("score"), field="total_score", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("avg"), field="average", width=ColumnWidths.average, align="center", decimal_places=1)
                    ]
                )
            )
            
            # Prepare data rows with merged position cells
            data = []
            row_metadata = []
            
            # Get all unique players who played in this event (same logic as New view)
            player_identifiers = []
            for _, row in player_data.iterrows():
                player_id = row[Columns.player_id] if not pd.isnull(row[Columns.player_id]) else row[Columns.player_name]
                player_name = row[Columns.player_name]
                # Create a unique identifier combining ID and name
                identifier = f"{player_id}_{player_name}"
                if identifier not in [p['identifier'] for p in player_identifiers]:
                    player_identifiers.append({
                        'identifier': identifier,
                        'player_id': player_id,
                        'player_name': player_name
                    })
            
            # Create player-position combinations
            player_position_combinations = []
            for player_info in player_identifiers:
                # Find all rows for this player
                player_rows = player_data[
                    (player_data[Columns.player_id] == player_info['player_id']) | 
                    (player_data[Columns.player_name] == player_info['player_name'])
                ]
                
                # Get all positions this player played
                positions = sorted(player_rows[Columns.position].dropna().unique())
                
                for position in positions:
                    player_position_combinations.append({
                        'player_info': player_info,
                        'position': position,
                        'player_rows': player_rows[player_rows[Columns.position] == position]
                    })
            
            # Sort by position first, then by player name
            player_position_combinations.sort(key=lambda x: (x['position'], x['player_info']['player_name']))
            
            # Group by position for merging
            position_groups = {}
            for combo in player_position_combinations:
                position = combo['position']
                if position not in position_groups:
                    position_groups[position] = []
                position_groups[position].append(combo)
            
            # Create merged data structure
            for position in sorted(position_groups.keys()):
                position_combos = position_groups[position]
                
                # Add first row of this position group with position number
                first_combo = position_combos[0]
                player_info = first_combo['player_info']
                player_rows = first_combo['player_rows']
                
                # Start with position and name
                row = [int(position + 1), player_info['player_name']]
                
                # Add game data - only fill if player participated in this position
                for game in games:
                    game_data = player_rows[_matches_round(player_rows, game)]
                    
                    if not game_data.empty:
                        row.append(int(game_data[Columns.score].iloc[0]))
                        row.append(round(float(game_data[Columns.points].iloc[0]), 1))
                    else:
                        row.append("")
                        row.append("")
                
                # Calculate totals for this player-position combination
                total_points = int(player_rows[Columns.points].sum()) if not player_rows.empty else 0
                total_score = sum_scores(player_rows[Columns.score]) if not player_rows.empty else 0
                average = mean_scores(player_rows[Columns.score], round_places=1) if not player_rows.empty else 0
                
                row.extend([total_points, total_score, average])
                
                # Add metadata for styling
                row_metadata.append({
                    'rowType': 'player',
                    'styling': {},
                    'position': int(position),
                    'isFirstInPosition': True,
                    'positionRowspan': len(position_combos)
                })
                
                data.append(row)
                
                # Add remaining rows for this position (without position number)
                for combo in position_combos[1:]:
                    player_info = combo['player_info']
                    player_rows = combo['player_rows']
                    
                    # Start with empty position and name
                    row = ["", player_info['player_name']]
                    
                    # Add game data - only fill if player participated in this position
                    for game in games:
                        game_data = player_rows[_matches_round(player_rows, game)]
                        
                        if not game_data.empty:
                            row.append(int(game_data[Columns.score].iloc[0]))
                            row.append(round(float(game_data[Columns.points].iloc[0]), 1))
                        else:
                            row.append("")
                            row.append("")
                    
                    # Calculate totals for this player-position combination
                    total_points = int(player_rows[Columns.points].sum()) if not player_rows.empty else 0
                    total_score = sum_scores(player_rows[Columns.score]) if not player_rows.empty else 0
                    average = mean_scores(player_rows[Columns.score], round_places=1) if not player_rows.empty else 0
                    
                    row.extend([total_points, total_score, average])
                    
                    # Add metadata for styling
                    row_metadata.append({
                        'rowType': 'player',
                        'styling': {},
                        'position': int(position),
                        'isFirstInPosition': False
                    })
                    
                    data.append(row)
            
            # Add team total row
            if not team_data.empty:
                # Start with position and name
                team_row = ["Team", team]
                
                # Add game data for team
                for game in games:
                    game_data = team_data[_matches_round(team_data, game)]
                    if not game_data.empty:
                        team_row.append(int(game_data[Columns.score].iloc[0]))
                        team_row.append(round(float(game_data[Columns.points].iloc[0]), 1))
                    else:
                        team_row.append(0)
                        team_row.append(0)
                
                # Calculate team totals
                team_row.append(int(team_data[Columns.points].sum()))
                team_row.append(sum_scores(team_data[Columns.score]))
                team_row.append(mean_scores(player_data[Columns.score], round_places=1) if len(player_data) > 0 else 0)
                
                # Add metadata for styling
                row_metadata.append({
                    'rowType': 'team',
                    'separator_before': True,
                    'styling': {
                        'fontWeight': 'bold'
                    }
                })
                
                data.append(team_row)
            
            # Add opponent total row right after team row
            if not opponent_data.empty:
                # Start with position and name
                opponent_row = ["Team", "Opponents"]
                
                # Add game data for opponents
                for game in games:
                    game_data = opponent_data[_matches_round(opponent_data, game)]
                    if not game_data.empty:
                        opponent_row.append(int(game_data[Columns.score].iloc[0]))
                        opponent_row.append("")  # Replace opponent points with empty string
                    else:
                        opponent_row.append(0)
                        opponent_row.append("")
                
                # Calculate opponent totals
                opponent_row.append("")  # Replace opponent total points with empty string
                opponent_row.append(sum_scores(opponent_data[Columns.score]))
                
                # Calculate opponent average based on individual results
                if not opponent_individual_data.empty:
                    opponent_average = mean_scores(opponent_individual_data[Columns.score], round_places=1)
                else:
                    opponent_average = 0
                
                opponent_row.append(opponent_average)
                
                # Add metadata for styling
                row_metadata.append({
                    'rowType': 'opponents',
                    'styling': {}
                })
                
                data.append(opponent_row)
            
            # Add Total row that sums all points (individual + team)
            total_row = ["Total", "Points"]
            
            # Calculate total points for each game (individual + team)
            for game in games:
                game_player_data = player_data[_matches_round(player_data, game)]
                game_team_data = team_data[_matches_round(team_data, game)] if not team_data.empty else None
                
                # Individual points for this game
                game_points_total = round(float(game_player_data[Columns.points].sum()), 1) if not game_player_data.empty else 0
                
                # Add team points for this game if available
                if game_team_data is not None and not game_team_data.empty:
                    game_points_total += round(float(game_team_data[Columns.points].iloc[0]), 1)
                
                # Add empty string for score and points for this game
                total_row.extend(["", game_points_total])
            
            # Calculate overall totals (individual + team)
            total_points = int(player_data[Columns.points].sum())
            if not team_data.empty:
                total_points += int(team_data[Columns.points].sum())
            
            total_row.extend([total_points, "", ""])  # Replace score and average with empty strings
            
            # Add metadata for styling
            row_metadata.append({
                'rowType': 'total',
                'separator_before': True,
                'styling': {
                    'fontWeight': 'bold',
                    'borderBottom': '2px solid #000000'
                }
            })
            
            data.append(total_row)
            
            return TableData(
                columns=columns,
                data=data,
                row_metadata=row_metadata,
            title=f"{team} - {i18n_service.get_text('match_day')} {week}",
            description=f"{i18n_service.get_text('score_sheet_for')} {team} in {league} - {season}",
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False
                }
            )
            
        except Exception as e:
            print(f"Error in get_team_week_details_table_data: {e}")
            return TableData(
                columns=[],
                data=[],
                title=f"{i18n_service.get_text('error_loading_data_for')} {team} - {i18n_service.get_text('week')} {week}"
            )

    def get_team_averages_during_season(self, league_name: str, season: str) -> Dict[str, Any]:
        """Get team averages throughout a season"""
        # Get all teams and their performances
        standings = self.get_league_standings(season, league_name)
        
        if not standings.teams:
            return SeriesData().to_dict()
        
        series_data = SeriesData(label_x_axis="Spieltag", label_y_axis="Durchschnitt", name="Durchschnitt im Saisonverlauf", 
                                 query_params={"season": season, "league": league_name})
        
        for team in standings.teams:
            # Calculate average for each week
            averages = []
            for perf in team.weekly_performances:
                if perf.score > 0 and perf.number_of_games > 0:
                    # Calculate team average: total pins divided by number of games
                    # perf.score is the total pins of all players on the team for this week
                    # perf.number_of_games is the number of games played by all players on the team for this week
                    avg = perf.score / perf.number_of_games
                    averages.append(round(avg, 2))
                else:
                    averages.append(0)
            
            series_data.add_data(team.team_name, averages)

        return series_data.to_dict()

    def get_team_positions_during_season(self, league_name: str, season: str) -> Dict[str, List[int]]:
        """Get team positions throughout a season"""
        # Get all teams and their performances
        standings = self.get_league_standings(season, league_name)
        
        if not standings.teams:
            return {}
        
        # Get all weeks in the season
        all_weeks = sorted(set(
            perf.week for team in standings.teams 
            for perf in team.weekly_performances
        ))

        series_data = SeriesData(label_x_axis="Spieltag", label_y_axis="Position", name="Position im Saisonverlauf", 
                                 query_params={"season": season, "league": league_name})
        points_per_team = {}
        points_per_team_accumulated = {}
        for team in standings.teams:
            points_per_team[team.team_name] = [p.points for p in team.weekly_performances]
            points_per_team_accumulated[team.team_name] = list(accumulate(points_per_team[team.team_name]))
        

        position_per_week = {team_name: [] for team_name in points_per_team.keys()}
        position_per_week_accumulated = {team_name: [] for team_name in points_per_team.keys()}
        # create a tuple of team name and points per week and sort it by points

        for week in all_weeks:
            week = week - 1

            # create a tuple of team name and points per week
            team_points_week = [(team_name, points_per_team[team_name][week]) for team_name in points_per_team.keys()]
            # sort it by points
            team_points_week.sort(key=lambda x: x[1], reverse=True)

            # create a tuple of team name and points accumulated per week
            team_points_week_accumulated = [(team_name, points_per_team_accumulated[team_name][week]) for team_name in points_per_team.keys()]
            # sort it by points
            team_points_week_accumulated.sort(key=lambda x: x[1], reverse=True)

            # position per week
            for idx, team_n_points in enumerate(team_points_week):
                # find position of team_name in points_per_team[team_name]

                position_per_week[team_n_points[0]].append(idx+1)

            for idx, team_n_points in enumerate(team_points_week_accumulated):
                # position per week accumulated
                # find position of team_name in points_per_team_accumulated[team_name]
                #position_accumulated = team_points_week_accumulated.index(team_name) + 1
                position_per_week_accumulated[team_n_points[0]].append(idx+1)

            # position per week accumulated

        # add the data to the series data
        for team in standings.teams:
            series_data.add_data(team.team_name, position_per_week[team.team_name])
            # replace auto generated accumulated data             
            series_data.data_accumulated[team.team_name] = position_per_week_accumulated[team.team_name]

        return series_data.to_dict()


    
        # Calculate positions for each week
        positions = {}
        
        for week in all_weeks:
            # Get performances for this week
            week_performances = []
            for team in standings.teams:
                perf = next((p for p in team.weekly_performances if p.week == week), None)
                if perf:
                    week_performances.append({
                        "team": team.team_name,
                        "points": perf.points,
                        "score": perf.score
                    })
            
            # Sort by points (and score as tiebreaker)
            week_performances.sort(key=lambda x: (x["points"], x["score"]), reverse=True)
            
            # Assign positions
            for i, perf in enumerate(week_performances, 1):
                team_name = perf["team"]
                if team_name not in positions:
                    positions[team_name] = [0] * len(all_weeks)
                
                # Find the index for this week
                week_index = all_weeks.index(week)
                positions[team_name][week_index] = i
        
        return positions

    def get_honor_scores(self, league: str, season: str, week: int, 
                        number_of_individual_scores: int = 3, number_of_team_scores: int = 3,
                        number_of_individual_averages: int = 3, number_of_team_averages: int = 3) -> Dict[str, Any]:
        """Get honor scores for a specific week"""
        if self._warm_slice_cache is not None:
            league_data_individual = self._filter_dataframe_week(
                self._season_league_dataframe(league, season, computed_data=False),
                week,
            )
            league_data_team = self._filter_dataframe_week(
                self._season_league_dataframe(league, season, computed_data=True),
                week,
            )
        else:
            query_individual = LeagueQuery(season=season, league=league, week=week, computed_data=False)
            query_team = LeagueQuery(season=season, league=league, week=week, computed_data=True)
            league_data_individual = self.adapter.get_filtered_data(query_individual.to_filter_dict())
            league_data_team = self.adapter.get_filtered_data(query_team.to_filter_dict())
        
        if league_data_individual.empty:
            return {
                "individual_scores": [],
                "team_scores": [],
                "individual_averages": [],
                "team_averages": []
            }
        
        # Process individual scores
        individual_scores_list = []
        if Columns.player_name in league_data_individual.columns and Columns.score in league_data_individual.columns:
            player_scores = league_data_individual.sort_values(Columns.score, ascending=False).head(number_of_individual_scores)

            for _, row in player_scores.iterrows():
                individual_scores_list.append({
                    "player": row[Columns.player_name] + " (" + row[Columns.team_name] + ")",
                    "score": row[Columns.score]
                })

        # Process team scores
        team_scores_list = []
        if Columns.team_name in league_data_team.columns and Columns.score in league_data_team.columns:
            team_scores = league_data_team.sort_values(Columns.score, ascending=False).head(number_of_team_scores)
            
            for _, row in team_scores.iterrows():
                team_scores_list.append({
                    "team": row[Columns.team_name],
                    "score": row[Columns.score]
                })
        
        # Process individual averages
        individual_averages_list = []
        if Columns.player_name in league_data_individual.columns and Columns.score in league_data_individual.columns:
            player_averages = (
                league_data_individual.groupby([Columns.player_name, Columns.team_name])[Columns.score]
                .apply(lambda s: mean_scores(s))
                .reset_index(name=Columns.score)
            )
            player_averages = player_averages.sort_values(Columns.score, ascending=False).head(number_of_individual_averages)
            
            for _, row in player_averages.iterrows():
                individual_averages_list.append({
                    "player": row[Columns.player_name] + " (" + row[Columns.team_name] + ")",
                    "average": round(row[Columns.score], 2)
                })

        # Process team averages
        team_averages_list = []
        if Columns.team_name in league_data_team.columns and Columns.score in league_data_team.columns:
            league_data_team = league_data_team.copy()
            league_data_team[Columns.score] = pd.to_numeric(league_data_team[Columns.score], errors="coerce")
            if Columns.players_per_team in league_data_team.columns:
                league_data_team[Columns.players_per_team] = pd.to_numeric(
                    league_data_team[Columns.players_per_team], errors="coerce"
                )
            team_averages = (
                league_data_team.groupby([Columns.team_name, Columns.players_per_team])[Columns.score]
                .apply(lambda s: mean_scores(s))
                .reset_index(name=Columns.score)
            )
            team_averages = team_averages.sort_values(Columns.score, ascending=False).head(number_of_team_averages)
            
            for _, row in team_averages.iterrows():
                players_per_team = row.get(Columns.players_per_team)
                avg = None
                if pd.notna(players_per_team) and float(players_per_team) != 0:
                    avg = float(row[Columns.score]) / float(players_per_team)
                team_averages_list.append({
                    "team": row[Columns.team_name],
                    "average": round(avg, 2) if avg is not None else 0.0
                })

        return {
            "individual_scores": individual_scores_list,
            "team_scores": team_scores_list,
            "individual_averages": individual_averages_list,
            "team_averages": team_averages_list
        }

    def get_league_history_table_data(self, league_name: str, season: str, week: Optional[int] = None) -> TableData:
        """
        Get league history as a TableData object for rendering.
        
        Args:
            league_name: The league name
            season: The season identifier
            week: The week number (if None, gets the latest)
            
        Returns:
            TableData object with the league history
        """
        return self.get_league_table_simple(season=season, league=league_name, week=week, include_history=True)

    def get_team_averages_simple(self, league_name: str, season: str) -> Dict[str, Any]:
        """Get team averages throughout a season - simple direct query approach"""
        try:
            team_data = self._season_league_dataframe(league_name, season, computed_data=False)
            
            if team_data.empty:
                return SeriesData(
                    label_x_axis="Spieltag", 
                    label_y_axis="Durchschnitt", 
                    name="Durchschnitt im Saisonverlauf", 
                    query_params={"season": season, "league": league_name, "computed_data": False}
                ).to_dict()
            
            # Group by team and week to calculate averages
            series_data = SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Durchschnitt", 
                name="Durchschnitt im Saisonverlauf", 
                query_params={"season": season, "league": league_name}
            )
            
            # Get all teams and weeks
            teams = team_data[Columns.team_name].unique()
            weeks = sorted(
                {
                    int(round(float(w)))
                    for w in team_data[Columns.week].unique()
                    if pd.notna(w)
                }
            )
            
            for team in teams:
                team_week_data = team_data[team_data[Columns.team_name] == team]
                averages = []
                
                for week in weeks:
                    week_data = team_week_data[team_week_data[Columns.week] == week]
                    
                    if not week_data.empty:
                        averages.append(mean_scores(week_data[Columns.score], round_places=2))
                    else:
                        averages.append(0)
                
                series_data.add_data(team, averages)
            
            return series_data.to_dict()
            
        except Exception as e:
            print(f"Error in get_team_averages_simple: {e}")
            return SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Durchschnitt", 
                name="Durchschnitt im Saisonverlauf", 
                query_params={"season": season, "league": league_name}
            ).to_dict()

    def get_league_week_table_simple(self, season: str, league: str, week: Optional[int] = None) -> TableData:
        """
        Get a simplified league week table with direct data query.
        
        Args:
            season: The season identifier
            league: The league name
            week: The current week (if None, gets the latest)
            
        Returns:
            TableData object with the league standings
        """
        return self.get_league_table_simple(season=season, league=league, week=week, include_history=False)

    def get_league_table_simple(self, season: str, league: str, week: Optional[int] = None, include_history: bool = False) -> TableData:
        """
        Get a simplified league table with direct data query.
        Can handle both single week and multiple weeks (history).
        
        Args:
            season: The season identifier
            league: The league name
            week: The current week (if None, gets the latest)
            include_history: If True, shows all weeks up to the selected week
            
        Returns:
            TableData object with the league standings
        """
        try:
            # If week is not specified, get the latest week
            if week is None:
                week = self.get_latest_week(season, league)
            week = int(week)

            individual_data = self._season_league_dataframe(league, season, computed_data=False)
            team_bonus_data = self._season_league_dataframe(league, season, computed_data=True)
            
            # Use individual data for the main league data (scores and averages)
            league_data = individual_data
            
            if league_data.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available_for')} {league} - {season}"
                )
            
            # Get teams and weeks (integer week indices — avoids float 1.0 vs int 1 mismatches)
            teams = league_data[Columns.team_name].unique()
            all_weeks = sorted(
                {
                    int(round(float(w)))
                    for w in league_data[Columns.week].unique()
                    if pd.notna(w)
                }
            )

            # Determine which weeks to show
            if include_history:
                weeks_to_show = [w for w in all_weeks if w <= week]
            else:
                weeks_to_show = [week]
            
            # Calculate data for each team
            team_data = {}
            
            for team in teams:
                team_data[team] = {
                    'weekly_data': {},
                    'season_score': 0,
                    'season_points': 0,
                    'season_avg': 0
                }
                
                # Initialize variables to avoid "referenced before assignment" errors
                team_bonus_team_data = pd.DataFrame()
                
                # Get individual player data for this team (for scores and averages)
                team_individual_data = individual_data[individual_data[Columns.team_name] == team]
                
                # Get team bonus data for this team (for team points only)
                if Columns.team_name in team_bonus_data.columns:
                    team_bonus_team_data = team_bonus_data[team_bonus_data[Columns.team_name] == team]
                else:
                    team_bonus_team_data = pd.DataFrame()
                
                # Calculate season totals (accumulated up to selected week)
                if not team_individual_data.empty:
                    # Filter individual data up to selected week
                    team_individual_until_week = team_individual_data[team_individual_data[Columns.week] <= week]
                    team_data[team]['season_score'] = sum_scores(team_individual_until_week[Columns.score])
                    team_data[team]['season_points'] = float(team_individual_until_week[Columns.points].sum())
                    
                    # Calculate season average based on individual scores
                    if len(team_individual_until_week) > 0:
                        team_data[team]['season_avg'] = mean_scores(team_individual_until_week[Columns.score], round_places=1)
                
                # Add team bonus points to season total (up to selected week)
                if not team_bonus_team_data.empty:
                    team_bonus_until_week = team_bonus_team_data[team_bonus_team_data[Columns.week] <= week]
                    team_data[team]['season_points'] += sum_league_points(team_bonus_until_week)
                
                # Calculate weekly data
                for w in weeks_to_show:
                    team_week_individual = team_individual_data[team_individual_data[Columns.week] == w]
                    team_week_bonus = team_bonus_team_data[team_bonus_team_data[Columns.week] == w]
                    
                    if not team_week_individual.empty:
                        week_score = sum_scores(team_week_individual[Columns.score])
                        week_points = float(team_week_individual[Columns.points].sum())
                        week_avg = week_score / len(team_week_individual) if len(team_week_individual) > 0 else 0
                        
                        # Add team bonus points for this week
                        if not team_week_bonus.empty:
                            week_points += sum_league_points(team_week_bonus)
                        
                        team_data[team]['weekly_data'][w] = {
                            'points': format_float_one_decimal(week_points),
                            'score': week_score,
                            'avg': round(week_avg, 1)
                        }
                    else:
                        team_data[team]['weekly_data'][w] = {
                            'points': 0,
                            'score': 0,
                            'avg': 0
                        }
            
            # Sort teams: first by season_points (descending), then by season_score (descending) as tiebreaker
            # When points are equal, team with higher score (pins) should rank higher
            sorted_teams = sorted(
                teams,
                key=lambda t: (
                    float(team_data[t]['season_points'] or 0),
                    float(team_data[t]['season_score'] or 0)
                ),
                reverse=True
            )
            
            # Create column groups
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("ranking"),
                    frozen="left",
                    columns=[
                        Column(title="#", field="pos", width=ColumnWidths.position, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left")
                    ]
                )
            ]
            
            # Add totals column group first (after ranking) - matches data order
            columns.append(
                ColumnGroup(
                    title=i18n_service.get_text("season"),
                    highlighted=True,  # Highlight the Total group
                    columns=[
                        Column(title=i18n_service.get_text("points"), field="season_points", width=ColumnWidths.points, decimal_places=1, align="center"),
                        Column(title=i18n_service.get_text("pins"), field="season_score", width=ColumnWidths.pins, decimal_places=0, align="center"),
                        Column(title=i18n_service.get_text("average"), field="season_avg", width=ColumnWidths.average, decimal_places=1, align="center")
                    ]
                )
            )

            # Add weekly column groups after totals
            for w in weeks_to_show:
                columns.append(
                    ColumnGroup(
                        title=f"{i18n_service.get_text('week')} {w}",
                        columns=[
                            Column(title=i18n_service.get_text("points"), field=f"week{w}_points", width=ColumnWidths.points, decimal_places=1),
                            Column(title=i18n_service.get_text("score"), field=f"week{w}_score", width=ColumnWidths.pins, decimal_places=0),
                            Column(title=i18n_service.get_text("average"), field=f"week{w}_avg", width=ColumnWidths.average, decimal_places=1)
                        ]
                    )
                )

            
            # Prepare the data rows
            data = []
            for i, team in enumerate(sorted_teams, 1):
                team_info = team_data[team]
                
                # Start with position and team name
                row = [i, team]
                
                # Add season totals first (matches column order: Ranking -> Totals -> Weeks)
                row.extend([
                    format_float_one_decimal(team_info['season_points']),
                    team_info['season_score'],
                    format_float_one_decimal(team_info['season_avg'])
                ])
                
                # Add weekly data after totals
                for w in weeks_to_show:
                    week_info = team_info['weekly_data'][w]
                    row.extend([
                        format_float_one_decimal(week_info['points']),
                        week_info['score'],
                        format_float_one_decimal(week_info['avg'])
                    ])
                
                data.append(row)
            
            # Create and return the TableData
            if include_history:
                title = f"{league} {i18n_service.get_text('league_history')} - {season}"
                description = f"{i18n_service.get_text('through_week')} {week}"
            else:
                title = f"{league} {i18n_service.get_text('league_standings')} - {season}"
                description = f"{i18n_service.get_text('week_results')}"
            
            return TableData(
                columns=columns,
                data=data,
                title=title,
                description=description,
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False,
                    "stripedColGroups": True
                }
            )
            
        except Exception as e:
            print(f"Error in get_league_table_simple: {e}")
            return TableData(
                columns=[],
                data=[],
                title=f"Error loading data for {league} - {season}"
            )

    def _teams_in_standings_order(
        self, league: str, season: str, week: Optional[int] = None
    ) -> List[str]:
        """Teams sorted like ``get_league_table_simple`` (cumulative points, pins tiebreak)."""
        individual_filters = {
            Columns.league_name: {"value": league, "operator": "eq"},
            Columns.season: {"value": season, "operator": "eq"},
            Columns.computed_data: {"value": False, "operator": "eq"},
        }
        individual_data = self.adapter.get_filtered_data(filters=individual_filters)
        if individual_data is None or individual_data.empty:
            return []

        team_bonus_filters = {
            Columns.league_name: {"value": league, "operator": "eq"},
            Columns.season: {"value": season, "operator": "eq"},
            Columns.computed_data: {"value": True, "operator": "eq"},
        }
        team_bonus_data = self.adapter.get_filtered_data(filters=team_bonus_filters)
        if team_bonus_data is None:
            team_bonus_data = pd.DataFrame()

        teams = list(individual_data[Columns.team_name].dropna().astype(str).unique())
        week_cap: Optional[int] = int(week) if week is not None else None

        totals: Dict[str, tuple] = {}
        for team in teams:
            t_ind = individual_data[individual_data[Columns.team_name] == team]
            if week_cap is not None:
                t_ind = t_ind[pd.to_numeric(t_ind[Columns.week], errors="coerce") <= week_cap]
            season_score = sum_scores(t_ind[Columns.score]) if not t_ind.empty else 0
            season_points = float(t_ind[Columns.points].sum()) if not t_ind.empty else 0.0
            if not team_bonus_data.empty and Columns.team_name in team_bonus_data.columns:
                t_bonus = team_bonus_data[team_bonus_data[Columns.team_name] == team]
                if week_cap is not None:
                    t_bonus = t_bonus[pd.to_numeric(t_bonus[Columns.week], errors="coerce") <= week_cap]
                if not t_bonus.empty:
                    season_points += sum_league_points(t_bonus)
            totals[team] = (season_points, season_score)

        return sorted(teams, key=lambda t: totals.get(t, (0.0, 0)), reverse=True)

    def get_team_positions_simple(self, league_name: str, season: str) -> Dict[str, Any]:
        """Get team positions throughout a season using direct data adapter queries"""
        # Get weekly points from get_team_points_simple
        points_data = self.get_team_points_simple(league_name, season)
        
        if not points_data or 'data' not in points_data:
            return SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Position", 
                name="Position im Saisonverlauf", 
                query_params={"season": season, "league": league_name}
            ).to_dict()
        
        # Extract weekly points from the SeriesData
        weekly_points = points_data.get('data', {})
        all_teams = list(weekly_points.keys())
        all_weeks = list(range(1, len(next(iter(weekly_points.values()), [])) + 1)) if weekly_points else []
        
        if not all_teams:
            return SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Position", 
                name="Position im Saisonverlauf", 
                query_params={"season": season, "league": league_name}
            ).to_dict()
        
        # Create SeriesData for positions
        series_data = SeriesData(
            label_x_axis="Spieltag", 
            label_y_axis="Position", 
            name="Position im Saisonverlauf", 
            query_params={"season": season, "league": league_name}
        )
        
        # Calculate positions for each week
        positions_per_team = {team: [] for team in all_teams}
        
        for week_idx, week in enumerate(all_weeks):
            # Get accumulated points up to this week for each team
            accumulated_points = {}
            for team in all_teams:
                accumulated_points[team] = sum(weekly_points[team][:week_idx + 1])
            
            # Sort teams by accumulated points (descending) for this week
            sorted_teams = sorted(accumulated_points.items(), key=lambda x: x[1], reverse=True)
            
            # Create a mapping of team to position for this week
            week_positions = {}
            for pos, (team, _) in enumerate(sorted_teams, 1):
                week_positions[team] = pos
            
            # Add the position for this week to each team's list
            for team in all_teams:
                positions_per_team[team].append(week_positions[team])
        
        # Add data for each team using the proper add_data method
        for team in all_teams:
            series_data.add_data(team, positions_per_team[team])
        
        return series_data.to_dict()

    def get_team_points_simple(self, league_name: str, season: str) -> Dict[str, Any]:
        """Get team points throughout a season using direct data adapter queries"""
        individual_data = self._season_league_dataframe(league_name, season, computed_data=False)
        team_data = self._season_league_dataframe(league_name, season, computed_data=True)
        
        if individual_data.empty and team_data.empty:
            return SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Punkte", 
                name="Punkte im Saisonverlauf", 
                query_params={"season": season, "league": league_name}
            ).to_dict()
        
        # Get all weeks and teams (from individual data for weeks, from both for teams)
        all_weeks = (
            sorted(
                {
                    int(round(float(w)))
                    for w in individual_data[Columns.week].unique()
                    if pd.notna(w)
                }
            )
            if not individual_data.empty
            else []
        )
        all_teams_individual = set(individual_data[Columns.team_name].unique()) if not individual_data.empty else set()
        all_teams_team = set(team_data[Columns.team_name].unique()) if not team_data.empty else set()
        all_teams = sorted(all_teams_individual | all_teams_team)
        
        # Calculate weekly points for each team (individual + team points)
        weekly_points = {}
        for team in all_teams:
            weekly_points[team] = []
            for week in all_weeks:
                # Get individual player points for this team and week
                individual_week_data = individual_data[(individual_data[Columns.team_name] == team) & (individual_data[Columns.week] == week)]
                individual_points = individual_week_data[Columns.points].sum() if not individual_week_data.empty else 0
                
                # Get team bonus points for this team and week
                team_week_data = team_data[(team_data[Columns.team_name] == team) & (team_data[Columns.week] == week)]
                team_points = sum_league_points(team_week_data) if not team_week_data.empty else 0
                
                # Total points = individual + team (match + bonus columns)
                total_week_points = individual_points + team_points
                weekly_points[team].append(total_week_points)
        
        # Create SeriesData
        series_data = SeriesData(
            label_x_axis="Spieltag", 
            label_y_axis="Punkte", 
            name="Punkte im Saisonverlauf", 
            query_params={"season": season, "league": league_name}
        )
        
        # Add data for each team
        for team in all_teams:
            series_data.add_data(team, weekly_points[team])
        
        return series_data.to_dict()

    def get_team_week_head_to_head_table_data(self, league: str, season: str, team: str, week: int, view_mode: str = 'own_team') -> TableData:
        """
        Get head-to-head comparison table data for a team vs their opponents in a specific week.
        view_mode: 'own_team' (default), 'opponents', 'full'
        """
        try:
            # Get all matches for the team in this week
            team_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}
            }
            team_data = self.adapter.get_filtered_data(filters=team_filters)
            if team_data.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"{i18n_service.get_text('no_data_available_for_team_week')} {team} - {i18n_service.get_text('week')} {week}"
                )
            
            # Get all matches for the opponent teams in this week
            opponent_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name_opponent: {'value': team, 'operator': 'eq'},
                Columns.week: {'value': week, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}
            }
            opponent_data = self.adapter.get_filtered_data(filters=opponent_filters)
            
            # Get unique round numbers (matches)
            all_rounds = sorted(set(team_data[Columns.round_number].unique()) | set(opponent_data[Columns.round_number].unique()))

            # --- Determine which players to show ---
            show_own = view_mode in ('own_team', 'full')
            show_opp = view_mode in ('opponents', 'full')

            # Get unique players for each side
            own_players = team_data[Columns.player_name].unique() if show_own else []
            opp_players = opponent_data[Columns.player_name].unique() if show_opp else []

            # Build player participation map: {player: {round: row(s)}}
            def build_participation_map(df):
                part_map = {}
                for player in df[Columns.player_name].unique():
                    player_rows = df[df[Columns.player_name] == player]
                    part_map[player] = {}
                    for rnd in player_rows[Columns.round_number].unique():
                        part_map[player][rnd] = player_rows[player_rows[Columns.round_number] == rnd].iloc[0]
                return part_map
            own_part_map = build_participation_map(team_data) if show_own else {}
            opp_part_map = build_participation_map(opponent_data) if show_opp else {}

            # --- Build columns ---
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("match_info"),
                    style={"backgroundColor": get_theme_color("background")},
                    columns=[
                        Column(title=i18n_service.get_text("round"), field="round_number", width=ColumnWidths.games, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("opponent"), field="opponent_name", width=ColumnWidths.team, align="left"),
                    ]
                )
            ]

            # Helper to build player col group
            def player_col_group(player, prefix):
                return ColumnGroup(
                    title=player,
                        columns=[
                        Column(title=i18n_service.get_text("position"), field=f"{prefix}{player}_pos", width=ColumnWidths.position, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("score"), field=f"{prefix}{player}_score", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("points"), field=f"{prefix}{player}_points", width=ColumnWidths.points, align="center", decimal_places=0),
                    ]
                )

            # Add own team player columns
            for player in own_players:
                columns.append(player_col_group(player, "own_"))
            # Add opponent player columns
            for player in opp_players:
                columns.append(player_col_group(player, "opp_"))

            # Add team column group
            columns.append(
                ColumnGroup(
                    title=i18n_service.get_text("team"),
                    style={"backgroundColor": get_theme_color("surface_alt")},
                    header_style={"fontWeight": "bold"},
                    columns=[
                        Column(title=i18n_service.get_text("score"), field="team_score", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("points"), field="team_points", width=ColumnWidths.points, align="center", decimal_places=0)
                    ]
                )
            )
            
            # --- Build data rows ---
            if view_mode == 'own_team':
                # Build main data rows (one per round)
                data = []
                for rnd in all_rounds:
                    # Get opponent team name for this round (from own or opponent data)
                    if rnd in team_data[Columns.round_number].values:
                        opponent_team = team_data[team_data[Columns.round_number] == rnd][Columns.team_name_opponent].iloc[0]
                    elif rnd in opponent_data[Columns.round_number].values:
                        opponent_team = opponent_data[opponent_data[Columns.round_number] == rnd][Columns.team_name].iloc[0]
                    else:
                        opponent_team = ""
                    row = [int(rnd), opponent_team]
                    # For each player, always output pos, score, points (blank if not played)
                    for player in own_players:
                        if rnd in own_part_map[player]:
                            row_data = own_part_map[player][rnd]
                            row.append(int(row_data[Columns.position] + 1) if not pd.isnull(row_data[Columns.position]) else "")
                            row.append(int(row_data[Columns.score]) if not pd.isnull(row_data[Columns.score]) else "")
                            row.append(float(row_data[Columns.points]) if not pd.isnull(row_data[Columns.points]) else "")
                        else:
                            row.extend(["", "", ""])
                    # Team totals for this round (if available)
                    team_totals = team_data[(team_data[Columns.round_number] == rnd) & (team_data[Columns.computed_data] == True)]
                    if not team_totals.empty:
                        row.append(int(team_totals[Columns.score].iloc[0]))
                        row.append(int(team_totals[Columns.points].iloc[0]))
                    else:
                        row.extend(["", ""])
                    data.append(row)
                # Add team totals row at the end
                team_total_row = ["Team", ""]
                for player in own_players:
                    # Sum score and points for this player across all rounds
                    player_rows = [own_part_map[player][rnd] for rnd in own_part_map[player] if not pd.isnull(own_part_map[player][rnd][Columns.score])]
                    if player_rows:
                        total_score = sum_scores(player_rows[Columns.score])
                        total_points = sum(float(row[Columns.points]) for row in player_rows if not pd.isnull(row[Columns.points]))
                        team_total_row.extend(["", total_score, total_points])
                    else:
                        team_total_row.extend(["", "", ""])
                # Team total score/points for all rounds
                team_score_total = (
                    sum_scores(team_data[team_data[Columns.computed_data] == True][Columns.score])
                    if not team_data.empty
                    else ""
                )
                team_points_total = team_data[team_data[Columns.computed_data] == True][Columns.points].sum() if not team_data.empty else ""
                team_total_row.append(int(team_score_total) if team_score_total != "" else "")
                team_total_row.append(int(team_points_total) if team_points_total != "" else "")
                data.append(team_total_row)
                # Debug print for non-serializable values
                for i, row in enumerate(data):
                    for j, cell in enumerate(row):
                        if hasattr(cell, 'dtype') or type(cell).__module__ == 'numpy':
                            print(f"Non-serializable value at row {i}, col {j}: {cell} ({type(cell)})")
                return TableData(
                    columns=columns,
                    data=data,
                    title=f"{team} - Head-to-Head (Week {week}) [own_team]",
                    description=f"Head-to-Head table for {team} in {league} - {season} (view: own_team)",
                    config={
                        "stickyHeader": True,
                        "striped": True,
                        "hover": True,
                        "responsive": True,
                        "compact": False
                    }
                )
            else: # view_mode in ('opponents', 'full')
                # --- Own team row ---
                if show_own:
                    row = [int(rnd), opponent_team]
                    # Own players
                    for player in own_players:
                        if rnd in own_part_map[player]:
                            row_data = own_part_map[player][rnd]
                            row.append(int(row_data[Columns.position] + 1) if not pd.isnull(row_data[Columns.position]) else "")
                            row.append(int(row_data[Columns.score]) if not pd.isnull(row_data[Columns.score]) else "")
                            row.append(float(row_data[Columns.points]) if not pd.isnull(row_data[Columns.points]) else "")
                        else:
                            row.extend(["", "", ""])
                    # Opponent players (blank)
                    for player in opp_players:
                        row.extend(["", "", ""])
                    # Team totals (if available)
                    team_totals = team_data[(team_data[Columns.round_number] == rnd) & (team_data[Columns.computed_data] == True)]
                    if not team_totals.empty:
                        row.append(int(team_totals[Columns.score].iloc[0]))
                        row.append(int(team_totals[Columns.points].iloc[0]))
                    else:
                        row.extend(["", ""])
                    data.append(row)

                # --- Opponent team row (only in 'full' or 'opponents' mode) ---
                if show_opp:
                    row = [int(rnd), team]  # Opponent's view: their opponent is 'team'
                    # Own players (blank)
                    for player in own_players:
                        row.extend(["", "", ""])
                    # Opponent players
                    for player in opp_players:
                        if rnd in opp_part_map[player]:
                            row_data = opp_part_map[player][rnd]
                            row.append(int(row_data[Columns.position] + 1) if not pd.isnull(row_data[Columns.position]) else "")
                            row.append(int(row_data[Columns.score]) if not pd.isnull(row_data[Columns.score]) else "")
                            row.append(float(row_data[Columns.points]) if not pd.isnull(row_data[Columns.points]) else "")
                        else:
                            row.extend(["", "", ""])
                    # Team totals (if available)
                    opp_totals = opponent_data[(opponent_data[Columns.round_number] == rnd) & (opponent_data[Columns.computed_data] == True)]
                    if not opp_totals.empty:
                        row.append(int(opp_totals[Columns.score].iloc[0]))
                        row.append(int(opp_totals[Columns.points].iloc[0]))
                    else:
                        row.extend(["", ""])
                    data.append(row)

                for i, row in enumerate(data):
                    for j, cell in enumerate(row):
                        if hasattr(cell, 'dtype') or type(cell).__module__ == 'numpy':
                            print(f"Non-serializable value at row {i}, col {j}: {cell} ({type(cell)})")

                return TableData(
                    columns=columns,
                    data=data,
                    title=f"{team} - Head-to-Head (Week {week}) [{view_mode}]",
                    description=f"Head-to-Head table for {team} in {league} - {season} (view: {view_mode})",
                    config={
                        "stickyHeader": True,
                        "striped": True,
                        "hover": True,
                        "responsive": True,
                        "compact": False
                    }
                )
        except Exception as e:
            print(f"Error in get_team_week_head_to_head_table_data: {e}")
            return TableData(
                columns=[],
                data=[],
                title=f"{i18n_service.get_text('error_loading_data_for')} {team} - {i18n_service.get_text('week')} {week}"
            )

    def get_team_individual_scores_table(self, league: str, season: str, team: str, week: int) -> TableData:
        """
        Returns a table with all individual scores of each player of the selected team at the given event (league, season, week).
        - Col group 'Opponents': Name (opponent name)
        - Col group with team name: Score, Points, Total Points (sum of all individual points + team points for the match)
        - One col group per player who played: Pos, Score, Points
        - Each row is a match (round) for the team in that week
        - Summary row at the end: sum of all individual scores and points per player, sum of team totals
        - hbar above the final row, final row bold
        """
        import pandas as pd
        from app.models.table_data import TableData, ColumnGroup, Column
        from data_access.schema import Columns

        # Get all individual player results for the team in this event
        player_filters = {
            Columns.league_name: {'value': league, 'operator': 'eq'},
            Columns.season: {'value': season, 'operator': 'eq'},
            Columns.team_name: {'value': team, 'operator': 'eq'},
            Columns.week: {'value': week, 'operator': 'eq'},
            Columns.computed_data: {'value': False, 'operator': 'eq'}
        }
        player_data = self.adapter.get_filtered_data(filters=player_filters)
        if player_data.empty:
            return TableData(columns=[], data=[], title=f"No data available for {team} - Week {week}")

        # Get team totals (computed data)
        team_filters = {
            Columns.league_name: {'value': league, 'operator': 'eq'},
            Columns.season: {'value': season, 'operator': 'eq'},
            Columns.team_name: {'value': team, 'operator': 'eq'},
            Columns.week: {'value': week, 'operator': 'eq'},
            Columns.computed_data: {'value': True, 'operator': 'eq'}
        }
        team_data = self.adapter.get_filtered_data(filters=team_filters)

        # Get all rounds (matches) for this team in this event
        rounds = sorted(player_data[Columns.round_number].unique())
        
        # Get all unique players who played in this event.
        # Use player_id as primary identifier, fallback to player_name
        player_identifiers = []
        for _, row in player_data.iterrows():
            player_id = row[Columns.player_id] if not pd.isnull(row[Columns.player_id]) else row[Columns.player_name]
            player_name = row[Columns.player_name]
            # Create a unique identifier combining ID and name
            identifier = f"{player_id}_{player_name}"
            if identifier not in [p['identifier'] for p in player_identifiers]:
                player_identifiers.append({
                    'identifier': identifier,
                    'player_id': player_id,
                    'player_name': player_name
                })
        
        players = [p['identifier'] for p in player_identifiers]

        # Build columns
        columns = [
            ColumnGroup(
                title=i18n_service.get_text("match"),
                columns=[
                    Column(title=i18n_service.get_text("opponent"), field="opponent", width=ColumnWidths.player, align="left", sortable=False),
                    Column(title=i18n_service.get_text("total_points"), field="team_total_points", width=ColumnWidths.points, align="center", sortable=False,
                           style={"fontWeight": "bold"}, decimal_places=0),
                ]
                #style={"borderRight": "2px solid #264653"}  # Vertical bar after Opponents group (same color as other borders)
            ),
            ColumnGroup(
                title=team,
                columns=[
                    Column(title=i18n_service.get_text("pins"), field="team_score", width=ColumnWidths.pins, align="center", sortable=False, decimal_places=0),
                    Column(title=i18n_service.get_text("points"), field="team_points", width=ColumnWidths.points, align="center", sortable=False, decimal_places=0),
                      # Make Total Points column bold
                ]
            )
        ]
        for player_info in player_identifiers:
            player_name = player_info['player_name']
            columns.append(
                ColumnGroup(
                    title=player_name,
                    columns=[
                        Column(title=i18n_service.get_text("pins"), field=f"{player_info['identifier']}_score", width=ColumnWidths.pins, align="center", sortable=False, decimal_places=0),
                        Column(title=i18n_service.get_text("points"), field=f"{player_info['identifier']}_points", width=ColumnWidths.points, align="center", sortable=False, decimal_places=0),
                        Column(title=i18n_service.get_text("position"), field=f"{player_info['identifier']}_pos", width=ColumnWidths.position, align="center", sortable=False, decimal_places=0),
                        
                    ]
                )
            )

        # Build data rows (one per round)
        data = []
        row_metadata = []
        for rnd in rounds:
            row = []
            # Opponent name for this round
            round_data = player_data[player_data[Columns.round_number] == rnd]
            opponent = round_data[Columns.team_name_opponent].iloc[0] if not round_data.empty else ""
            row.append(str(opponent))
            # Team totals for this round
            team_row = team_data[team_data[Columns.round_number] == rnd] if not team_data.empty else pd.DataFrame()
            team_score = int(team_row[Columns.score].iloc[0]) if not team_row.empty else 0
            team_points = float(team_row[Columns.points].iloc[0]) if not team_row.empty else 0.0
            # Total Points = sum of all individual points + team points
            indiv_points = float(round_data[Columns.points].sum()) if not round_data.empty else 0.0
            total_points = indiv_points + team_points
            row.append(total_points)
            row.append(team_score)
            row.append(team_points)
            
            # For each player, get their data for this round
            for player_info in player_identifiers:
                # Find all rows for this player in this round
                pdata = round_data[
                    (round_data[Columns.player_id] == player_info['player_id']) | 
                    (round_data[Columns.player_name] == player_info['player_name'])
                ]
                
                if not pdata.empty:
                    # If player played multiple positions, aggregate the data
                    total_score = sum_scores(pdata[Columns.score]) if not pdata.empty else ""
                    total_points = float(pdata[Columns.points].sum()) if not pdata.empty else ""
                    
                    # For position, show all positions played (e.g., "0,1" if played both positions)
                    positions = sorted(pdata[Columns.position].dropna().unique())
                    pos_str = ",".join([str(int(pos + 1)) for pos in positions]) if len(positions) > 0 else ""
                    
                    row.extend([total_score, total_points, pos_str])
                else:
                    row.extend(["", "", ""])
            
            data.append(row)
            row_metadata.append({'rowType': 'match', 'styling': {}})

        # Add summary row
        summary_row = ["Total", 0, 0.0, 0.0]
        for player_info in player_identifiers:
            # Find all rows for this player in the entire event
            player_rows = player_data[
                (player_data[Columns.player_id] == player_info['player_id']) | 
                (player_data[Columns.player_name] == player_info['player_name'])
            ]
            total_score = sum_scores(player_rows[Columns.score]) if not player_rows.empty else 0
            total_points = float(player_rows[Columns.points].sum()) if not player_rows.empty else 0.0
            summary_row.extend([total_score, total_points, ""])
        # Team total score/points for all rounds
        team_score_total = sum_scores(team_data[Columns.score]) if not team_data.empty else 0
        team_points_total = float(team_data[Columns.points].sum()) if not team_data.empty else 0.0
        indiv_points_total = float(player_data[Columns.points].sum()) if not player_data.empty else 0.0
        team_total_points_total = indiv_points_total + team_points_total
        summary_row[1] = team_total_points_total
        summary_row[2] = team_score_total
        summary_row[3] = team_points_total
        data.append(summary_row)
        row_metadata.append({'rowType': 'summary', 'separator_before': True, 'styling': {'fontWeight': 'bold'}})
            
        return TableData(
                columns=columns,
                data=data,
            row_metadata=row_metadata,
            title=f"{team} - Individual Scores (Week {week})",
            description=f"All individual scores for {team} in {league} - {season}, week {week}",
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False
            }
        )

    # ==========================================
    # AGGREGATION ENDPOINTS (League-wide over time)
    # ==========================================

    def get_league_averages_history(self, league: str, debug: bool = False) -> Dict[str, Any]:
        """Get league average scores across all seasons"""
        try:
            seasons = self.get_seasons()
            
            # Get league averages for each season
            season_averages = {}
            valid_seasons = []
            
            for season in seasons:
                try:
                    # Use existing team averages method and calculate league average
                    team_averages = self.get_team_averages_simple(league, season)
                    
                    if team_averages and 'data' in team_averages:
                        # Calculate overall league average for the season
                        all_averages = []
                        for team_name, team_data in team_averages['data'].items():
                            if isinstance(team_data, list) and team_data:
                                # Get final average (last value in the series)
                                final_avg = team_data[-1] if team_data[-1] is not None else 0
                                all_averages.append(final_avg)
                        
                        if all_averages:
                            league_avg = sum(all_averages) / len(all_averages)
                            season_averages[season] = league_avg
                            valid_seasons.append(season)
                            
                except Exception as e:
                    print(f"ERROR calculating average for {league} {season}: {e}")
                    continue
            
            # Prepare data for line chart
            result = {
                'data': {'League Average': [season_averages.get(season, 0) for season in valid_seasons]},
                'seasons': valid_seasons,
                'labels': valid_seasons,
                'title': f'{league} - Average Scores by Season',
                'y_axis_title': 'Average Score'
            }
            return result
            
        except Exception as e:
            print(f"ERROR in get_league_averages_history: {e}")
            return {'data': {}, 'seasons': [], 'labels': []}

    def get_points_to_win_history(self, league: str, debug: bool = False) -> Dict[str, Any]:
        """Get total league points earned by the winning team across seasons"""
        try:
            seasons = self.get_seasons()
            
            season_points = {}
            valid_seasons = []
            
            for season in seasons:
                try:
                    
                    # Filter data for league + season
                    filters = {
                        Columns.league_name: {'value': league, 'operator': 'eq'},
                        Columns.season: {'value': season, 'operator': 'eq'}
                    }
                    
                    season_data = self.adapter.get_filtered_data(filters=filters)
                    
                    if not season_data.empty:
                        # Group by team_name and sum Columns.points
                        team_totals = season_data.groupby(Columns.team_name)[Columns.points].sum().reset_index()
                        
                        if not team_totals.empty:
                            # Sort by sum of points (descending) and take top entry
                            team_totals = team_totals.sort_values(by=Columns.points, ascending=False)
                            winning_team_points = team_totals.iloc[0][Columns.points]
                            winning_team_name = team_totals.iloc[0][Columns.team_name]
                            
                            season_points[season] = winning_team_points
                            valid_seasons.append(season)
                                
                except Exception as e:
                    print(f"ERROR getting winning team league points for {league} {season}: {e}")
                    continue
            
            result = {
                'data': {'League Points to Win': [season_points.get(season, 0) for season in valid_seasons]},
                'seasons': valid_seasons,
                'labels': valid_seasons,
                'title': f'{league} - League Points Needed to Win by Season',
                'y_axis_title': 'Total League Points'
            }
            return result
            
        except Exception as e:
            print(f"ERROR in get_points_to_win_history: {e}")
            return {'data': {}, 'seasons': [], 'labels': []}

    def get_top_team_performances(self, league: str) -> TableData:
        """Get top team performances across all seasons based on team averages"""
        try:
            seasons = self.get_seasons()
            all_performances = []
            
            for season in seasons:
                try:
                    # Get team averages for the season
                    team_averages_data = self.get_team_averages_simple(league, season)
                    
                    if team_averages_data and 'data' in team_averages_data:
                        # Extract team averages (final values from the season)
                        for team_name, avg_series in team_averages_data['data'].items():
                            if isinstance(avg_series, list) and avg_series:
                                # Get final average (last value in the series)
                                final_average = avg_series[-1] if avg_series[-1] is not None else 0
                                
                                all_performances.append([
                                    team_name,
                                    format_float_one_decimal(final_average),
                                    season,
                                    league  # Add league as second-to-last
                                ])
                                
                except Exception as e:
                    print(f"Error processing season {season}: {e}")
                    continue
            
            # Sort by average descending (now index 3)
            all_performances.sort(key=lambda x: x[3] if isinstance(x[3], (int, float)) else 0, reverse=True)
            
            # Create table structure - remove ColumnGroup title (use empty string)
            columns = [
                ColumnGroup(
                    title="",  # Empty title since it's shown in card header
                    columns=[
                        Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left"),
                        Column(title=i18n_service.get_text("average"), field="average", width=ColumnWidths.average, align="center", decimal_places=1),
                        Column(title=i18n_service.get_text("season"), field="season", width=ColumnWidths.season, align="center"),
                        Column(title=i18n_service.get_text("league"), field="league", width=ColumnWidths.league, align="left")
                    ]
                )
            ]
            
            return TableData(
                columns=columns,
                data=all_performances[:20],  # Top 20 performances by average
                title=f"{league} - Top Team Performances",
                description="Best team season averages across all years",
                default_sort={"field": "average", "dir": "desc"}  # Sort by average descending
            )
            
        except Exception as e:
            print(f"Error in get_top_team_performances: {e}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_data"))

    def get_season_timetable(self, league: str, season: str) -> TableData:
        """Get season timetable with match day schedule as structured table data"""
        try:
            # Get available weeks for the season
            available_weeks = self.get_available_weeks(season, league)
            
            if not available_weeks:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"No timetable available for {league} - {season}"
                )
            
            latest_week = self.get_latest_week(season, league)
            
            # Get actual week data with dates and locations from the database
            filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.computed_data: {'value': True, 'operator': 'eq'}  # Get team summary data
            }
            
            week_data = self.adapter.get_filtered_data(filters=filters)
    
            
            # Group data by week to get unique week info
            week_info = {}
            for _, row in week_data.iterrows():
                week_num = row[Columns.week]
                if week_num not in week_info:
                    week_info[week_num] = {
                        'date': row.get(Columns.date, 'TBD'),
                        'location': row.get(Columns.location, f"{league} Venue"),
                        'has_data': True
                    }
            
            # Create table data only for existing weeks
            table_data = []
            for week_num in sorted(available_weeks):
                is_completed = week_num <= latest_week
                
                # Get real data if available
                if week_num in week_info:
                    date = week_info[week_num]['date']
                    location = week_info[week_num]['location']
                else:
                    date = "TBD"
                    location = f"{league} Venue"
                
                # Determine status
                if is_completed:
                    status = "✅ Completed"
                elif week_num in available_weeks:
                    status = "📊 Data Available"
                else:
                    status = "⏳ Pending"
                
                table_data.append([
                    week_num,
                    date if date and str(date) != 'nan' else "TBD",
                    location if location and str(location) != 'nan' else f"{league} Venue",
                    status
                ])
            
            # Create table structure - can pass bare Columns directly, no need for ColumnGroup wrapper
            columns = [
                Column(title=i18n_service.get_text("week"), field="week", width=ColumnWidths.week, align="center", decimal_places=0),
                Column(title=i18n_service.get_text("date"), field="date", width=ColumnWidths.date, align="center"),
                Column(title=i18n_service.get_text("location"), field="location", width=ColumnWidths.player, align="left"),
                Column(title=i18n_service.get_text("status"), field="status", width=ColumnWidths.misc, align="center")
            ]
            
            return TableData(
                columns=columns,
                data=table_data,
                title=f"{league} {season} - Match Schedule",
                description="Season timetable and completion status"
            )
            
        except Exception as e:
            print(f"Error in get_season_timetable: {e}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_timetable"))

    def get_individual_averages(self, league: str, season: str, week: int = None, team: str = None) -> TableData:
        """Get individual player averages for a season, optionally filtered by week and/or team, sorted by performance"""
        try:
            filter_text = ""
            if week is not None:
                filter_text += f" for week {week}"
            if team is not None:
                filter_text += f" for team {team}"
    
            
            # Get all player data for the league/season (and optionally week/team)
            filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual players only
            }
            if isinstance(week, str) and week.isdigit():
                week = int(week)
            
            # Add week filter if specified
            if week is not None:
                filters[Columns.week] = {'value': week, 'operator': 'eq'}
                
            # Add team filter if specified
            if team is not None:
                filters[Columns.team_name] = {'value': team, 'operator': 'eq'}
    
            if self._warm_slice_cache is not None and week is None and team is None:
                player_data = self._season_league_dataframe(league, season, computed_data=False)
            else:
                player_data = self.adapter.get_filtered_data(filters=filters)

            
            if player_data.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"No individual data available for {league} - {season}"
                )
            

            
            # Calculate averages per player
            player_stats = {}
            
            for _, row in player_data.iterrows():
                player_name = row[Columns.player_name]
                team_name = row[Columns.team_name]
                score = row[Columns.score]
                
                # Skip rows with missing essential data
                if pd.isna(player_name) or pd.isna(team_name):
                    continue
                
                # Create unique player identifier
                player_key = f"{player_name}|{team_name}"
                
                if player_key not in player_stats:
                    player_stats[player_key] = {
                        'player_name': player_name,
                        'team_name': team_name,
                        'scores': [],
                        'games': 0
                    }
                
                # Count all games, even if score is missing (DNP, etc.)
                player_stats[player_key]['games'] += 1
                
                if pd.notna(score):
                    num = pd.to_numeric(score, errors="coerce")
                    if pd.notna(num):
                        player_stats[player_key]['scores'].append(float(num))
            
    
            
            # Calculate averages and prepare table data
            table_data = []
            for player_key, stats in player_stats.items():
                if stats['games'] > 0:
                    # Handle players with no valid scores (DNP, etc.)
                    if len(stats['scores']) > 0:
                        score_series = pd.Series(stats['scores'])
                        average = mean_scores(score_series, round_places=1)
                        total_points = sum_scores(score_series)
                        high_game = int(scores_for_totals(score_series).max())
                    else:
                        # Player has games but no valid scores
                        average = 0.0
                        total_points = 0.0
                        high_game = 0.0
                    
                    table_data.append([
                        stats['player_name'],
                        stats['team_name'],
                        stats['games'],
                        round(total_points, 1),
                        round(average, 1),
                        round(high_game, 1)
                    ])
            
    
            
            # Sort by average descending (index 4 now contains average)
            table_data.sort(key=lambda x: x[4], reverse=True)
            
            # Create table structure
            columns = [
                Column(title=i18n_service.get_text("player"), field="player", width=ColumnWidths.player, align="left"),
                Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left"),
                Column(title=i18n_service.get_text("games"), field="games", width=ColumnWidths.misc, align="center", decimal_places=0),
                Column(title=i18n_service.get_text("total_points"), field="total_points", width=ColumnWidths.points, align="center", decimal_places=0),
                Column(title=i18n_service.get_text("average"), field="average", width=ColumnWidths.average, align="center", decimal_places=1),
                Column(title=i18n_service.get_text("high_game"), field="high_game", width=ColumnWidths.pins, align="center", decimal_places=0)
            ]
                
            
            # Build title with i18n and article_male + season/week logic (description content moved to title)
            if week is not None:
                title = f"{i18n_service.get_text('individual_performance')} {i18n_service.get_text('week')} {week}"
            else:
                title = f"{i18n_service.get_text('individual_performance')} {i18n_service.get_text('article_male')} {i18n_service.get_text('season')}"
            
            if team is not None:
                # Add team info if specified
                title += f" - {team}"
            
            return TableData(
                columns=columns,
                data=table_data,
                title=title,
                description=None
            )
            
        except Exception as e:
            print(f"ERROR in get_individual_averages: {e}")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_individual_averages"))

    def get_top_individual_performances(self, league: str) -> TableData:
        """Get top individual performances across all seasons"""
        try:
            seasons = self.get_seasons()
            
            # Also check what leagues exist in the data
            league_filters = {}
            all_league_data = self.adapter.get_filtered_data(filters=league_filters)
            unique_leagues = all_league_data[Columns.league_name].unique() if not all_league_data.empty else []
            
            all_performances = []
            
            for season in seasons:
                try:
                    
                    # First check if any data exists for this league/season combination
                    basic_filters = {
                        Columns.league_name: {'value': league, 'operator': 'eq'},
                        Columns.season: {'value': season, 'operator': 'eq'}
                    }
                    basic_data = self.adapter.get_filtered_data(filters=basic_filters)
                    
                    if not basic_data.empty:
                        computed_data_values = basic_data[Columns.computed_data].unique()
                        individual_rows = basic_data[basic_data[Columns.computed_data] == False]
                        team_rows = basic_data[basic_data[Columns.computed_data] == True]
                    
                    # Get individual averages for each season
                    individual_data = self.get_individual_averages(league, season)
                    
                    if individual_data and individual_data.data:
                        # Take top 5 from each season
                        for row in individual_data.data[:5]:
                            # New individual_averages structure: [player_name, team_name, games, total_points, average, high_game]
                            if len(row) >= 6:
                                performance_entry = [
                                    row[0],  # player_name
                                    format_float_one_decimal(row[4]),  # average (index 4 in the new structure)
                                    season,
                                    league,   # Add league as second-to-last
                                    row[1]   # team_name
                                ]
                                all_performances.append(performance_entry)
                                
                except Exception as e:
                    print(f"ERROR: processing individual data for season {season}: {e}")
                    import traceback
                    print(f"TRACEBACK: {traceback.format_exc()}")
                    continue
            

            
            # Sort by average descending (now index 4 since we added league)
            all_performances.sort(key=lambda x: x[4] if isinstance(x[4], (int, float)) else 0, reverse=True)
            
            # Create table structure - remove ColumnGroup title (use empty string)
            columns = [
                ColumnGroup(
                    title="",  # Empty title since it's shown in card header
                    columns=[
                        Column(title=i18n_service.get_text("player"), field="player", width=ColumnWidths.player, align="left"),
                        Column(title=i18n_service.get_text("average"), field="average", width=ColumnWidths.average, align="center", decimal_places=1),
                        Column(title=i18n_service.get_text("season"), field="season", width=ColumnWidths.season, align="center"),
                        Column(title=i18n_service.get_text("league"), field="league", width=ColumnWidths.league, align="left"),
                        Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left")                        
                    ]
                )
            ]
            
            result_data = all_performances[:30]  # Top 30 individual performances

            
            return TableData(
                columns=columns,
                data=result_data,
                title=f"{league} - Top Individual Performances",
                description="Best individual averages across all seasons",
                default_sort={"field": "average", "dir": "desc"}  # Sort by average descending
            )
            
        except Exception as e:
            print(f"ERROR in get_top_individual_performances: {e}")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_data"))

    def get_record_individual_games(self, league: str) -> TableData:
        """Get record individual games (highest scoring individual performances)"""
        try:
            seasons = self.get_seasons()
            record_games = []
            
            for season in seasons:
                try:
                    # Get all individual data for the season to find high scores
                    filters = {
                        Columns.league_name: {'value': league, 'operator': 'eq'},
                        Columns.season: {'value': season, 'operator': 'eq'},
                        Columns.computed_data: {'value': False, 'operator': 'eq'}
                    }
                    
                    player_data = self.adapter.get_filtered_data(filters=filters)
                    
                    if not player_data.empty:
                        # Find highest individual games (top 3 per season)
                        highest_individual = player_data.nlargest(3, Columns.score)
                        
                        for _, row in highest_individual.iterrows():
                            record_games.append([
                                row[Columns.player_name],
                                row[Columns.score],
                                season,
                                league,   # Add league as second-to-last
                                row[Columns.team_name],
                                row[Columns.week] if Columns.week in row else ''
                            ])
                            
                except Exception as e:
                    print(f"Error processing individual record games for season {season}: {e}")
                    continue
            
            # Sort by score descending (now index 5)
            record_games.sort(key=lambda x: x[5] if isinstance(x[5], (int, float)) else 0, reverse=True)
            
            # Create table structure - remove ColumnGroup title (use empty string)
            columns = [
                ColumnGroup(
                    title="",  # Empty title since it's shown in card header
                    columns=[
                        Column(title=i18n_service.get_text("player"), field="player", width=ColumnWidths.player, align="left"),
                        Column(title=i18n_service.get_text("score"), field="score", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("season"), field="season", width=ColumnWidths.season, align="center"),
                        Column(title=i18n_service.get_text("league"), field="league", width=ColumnWidths.league, align="left"),
                        Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left"),
                        Column(title=i18n_service.get_text("week"), field="week", width=ColumnWidths.week, align="center", decimal_places=0)
                    ]
                )
            ]
            
            return TableData(
                columns=columns,
                data=record_games[:15],  # Top 15 individual record games
                title=f"{league} - Record Individual Games",
                description="Highest scoring individual performances across all seasons",
                default_sort={"field": "score", "dir": "desc"}  # Sort by score descending
            )
            
        except Exception as e:
            print(f"Error in get_record_individual_games: {e}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_individual_record_games"))

    def get_record_team_games(self, league: str) -> TableData:
        """Get record team games (highest scoring team performances)"""
        try:
            seasons = self.get_seasons()
            record_games = []
            
            for season in seasons:
                try:
                    # Get team totals for the season
                    team_filters = {
                        Columns.league_name: {'value': league, 'operator': 'eq'},
                        Columns.season: {'value': season, 'operator': 'eq'},
                        Columns.computed_data: {'value': True, 'operator': 'eq'}
                    }
                    
                    team_data = self.adapter.get_filtered_data(filters=team_filters)
                    
                    if not team_data.empty:
                        # Find highest team games (top 2 per season)
                        highest_team = team_data.nlargest(2, Columns.score)
                        
                        for _, row in highest_team.iterrows():
                            record_games.append([
                                row[Columns.team_name],
                                row[Columns.score],
                                season,
                                league,  # Add league as second-to-last
                                row[Columns.week] if Columns.week in row else ''
                            ])
                            
                except Exception as e:
                    print(f"Error processing team record games for season {season}: {e}")
                    continue
            
            # Sort by score descending (now index 4)
            record_games.sort(key=lambda x: x[4] if isinstance(x[4], (int, float)) else 0, reverse=True)
            
            # Create table structure - remove ColumnGroup title (use empty string)
            columns = [
                ColumnGroup(
                    title="",  # Empty title since it's shown in card header
                    columns=[
                        Column(title=i18n_service.get_text("team"), field="team", width=ColumnWidths.team, align="left"), 
                        Column(title=i18n_service.get_text("score"), field="score", width=ColumnWidths.pins, align="center", decimal_places=0),
                        Column(title=i18n_service.get_text("season"), field="season", width=ColumnWidths.season, align="center"),
                        Column(title=i18n_service.get_text("league"), field="league", width=ColumnWidths.league, align="left"),
                        Column(title=i18n_service.get_text("week"), field="week", width=ColumnWidths.week, align="center", decimal_places=0),
                    ]
                        
                )
            ]
            
            return TableData(
                columns=columns,
                data=record_games[:15],  # Top 15 team record games
                title=f"{league} - Record Team Games",
                description="Highest scoring team performances across all seasons",
                default_sort={"field": "score", "dir": "desc"}  # Sort by score descending

            )
            
        except Exception as e:
            print(f"Error in get_record_team_games: {e}")
            return TableData(columns=[], data=[], title=i18n_service.get_text("error_loading_team_record_games"))

    def _convert_to_simple_types(self, data):
        """Convert numpy types to simple Python types for JSON serialization (delegates to utility function)"""
        return convert_to_simple_types(data)

    def get_team_analysis(self, league: str, season: str, team: str) -> Dict[str, Any]:
        """Get detailed team analysis including individual player performance and win percentages"""
        try:
            # Get all player data for the team in the specified season and league
            # EXCLUDE team totals - only get individual player records
            player_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.team_name: {'value': team, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual players only
            }
            
            player_data = self.adapter.get_filtered_data(filters=player_filters)
            
            if not player_data.empty:
                # Filter out team totals - only keep individual player records
                # Team totals typically have "Team Total" or similar in the Player column
                player_data = player_data[player_data[Columns.player_name] != 'Team Total']
                player_data = player_data[player_data[Columns.player_name] != 'team_total']
                player_data = player_data[player_data[Columns.player_name] != 'TEAM TOTAL']
                
                # Also filter out any records where Player ID is NaN (these are usually team totals)
                player_data = player_data.dropna(subset=[Columns.player_id])
            
            if player_data.empty:
                return {
                    'error': f'No individual player data found for team {team} in {league} {season}',
                    'performance_data': [],
                    'win_percentage_data': [],
                    'weeks': [],
                    'players': []
                }
            
            # Get unique weeks and players
            weeks = sorted(player_data[Columns.week].unique())
            players = sorted(player_data[Columns.player_name].unique())
            
            # Get individual player matches for PvP win calculation
            individual_matches = self.get_individual_matches(team=team, season=season, league=league)
            
            # Get team matches for team win percentage
            team_matches = self.adapter.get_matches(team=team, season=season, league=league)
            
            # Create SeriesData objects for charts
            performance_series = SeriesData(
                label_x_axis="Spieltag",
                label_y_axis="Durchschnittliche Punkte",
                name=f"Leistung {team}",
                query_params={'league': league, 'season': season, 'team': team}
            )
            
            win_percentage_series = SeriesData(
                label_x_axis="Spieltag", 
                label_y_axis="Siegquote (%)",
                name=f"Siegquote {team}",
                query_params={'league': league, 'season': season, 'team': team}
            )
            
            # Add individual player data to performance series
            for player in players:
                player_week_scores = []
                player_total_score = 0
                player_total_games = 0
                
                for week in weeks:
                    week_data = player_data[
                        (player_data[Columns.player_name] == player) & 
                        (player_data[Columns.week] == week)
                    ]
                    
                    if not week_data.empty:
                        # Calculate average score per game for this player in this week
                        week_total_score = sum_scores_float(week_data[Columns.score])
                        week_games = len(week_data)
                        week_avg_score = round(week_total_score / week_games, 2) if week_games > 0 else 0
                        player_week_scores.append(week_avg_score)
                        
                        # Accumulate totals for correct calculation
                        player_total_score += week_total_score
                        player_total_games += week_games
                        
                    else:
                        player_week_scores.append(None)  # Use None for missing data
                
                # Add data to series
                performance_series.add_data(player, player_week_scores)
                
                # Override the incorrect totals with correct ones
                performance_series.total[player] = round(player_total_score, 2)
                performance_series.average[player] = round(player_total_score / player_total_games, 2) if player_total_games > 0 else 0
                
                # Store count of valid data points for frontend use
                performance_series.counts[player] = player_total_games
                
            
            # Add team average to performance series
            team_week_scores = []
            team_total_score = 0
            team_total_games = 0
            
            for week in weeks:
                week_data = player_data[player_data[Columns.week] == week]
                if not week_data.empty:
                    # Calculate team average per person per game for this week
                    week_total_score = sum_scores_float(week_data[Columns.score])
                    week_games = len(week_data)
                    week_avg_score = round(week_total_score / week_games, 2) if week_games > 0 else 0
                    team_week_scores.append(week_avg_score)
                    
                    # Accumulate totals for correct calculation
                    team_total_score += week_total_score
                    team_total_games += week_games
                else:
                    team_week_scores.append(None)  # Use None for missing data
            
            # Add data to series
            performance_series.add_data(f"{team}", team_week_scores)
            
            # Override the incorrect totals with correct ones
            performance_series.total[f"{team}"] = round(team_total_score, 2)
            performance_series.average[f"{team}"] = round(team_total_score / team_total_games, 2) if team_total_games > 0 else 0
            
            # Store count of valid data points for frontend use
            performance_series.counts[f"{team}"] = team_total_games
            
            # Add individual player win percentage data
            for player in players:
                player_week_wins = []
                player_total_wins = 0
                player_total_matches = 0
                
                for week in weeks:
                    if not individual_matches.empty:
                        # Get individual matches for this player in this week
                        week_matches = individual_matches[
                            (individual_matches['player_name'] == player) & 
                            (individual_matches['week'] == week)
                        ]
                        
                        if not week_matches.empty:
                            # Count PvP wins for this player in this week
                            week_wins = int(week_matches['is_win'].sum())
                            week_matches_count = len(week_matches)
                            week_win_pct = round((week_wins / week_matches_count) * 100, 1) if week_matches_count > 0 else 0
                            player_week_wins.append(week_win_pct)
                            
                            # Accumulate totals for correct calculation
                            player_total_wins += week_wins
                            player_total_matches += week_matches_count
                        else:
                            player_week_wins.append(None)  # Use None for missing data
                    else:
                        player_week_wins.append(None)  # Use None for missing data
                
                # Add data to series
                win_percentage_series.add_data(player, player_week_wins)
                
                # Override the incorrect totals with correct ones
                win_percentage_series.total[player] = player_total_wins
                win_percentage_series.average[player] = round((player_total_wins / player_total_matches) * 100, 1) if player_total_matches > 0 else 0
                
                # Store count of valid data points for frontend use
                win_percentage_series.counts[player] = player_total_matches
            
            # Add team win percentage
            team_week_wins = []
            team_total_wins = 0
            team_total_matches = 0
            
            for week in weeks:
                week_matches = team_matches[team_matches[Columns.week] == week]
                week_wins = 0
                week_matches_count = 0
                
                for _, match in week_matches.iterrows():
                    team_score = match[Columns.score]
                    opponent_score = match['opponent_score']
                    
                    if team_score > opponent_score:
                        week_wins += 1
                    week_matches_count += 1
                
                if week_matches_count > 0:
                    week_win_pct = round((week_wins / week_matches_count) * 100, 1)
                    team_week_wins.append(week_win_pct)
                else:
                    team_week_wins.append(None)  # Use None for missing data
                
                # Accumulate totals for correct calculation
                team_total_wins += week_wins
                team_total_matches += week_matches_count
            
            # Add data to series
            win_percentage_series.add_data(f"{team}", team_week_wins)
            
            # Override the incorrect totals with correct ones
            win_percentage_series.total[f"{team}"] = team_total_wins
            win_percentage_series.average[f"{team}"] = round((team_total_wins / team_total_matches) * 100, 1) if team_total_matches > 0 else 0
            
            # Store count of valid data points for frontend use
            win_percentage_series.counts[f"{team}"] = team_total_matches
            
            # Return data using existing SeriesData interface
            player_order_by_average = sorted(
                [str(p) for p in players],
                key=lambda p: (float(performance_series.average.get(p, 0) or 0), p),
                reverse=True,
            )
            return {
                'performance_data': performance_series.to_dict(),
                'win_percentage_data': win_percentage_series.to_dict(),
                'weeks': [f'Week {int(w)}' for w in weeks],
                'players': [str(p) for p in players],
                'player_order_by_average': player_order_by_average,
                'team': str(team),
                'league': str(league),
                'season': str(season)
            }
            
        except Exception as e:
            print(f"Error in get_team_analysis: {e}")
            return {
                'error': f'Error analyzing team data: {str(e)}',
                'performance_data': [],
                'win_percentage_data': [],
                'weeks': [],
                'players': []
            }

    def get_team_performance_table_data(self, league: str, season: str, team: str) -> TableData:
        """Get team performance table as TableData - can be passed directly to createTableTabulator"""
        try:
            # Reuse the data collection logic from get_team_analysis
            analysis_data = self.get_team_analysis(league=league, season=season, team=team)
            
            if 'error' in analysis_data:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"Error: {analysis_data['error']}"
                )
            
            performance_data = analysis_data.get('performance_data', {})
            # weeks comes as list of strings like ['Week 1', 'Week 2', ...], extract count
            weeks_list = analysis_data.get('weeks', [])
            num_weeks = len(weeks_list) if weeks_list else 0
            team_name = analysis_data.get('team', team)
            teamAverageKey = f"{team_name}"
            
            # Debug: Check if we have data
            if num_weeks == 0:
                print(f"WARNING: No weeks data in get_team_performance_table_data for {team} in {league} {season}")
                print(f"analysis_data keys: {list(analysis_data.keys())}")
                print(f"performance_data keys: {list(performance_data.keys()) if isinstance(performance_data, dict) else type(performance_data)}")
            
            # Build columns
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text('player'),
                    columns=[
                        Column(title='#', field='pos', width='50px', align='center', decimal_places=0),
                        Column(title=i18n_service.get_text('player'), field='player_name', width='150px', align="left")
                    ]
                )
            ]
            
            # Add week columns
            week_columns = []
            for idx in range(num_weeks):
                week_columns.append(
                    Column(
                        title=f"{idx + 1}",
                        field=f'week_{idx + 1}',
                        width='80px',
                        align='center',
                        tooltip=i18n_service.get_text('match_day_label') + ' ' + str(idx + 1),
                        decimal_places=1  # Weekly averages typically have 1 decimal place
                    )
                )
            if week_columns:
                columns.append(ColumnGroup(
                    title=i18n_service.get_text('ui.team_performance.weekly_avg_game'),
                    columns=week_columns
                ))
            
            # Add totals columns
            columns.append(ColumnGroup(
                title=i18n_service.get_text('ui.win_percentage.totals'),
                columns=[
                    Column(title=i18n_service.get_text('ui.team_performance.total_score'), field='total_score', width=ColumnWidths.pins, align='center', decimal_places=0),
                    Column(title=i18n_service.get_text('games'), field='total_games', width=ColumnWidths.misc, align='center', decimal_places=0),
                    Column(title=i18n_service.get_text('ui.team_performance.avg_per_game'), field='avg_per_game', width=ColumnWidths.average, align='center', decimal_places=1)
                ]
            ))
            
            # Build data rows
            table_data = []
            data_dict = performance_data.get('data', {})
            total_dict = performance_data.get('total', {})
            average_dict = performance_data.get('average', {})
            counts_dict = performance_data.get('counts', {})
            
            # Process individual players in chart/table order (by season average).
            order_from_analysis = [str(x) for x in analysis_data.get('player_order_by_average', [])]
            player_names = [name for name in data_dict.keys() if name != teamAverageKey]
            if order_from_analysis:
                order_index = {name: idx for idx, name in enumerate(order_from_analysis)}
                player_names.sort(key=lambda n: (order_index.get(n, 10**6), n))
            else:
                player_names.sort(key=lambda n: (float(average_dict.get(n, 0) or 0), str(n)), reverse=True)
            for rank, playerName in enumerate(player_names, start=1):
                playerData = data_dict[playerName]
                row = {
                    'pos': rank,
                    'player_name': playerName
                }

                # Add week data
                for idx in range(num_weeks):
                    weekValue = playerData[idx] if idx < len(playerData) else None
                    row[f'week_{idx + 1}'] = weekValue

                # Add totals
                row['total_score'] = round(total_dict.get(playerName, 0) * 100) / 100
                row['total_games'] = counts_dict.get(playerName, 0)
                row['avg_per_game'] = round(average_dict.get(playerName, 0) * 100) / 100

                table_data.append(row)
            
            # Add team average as last row
            if teamAverageKey in data_dict:
                teamData = data_dict[teamAverageKey]
                row = {
                    'pos': 'T',
                    'player_name': teamAverageKey
                }
                
                for idx in range(num_weeks):
                    weekValue = teamData[idx] if idx < len(teamData) else None
                    row[f'week_{idx + 1}'] = weekValue
                
                row['total_score'] = round(total_dict.get(teamAverageKey, 0) * 100) / 100
                row['total_games'] = counts_dict.get(teamAverageKey, 0)
                row['avg_per_game'] = round(average_dict.get(teamAverageKey, 0) * 100) / 100
                
                table_data.append(row)
            
            # Row metadata for team average row (bold)
            row_metadata = []
            for idx, row in enumerate(table_data):
                if row['player_name'] == teamAverageKey:
                    row_metadata.append({
                        'styling': {
                            'fontWeight': 'bold',
                            'backgroundColor': get_theme_color('background') or '#f8f9fa'
                        }
                    })
                else:
                    row_metadata.append({})
            
            result = TableData(
                columns=columns,
                data=table_data,
                title=f"{team_name} - {i18n_service.get_text('ui.team_performance.player_performance')}",
                description=i18n_service.get_text('ui.team_performance.player_perf_desc'),
                row_metadata=row_metadata,
                config={
                    'striped': True,
                    'hover': True,
                    'compact': True,
                    'stickyHeader': True,
                    'numberOfdecimalplaces': 1
                }
            )
            
            return result
            
        except Exception as e:
            print(f"Error in get_team_performance_table_data: {e}")
            return TableData(
                columns=[],
                data=[],
                title=f"Error: {str(e)}"
            )
    
    def get_team_win_percentage_table_data(self, league: str, season: str, team: str) -> TableData:
        """Get team win percentage table as TableData - can be passed directly to createTableTabulator"""
        try:
            # Reuse the data collection logic from get_team_analysis
            analysis_data = self.get_team_analysis(league=league, season=season, team=team)
            
            if 'error' in analysis_data:
                return TableData(
                    columns=[],
                    data=[],
                    title=f"Error: {analysis_data['error']}"
                )
            
            win_percentage_data = analysis_data.get('win_percentage_data', {})
            # weeks comes as list of strings like ['Week 1', 'Week 2', ...], extract count
            weeks_list = analysis_data.get('weeks', [])
            num_weeks = len(weeks_list) if weeks_list else 0
            team_name = analysis_data.get('team', team)
            teamKey = f"{team_name}"
            
            # Debug: Check if we have data
            if num_weeks == 0:
                print(f"WARNING: No weeks data in get_team_win_percentage_table_data for {team} in {league} {season}")
                print(f"analysis_data keys: {list(analysis_data.keys())}")
                print(f"win_percentage_data keys: {list(win_percentage_data.keys()) if isinstance(win_percentage_data, dict) else type(win_percentage_data)}")
            
            # Build columns
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text('player'),
                    columns=[
                        Column(title='#', field='pos', width=ColumnWidths.position, align='center', decimal_places=0),
                        Column(title=i18n_service.get_text('ui.win_percentage.player'), field='player_name', width=ColumnWidths.player, align='left')
                    ]
                )
            ]
            
            # Add week columns
            week_columns = []
            for idx in range(num_weeks):
                week_columns.append(
                    Column(
                        title=f"{idx + 1}",
                        field=f'week_{idx + 1}',
                        width=ColumnWidths.week,
                        align='center',
                        tooltip=f"{i18n_service.get_text('week')} {idx + 1}",
                        decimal_places=1  # Win percentages typically have 1 decimal place
                    )
                )
            if week_columns:
                columns.append(ColumnGroup(
                    title=i18n_service.get_text('ui.win_percentage.weekly'),
                    columns=week_columns
                ))
            
            # Add totals columns
            columns.append(ColumnGroup(
                title=i18n_service.get_text('ui.win_percentage.totals'),
                columns=[
                    Column(title=i18n_service.get_text('ui.win_percentage.total_wins'), field='total_wins', width=ColumnWidths.games, align='center', decimal_places=0),
                    Column(title=i18n_service.get_text('ui.win_percentage.total_matches'), field='total_matches', width=ColumnWidths.games, align='center', decimal_places=0),
                    Column(title=i18n_service.get_text('ui.win_percentage.win_percentage'), field='win_percentage', width=ColumnWidths.average, align='center', decimal_places=1)
                ]
            ))
            
            # Build data rows
            table_data = []
            data_dict = win_percentage_data.get('data', {})
            total_dict = win_percentage_data.get('total', {})
            average_dict = win_percentage_data.get('average', {})
            counts_dict = win_percentage_data.get('counts', {})
            perf_average_dict = analysis_data.get('performance_data', {}).get('average', {})
            
            # Process individual players first, ordered by performance average.
            order_from_analysis = [str(x) for x in analysis_data.get('player_order_by_average', [])]
            player_names = [name for name in data_dict.keys() if name != teamKey]
            if order_from_analysis:
                order_index = {name: idx for idx, name in enumerate(order_from_analysis)}
                player_names.sort(key=lambda n: (order_index.get(n, 10**6), n))
            else:
                player_names.sort(
                    key=lambda n: (float(perf_average_dict.get(n, 0) or 0), str(n)),
                    reverse=True
                )

            for rank, playerName in enumerate(player_names, start=1):
                playerData = data_dict[playerName]
                row = {
                    'pos': rank,
                    'player_name': playerName
                }
                
                # Add week data
                for idx in range(num_weeks):
                    weekValue = playerData[idx] if idx < len(playerData) else None
                    row[f'week_{idx + 1}'] = weekValue
                
                # Add totals
                row['total_wins'] = total_dict.get(playerName, 0)
                row['total_matches'] = counts_dict.get(playerName, 0)
                row['win_percentage'] = average_dict.get(playerName, 0)
                
                table_data.append(row)
            
            # Add team as last row
            if teamKey in data_dict:
                teamData = data_dict[teamKey]
                row = {
                    'pos': 'T',
                    'player_name': teamKey
                }
                
                for idx in range(num_weeks):
                    weekValue = teamData[idx] if idx < len(teamData) else None
                    row[f'week_{idx + 1}'] = weekValue
                
                row['total_wins'] = total_dict.get(teamKey, 0)
                row['total_matches'] = counts_dict.get(teamKey, 0)
                row['win_percentage'] = average_dict.get(teamKey, 0)
                
                table_data.append(row)
            
            # Row metadata for team row (bold)
            row_metadata = []
            for idx, row in enumerate(table_data):
                if row['player_name'] == teamKey:
                    row_metadata.append({
                        'styling': {
                            'fontWeight': 'bold',
                            'backgroundColor': get_theme_color('background') or '#f8f9fa'
                        }
                    })
                else:
                    row_metadata.append({})
            
            result = TableData(
                columns=columns,
                data=table_data,
                title=f"{team_name} - {i18n_service.get_text('ui.win_percentage.title')}",
                description=i18n_service.get_text('ui.win_percentage.individual_desc'),
                row_metadata=row_metadata,
                config={
                    'striped': True,
                    'hover': True,
                    'compact': True,
                    'stickyHeader': True
                }
            )
            
            return result
            
        except Exception as e:
            print(f"Error in get_team_win_percentage_table_data: {e}")
            return TableData(
                columns=[],
                data=[],
                title=f"Error: {str(e)}"
            )

    def _apply_heat_map_to_columns(self, table_data: List[List], cell_metadata: Dict[str, Dict],
                                    column_indices: List[int], min_val: float = None, max_val: float = None) -> Dict[str, Dict]:
        """
        Apply heat map coloring to specified column indices (delegates to utility function).
        
        Args:
            table_data: List of rows, where each row is a list of values
            cell_metadata: Dictionary mapping "row:col" to cell metadata
            column_indices: List of column indices (0-based) to apply coloring to
            min_val: Optional minimum value for color scale. If None, calculated from data
            max_val: Optional maximum value for color scale. If None, calculated from data
            
        Returns:
            Updated cell_metadata dictionary
        """
        return apply_heat_map_to_columns(table_data, cell_metadata, column_indices, min_val, max_val)

    def get_team_vs_team_comparison_table(self, league: str, season: str, week: int = None) -> 'TableData':
        """
        Get team vs team comparison as TableData with heat map.
        Row/column order follows full-season league standings (total points, pins tiebreak),
        independent of which week's cells are shown — not matrix-specific weekly averages.
        """
        from app.models.table_data import TableData, ColumnGroup, Column
        
        try:
            # ========== DATA COLLECTION ==========
            if self._warm_slice_cache is not None and week is None:
                teams_data = self._season_league_dataframe(league, season, computed_data=False)
                if Columns.input_data in teams_data.columns:
                    teams_data = teams_data[self._computed_data_mask(teams_data[Columns.input_data], want_true=True)]
                if not teams_data.empty:
                    teams_data = teams_data[[Columns.team_name]]

                team_matches = self._season_league_dataframe(league, season, computed_data=True)
                if Columns.input_data in team_matches.columns:
                    team_matches = team_matches[self._computed_data_mask(team_matches[Columns.input_data], want_true=False)]
                if Columns.position in team_matches.columns:
                    team_matches = team_matches[pd.to_numeric(team_matches[Columns.position], errors="coerce") == 0]
                if not team_matches.empty:
                    keep_cols = [
                        c
                        for c in (
                            Columns.team_name,
                            Columns.team_name_opponent,
                            Columns.score,
                            Columns.points,
                            Columns.week,
                            Columns.round_number,
                        )
                        if c in team_matches.columns
                    ]
                    team_matches = team_matches[keep_cols]

                individual_data = self._season_league_dataframe(league, season, computed_data=False)
                if Columns.input_data in individual_data.columns:
                    individual_data = individual_data[self._computed_data_mask(individual_data[Columns.input_data], want_true=True)]
                if not individual_data.empty:
                    keep_cols = [
                        c
                        for c in (
                            Columns.team_name,
                            Columns.team_name_opponent,
                            Columns.points,
                            Columns.week,
                            Columns.match_number,
                            Columns.round_number,
                        )
                        if c in individual_data.columns
                    ]
                    individual_data = individual_data[keep_cols]
            else:
                # Get all teams in the league/season
                team_filters = {
                    Columns.league_name: {'value': league, 'operator': 'eq'},
                    Columns.season: {'value': season, 'operator': 'eq'},
                    Columns.computed_data: {'value': False, 'operator': 'eq'},
                    Columns.input_data: {'value': True, 'operator': 'eq'}
                }
                
                if week is not None:
                    team_filters[Columns.week] = {'value': week, 'operator': 'eq'}
                
                teams_data = self.adapter.get_filtered_data(
                    columns=[Columns.team_name], 
                    filters=team_filters
                )
                
                team_total_filters = {
                    Columns.league_name: {'value': league, 'operator': 'eq'},
                    Columns.season: {'value': season, 'operator': 'eq'},
                    Columns.computed_data: {'value': True, 'operator': 'eq'},
                    Columns.input_data: {'value': False, 'operator': 'eq'},
                    Columns.position: {'value': 0, 'operator': 'eq'}  # Team totals have position 0
                }
                
                if week is not None:
                    team_total_filters[Columns.week] = {'value': week, 'operator': 'eq'}
                
                team_matches = self.adapter.get_filtered_data(
                    columns=[Columns.team_name, Columns.team_name_opponent, Columns.score, Columns.points, Columns.week, Columns.round_number],
                    filters=team_total_filters
                )
                
                individual_filters = {
                    Columns.league_name: {'value': league, 'operator': 'eq'},
                    Columns.season: {'value': season, 'operator': 'eq'},
                    Columns.computed_data: {'value': False, 'operator': 'eq'},
                    Columns.input_data: {'value': True, 'operator': 'eq'}
                }
                
                if week is not None:
                    individual_filters[Columns.week] = {'value': week, 'operator': 'eq'}
                
                individual_data = self.adapter.get_filtered_data(
                    columns=[Columns.team_name, Columns.team_name_opponent, Columns.points, Columns.week, Columns.match_number, Columns.round_number],
                    filters=individual_filters
                )
            
            if teams_data.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=i18n_service.get_text("team_vs_team_comparison_matrix"),
                    description="No data available",
                    config={"striped": True, "hover": True, "compact": True, "stickyHeader": True}
                )
            
            teams = sorted(teams_data[Columns.team_name].unique())
            
            if team_matches.empty:
                return TableData(
                    columns=[],
                    data=[],
                    title=i18n_service.get_text("team_vs_team_comparison_matrix"),
                    description="No match data available",
                    config={"striped": True, "hover": True, "compact": True, "stickyHeader": True}
                )
            
            # ========== CALCULATE COMPARISON DATA ==========
            comparison_data = {}
            for team in teams:
                comparison_data[team] = {}
                for opponent in teams:
                    if team != opponent:
                        # Get matches between this team and opponent
                        team_vs_opponent = team_matches[
                            (team_matches[Columns.team_name] == team) & 
                            (team_matches[Columns.team_name_opponent] == opponent)
                        ]
                        
                        if not team_vs_opponent.empty:
                            avg_score = mean_scores(team_vs_opponent[Columns.score], round_places=1)
                            
                            # Calculate total points (individual + team match points)
                            total_points_list = []
                            for _, match in team_vs_opponent.iterrows():
                                round_number = match[Columns.round_number]
                                match_week = match[Columns.week]
                                
                                # Get team match points (0-3)
                                team_match_points = match[Columns.points]
                                
                                # Get individual points for this match
                                individual_match_data = individual_data[
                                    (individual_data[Columns.team_name] == team) & 
                                    (individual_data[Columns.team_name_opponent] == opponent) &
                                    (individual_data[Columns.week] == match_week)
                                ]
                                
                                # Filter by round number to get the specific match
                                individual_round_data = individual_match_data[
                                    individual_match_data[Columns.round_number] == round_number
                                ]
                                
                                individual_points = individual_round_data[Columns.points].sum() if not individual_round_data.empty else 0
                                
                                # Total points = individual points + team match points
                                total_points = individual_points + team_match_points
                                total_points_list.append(total_points)
                            
                            avg_points = round(sum(total_points_list) / len(total_points_list), 1) if total_points_list else 0.0
                            comparison_data[team][opponent] = {
                                'avg_score': avg_score,
                                'avg_points': avg_points,
                            }
            
            # Row/column order = full-season standings (not the selected week's points).
            standings_order = self._teams_in_standings_order(league, season, week=None)
            team_set = set(teams)
            sorted_teams = [t for t in standings_order if t in team_set]
            for t in teams:
                if t not in sorted_teams:
                    sorted_teams.append(t)
            team_positions = {team: pos + 1 for pos, team in enumerate(sorted_teams)}
            
            # ========== CREATE TABLE STRUCTURE ==========
            columns = [
                ColumnGroup(
                    title=f'{i18n_service.get_text("opponent")} →',
                    frozen='left',
                    columns=[
                        Column(
                            title="#", 
                            field='pos', 
                            width=ColumnWidths.position, 
                            align='center'
                        ),
                        Column(
                            title=f'{i18n_service.get_text("team")} ↓', 
                            field='team', 
                            width=ColumnWidths.team, 
                            align='left'
                        )
                    ]
                )
            ]
            
            # Add average columns first (bold) - right after position/team group
            columns.append(ColumnGroup(
                title=i18n_service.get_text("average"),
                columns=[
                    Column(
                        title=i18n_service.get_text("score"), 
                        field='avg_score', 
                        width=ColumnWidths.pins, 
                        align='center',
                        tooltip=f'{i18n_service.get_text("average")} {i18n_service.get_text("score")} vs. {i18n_service.get_text("all_opponents")}'
                    ),
                    Column(
                        title=i18n_service.get_text("points"), 
                        field='avg_points', 
                        width=ColumnWidths.points, 
                        align='center',
                        tooltip=f'{i18n_service.get_text("average")} {i18n_service.get_text("points")} vs. {i18n_service.get_text("all_opponents")}'
                    )
                ],
                header_style={"fontWeight": "bold"}
            ))
            
            # Add columns for each team (using sorted order)
            for team in sorted_teams:
                columns.append(ColumnGroup(
                    title=team,
                    columns=[
                        Column(
                            title=i18n_service.get_text("score"), 
                            field=f'{team}_score', 
                            width=ColumnWidths.pins, 
                            align='center',
                            tooltip=f'{i18n_service.get_text("average")} {i18n_service.get_text("score")} vs. {team}'
                        ),
                        Column(
                            title=i18n_service.get_text("points"), 
                            field=f'{team}_points', 
                            width=ColumnWidths.points, 
                            align='center',
                            tooltip=f'{i18n_service.get_text("average")} {i18n_service.get_text("points")} vs. {team}'
                        )
                    ]
                ))
            
            # ========== GENERATE TABLE ROWS ==========
            table_data = []
            cell_metadata = {}
            
            # Collect all score and points values for heat map min/max calculation
            all_scores = []
            all_points = []
            
            for team in sorted_teams:
                for opponent in sorted_teams:
                    if team != opponent and opponent in comparison_data.get(team, {}):
                        all_scores.append(comparison_data[team][opponent]['avg_score'])
                        all_points.append(comparison_data[team][opponent]['avg_points'])
            
            if not all_scores or not all_points:
                return TableData(
                    columns=columns,
                    data=[],
                    title=i18n_service.get_text("team_vs_team_comparison_matrix"),
                    description="No match data available",
                    config={"striped": True, "hover": True, "compact": True, "stickyHeader": True}
                )
            
            score_min, score_max = min(all_scores), max(all_scores)
            points_min, points_max = min(all_points), max(all_points)
            
            # Determine column indices for heat map (same for all rows)
            # Position: 0, Team: 1, Average: 2-3, then pairs of (score, points) for each opponent
            num_teams = len(sorted_teams)
            score_column_indices = []
            points_column_indices = []
            
            # Average columns are first (right after position and team)
            avg_score_col_idx = 2
            avg_points_col_idx = 3
            
            # Team columns come after averages
            col_idx = 4  # Start after position (0), team name (1), and averages (2-3)
            for _ in range(num_teams):
                score_column_indices.append(col_idx)
                points_column_indices.append(col_idx + 1)
                col_idx += 2
            
            empty_cell_style = {"backgroundColor": get_theme_color("background")}

            # Generate rows (using sorted teams)
            for row_idx, team in enumerate(sorted_teams):
                position = team_positions[team]
                row = [position, team]

                played_scores: List[float] = []
                played_points: List[float] = []

                # Add team columns (starting at column 4)
                col_idx = 4
                for opponent in sorted_teams:
                    if team != opponent:
                        if opponent in comparison_data.get(team, {}):
                            score = comparison_data[team][opponent]['avg_score']
                            points = comparison_data[team][opponent]['avg_points']
                            played_scores.append(score)
                            played_points.append(points)
                            row.extend([score, points])
                        else:
                            row.extend(["", ""])
                            cell_metadata[f"{row_idx}:{col_idx}"] = empty_cell_style
                            cell_metadata[f"{row_idx}:{col_idx + 1}"] = empty_cell_style
                        col_idx += 2
                    else:
                        row.extend(["", ""])
                        cell_metadata[f"{row_idx}:{col_idx}"] = empty_cell_style
                        cell_metadata[f"{row_idx}:{col_idx + 1}"] = empty_cell_style
                        col_idx += 2

                avg_score = (
                    round(sum(played_scores) / len(played_scores), 1) if played_scores else ""
                )
                avg_points = (
                    round(sum(played_points) / len(played_points), 1) if played_points else ""
                )
                row[2:2] = [avg_score, avg_points]

                table_data.append(row)
            
            # Heatmap coloring is now handled in the frontend
            # ========== RETURN TABLE DATA ==========
            return TableData(
                columns=columns,
                data=table_data,
                title=i18n_service.get_text("team_vs_team_comparison_matrix"),
                description=f"{i18n_service.get_text('team_vs_team_comparison_matrix_explanation')}{f' {i18n_service.get_text('week')} {week}.' if week else f' {i18n_service.get_text('article_male')} {i18n_service.get_text('season')}.'}",
                config={
                    "striped": True,
                    "hover": True,
                    "compact": True,
                    "stickyHeader": True
                },
                metadata={
                    "score_range": {"min": score_min, "max": score_max},
                    "points_range": {"min": points_min, "max": points_max},
                    "week": week
                }
            )
            
        except Exception as e:
            print(f"Error in get_team_vs_team_comparison_table: {str(e)}")
            return TableData(
                columns=[],
                data=[],
                title=i18n_service.get_text("team_vs_team_comparison_matrix"),
                description=f"Error: {str(e)}",
                config={"striped": True, "hover": True, "compact": True, "stickyHeader": True}
            )

    def _latest_week_by_league(self, season: str) -> Dict[str, int]:
        """One pass over season rows: max week per league (non-computed rows only)."""
        filters = {
            Columns.season: {"value": season, "operator": "eq"},
            Columns.computed_data: {"value": False, "operator": "eq"},
        }
        frame = self.adapter.get_filtered_data(
            columns=[Columns.league_name, Columns.week],
            filters=filters,
        )
        if frame.empty:
            return {}

        weeks = pd.to_numeric(frame[Columns.week], errors="coerce")
        frame = frame.assign(_week=weeks).dropna(subset=["_week"])
        if frame.empty:
            return {}

        out: Dict[str, int] = {}
        for league, group in frame.groupby(Columns.league_name, sort=False):
            league_name = str(league).strip()
            if not league_name or league_name.lower() in ("nan", "none", "<na>"):
                continue
            out[league_name] = int(group["_week"].max())
        return out

    def get_season_league_standings(self, season: str, division: Optional[str] = None) -> Dict[str, Any]:
        """
        Get latest week standings for all leagues in a season.
        
        Args:
            season: The season identifier
            
        Returns:
            Dictionary with leagues and their latest week standings
        """
        try:
            leagues = self.get_leagues(season=season)
            if not leagues:
                return {"leagues": []}

            if division:
                division_map = get_league_division_map()
                leagues = [lg for lg in leagues if division_map.get(lg) == division]

            latest_week_by_league = self._latest_week_by_league(season)

            # Get standings for each league's latest week
            league_standings = []
            
            for league in leagues:
                try:
                    latest_week = latest_week_by_league.get(league)
                    
                    if latest_week:
                        # Get the standings for the latest week
                        standings = self.get_league_week_table_simple(
                            season=season, 
                            league=league, 
                            week=latest_week
                        )
                        
                        # Get honor scores for the latest week
                        honor_scores = self.get_honor_scores(league, season, latest_week)
                        
                        if standings:
                            league_standings.append({
                                'league': league,
                                'league_long': resolve_league_long_name(league),
                                'week': latest_week,
                                'standings': standings.to_dict(),
                                'honor_scores': honor_scores
                            })
                            
                except Exception as e:
                    print(f"Error getting standings for league {league}: {e}")
                    continue
            
            return json_safe(
                {
                    "leagues": league_standings,
                    "season": season,
                }
            )

        except Exception as e:
            print(f"Error in get_season_league_standings: {e}")
            return {"leagues": []}

    def get_record_games(self, league: str) -> TableData:
        """Legacy method - returns individual records for backward compatibility"""
        return self.get_record_individual_games(league)

    def get_individual_matches(self, team: str, season: str, league: str) -> pd.DataFrame:
        """Get individual player matches with opponent scores for PvP win calculation"""
        try:
            # Get ALL individual player data for the league/season (not just our team)
            # We need this to find opponent matches
            all_player_filters = {
                Columns.league_name: {'value': league, 'operator': 'eq'},
                Columns.season: {'value': season, 'operator': 'eq'},
                Columns.computed_data: {'value': False, 'operator': 'eq'}  # Individual players only
            }
            
            all_player_data = self.adapter.get_filtered_data(filters=all_player_filters)
            
            if all_player_data.empty:
                return pd.DataFrame()
            
            # Filter to just our team's players
            our_team_data = all_player_data[all_player_data[Columns.team_name] == team]
            
            if our_team_data.empty:
                return pd.DataFrame()
            
            # For each player match, we need to find the opponent's score
            result_data = []
            
            for _, player_match in our_team_data.iterrows():
                week = player_match[Columns.week]
                round_num = player_match[Columns.round_number]
                opponent_team = player_match[Columns.team_name_opponent]
                player_name = player_match[Columns.player_name]
                player_score = player_match[Columns.score]
                
                # Find the opponent's score for the same match
                # Look in ALL player data for opponent team players in same week/round
                opponent_match = all_player_data[
                    (all_player_data[Columns.week] == week) &
                    (all_player_data[Columns.round_number] == round_num) &
                    (all_player_data[Columns.team_name] == opponent_team) &  # Their team is the opponent
                    (all_player_data[Columns.team_name_opponent] == team)  # They're playing against us
                ]
                
                if not opponent_match.empty:
                    # Find the opponent player with the same position or similar role
                    # For simplicity, we'll take the first opponent player
                    opponent_score = opponent_match[Columns.score].iloc[0]
                    
                    result_data.append({
                        'week': week,
                        'round_number': round_num,
                        'player_name': player_name,
                        'player_score': player_score,
                        'opponent_team': opponent_team,
                        'opponent_score': opponent_score,
                        'is_win': player_score > opponent_score
                    })
            
            return pd.DataFrame(result_data)
            
        except Exception as e:
            return pd.DataFrame()