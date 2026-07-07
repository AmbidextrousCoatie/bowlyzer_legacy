import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from app.models.table_data import Column, ColumnGroup, TableData
from app.services.i18n_service import i18n_service
from app.utils.color_constants import get_theme_color
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns

from app.cache.league_response_cache import league_cache_put, league_cache_try_get
from app.utils.tournament_benchmark import TournamentBenchmark, tournament_benchmark_enabled
from app.utils.tournament_stage_config import (
    public_stage_summary,
    stage_cut_rank_for_round,
)
from app.utils.tournament_utils import normalize_tournament_group_name

# KO-Finale last cluster: best-of-3 pin games vs two-game scratch total (see database/data/tournament_ko_config.json).
KO_FINALE_SERIES_BO3 = "bo3_pins"
KO_FINALE_SERIES_SCRATCH_2G = "scratch_total_2g"

# Gesamtwertung column widths (rank/hcp −30%, player −15%; Set round cols −15%).
_LB_COL_RANK_W = "44px"
_LB_COL_PLAYER_W = "110px"
_LB_COL_HCP_W = "55px"
_LB_COL_TOTAL_W = "90px"  # Gesamt / Ø totals (−15% from 100px)
_LB_COL_TOTAL_AVG = "60px"
_LB_COL_ROUND_W = "80px"  # Set 1, Set 2, … (−15% from 94px)

# Individual player stats page: `player_cards` in tournament_ko_config.json (same key as KO block: season||Event Name).
# Canonical render order when merging with explicit config (unknown ids dropped).
TOURNAMENT_PLAYER_CARD_ORDER: Tuple[str, ...] = (
    "summary_final_position",
    "summary_average",
    "summary_best_position",
    "best_highest_game",
    "best_highest_pair",
    "handicap_profile",
    "best_highest_block",
)
TOURNAMENT_PLAYER_VALID_CARDS = frozenset(TOURNAMENT_PLAYER_CARD_ORDER)


def _arith_round_int(x: float) -> int:
    """Round to nearest int, half away from zero (not Python banker's rounding)."""
    if not math.isfinite(x):
        return 0
    if x >= 0:
        return math.floor(x + 0.5)
    return -math.floor(-x + 0.5)


def _season_filter_tokens(season: str) -> Tuple[str, ...]:
    """
    Values that may appear in the Season column for the same competition year.

    URLs and some UIs use a calendar year (e.g. 2026) while CSVs use bowling labels (25/26).
    """
    s = str(season).strip()
    if not s:
        return ()
    out: List[str] = [s]
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        yy = f"{y % 100:02d}"
        yy_prev = f"{(y - 1) % 100:02d}"
        out.append(f"{yy_prev}/{yy}")
    return tuple(dict.fromkeys(out))


def _tournament_df_string_series(series: pd.Series) -> pd.Series:
    """
    Strip and stringify tournament key columns.

    ``dtype_normalization`` may coerce Player ID to nullable ``Int64``; ``fillna("")`` on that
    dtype raises, so nullable/extension numerics are cast through pandas string first.
    """
    s = series
    if pd.api.types.is_numeric_dtype(s.dtype) or pd.api.types.is_extension_array_dtype(
        s.dtype
    ):
        return s.astype("string").fillna("").str.strip()
    return s.fillna("").astype(str).str.strip()


def _attach_round_handicap_pivot(
    pivot: pd.DataFrame,
    work: pd.DataFrame,
    key_cols: List[str],
    game_numbers: List[int],
) -> pd.DataFrame:
    """Left-merge per-game handicap as ``__hc_{game}`` (pins per game, same grain as scratch)."""
    if not game_numbers or Columns.handicap not in work.columns:
        return pivot
    w = work
    per_game_hc = (
        w.assign(
            __hcv=pd.to_numeric(w[Columns.handicap], errors="coerce").fillna(0.0),
        )
        .groupby(key_cols + [Columns.game_number], dropna=False)["__hcv"]
        .max()
        .reset_index()
    )
    ph = per_game_hc.pivot_table(
        index=key_cols,
        columns=Columns.game_number,
        values="__hcv",
        aggfunc="max",
        fill_value=0.0,
    ).reset_index()
    for g in game_numbers:
        if g not in ph.columns:
            ph[g] = 0.0
    hc_merge = ph[key_cols].copy()
    for g in game_numbers:
        hc_merge[f"__hc_{g}"] = pd.to_numeric(ph[g], errors="coerce").fillna(0.0)
    out = pivot.merge(hc_merge, on=key_cols, how="left")
    for g in game_numbers:
        col = f"__hc_{g}"
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def _aggregate_handicap_leaderboard_label(player_rows: pd.DataFrame) -> Any:
    """
    Single handicap label for a player row on the total leaderboard (pins per game).
    Matches the player card idea: one int when constant, otherwise a min–max range.
    """
    if player_rows.empty or Columns.handicap not in player_rows.columns:
        return "—"
    hc_series = pd.to_numeric(player_rows[Columns.handicap], errors="coerce").dropna()
    if hc_series.empty:
        return "—"
    uniq = {round(float(x), 4) for x in hc_series.unique()}
    if len(uniq) == 1:
        return _arith_round_int(float(hc_series.iloc[0]))
    mn_f, mx_f = float(hc_series.min()), float(hc_series.max())
    return f"{_arith_round_int(mn_f)}-{_arith_round_int(mx_f)}"


def _handicap_per_game_label_and_scratch_plus_total(
    row: pd.Series, game_numbers: List[int]
) -> Tuple[Any, int]:
    """
    Label for one handicap column: single int when all games share the same hcp; else ``min-max`` range.

    ``total`` is sum over games of (scratch + handicap) for that stage row (works for any game count).
    """
    if not game_numbers:
        return 0, _arith_round_int(float(row.get("round_total", 0) or 0))
    hcs = [float(row.get(f"__hc_{g}", 0) or 0) for g in game_numbers]
    scrs = [float(row.get(g, 0) or 0) for g in game_numbers]
    total_wh = _arith_round_int(sum(s + h for s, h in zip(scrs, hcs)))
    if max(abs(h) for h in hcs) == 0:
        return 0, total_wh
    uniq = {round(h, 4) for h in hcs}
    if len(uniq) == 1:
        return _arith_round_int(hcs[0]), total_wh
    mn, mx = min(hcs), max(hcs)
    return f"{_arith_round_int(mn)}-{_arith_round_int(mx)}", total_wh


RoundLengthRow = Tuple[int, str, int]


def _with_progress_pins(df: pd.DataFrame, use_net: bool) -> pd.DataFrame:
    out = df.copy()
    scratch = pd.to_numeric(out[Columns.score], errors="coerce").fillna(0.0)
    if use_net and Columns.handicap in out.columns:
        hc = pd.to_numeric(out[Columns.handicap], errors="coerce").fillna(0.0)
        out["__pins"] = scratch + hc
    else:
        out["__pins"] = scratch
    return out


def _progress_player_names(df: pd.DataFrame) -> Set[str]:
    if Columns.player_name not in df.columns:
        return set()
    out: Set[str] = set()
    for raw in df[Columns.player_name].dropna().astype(str):
        name = str(raw).strip()
        if name and not TournamentService._is_ko_bye_player(name):
            out.add(name)
    return out


def _player_has_game_score(stage_df: pd.DataFrame, game_num: int) -> bool:
    sub = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(float(game_num))]
    if sub.empty:
        return False
    scores = pd.to_numeric(sub[Columns.score], errors="coerce").fillna(0)
    return bool((scores > 0).any())


def _player_completed_round_through(
    all_df: pd.DataFrame, player: str, rn: int, through_game: int
) -> bool:
    stage = all_df[
        all_df[Columns.round_number].eq(float(rn))
        & all_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())
    ]
    for g in range(through_game + 1):
        if not _player_has_game_score(stage, g):
            return False
    return True


def _player_completed_full_round(
    all_df: pd.DataFrame, player: str, rn: int, round_length: int
) -> bool:
    if round_length <= 0:
        return True
    return _player_completed_round_through(all_df, player, rn, round_length - 1)


def _field_max_games_played(all_df: pd.DataFrame) -> int:
    """Most games bowled by any participant (unique round + game index)."""
    played = all_df[pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0) > 0]
    if played.empty:
        return 0
    per_player = (
        played.groupby([Columns.player_name, Columns.round_number, Columns.game_number], dropna=False)
        .size()
        .reset_index()
        .groupby(Columns.player_name, dropna=False)
        .size()
    )
    return int(per_player.max()) if not per_player.empty else 0


def _progress_game_slots(
    round_lengths: List[RoundLengthRow], limit: int
) -> List[Tuple[int, int]]:
    """Global game timeline as (round_number, game_index) up to limit slots."""
    if limit <= 0:
        return []
    slots: List[Tuple[int, int]] = []
    for rn, _, length in round_lengths:
        for g in range(length):
            slots.append((rn, g))
            if len(slots) >= limit:
                return slots
    return slots


def _eligible_players_pace_snapshot(
    all_df: pd.DataFrame,
    round_lengths: List[RoundLengthRow],
    rn: int,
    through_game: int,
) -> Set[str]:
    eligible: Set[str] = set()
    for name in _progress_player_names(all_df):
        ok = True
        for prev_rn, _, prev_len in round_lengths:
            if prev_rn >= rn:
                break
            if not _player_completed_full_round(all_df, name, prev_rn, prev_len):
                ok = False
                break
        if ok and _player_completed_round_through(all_df, name, rn, through_game):
            eligible.add(name)
    return eligible


def _cumulative_pins_through(
    all_df: pd.DataFrame,
    player: str,
    rn: int,
    through_game_in_round: int,
    round_lengths: List[RoundLengthRow],
) -> Tuple[float, int]:
    name = str(player).strip()
    total_pins = 0.0
    games = 0
    for rno, _, length in round_lengths:
        if rno < rn:
            g_end = length - 1
        elif rno == rn:
            g_end = through_game_in_round
        else:
            continue
        stage = all_df[
            all_df[Columns.round_number].eq(float(rno))
            & all_df[Columns.player_name].astype(str).str.strip().eq(name)
        ]
        for g in range(g_end + 1):
            sub = stage[pd.to_numeric(stage[Columns.game_number], errors="coerce").eq(float(g))]
            if sub.empty:
                continue
            scratch = pd.to_numeric(sub[Columns.score], errors="coerce").fillna(0)
            if not (scratch > 0).any():
                continue
            pins = pd.to_numeric(sub["__pins"], errors="coerce").fillna(0).sum()
            total_pins += float(pins)
            games += 1
    return total_pins, games


def _progress_snapshot_rows(
    all_df: pd.DataFrame,
    round_lengths: List[RoundLengthRow],
    rn: int,
    through_game: int,
) -> List[Tuple[str, float, float, int]]:
    """Per-player cumulative net standings through (rn, through_game).

    Each row is (name, total_pins, net_avg, games). Sorted by total_pins desc (tournament
    standing / leader), then net_avg, then name.
    """
    chunks: List[pd.DataFrame] = []
    for rno, _, length in round_lengths:
        if rno > rn:
            break
        g_end = through_game if rno == rn else length - 1
        stage = all_df[
            all_df[Columns.round_number].eq(float(rno))
            & pd.to_numeric(all_df[Columns.game_number], errors="coerce").le(float(g_end))
        ]
        if not stage.empty:
            chunks.append(stage)
    if not chunks:
        return []
    subset = pd.concat(chunks, ignore_index=True)
    played = pd.to_numeric(subset[Columns.score], errors="coerce").fillna(0) > 0
    subset = subset[played]
    if subset.empty:
        return []
    per_game = (
        subset.groupby(
            [Columns.player_name, Columns.round_number, Columns.game_number],
            dropna=False,
        )["__pins"]
        .sum()
        .reset_index()
    )
    by_player = per_game.groupby(Columns.player_name, dropna=False).agg(
        total_pins=("__pins", "sum"),
        games=("__pins", "count"),
    )
    rows: List[Tuple[str, float, float, int]] = []
    for pname, row in by_player.iterrows():
        name = str(pname)
        if TournamentService._is_ko_bye_player(name):
            continue
        games = int(row["games"])
        if games <= 0:
            continue
        total = float(row["total_pins"])
        rows.append((name, total, total / games, games))
    rows.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return rows


def _pace_cut_from_eligible(
    all_df: pd.DataFrame,
    eligible: Set[str],
    rn: int,
    through_game: int,
    round_lengths: List[RoundLengthRow],
    cut_rank: int,
) -> Optional[Tuple[float, int]]:
    """Return (cut_average, cut_rank) from eligible players at this snapshot, or None if too few."""
    if cut_rank < 1 or len(eligible) < cut_rank:
        return None
    rows: List[Tuple[str, float, float]] = []
    for name in eligible:
        total_pins, games = _cumulative_pins_through(all_df, name, rn, through_game, round_lengths)
        if games <= 0:
            continue
        rows.append((name, total_pins / games, total_pins))
    if len(rows) < cut_rank:
        return None
    rows.sort(key=lambda t: (-t[1], -t[2], t[0]))
    cut_avg = round(rows[cut_rank - 1][1], 2)
    return cut_avg, cut_rank


def _field_progress_prepare_game_pins(all_df: pd.DataFrame) -> Dict[Tuple[int, int], Dict[str, float]]:
    """(round_number, game_number) -> {player: pin_sum} for bowled games (score > 0)."""
    played = all_df[pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0) > 0]
    if played.empty:
        return {}
    tmp = played.copy()
    tmp["_player"] = tmp[Columns.player_name].astype(str).str.strip()
    tmp["_rn"] = pd.to_numeric(tmp[Columns.round_number], errors="coerce").astype(int)
    tmp["_gn"] = pd.to_numeric(tmp[Columns.game_number], errors="coerce").astype(int)
    out: Dict[Tuple[int, int], Dict[str, float]] = {}
    grouped = tmp.groupby(["_rn", "_gn", "_player"], dropna=False)["__pins"].sum()
    for (rn, gn, player), pins in grouped.items():
        name = str(player).strip()
        if TournamentService._is_ko_bye_player(name):
            continue
        key = (int(rn), int(gn))
        out.setdefault(key, {})[name] = float(pins)
    return out


def _field_progress_prepare_round_games(all_df: pd.DataFrame) -> Dict[Tuple[str, int], frozenset[int]]:
    """(player, round_number) -> game indices with score > 0 in that round."""
    played = all_df[pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0) > 0]
    if played.empty:
        return {}
    tmp = played.copy()
    tmp["_player"] = tmp[Columns.player_name].astype(str).str.strip()
    tmp["_rn"] = pd.to_numeric(tmp[Columns.round_number], errors="coerce").astype(int)
    tmp["_gn"] = pd.to_numeric(tmp[Columns.game_number], errors="coerce").astype(int)
    out: Dict[Tuple[str, int], frozenset[int]] = {}
    for (player, rn), games in tmp.groupby(["_player", "_rn"], dropna=False)["_gn"]:
        name = str(player).strip()
        if TournamentService._is_ko_bye_player(name):
            continue
        out[(name, int(rn))] = frozenset(int(g) for g in games)
    return out


def _field_progress_cumulative_games(
    rn: int, through_game: int, round_lengths: List[RoundLengthRow]
) -> List[Tuple[int, int]]:
    games: List[Tuple[int, int]] = []
    for rno, _, length in round_lengths:
        if rno > rn:
            break
        g_end = through_game if rno == rn else length - 1
        for g in range(g_end + 1):
            games.append((rno, g))
    return games


def _field_progress_delta_games(
    prev: Optional[Tuple[int, int]],
    curr: Tuple[int, int],
    round_lengths: List[RoundLengthRow],
) -> List[Tuple[int, int]]:
    curr_games = _field_progress_cumulative_games(curr[0], curr[1], round_lengths)
    if prev is None:
        return curr_games
    prev_set = set(_field_progress_cumulative_games(prev[0], prev[1], round_lengths))
    return [g for g in curr_games if g not in prev_set]


def _field_progress_snapshot_from_cumulative(
    cum_pins: Dict[str, float],
    cum_games: Dict[str, int],
) -> List[Tuple[str, float, float, int]]:
    rows: List[Tuple[str, float, float, int]] = []
    for name, games in cum_games.items():
        if games <= 0:
            continue
        total = float(cum_pins.get(name, 0.0))
        rows.append((name, total, total / games, games))
    rows.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return rows


def _field_progress_eligible_at_snapshot(
    field_players: List[str],
    rn: int,
    through_game: int,
    round_lengths: List[RoundLengthRow],
    player_round_games: Dict[Tuple[str, int], frozenset[int]],
) -> Set[str]:
    eligible: Set[str] = set()
    for name in field_players:
        ok = True
        for prev_rn, _, prev_len in round_lengths:
            if prev_rn >= rn:
                break
            played = player_round_games.get((name, prev_rn), frozenset())
            if not all(g in played for g in range(prev_len)):
                ok = False
                break
        if not ok:
            continue
        played_curr = player_round_games.get((name, rn), frozenset())
        if all(g in played_curr for g in range(through_game + 1)):
            eligible.add(name)
    return eligible


def _pace_cut_from_cumulative(
    eligible: Set[str],
    cum_pins: Dict[str, float],
    cum_games: Dict[str, int],
    cut_rank: int,
) -> Optional[Tuple[float, int]]:
    if cut_rank < 1 or len(eligible) < cut_rank:
        return None
    rows: List[Tuple[str, float, float]] = []
    for name in eligible:
        games = cum_games.get(name, 0)
        if games <= 0:
            continue
        total = float(cum_pins.get(name, 0.0))
        rows.append((name, total / games, total))
    if len(rows) < cut_rank:
        return None
    rows.sort(key=lambda t: (-t[1], -t[2], t[0]))
    cut_avg = round(rows[cut_rank - 1][1], 2)
    return cut_avg, cut_rank


class TournamentService:
    def __init__(self, adapter_type=DataAdapterSelector.PANDAS, database: str = None):
        self.database = database
        self.adapter = DataAdapterFactory.create_adapter(adapter_type, database=database)
        self._tournament_df_cache: Dict[Tuple[str, str], pd.DataFrame] = {}
        self._ko_bracket_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._field_progress_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _tournament_cache_key(self, season: Optional[str], tournament: Optional[str]) -> Tuple[str, str]:
        return (str(season or "").strip(), str(tournament or "").strip())

    def _store_ko_bracket_cache(self, season: str, tournament: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ko_bracket_cache[self._tournament_cache_key(season, tournament)] = payload
        return payload

    def _get_tournament_df(self, season: Optional[str] = None, tournament: Optional[str] = None) -> pd.DataFrame:
        """
        Load data and apply robust string-based filters.
        This avoids dtype mismatches (e.g., Season 2026 as int in CSV vs "2026" in query).
        """
        cache_key = self._tournament_cache_key(season, tournament)
        cached = self._tournament_df_cache.get(cache_key)
        if cached is not None:
            return cached

        df = self.adapter.get_filtered_data(filters={})
        if df.empty:
            return df

        # Event type filter is mandatory for this service.
        if Columns.event_type in df.columns:
            event_type_series = df[Columns.event_type].astype(str).str.strip().str.lower()
            df = df[event_type_series.eq("tournament")]
        else:
            return df.iloc[0:0].copy()

        if season and Columns.season in df.columns:
            tokens = _season_filter_tokens(str(season))
            col = df[Columns.season].astype(str).str.strip()
            df = df[col.isin(tokens)]

        if tournament:
            from data_access.competition_schema import competition_event_column

            event_col = competition_event_column(df)
            if event_col:
                tournament_norm = str(tournament).strip()
                event_series = df[event_col].astype(str).str.strip()
                exact_mask = event_series.eq(tournament_norm)
                if exact_mask.any():
                    df = df[exact_mask]
                else:
                    group_norm = normalize_tournament_group_name(tournament_norm)
                    df = df[
                        event_series.map(normalize_tournament_group_name).eq(group_norm)
                    ]

        # Normalize frequently used tournament keys so downstream groupby/pivot
        # logic is stable even when source CSV has empty cells (read as NaN).
        if Columns.club in df.columns:
            df[Columns.club] = _tournament_df_string_series(df[Columns.club])
        if Columns.player_name in df.columns:
            df[Columns.player_name] = _tournament_df_string_series(df[Columns.player_name])
        if Columns.player_id in df.columns:
            df[Columns.player_id] = _tournament_df_string_series(df[Columns.player_id])
        if Columns.round_name in df.columns:
            df[Columns.round_name] = _tournament_df_string_series(df[Columns.round_name])
        self._tournament_df_cache[cache_key] = df
        return df

    def _config_event_name(
        self,
        season: str,
        tournament: str,
        df: Optional[pd.DataFrame] = None,
    ) -> str:
        """Canonical event label for tournament_ko_config / stage_definitions lookups."""
        if df is not None and not df.empty:
            from data_access.competition_schema import competition_event_column

            event_col = competition_event_column(df)
            if event_col:
                names = sorted(
                    {
                        str(x).strip()
                        for x in df[event_col].dropna().astype(str).tolist()
                        if str(x).strip()
                    }
                )
                if len(names) == 1:
                    return names[0]
        from app.utils.tournament_stage_config import resolve_stage_event_name

        return resolve_stage_event_name(season, tournament)

    def get_tournaments(self, season: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=None)
        from data_access.competition_schema import competition_event_column

        event_col = competition_event_column(df)
        if df.empty or not event_col:
            return []
        raw = [x for x in df[event_col].dropna().astype(str).unique().tolist() if x.strip()]
        groups = {normalize_tournament_group_name(name) for name in raw}
        return sorted(name for name in groups if name)

    def get_seasons(self, tournament: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=None, tournament=tournament)
        if df.empty or Columns.season not in df.columns:
            return []
        vals = [str(x).strip() for x in df[Columns.season].dropna().astype(str).tolist() if str(x).strip()]
        return sorted(list(set(vals)))

    def get_players(self, season: str, tournament: str, round_number: Optional[int] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if round_number is not None and not df.empty:
            df = self._scope_df(df, round_number)
        if df.empty or Columns.player_name not in df.columns:
            return []
        return sorted([x for x in df[Columns.player_name].dropna().astype(str).unique().tolist() if x.strip()])

    def get_rounds(
        self,
        season: str,
        tournament: str,
        df: Optional[pd.DataFrame] = None,
    ) -> List[Dict[str, Any]]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return []
        pairs = (
            df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .copy()
        )
        pairs[Columns.round_number] = pd.to_numeric(pairs[Columns.round_number], errors="coerce").astype("Int64")
        pairs = pairs.dropna(subset=[Columns.round_number]).sort_values(by=Columns.round_number)
        out = []
        for _, row in pairs.iterrows():
            out.append(
                {
                    "round_number": int(row[Columns.round_number]),
                    "round_name": str(row.get(Columns.round_name, "") or "").strip(),
                }
            )
        return out

    def _handicap_format_info(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Tournament-wide summary of handicap-related CSV columns for the format infobox.

        ``pins`` uses integer pins per game from ``Handicap`` when the column exists and has
        values. ``a_priori_average`` and ``handicap_reference`` use float summaries when present.
        """
        cols = {
            "handicap": Columns.handicap in df.columns,
            "apriori_average": Columns.apriori_average in df.columns,
            "handicap_reference": Columns.handicap_reference in df.columns,
        }

        def _pin_summary(series: pd.Series) -> Optional[Dict[str, Any]]:
            s = pd.to_numeric(series, errors="coerce").dropna()
            if s.empty:
                return None
            vmin, vmax = float(s.min()), float(s.max())
            if abs(vmax - vmin) < 0.5:
                return {"kind": "uniform", "value": _arith_round_int((vmin + vmax) / 2)}
            return {
                "kind": "range",
                "min": _arith_round_int(vmin),
                "max": _arith_round_int(vmax),
                "mean": round(float(s.mean()), 1),
            }

        def _float_summary(series: pd.Series, decimals: int = 1) -> Optional[Dict[str, Any]]:
            s = pd.to_numeric(series, errors="coerce").dropna()
            if s.empty:
                return None
            vmin, vmax = float(s.min()), float(s.max())
            tol = 10 ** (-decimals)
            if abs(vmax - vmin) < tol:
                return {"kind": "uniform", "value": round((vmin + vmax) / 2.0, decimals)}
            return {
                "kind": "range",
                "min": round(vmin, decimals),
                "max": round(vmax, decimals),
                "mean": round(float(s.mean()), decimals),
            }

        out: Dict[str, Any] = {
            "used": self._tournament_df_has_meaningful_handicap(df),
            "columns": cols,
            "pins": None,
            "a_priori_average": None,
            "handicap_reference": None,
        }
        if df.empty:
            return out

        if cols["handicap"]:
            out["pins"] = _pin_summary(df[Columns.handicap])

        if cols["apriori_average"]:
            out["a_priori_average"] = _float_summary(df[Columns.apriori_average], 1)

        if cols["handicap_reference"]:
            out["handicap_reference"] = _float_summary(df[Columns.handicap_reference], 1)

        return out

    def get_tournament_format_info(self, season: str, tournament: str) -> Dict[str, Any]:
        """
        Rounds from CSV plus KO/cut settings from ``database/data/tournament_ko_config.json``.

        Used by the Turnier UI (format info popup).
        """
        df = self._get_tournament_df(season=season, tournament=tournament)
        rounds = self.get_rounds(season, tournament, df=df)
        config_event = self._config_event_name(season, tournament, df)
        block = self._ko_config_entry(season, tournament, df=df)

        public_config: Dict[str, Any] = {}
        config_note: Optional[str] = None
        for k, v in block.items():
            sk = str(k)
            if sk == "_comment":
                if isinstance(v, str) and v.strip():
                    config_note = v.strip()
                continue
            if sk.startswith("_"):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                public_config[sk] = v
            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                public_config[sk] = list(v)

        mode = self._ko_finale_series_mode(season, tournament)
        if mode == KO_FINALE_SERIES_SCRATCH_2G:
            finale_de = "KO-Finale: zwei Spiele Scratch-Gesamt"
            finale_en = "KO finals: two-game scratch series total"
        else:
            finale_de = "KO-Finale: Best-of-3 (Pinfall je Spiel)"
            finale_en = "KO finals: best-of-3 pinfall"

        span = self._ko_qualifying_cut_span_config(season, tournament)
        pair = self._ko_qualifying_cut_pair(season, tournament)
        ko_fin_rn: Optional[int] = None
        if not df.empty:
            ko_fin_rn = self._ko_finale_round_number(df)

        enriched_rounds: List[Dict[str, Any]] = []
        for r in rounds:
            rn = int(r["round_number"])
            name = str(r.get("round_name") or "").strip()
            enriched_rounds.append(
                {
                    "round_number": rn,
                    "round_name": name,
                    "is_ko_finale_cluster": bool(
                        ko_fin_rn is not None and rn == int(ko_fin_rn)
                    ),
                }
            )

        return {
            "round_count": len(rounds),
            "rounds": enriched_rounds,
            "handicap": self._handicap_format_info(df),
            "ko_finale_round_number_in_data": ko_fin_rn,
            "ko_finale_series": mode,
            "ko_finale_series_label_de": finale_de,
            "ko_finale_series_label_en": finale_en,
            "qualifying_cut_span": span,
            "qualifying_cut_pair": (
                {"round": int(pair[0]), "rank": int(pair[1])} if pair else None
            ),
            "qualifying_stages": public_stage_summary(season, config_event),
            "config": public_config,
            "config_note": config_note,
        }

    def _scope_df(self, df: pd.DataFrame, round_number: Optional[int]) -> pd.DataFrame:
        if round_number is None:
            return df.copy()
        return df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(round_number))].copy()

    @staticmethod
    def _has_any_club_value(df: pd.DataFrame) -> bool:
        if Columns.club not in df.columns:
            return False
        vals = df[Columns.club].fillna("").astype(str).str.strip()
        return vals.ne("").any()

    @staticmethod
    def _played_games_count(series: pd.Series) -> int:
        scores = pd.to_numeric(series, errors="coerce").fillna(0)
        return int(scores.gt(0).sum())

    def _top_n_games(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        game_df = scope_df.copy()
        game_df[Columns.score] = pd.to_numeric(game_df[Columns.score], errors="coerce")
        game_df = game_df.dropna(subset=[Columns.score]).sort_values(by=Columns.score, ascending=False).head(n)
        out: List[Dict[str, Any]] = []
        for _, row in game_df.iterrows():
            g = int(pd.to_numeric(row.get(Columns.game_number), errors="coerce")) + 1
            out.append(
                {
                    "player": str(row.get(Columns.player_name, "")),
                    "club": str(row.get(Columns.club, "")),
                    "stage": str(row.get(Columns.round_name, "")),
                    "label": f"G{g}",
                    "value": int(row[Columns.score]),
                    "display_value": f"{int(row[Columns.score])}",
                }
            )
        return out

    def _top_n_pairs(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        pair_rows: List[Dict[str, Any]] = []
        work = scope_df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")
        grouped = work.groupby([Columns.round_name, Columns.player_name, Columns.club], dropna=False)
        for (round_name, player_name, club), gdf in grouped:
            scores = {int(r[Columns.game_number]): int(r[Columns.score]) for _, r in gdf.iterrows() if pd.notna(r[Columns.game_number])}
            one_based_games = sorted([x + 1 for x in scores.keys()])
            for start in one_based_games:
                if start % 2 == 1 and (start + 1) in one_based_games:
                    pair_rows.append(
                        {
                            "player": str(player_name),
                            "club": str(club),
                            "stage": str(round_name or ""),
                            "label": f"G{start}+G{start+1}",
                            "value": int(scores[start - 1] + scores[start]),
                            "display_value": f"{int(scores[start - 1] + scores[start])}",
                        }
                    )
        if not pair_rows:
            return []
        return (
            pd.DataFrame(pair_rows)
            .sort_values(by="value", ascending=False)
            .head(n)
            .to_dict(orient="records")
        )

    def _top_n_blocks(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        work = scope_df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        block_df = (
            work.groupby([Columns.round_name, Columns.player_name, Columns.club], dropna=False)[Columns.score]
            .agg(["sum", "count"])
            .reset_index()
            .rename(columns={"sum": "value", "count": "games"})
            .sort_values(by="value", ascending=False)
            .head(n)
        )
        out: List[Dict[str, Any]] = []
        for _, r in block_df.iterrows():
            avg = float(r["value"]) / max(int(r["games"]), 1)
            out.append(
                {
                    "player": str(r[Columns.player_name]),
                    "club": str(r.get(Columns.club, "")),
                    "stage": str(r[Columns.round_name]),
                    "label": "Block",
                    "value": int(r["value"]),
                    "display_value": f"{int(r['value'])} (\u2300{avg:.1f})",
                }
            )
        return out

    def _build_best_efforts_scope_payload(self, scope_df: pd.DataFrame, stage_label: str, n: int) -> Dict[str, Any]:
        return {
            "scope": stage_label,
            "best_games": self._top_n_games(scope_df, n),
            "best_pairs": self._top_n_pairs(scope_df, n),
            "best_blocks": self._top_n_blocks(scope_df, n),
        }

    def get_best_efforts(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        top_n: int = 5,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"n": top_n, "sections": []}

        if round_number is not None:
            scope_df = self._scope_df(df, round_number)
            stage_name = (
                str(scope_df[Columns.round_name].dropna().iloc[0])
                if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                else f"Round {round_number}"
            )
            return {"n": top_n, "sections": [self._build_best_efforts_scope_payload(scope_df, stage_name, top_n)]}

        sections: List[Dict[str, Any]] = []
        round_rows = (
            df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        for _, rr in round_rows.iterrows():
            rn = int(pd.to_numeric(rr[Columns.round_number], errors="coerce"))
            stage_name = str(rr.get(Columns.round_name, "") or f"Round {rn}")
            stage_df = self._scope_df(df, rn)
            sections.append(self._build_best_efforts_scope_payload(stage_df, stage_name, top_n))

        sections.append(self._build_best_efforts_scope_payload(df, "Overall", top_n))
        return {"n": top_n, "sections": sections}

    def get_summary_cards(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        top_n: int = 5,
        df: Optional[pd.DataFrame] = None,
        ko_bracket: Optional[Dict[str, Any]] = None,
        rounds: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"cards": []}
        scope_df = self._scope_df(df, round_number)
        if scope_df.empty:
            return {"cards": []}

        ko_bracket_pre = ko_bracket or self._build_ko_bracket_payload(season, tournament, df=df)
        ko_fin_rn = self._ko_finale_round_number(df)
        is_ko_finale_view = (
            round_number is not None
            and ko_fin_rn is not None
            and int(round_number) == int(ko_fin_rn)
            and bool(ko_bracket_pre.get("matches"))
        )
        fin_m = next((m for m in ko_bracket_pre.get("matches", []) if m.get("key") == "F"), None)
        ko_final_winner_name = self._ko_match_winner_name(fin_m) if fin_m else None
        # Gesamt + decided KO final: same summary as KO-finale filter — winner only, no pin-leader / stage cards.
        gesamt_ko_tournament_winner = (
            round_number is None
            and ko_fin_rn is not None
            and bool(ko_bracket_pre.get("matches"))
            and bool(ko_final_winner_name)
        )

        participants = int(scope_df[Columns.player_id].nunique()) if Columns.player_id in scope_df.columns else 0
        rounds = rounds if rounds is not None else (
            self.get_rounds(season, tournament, df=df)
            if round_number is None
            else [
                {
                    "round_number": round_number,
                    "round_name": str(scope_df[Columns.round_name].dropna().iloc[0])
                    if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                    else f"Round {round_number}",
                }
            ]
        )
        latest_round = rounds[-1] if rounds else {"round_number": None, "round_name": ""}
        latest_round_date_subtitle = ""
        if latest_round.get("round_number") is not None and Columns.date in scope_df.columns:
            latest_round_df_for_date = scope_df[
                pd.to_numeric(scope_df[Columns.round_number], errors="coerce").eq(float(latest_round["round_number"]))
            ].copy()
            date_vals = (
                latest_round_df_for_date[Columns.date].dropna().astype(str).str.strip().tolist()
                if not latest_round_df_for_date.empty
                else []
            )
            date_vals = sorted([d for d in date_vals if d])
            if date_vals:
                latest_round_date_subtitle = date_vals[0] if len(set(date_vals)) == 1 else f"{date_vals[0]} to {date_vals[-1]}"

        # Stage cutoff for cumulative leader/cutline when viewing Gesamt (latest qualifying stage).
        # Tournament leader: same avg_net ladder as Gesamtwertung sorted by average.
        tournament_leader = None
        tournament_leader_avg = None
        tournament_leader_total = None
        use_net_pins = self._tournament_df_has_meaningful_handicap(df)
        include_club = self._has_any_club_value(df)
        summary_through_round: Optional[int] = (
            None if round_number is None else int(round_number)
        )
        ranked_avg = self._avg_net_standings_from_gesamt_pivot(
            df, through_round=summary_through_round, include_club=include_club
        )
        if not ranked_avg.empty:
            leader_row = ranked_avg.iloc[0]
            tournament_leader = leader_row
            tournament_leader_avg = float(leader_row["avg_net"])
            metric_col = "total_net" if use_net_pins and "total_net" in leader_row else "total_score"
            tournament_leader_total = int(round(float(leader_row[metric_col])))

        # Round / stage winner: highest set total (incl. handicap) in scope.
        set_winner_scope_round = round_number
        best_set = self._best_set_winner_in_scope(df, round_number=set_winner_scope_round)

        cards = [
            {"title": "Tournament", "value": tournament, "subtitle": season, "type": "stat"},
            {
                "title": "Current Round",
                "value": latest_round.get("round_name") or f"Round {latest_round.get('round_number')}",
                "subtitle": latest_round_date_subtitle
                or (f"#{latest_round.get('round_number')}" if latest_round.get("round_number") else ""),
                "type": "stat",
            },
        ]
        card_round: Optional[int] = int(round_number) if round_number is not None else None
        if card_round is None:
            card_round = self._latest_qualifying_round_number(df)
        if card_round is None and latest_round.get("round_number") is not None:
            card_round = int(latest_round["round_number"])
        cut_line_card = (
            self._build_cut_line_card(
                df,
                season,
                tournament,
                card_round,
                gesamt_view=round_number is None,
            )
            if card_round is not None
            else None
        )
        pins_label = "pins (netto)" if use_net_pins else "pins"
        if tournament_leader is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
            subtitle = f"\u2300{tournament_leader_avg:.1f} ({tournament_leader_total} {pins_label})"
            cards.append(
                {
                    "title": "Tournament Leader",
                    "value": tournament_leader[Columns.player_name],
                    "subtitle": subtitle,
                    "type": "stat",
                }
            )
        cards.append(
            {
                "title": "Participants",
                "value": participants,
                "subtitle": "Field size",
                "type": "stat",
            }
        )
        if (is_ko_finale_view or gesamt_ko_tournament_winner) and ko_final_winner_name:
            cards.append(
                {
                    "title": "Tournament Winner",
                    "value": ko_final_winner_name,
                    "subtitle": self._ko_final_winner_card_subtitle(fin_m) if fin_m else "",
                    "type": "stat",
                }
            )
        if best_set is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
            stage_subtitle = f"{best_set['round_name']}: {best_set['set_total']} {pins_label}"
            cards.append(
                {
                    "title": "Stage Winner",
                    "value": best_set["player"],
                    "subtitle": stage_subtitle,
                    "type": "stat",
                }
            )
        if cut_line_card is not None:
            cards.append(cut_line_card)
        return {"cards": cards}

    def _build_leaderboard_df(self, df: pd.DataFrame, round_number: Optional[int] = None) -> pd.DataFrame:
        work = df.copy()
        if round_number is not None:
            work = work[pd.to_numeric(work[Columns.round_number], errors="coerce").eq(float(round_number))]
        if work.empty:
            return pd.DataFrame()
        include_club = self._has_any_club_value(work)

        # If postprocessed data exists, use the last game snapshot per player.
        if Columns.cumulative_score in work.columns and Columns.stage_rank in work.columns:
            game_vals = pd.to_numeric(work[Columns.game_number], errors="coerce")
            max_game = game_vals.max()
            snap = work[game_vals.eq(max_game)].copy()
            snap["rank"] = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
            snap["total_score"] = pd.to_numeric(snap[Columns.cumulative_score], errors="coerce")
            snap["player"] = snap[Columns.player_name].astype(str)
            snap["player_id"] = snap[Columns.player_id].astype(str)
            snap["club"] = snap.get(Columns.club, "").astype(str) if include_club else ""
            out_cols = ["rank", "player", "player_id", "total_score"]
            if include_club:
                out_cols.insert(3, "club")
            out = snap[out_cols].dropna(subset=["total_score"])
            return out.sort_values(by=["rank", "player"]).reset_index(drop=True)

        group_keys = [Columns.player_name, Columns.player_id]
        if include_club:
            group_keys.append(Columns.club)
        grouped = (
            work.groupby(group_keys, dropna=False)[Columns.score]
            .sum()
            .reset_index()
            .rename(
                columns={
                    Columns.player_name: "player",
                    Columns.player_id: "player_id",
                    Columns.score: "total_score",
                }
            )
        )
        if include_club:
            grouped = grouped.rename(columns={Columns.club: "club"})
        else:
            grouped["club"] = ""
        grouped["rank"] = grouped["total_score"].rank(method="min", ascending=False).astype(int)
        return grouped.sort_values(by=["rank", "player"]).reset_index(drop=True)

    def _latest_qualifying_round_number(self, df: pd.DataFrame) -> Optional[int]:
        """Last pre-KO stage (or last stage when there is no KO round)."""
        if df.empty or Columns.round_number not in df.columns:
            return None
        work = df.copy()
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        round_numbers = sorted({int(x) for x in work[Columns.round_number].dropna().unique().tolist()})
        if not round_numbers:
            return None
        ko_fin_rn = self._ko_finale_round_number(df)
        qualifying = [r for r in round_numbers if ko_fin_rn is None or int(r) != int(ko_fin_rn)]
        return max(qualifying) if qualifying else max(round_numbers)

    def _leaderboard_group_keys(self, df: pd.DataFrame, *, include_club: bool) -> Tuple[List[Any], str]:
        """Group-by keys for tournament leaderboard rows (must match across rank map + Gesamt shading)."""
        id_col = Columns.player_id if Columns.player_id in df.columns else "__player_id_missing__"
        group_keys: List[Any] = [Columns.player_name, id_col]
        if include_club:
            group_keys.append(Columns.club)
        return group_keys, id_col

    @staticmethod
    def _leaderboard_row_key(row: Any, group_keys: List[Any]) -> Tuple[Any, ...]:
        return tuple(row[gk] for gk in group_keys)

    def _leaderboard_rank_map_at_round(
        self,
        df: pd.DataFrame,
        round_number: int,
        *,
        include_club: bool,
    ) -> Dict[Tuple[Any, ...], int]:
        """
        Per-player # rank at the end of ``round_number``, matching the single-stage
        leaderboard ladder (used for cut-line row shading on Gesamtwertung).
        """
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        scoped = work[work[Columns.round_number].eq(float(round_number))].copy()
        if scoped.empty:
            return {}

        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)
            scoped[id_col] = scoped[Columns.player_name].astype(str)

        round_scores = (
            scoped.groupby(group_keys, dropna=False)[Columns.score]
            .sum()
            .reset_index(name="round_score")
        )
        use_hc = self._tournament_df_has_meaningful_handicap(df) and Columns.handicap in scoped.columns
        if use_hc:
            scoped_net = scoped.assign(
                _rn=scoped[Columns.score]
                + pd.to_numeric(scoped[Columns.handicap], errors="coerce").fillna(0)
            )
            rn_df = scoped_net.groupby(group_keys, dropna=False)["_rn"].sum().reset_index(name="round_net")
            leaderboard = round_scores.merge(rn_df, on=group_keys, how="left")
            leaderboard["round_net"] = (
                pd.to_numeric(leaderboard["round_net"], errors="coerce").fillna(0).astype(int)
            )
            leaderboard = leaderboard.sort_values(
                by=["round_net", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)
            leaderboard["rank"] = leaderboard["round_net"].rank(method="min", ascending=False).astype(int)
        else:
            leaderboard = round_scores.sort_values(
                by=["round_score", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)
            leaderboard["rank"] = leaderboard["round_score"].rank(method="min", ascending=False).astype(int)

        out: Dict[Tuple[Any, ...], int] = {}
        for _, row in leaderboard.iterrows():
            key: Tuple[Any, ...] = tuple(row[gk] for gk in group_keys)
            out[key] = int(row["rank"])
        return out

    def _leaderboard_rank_map_qualifying_total_pins(
        self,
        df: pd.DataFrame,
        *,
        include_club: bool,
        through_round: Optional[int] = None,
    ) -> Dict[Tuple[Any, ...], int]:
        """Cumulative pin rank through ``through_round``."""
        if df.empty or through_round is None:
            return {}
        ranked = self._cumulative_totals_ranked(df, int(through_round), include_club=include_club)
        if ranked.empty:
            return {}
        group_keys = [c for c in ranked.columns if c not in ("cumulative_pins", "rank")]
        out: Dict[Tuple[Any, ...], int] = {}
        for _, row in ranked.iterrows():
            out[self._leaderboard_row_key(row, group_keys)] = int(row["rank"])
        return out

    @staticmethod
    def _cut_row_style_for_rank(rank_val: int, cut_pos: Optional[int]) -> Dict[str, Any]:
        if cut_pos is None or rank_val <= 0:
            return {}
        if rank_val == 1:
            return {"backgroundColor": "#cfead6", "fontWeight": "700"}
        if rank_val < cut_pos:
            return {"backgroundColor": "#e6f4ea"}
        if rank_val == cut_pos:
            return {"backgroundColor": "#ffe8a1", "fontWeight": "700"}
        return {}

    def get_leaderboard_table(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        df: Optional[pd.DataFrame] = None,
        ko_bracket: Optional[Dict[str, Any]] = None,
    ) -> TableData:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Leaderboard")
        include_club = self._has_any_club_value(df)

        ko_fin_rn = self._ko_finale_round_number(df)
        ko_bracket = ko_bracket or self._build_ko_bracket_payload(season, tournament, df=df)
        if (
            round_number is not None
            and ko_fin_rn is not None
            and int(round_number) == int(ko_fin_rn)
            and ko_bracket.get("matches")
        ):
            return self._ko_placements_table_data(season, tournament, df, ko_bracket)

        def _cut_position_for_round(source_df: pd.DataFrame, target_round: int) -> Optional[int]:
            return self._resolved_cut_position_for_round(source_df, target_round, season, tournament)

        # Single-round leaderboard (Gesamtwertung when a round filter is active).
        if round_number is not None:
            work = df.copy()
            work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
            work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
            scoped = work[work[Columns.round_number].eq(float(round_number))].copy()
            if scoped.empty:
                return TableData(columns=[], data=[], title=f"{tournament} Leaderboard")

            id_col = Columns.player_id if Columns.player_id in work.columns else "__player_id_missing__"
            if id_col == "__player_id_missing__":
                work[id_col] = work[Columns.player_name].astype(str)
                scoped[id_col] = scoped[Columns.player_name].astype(str)

            group_keys = [Columns.player_name, id_col]
            if include_club:
                group_keys.append(Columns.club)

            round_scores = (
                scoped.groupby(group_keys, dropna=False)[Columns.score]
                .sum()
                .reset_index(name="round_score")
            )

            upto = work[work[Columns.round_number].le(float(round_number))].copy()
            total_scores = (
                upto.groupby(group_keys, dropna=False)[Columns.score]
                .sum()
                .reset_index(name="total_score")
            )

            leaderboard = round_scores.merge(total_scores, on=group_keys, how="left")

            use_hc_round = self._tournament_df_has_meaningful_handicap(df) and Columns.handicap in scoped.columns
            if use_hc_round:
                scoped_net = scoped.assign(
                    _rn=scoped[Columns.score]
                    + pd.to_numeric(scoped[Columns.handicap], errors="coerce").fillna(0)
                )
                rn_df = scoped_net.groupby(group_keys, dropna=False)["_rn"].sum().reset_index(name="round_net")
                leaderboard = leaderboard.merge(rn_df, on=group_keys, how="left")
                leaderboard["round_net"] = pd.to_numeric(leaderboard["round_net"], errors="coerce").fillna(0).astype(int)

                upto_net = upto.assign(
                    _tn=upto[Columns.score]
                    + pd.to_numeric(upto[Columns.handicap], errors="coerce").fillna(0)
                )
                tn_df = upto_net.groupby(group_keys, dropna=False)["_tn"].sum().reset_index(name="total_net")
                leaderboard = leaderboard.merge(tn_df, on=group_keys, how="left")
                leaderboard["total_net"] = pd.to_numeric(leaderboard["total_net"], errors="coerce").fillna(0).astype(int)

            games_per_player = (
                scoped[scoped[Columns.score].gt(0)]
                .groupby([Columns.player_name], dropna=False)
                .size()
                .to_dict()
            )
            leaderboard["avg_score"] = leaderboard.apply(
                lambda r: round(float(r["round_score"]) / max(int(games_per_player.get(r[Columns.player_name], 1)), 1), 1),
                axis=1,
            )
            games_upto_player = (
                upto[upto[Columns.score].gt(0)].groupby([Columns.player_name], dropna=False).size().to_dict()
                if not upto.empty and Columns.player_name in upto.columns
                else {}
            )
            leaderboard["total_avg"] = leaderboard.apply(
                lambda r: round(float(r["total_score"]) / max(int(games_upto_player.get(r[Columns.player_name], 1)), 1), 1),
                axis=1,
            )

            if use_hc_round:
                leaderboard["avg_round_net"] = leaderboard.apply(
                    lambda r: round(
                        float(r["round_net"]) / max(int(games_per_player.get(r[Columns.player_name], 1)), 1),
                        1,
                    ),
                    axis=1,
                )
                leaderboard["total_avg_net"] = leaderboard.apply(
                    lambda r: round(
                        float(r["total_net"]) / max(int(games_upto_player.get(r[Columns.player_name], 1)), 1),
                        1,
                    ),
                    axis=1,
                )
                leaderboard = leaderboard.sort_values(
                    by=["total_net", Columns.player_name], ascending=[False, True]
                ).reset_index(drop=True)
                leaderboard["rank"] = leaderboard["total_net"].rank(method="min", ascending=False).astype(int)
            else:
                leaderboard = leaderboard.sort_values(
                    by=["total_score", Columns.player_name], ascending=[False, True]
                ).reset_index(drop=True)
                leaderboard["rank"] = leaderboard["total_score"].rank(method="min", ascending=False).astype(int)

            spieler_title = i18n_service.get_text("ui.tournament.lb_group_players")
            hcp_short = i18n_service.get_text("ui.tournament.handicap_col_short")
            hcp_tip = i18n_service.get_text("ui.tournament.handicap_per_game_tooltip")
            base_columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0, frozen="left"),
                Column(title=i18n_service.get_text("player"), field="player", width="132px", align="left", frozen="left"),
            ]
            if use_hc_round:
                base_columns.append(
                    Column(
                        title=hcp_short,
                        field="handicap_display",
                        width="100px",
                        align="center",
                        tooltip=hcp_tip,
                    )
                )
            if include_club:
                base_columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="center"))

            t_pin_sc = i18n_service.get_text("ui.tournament.col_pins_scratch")
            t_avg_sc = i18n_service.get_text("ui.tournament.col_avg_scratch")
            t_pin_nt = i18n_service.get_text("ui.tournament.col_pins_net")
            t_avg_nt = i18n_service.get_text("ui.tournament.col_avg_net")

            if use_hc_round:
                stage_columns = [
                    Column(title=t_pin_sc, field="round_score", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_sc, field="avg_score", width="100px", align="center", decimal_places=1),
                    Column(title=t_pin_nt, field="round_net", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_nt, field="avg_round_net", width="100px", align="center", decimal_places=1),
                ]
                total_columns = [
                    Column(title=t_pin_sc, field="total_score", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_sc, field="total_avg", width="110px", align="center", decimal_places=1),
                    Column(title=t_pin_nt, field="total_net", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_nt, field="total_avg_net", width="110px", align="center", decimal_places=1),
                ]
            else:
                stage_columns = [
                    Column(title=i18n_service.get_text("score"), field="round_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="avg_score", width="100px", align="center", decimal_places=1),
                ]
                total_columns = [
                    Column(title=i18n_service.get_text("score"), field="total_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="total_avg", width="110px", align="center", decimal_places=1),
                ]

            stage_group = ColumnGroup(
                title=i18n_service.get_text("ui.tournament.stage_results"),
                header_style={"fontWeight": "bold"},
                columns=stage_columns,
            )
            total_group = ColumnGroup(
                title=i18n_service.get_text("ui.tournament.total_results"),
                highlighted=True,
                style={"backgroundColor": get_theme_color("surface_alt")},
                header_style={"fontWeight": "bold"},
                columns=total_columns,
            )

            hc_label_by_key: Dict[tuple, Any] = {}
            if use_hc_round:
                for kt, sub in scoped.groupby(group_keys, dropna=False):
                    hc_label_by_key[tuple(kt) if isinstance(kt, tuple) else (kt,)] = _aggregate_handicap_leaderboard_label(sub)

            data = []
            row_metadata = []
            cell_metadata: Dict[str, Dict[str, Any]] = {}
            default_sort_field = "total_net" if use_hc_round else "total_score"
            is_ko_finale_round_lb = (
                ko_fin_rn is not None and int(round_number) == int(ko_fin_rn)
            )
            cut_pos: Optional[int] = None
            cut_shade_ranks: Dict[Tuple[Any, ...], int] = {}
            if not is_ko_finale_round_lb:
                cut_pos = _cut_position_for_round(df, int(round_number))
                cut_shade_ranks = self._leaderboard_rank_map_qualifying_total_pins(
                    df, include_club=include_club, through_round=int(round_number)
                )

            for row_idx, (_, row) in enumerate(leaderboard.iterrows()):
                entry = [int(row["rank"]), str(row.get(Columns.player_name, ""))]
                if use_hc_round:
                    key_t = tuple(row[gk] for gk in group_keys)
                    entry.append(hc_label_by_key.get(key_t, "—"))
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                if use_hc_round:
                    entry.extend(
                        [
                            int(row.get("round_score", 0)),
                            float(row.get("avg_score", 0.0)),
                            int(row.get("round_net", 0)),
                            float(row.get("avg_round_net", 0.0)),
                            int(row.get("total_score", 0)),
                            float(row.get("total_avg", 0.0)),
                            int(row.get("total_net", 0)),
                            float(row.get("total_avg_net", 0.0)),
                        ]
                    )
                else:
                    entry.extend(
                        [
                            int(row.get("round_score", 0)),
                            float(row.get("avg_score", 0.0)),
                            int(row.get("total_score", 0)),
                            float(row.get("total_avg", 0.0)),
                        ]
                    )
                data.append(entry)

                if is_ko_finale_round_lb:
                    row_metadata.append({"styling": {}})
                else:
                    rank_key = self._leaderboard_row_key(row, group_keys)
                    if use_hc_round:
                        rank_for_cut = int(row.get("rank", 0))
                    else:
                        rank_for_cut = int(cut_shade_ranks.get(rank_key, row.get("rank", 0)))
                    style = self._cut_row_style_for_rank(rank_for_cut, cut_pos)
                    row_metadata.append({"styling": {}, "cut_shade_rank": rank_for_cut})
                    if style:
                        cell_metadata[f"{row_idx}:0"] = style

            lb_metadata: Dict[str, Any] = {}
            if use_hc_round:
                lb_metadata["leaderboard_mode"] = "single_round_net"
            if is_ko_finale_round_lb:
                lb_metadata["suppress_cut_styling"] = True

            return TableData(
                columns=[
                    ColumnGroup(
                        title=spieler_title,
                        style={"backgroundColor": "#f8f9fa"},
                        header_style={"fontWeight": "bold"},
                        columns=base_columns,
                    ),
                    stage_group,
                    total_group,
                ],
                data=data,
                title=f"{tournament} Leaderboard",
                default_sort={"field": default_sort_field, "dir": "desc"},
                row_metadata=row_metadata,
                cell_metadata=cell_metadata,
                metadata=lb_metadata,
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False,
                    "stripedColGroups": True,
                },
            )

        # Multi-stage mode: total = sum across all rounds, plus one column per round.
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")

        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)

        round_meta = (
            work[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        round_numbers = [int(x) for x in round_meta[Columns.round_number].tolist()]
        round_name_map = {
            int(row[Columns.round_number]): str(row.get(Columns.round_name, "") or f"Round {int(row[Columns.round_number])}")
            for _, row in round_meta.iterrows()
        }

        grouped = (
            work.groupby([Columns.player_name, id_col, Columns.club, Columns.round_number], dropna=False)[Columns.score]
            .sum()
            .reset_index(name="round_total")
        )
        pivot = grouped.pivot_table(
            index=[Columns.player_name, id_col, Columns.club],
            columns=Columns.round_number,
            values="round_total",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        for rn in round_numbers:
            if rn not in pivot.columns:
                pivot[rn] = 0

        pivot["total_score"] = pivot[round_numbers].sum(axis=1) if round_numbers else 0
        games_per_player_all = (
            work[work[Columns.score].gt(0)]
            .groupby([Columns.player_name, id_col], dropna=False)
            .size()
            .reset_index(name="games_played")
        )
        pivot = pivot.merge(games_per_player_all, on=[Columns.player_name, id_col], how="left")
        pivot["games_played"] = pd.to_numeric(pivot["games_played"], errors="coerce").fillna(1)

        use_scratch_net = self._tournament_df_has_meaningful_handicap(df)
        hc_label_by_key: Dict[tuple, Any] = {}
        if use_scratch_net:
            work["_row_net"] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
            if Columns.handicap in work.columns:
                work["_row_net"] = work["_row_net"] + pd.to_numeric(
                    work[Columns.handicap], errors="coerce"
                ).fillna(0)
            tot_net = (
                work.groupby([Columns.player_name, id_col, Columns.club], dropna=False)["_row_net"]
                .sum()
                .reset_index(name="total_net")
            )
            pivot = pivot.merge(
                tot_net,
                on=[Columns.player_name, id_col, Columns.club],
                how="left",
            )
            pivot["total_net"] = pd.to_numeric(pivot["total_net"], errors="coerce").fillna(0).round(0).astype(int)
            pivot["avg_scratch"] = (pivot["total_score"] / pivot["games_played"]).round(1)
            pivot["avg_net"] = (pivot["total_net"] / pivot["games_played"]).round(1)
            pivot["scratch_rank"] = pivot["total_score"].rank(method="min", ascending=False).astype(int)
            pivot = pivot.sort_values(
                by=["total_net", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)
            pivot["rank"] = pivot["total_net"].rank(method="min", ascending=False).astype(int)
            for kt, sub in work.groupby(group_keys, dropna=False):
                hc_label_by_key[kt if isinstance(kt, tuple) else (kt,)] = _aggregate_handicap_leaderboard_label(sub)
        else:
            pivot["total_avg"] = (pivot["total_score"] / pivot["games_played"]).round(1)
            pivot = pivot.sort_values(
                by=["total_score", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)
            pivot["rank"] = pivot["total_score"].rank(method="min", ascending=False).astype(int)

        if use_scratch_net:
            sp_grp = i18n_service.get_text("ui.tournament.lb_group_players")
            sc_grp = i18n_service.get_text("ui.tournament.lb_group_scratch")
            nt_grp = i18n_service.get_text("ui.tournament.lb_group_net")
            hcp_short = i18n_service.get_text("ui.tournament.handicap_col_short")
            hcp_tip = i18n_service.get_text("ui.tournament.handicap_per_game_tooltip")
            tot_sc = i18n_service.get_text("ui.tournament.lb_total_scratch")
            avg_sym = i18n_service.get_text("table.header.average")
            tot_n = i18n_service.get_text("ui.tournament.lb_total_net")
            spieler_columns = [
                Column(title="#", field="rank", width=_LB_COL_RANK_W, align="center", decimal_places=0, frozen="left"),
                Column(
                    title=i18n_service.get_text("player"),
                    field="player",
                    title_key="player",
                    width=_LB_COL_PLAYER_W,
                    align="left",
                    frozen="left",
                ),
                Column(
                    title=hcp_short,
                    field="handicap_display",
                    title_key="ui.tournament.handicap_col_short",
                    width=_LB_COL_HCP_W,
                    align="center",
                    tooltip=hcp_tip,
                ),
            ]
            if include_club:
                spieler_columns.append(
                    Column(
                        title=i18n_service.get_text("ui.player.club"),
                        field="club",
                        title_key="ui.player.club",
                        width="220px",
                        align="center",
                    )
                )
            scratch_columns: List[Column] = []
            for rn in round_numbers:
                title = round_name_map.get(rn) or f"Round {rn}"
                scratch_columns.append(
                    Column(title=title, field=f"round_{rn}", width=_LB_COL_ROUND_W, align="center", decimal_places=0)
                )
            scratch_columns.extend(
                [
                    Column(
                        title=tot_sc,
                        field="total_score",
                        title_key="ui.tournament.lb_total_scratch",
                        width=_LB_COL_TOTAL_W,
                        align="center",
                        decimal_places=0,
                    ),
                    Column(
                        title=avg_sym,
                        field="avg_scratch",
                        title_key="table.header.average",
                        width=_LB_COL_TOTAL_W,
                        align="center",
                        decimal_places=1,
                    ),
                ]
            )
            net_columns = [
                Column(
                    title=tot_n,
                    field="total_net",
                    title_key="ui.tournament.lb_total_net",
                    width=_LB_COL_TOTAL_W,
                    align="center",
                    decimal_places=0,
                ),
                Column(
                    title=avg_sym,
                    field="avg_net",
                    title_key="table.header.average",
                    width=_LB_COL_TOTAL_AVG,
                    align="center",
                    decimal_places=1,
                ),
            ]
            grouped_columns = [
                ColumnGroup(
                    title=sp_grp,
                    title_key="ui.tournament.lb_group_players",
                    header_style={"fontWeight": "bold"},
                    columns=spieler_columns,
                ),
                ColumnGroup(
                    title=nt_grp,
                    title_key="ui.tournament.lb_group_net",
                    highlight_header_only=True,
                    header_style={"fontWeight": "bold"},
                    columns=net_columns,
                ),
                ColumnGroup(
                    title=sc_grp,
                    title_key="ui.tournament.lb_group_scratch",
                    header_style={"fontWeight": "bold"},
                    columns=scratch_columns,
                ),
            ]
            default_sort_field = "total_net"
            table_metadata: Dict[str, Any] = {"leaderboard_mode": "scratch_net_handicap"}
        else:
            columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0, frozen="left"),
                Column(title=i18n_service.get_text("player"), field="player", width="132px", align="left", frozen="left"),
            ]
            if include_club:
                columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="center"))
            for rn in round_numbers:
                title = round_name_map.get(rn) or f"Round {rn}"
                columns.append(Column(title=title, field=f"round_{rn}", width=_LB_COL_ROUND_W, align="center", decimal_places=0))
            columns.append(
                Column(title=i18n_service.get_text("total"), field="total_score", width="100px", align="center", decimal_places=0)
            )
            columns.append(
                Column(title=i18n_service.get_text("average"), field="total_avg", width="110px", align="center", decimal_places=1)
            )
            lead_count = 2 + (1 if include_club else 0)
            leading_cols = columns[:lead_count]
            remaining_cols = columns[lead_count:]
            grouped_columns = [
                ColumnGroup(
                    title="",
                    style={"backgroundColor": "#f8f9fa"},
                    columns=leading_cols,
                ),
                ColumnGroup(title="", columns=remaining_cols),
            ]
            default_sort_field = "total_score"
            table_metadata = {}

        data = []
        row_metadata = []
        cell_metadata: Dict[str, Dict[str, Any]] = {}
        # Gesamtwertung cut shading: cut position from qualifying config/CSV; row colors use the
        # same ladder as the table sort (net total when handicap applies, else qual scratch pins).
        latest_qual_rn = self._latest_qualifying_round_number(df)
        cut_pos_gesamt: Optional[int] = None
        if latest_qual_rn is not None:
            cut_pos_gesamt = self._resolved_cut_position_for_round(
                df, int(latest_qual_rn), season, tournament
            )
        qual_round_cols = [
            r
            for r in round_numbers
            if latest_qual_rn is None or int(r) <= int(latest_qual_rn)
        ]
        if qual_round_cols:
            pivot["_cut_total_pins"] = pivot[qual_round_cols].sum(axis=1)
        else:
            pivot["_cut_total_pins"] = 0
        pivot["_cut_shade_rank"] = pivot["_cut_total_pins"].rank(method="min", ascending=False).astype(int)

        for row_idx, (_, row) in enumerate(pivot.iterrows()):
            rank_key = self._leaderboard_row_key(row, group_keys)
            if use_scratch_net:
                hc_lbl = hc_label_by_key.get(rank_key, "—")
                entry = [int(row["rank"]), str(row.get(Columns.player_name, "")), hc_lbl]
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                entry.append(int(row.get("total_net", 0)))
                entry.append(float(row.get("avg_net", 0.0)))
                for rn in round_numbers:
                    entry.append(int(row.get(rn, 0)))
                entry.append(int(row.get("total_score", 0)))
                entry.append(float(row.get("avg_scratch", 0.0)))
                scratch_for_cut = int(row.get("scratch_rank", 0))
                row_meta: Dict[str, Any] = {"styling": {}, "scratch_rank": scratch_for_cut}
            else:
                entry = [int(row["rank"]), str(row.get(Columns.player_name, ""))]
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                for rn in round_numbers:
                    entry.append(int(row.get(rn, 0)))
                entry.append(int(row.get("total_score", 0)))
                entry.append(float(row.get("total_avg", 0.0)))
                row_meta = {"styling": {}}

            if use_scratch_net:
                rank_for_cut_shading = int(row.get("rank", 0))
            else:
                rank_for_cut_shading = int(row["_cut_shade_rank"])
            row_meta["cut_shade_rank"] = rank_for_cut_shading
            style = self._cut_row_style_for_rank(rank_for_cut_shading, cut_pos_gesamt)
            if style:
                cell_metadata[f"{row_idx}:0"] = style
            row_metadata.append(row_meta)

            data.append(entry)

        return TableData(
            columns=grouped_columns,
            data=data,
            title=f"{tournament} Leaderboard",
            default_sort={"field": default_sort_field, "dir": "desc"},
            row_metadata=row_metadata,
            cell_metadata=cell_metadata,
            metadata=table_metadata,
            config={
                "stickyHeader": True,
                "striped": True,
                "hover": True,
                "responsive": True,
                "compact": False,
                "stripedColGroups": True,
            },
        )

    def get_round_results_table(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> TableData:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Round Results")
        include_club = self._has_any_club_value(df)

        work = df.copy()
        if round_number is not None:
            work = work[pd.to_numeric(work[Columns.round_number], errors="coerce").eq(float(round_number))]
        if Columns.club in work.columns:
            # KO_WO rows are bracket walkover markers from the Bayerische importer, not pinfall.
            work = work[work[Columns.club].astype(str).str.strip() != "KO_WO"].copy()
        if work.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Round Results")
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0).astype(int)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        id_col = Columns.player_id if Columns.player_id in work.columns else "__player_id_missing__"
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)

        key_cols = [Columns.round_number, Columns.round_name, Columns.player_name, id_col]
        if include_club:
            key_cols.append(Columns.club)

        # One row per stage + player with explicit game columns.
        game_numbers = sorted([int(g) for g in work[Columns.game_number].dropna().unique().tolist()])
        per_game = (
            work.groupby(key_cols + [Columns.game_number], dropna=False)[Columns.score]
            .sum()
            .reset_index()
        )
        pivot = per_game.pivot_table(
            index=key_cols,
            columns=Columns.game_number,
            values=Columns.score,
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        for g in game_numbers:
            if g not in pivot.columns:
                pivot[g] = 0

        pivot["round_total"] = pivot[game_numbers].sum(axis=1) if game_numbers else 0
        game_cols = [g for g in game_numbers if g in pivot.columns]
        if game_cols:
            played_games = pivot[game_cols].apply(pd.to_numeric, errors="coerce").fillna(0).gt(0).sum(axis=1)
            pivot["avg_score"] = (pivot["round_total"] / played_games.replace(0, 1)).round(1)
        else:
            pivot["avg_score"] = 0.0
        pivot = _attach_round_handicap_pivot(pivot, work, key_cols, game_numbers)
        pivot = pivot.sort_values(by=[Columns.player_name, Columns.round_number]).reset_index(drop=True)
        pivot["overall_total"] = pivot.groupby([Columns.player_name, id_col], dropna=False)["round_total"].cumsum()

        # Sort for display: stage first, then strongest totals.
        pivot = pivot.sort_values(
            by=[Columns.round_number, "round_total", Columns.player_name],
            ascending=[True, False, True],
        ).reset_index(drop=True)

        include_stage_column = round_number is None

        # Single-round mode: one selected stage — compact grouped table for "Rundenergebnisse" card.
        if round_number is not None:
            all_work = df.copy()
            all_work[Columns.score] = pd.to_numeric(all_work[Columns.score], errors="coerce").fillna(0).astype(int)
            all_work[Columns.round_number] = pd.to_numeric(all_work[Columns.round_number], errors="coerce").astype("Int64")

            upto = all_work[all_work[Columns.round_number].le(float(round_number))].copy()
            overall = (
                upto.groupby([Columns.player_name, id_col], dropna=False)[Columns.score]
                .sum()
                .reset_index(name="overall_score")
            )
            overall_games = (
                upto[upto[Columns.score].gt(0)]
                .groupby([Columns.player_name, id_col], dropna=False)[Columns.score]
                .count()
                .reset_index(name="overall_games")
            )
            overall = overall.merge(overall_games, on=[Columns.player_name, id_col], how="left")
            overall["overall_games"] = pd.to_numeric(overall["overall_games"], errors="coerce").fillna(1)
            overall["overall_avg"] = (overall["overall_score"] / overall["overall_games"]).round(1)
            overall["overall_rank"] = overall["overall_score"].rank(method="min", ascending=False).astype(int)

            pivot = pivot.merge(
                overall[
                    [Columns.player_name, id_col, "overall_score", "overall_avg", "overall_rank", "overall_games"]
                ],
                on=[Columns.player_name, id_col],
                how="left",
            )
            pivot["overall_score"] = pd.to_numeric(pivot["overall_score"], errors="coerce").fillna(0).astype(int)
            pivot["overall_avg"] = pd.to_numeric(pivot["overall_avg"], errors="coerce").fillna(0.0)
            pivot["overall_rank"] = pd.to_numeric(pivot["overall_rank"], errors="coerce").fillna(0).astype(int)
            pivot["overall_games"] = pd.to_numeric(pivot["overall_games"], errors="coerce").fillna(1)

            use_hc_rr = self._tournament_df_has_meaningful_handicap(df) and Columns.handicap in work.columns and bool(game_cols)
            if use_hc_rr:
                hc_cols = [f"__hc_{g}" for g in game_numbers if f"__hc_{g}" in pivot.columns]
                if hc_cols:
                    pivot["stage_net"] = (
                        pivot[game_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
                        + pivot[hc_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
                    ).round(0).astype(int)
                else:
                    pivot["stage_net"] = pivot["round_total"].astype(int)
                pivot["stage_avg_net"] = (
                    pivot["stage_net"] / played_games.replace(0, 1).astype(float)
                ).round(1)

                upto_h = upto.copy()
                upto_h["_tn"] = upto_h[Columns.score] + pd.to_numeric(upto_h[Columns.handicap], errors="coerce").fillna(0)
                onet = upto_h.groupby([Columns.player_name, id_col], dropna=False)["_tn"].sum().reset_index(name="overall_net")
                pivot = pivot.merge(onet, on=[Columns.player_name, id_col], how="left")
                pivot["overall_net"] = pd.to_numeric(pivot["overall_net"], errors="coerce").fillna(0).astype(int)
                pivot["overall_avg_net"] = (pivot["overall_net"] / pivot["overall_games"].replace(0, 1)).round(1)

                # Standings after this stage: cumulative net through the selected round.
                pivot["overall_rank"] = pivot["overall_net"].rank(method="min", ascending=False).astype(int)

            sort_by = (
                ["overall_net", Columns.player_name]
                if use_hc_rr
                else ["overall_rank", "round_total", Columns.player_name]
            )
            sort_asc = [False, True] if use_hc_rr else [True, False, True]
            pivot = pivot.sort_values(by=sort_by, ascending=sort_asc).reset_index(drop=True)

            spieler_title = i18n_service.get_text("ui.tournament.lb_group_players")
            hcp_short = i18n_service.get_text("ui.tournament.handicap_col_short")
            hcp_tip = i18n_service.get_text("ui.tournament.handicap_per_game_tooltip")
            player_keys = [Columns.player_name, id_col]
            if include_club:
                player_keys.append(Columns.club)

            hcp_lbl_map: Dict[tuple, Any] = {}
            if use_hc_rr:
                for pkt, sub in work.groupby(player_keys, dropna=False):
                    hcp_lbl_map[tuple(pkt) if isinstance(pkt, tuple) else (pkt,)] = _aggregate_handicap_leaderboard_label(sub)

            rank_cols = [
                Column(title="#", field="overall_rank", width="70px", align="center", decimal_places=0, frozen="left"),
                Column(title=i18n_service.get_text("player"), field="player", width="132px", align="left", frozen="left"),
            ]
            if use_hc_rr:
                rank_cols.append(
                    Column(
                        title=hcp_short,
                        field="handicap_display",
                        width="92px",
                        align="center",
                        tooltip=hcp_tip,
                    )
                )
            if include_club:
                rank_cols.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="center"))

            game_cols_schema = [
                Column(title=f"{g + 1}", field=f"game_{g}", width="75px", align="center", decimal_places=0)
                for g in game_numbers
            ]

            t_pin_sc = i18n_service.get_text("ui.tournament.col_pins_scratch")
            t_avg_sc = i18n_service.get_text("ui.tournament.col_avg_scratch")
            t_pin_nt = i18n_service.get_text("ui.tournament.col_pins_net")
            t_avg_nt = i18n_service.get_text("ui.tournament.col_avg_net")

            if use_hc_rr:
                stage_result_cols = [
                    Column(title=t_pin_sc, field="stage_score", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_sc, field="stage_avg", width="100px", align="center", decimal_places=1),
                    Column(title=t_pin_nt, field="stage_net", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_nt, field="stage_avg_net", width="100px", align="center", decimal_places=1),
                ]
                total_cols = [
                    Column(title=t_pin_sc, field="total_score", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_sc, field="total_avg", width="100px", align="center", decimal_places=1),
                    Column(title=t_pin_nt, field="overall_net", width="110px", align="center", decimal_places=0),
                    Column(title=t_avg_nt, field="overall_avg_net", width="100px", align="center", decimal_places=1),
                ]
                col_groups: List[ColumnGroup] = [
                    ColumnGroup(
                        title=spieler_title,
                        style={"backgroundColor": get_theme_color("background")},
                        header_style={"fontWeight": "bold"},
                        columns=rank_cols,
                    ),
                    ColumnGroup(
                        title=i18n_service.get_text("ui.tournament.games"),
                        header_style={"fontWeight": "bold"},
                        columns=game_cols_schema,
                    ),
                    ColumnGroup(
                        title=i18n_service.get_text("ui.tournament.stage_results"),
                        header_style={"fontWeight": "bold"},
                        columns=stage_result_cols,
                    ),
                    ColumnGroup(
                        title=i18n_service.get_text("ui.tournament.total_results"),
                        highlighted=True,
                        style={"backgroundColor": get_theme_color("surface_alt")},
                        header_style={"fontWeight": "bold"},
                        columns=total_cols,
                    ),
                ]
            else:
                handicap_cols_schema = [
                    Column(
                        title=hcp_short,
                        field="handicap_per_game",
                        width="92px",
                        align="center",
                        tooltip=hcp_tip,
                    ),
                    Column(
                        title=i18n_service.get_text("ui.tournament.scratch_plus_handicap_four"),
                        field="total_scratch_handicap",
                        width="118px",
                        align="center",
                        decimal_places=0,
                    ),
                ]
                stage_result_cols = [
                    Column(title=i18n_service.get_text("score"), field="stage_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="stage_avg", width="100px", align="center", decimal_places=1),
                ]
                total_cols = [
                    Column(title=i18n_service.get_text("score"), field="total_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="total_avg", width="100px", align="center", decimal_places=1),
                ]
                col_groups = [
                    ColumnGroup(
                        title=spieler_title,
                        style={"backgroundColor": get_theme_color("background")},
                        header_style={"fontWeight": "bold"},
                        columns=rank_cols,
                    ),
                    ColumnGroup(title=i18n_service.get_text("ui.tournament.games"), columns=game_cols_schema),
                    ColumnGroup(
                        title=i18n_service.get_text("ui.tournament.handicap_heading"),
                        columns=handicap_cols_schema,
                    ),
                    ColumnGroup(title=i18n_service.get_text("ui.tournament.stage_results"), columns=stage_result_cols),
                    ColumnGroup(title=i18n_service.get_text("ui.tournament.total_results"), columns=total_cols),
                ]

            columns = col_groups

            played_cells = {
                (str(r[Columns.player_name]), int(r[Columns.game_number]))
                for _, r in per_game.iterrows()
            }

            data = []
            for _, row in pivot.iterrows():
                entry = [int(row.get("overall_rank", 0)), str(row.get(Columns.player_name, ""))]
                if use_hc_rr:
                    pkt = tuple(row[pk] for pk in player_keys)
                    entry.append(hcp_lbl_map.get(pkt, "—"))
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                pname = str(row.get(Columns.player_name, ""))
                for g in game_numbers:
                    if (pname, g) in played_cells:
                        entry.append(int(row.get(g, 0)))
                    else:
                        entry.append("")
                if not use_hc_rr:
                    h_lbl, h_tot = _handicap_per_game_label_and_scratch_plus_total(row, game_numbers)
                    entry.append(h_lbl)
                    entry.append(h_tot)
                entry.append(int(row.get("round_total", 0)))
                entry.append(float(row.get("avg_score", 0.0)))
                if use_hc_rr:
                    entry.append(int(row.get("stage_net", 0)))
                    entry.append(float(row.get("stage_avg_net", 0.0)))
                entry.append(int(row.get("overall_score", 0)))
                entry.append(float(row.get("overall_avg", 0.0)))
                if use_hc_rr:
                    entry.append(int(row.get("overall_net", 0)))
                    entry.append(float(row.get("overall_avg_net", 0.0)))
                data.append(entry)

            default_sort_field = "overall_net" if use_hc_rr else "overall_rank"
            default_sort_dir = "desc" if use_hc_rr else "asc"

            return TableData(
                columns=columns,
                data=data,
                title=f"{tournament} Round Results",
                default_sort={"field": default_sort_field, "dir": default_sort_dir},
                metadata={
                    "heatmap_ranges": {
                        "game_score": {
                            "min": 130,
                            "max": 270,
                            "high_band_min": 271,
                            "high_band_max": 299,
                            "perfect_score": 300,
                        }
                    }
                },
            )

        hcp_short = i18n_service.get_text("ui.tournament.handicap_col_short")
        hcp_tip = i18n_service.get_text("ui.tournament.handicap_per_game_tooltip")
        columns = []
        if include_stage_column:
            columns.append(Column(title="Stage", field="round_name", width="150px", align="left"))
        columns.append(Column(title="Player", field="player", width="132px", align="left"))
        if include_club:
            columns.append(Column(title="Club", field="club", width="220px", align="left"))
        for g in game_numbers:
            columns.append(
                Column(
                    title=f"{g + 1}",
                    field=f"game_{g}",
                    width="75px",
                    align="center",
                    decimal_places=0,
                )
            )
        columns.append(
            Column(
                title=hcp_short,
                field="handicap_per_game",
                width="92px",
                align="center",
                tooltip=hcp_tip,
            )
        )
        columns.append(
            Column(
                title=i18n_service.get_text("ui.tournament.scratch_plus_handicap_four"),
                field="total_scratch_handicap",
                width="118px",
                align="center",
                decimal_places=0,
            )
        )
        columns.extend(
            [
                Column(title="Stage Score", field="round_total", width="110px", align="center", decimal_places=0),
                Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1),
                Column(title="Total Score", field="overall_total", width="120px", align="center", decimal_places=0),
            ]
        )

        data = []
        previous_player_key = None
        for _, row in pivot.iterrows():
            player_key = (
                str(row.get(Columns.player_name, "")),
                str(row.get(id_col, "")),
                str(row.get(Columns.club, "")) if include_club else "",
            )
            show_player = True
            if round_number is None and previous_player_key == player_key:
                show_player = False

            entry = []
            if include_stage_column:
                entry.append(str(row.get(Columns.round_name, "")))
            entry.append(str(row.get(Columns.player_name, "")) if show_player else "")
            if include_club:
                entry.append(str(row.get(Columns.club, "")) if show_player else "")
            for g in game_numbers:
                entry.append(int(row.get(g, 0)))
            h_lbl, h_tot = _handicap_per_game_label_and_scratch_plus_total(row, game_numbers)
            entry.append(h_lbl)
            entry.append(h_tot)
            entry.append(int(row.get("round_total", 0)))
            entry.append(float(row.get("avg_score", 0.0)))
            entry.append(int(row.get("overall_total", 0)))
            data.append(entry)
            previous_player_key = player_key

        return TableData(
            columns=columns,
            data=data,
            title=f"{tournament} Round Results",
            metadata={
                "heatmap_ranges": {
                    "game_score": {
                        "min": 130,
                        "max": 270,
                        "high_band_min": 271,
                        "high_band_max": 299,
                        "perfect_score": 300,
                    }
                }
            },
        )

    def get_player_round_table(
        self,
        season: str,
        tournament: str,
        player: str,
        df: Optional[pd.DataFrame] = None,
    ) -> TableData:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{player} - Tournament Progress")

        all_df = df.copy()
        work = all_df[all_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if work.empty:
            return TableData(columns=[], data=[], title=f"{player} - Tournament Progress")
        all_df[Columns.score] = pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0)
        all_df[Columns.round_number] = pd.to_numeric(all_df[Columns.round_number], errors="coerce").astype("Int64")
        all_df[Columns.game_number] = pd.to_numeric(all_df[Columns.game_number], errors="coerce").astype("Int64")

        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        use_hc = self._tournament_df_has_meaningful_handicap(all_df) and Columns.handicap in all_df.columns
        if use_hc:
            all_df[Columns.handicap] = pd.to_numeric(all_df[Columns.handicap], errors="coerce").fillna(0)
            work[Columns.handicap] = pd.to_numeric(work[Columns.handicap], errors="coerce").fillna(0)

        round_meta = (
            all_df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        round_numbers = [int(r) for r in round_meta[Columns.round_number].tolist()]
        round_name_map = {int(r[Columns.round_number]): str(r.get(Columns.round_name, "") or f"Round {int(r[Columns.round_number])}") for _, r in round_meta.iterrows()}
        max_game = int(pd.to_numeric(all_df[Columns.game_number], errors="coerce").dropna().max()) if not all_df.empty else -1
        game_cols = list(range(max_game + 1)) if max_game >= 0 else []

        rows: List[List[Any]] = []
        running_sc_total = 0
        running_net_total = 0
        running_games = 0

        for rn in round_numbers:
            round_all = all_df[all_df[Columns.round_number].eq(float(rn))].copy()
            round_player = work[work[Columns.round_number].eq(float(rn))].copy()
            if round_player.empty:
                # Skip non-participated rounds for this player.
                continue

            player_game_scores = {
                int(r[Columns.game_number]): int(r[Columns.score])
                for _, r in round_player.iterrows()
                if pd.notna(r[Columns.game_number])
            }

            round_total_sc = int(round_player[Columns.score].sum())
            round_games = int(self._played_games_count(round_player[Columns.score]))
            round_hcp_sum = int(round_player[Columns.handicap].sum()) if use_hc else 0
            round_net = round_total_sc + round_hcp_sum
            round_avg_sc = round(round_total_sc / max(round_games, 1), 1)
            round_avg_net = round(round_net / max(round_games, 1), 1)

            if use_hc:
                ra = round_all.assign(
                    _net_pins=pd.to_numeric(round_all[Columns.score], errors="coerce").fillna(0)
                    + pd.to_numeric(round_all[Columns.handicap], errors="coerce").fillna(0)
                )
                round_totals = (
                    ra.groupby(Columns.player_name, dropna=False)["_net_pins"]
                    .sum()
                    .sort_values(ascending=False)
                )
            else:
                round_totals = (
                    round_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .sort_values(ascending=False)
                )
            round_rank = (
                int(round_totals.rank(method="min", ascending=False).get(player, float("nan")))
                if player in round_totals.index
                else None
            )

            running_sc_total += round_total_sc
            running_net_total += round_net
            running_games += round_games
            cum_avg_sc = round(running_sc_total / max(running_games, 1), 1)
            cum_avg_net = round(running_net_total / max(running_games, 1), 1)

            upto_all = all_df[all_df[Columns.round_number].le(float(rn))].copy()
            if use_hc:
                ua = upto_all.assign(
                    _net_pins=pd.to_numeric(upto_all[Columns.score], errors="coerce").fillna(0)
                    + pd.to_numeric(upto_all[Columns.handicap], errors="coerce").fillna(0)
                )
                cum_totals = (
                    ua.groupby(Columns.player_name, dropna=False)["_net_pins"]
                    .sum()
                    .sort_values(ascending=False)
                )
            else:
                cum_totals = (
                    upto_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .sort_values(ascending=False)
                )
            cum_rank = (
                int(cum_totals.rank(method="min", ascending=False).get(player, float("nan")))
                if player in cum_totals.index
                else None
            )

            row: List[Any] = [round_name_map.get(rn, f"Round {rn}")]
            if use_hc:
                row.append(_aggregate_handicap_leaderboard_label(round_player))
            for g in game_cols:
                row.append(int(player_game_scores.get(g, 0)) if g in player_game_scores else "")
            if use_hc:
                row.extend(
                    [
                        round_total_sc,
                        round_avg_sc,
                        round_net,
                        round_avg_net,
                        round_rank if round_rank is not None else "",
                        running_sc_total,
                        cum_avg_sc,
                        running_net_total,
                        cum_avg_net,
                        cum_rank if cum_rank is not None else "",
                    ]
                )
            else:
                row.extend(
                    [
                        round_total_sc,
                        round_avg_sc,
                        round_rank if round_rank is not None else "",
                        running_sc_total,
                        cum_avg_sc,
                        cum_rank if cum_rank is not None else "",
                    ]
                )
            rows.append(row)

        stage_info_cols = [
            Column(title=i18n_service.get_text("ui.tournament.stage"), field="stage", width="140px", align="left"),
        ]
        game_score_cols = [
            Column(title=f"{g + 1}", field=f"game_{g}", width="70px", align="center", decimal_places=0)
            for g in game_cols
        ]
        hcp_pg_title = i18n_service.get_text("ui.tournament.handicap_per_game")
        hcp_pg_tip = i18n_service.get_text("ui.tournament.handicap_per_game_tooltip")
        hcp_stage_col = [
            Column(
                title=hcp_pg_title,
                field="round_hcp",
                width="92px",
                align="center",
                tooltip=hcp_pg_tip,
            )
        ]

        if use_hc:
            t_pin_sc = i18n_service.get_text("ui.tournament.col_pins_scratch")
            t_avg_sc = i18n_service.get_text("ui.tournament.col_avg_scratch")
            t_pin_nt = i18n_service.get_text("ui.tournament.col_pins_net")
            t_avg_nt = i18n_service.get_text("ui.tournament.col_avg_net")
            rank_t = i18n_service.get_text("ui.tournament.rank")
            stage_stat_cols = [
                Column(title=t_pin_sc, field="stage_score", width="110px", align="center", decimal_places=0),
                Column(title=t_avg_sc, field="stage_avg", width="100px", align="center", decimal_places=1),
                Column(title=t_pin_nt, field="stage_net", width="110px", align="center", decimal_places=0),
                Column(title=t_avg_nt, field="stage_avg_net", width="100px", align="center", decimal_places=1),
                Column(title=rank_t, field="round_rank", width="95px", align="center", decimal_places=0),
            ]
            total_stat_cols = [
                Column(title=t_pin_sc, field="cum_score", width="110px", align="center", decimal_places=0),
                Column(title=t_avg_sc, field="cum_avg_sc", width="100px", align="center", decimal_places=1),
                Column(title=t_pin_nt, field="overall_net", width="110px", align="center", decimal_places=0),
                Column(title=t_avg_nt, field="overall_avg_net", width="100px", align="center", decimal_places=1),
                Column(title=rank_t, field="cum_rank", width="90px", align="center", decimal_places=0),
            ]
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("ui.tournament.stage"),
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=stage_info_cols,
                ),
                ColumnGroup(
                    title="",
                    columns=hcp_stage_col,
                ),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.games"), columns=game_score_cols),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.stage_results"), columns=stage_stat_cols),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.total_results"), columns=total_stat_cols),
            ]
        else:
            stage_stat_cols = [
                Column(title=i18n_service.get_text("score"), field="score_total", width="105px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("average"), field="round_avg", width="90px", align="center", decimal_places=1),
                Column(title=i18n_service.get_text("ui.tournament.rank"), field="round_rank", width="95px", align="center", decimal_places=0),
            ]
            total_stat_cols = [
                Column(title=i18n_service.get_text("score"), field="cum_score", width="95px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("average"), field="cum_avg", width="90px", align="center", decimal_places=1),
                Column(title=i18n_service.get_text("ui.tournament.rank"), field="cum_rank", width="90px", align="center", decimal_places=0),
            ]
            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("ui.tournament.stage"),
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=stage_info_cols,
                ),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.games"), columns=game_score_cols),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.stage_results"), columns=stage_stat_cols),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.total_results"), columns=total_stat_cols),
            ]

        return TableData(
            columns=columns,
            data=rows,
            title=f"{player} - Tournament Progress",
            metadata={
                "heatmap_ranges": {
                    "game_score": {
                        "min": 130,
                        "max": 270,
                        "high_band_min": 271,
                        "high_band_max": 299,
                        "perfect_score": 300,
                    }
                }
            },
        )

    def get_player_best_efforts(
        self,
        season: str,
        tournament: str,
        player: str,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        empty = {"highest_game": None, "highest_pair": None, "highest_block": None, "handicap_profile": None}
        if df.empty:
            return empty
        work = df[df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if work.empty:
            return empty

        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        # Highest game
        hg_row = work.sort_values(by=Columns.score, ascending=False).iloc[0]
        highest_game = {
            "score": int(hg_row[Columns.score]),
            "stage": str(hg_row.get(Columns.round_name, "")),
            "game": int(hg_row[Columns.game_number]) + 1 if pd.notna(hg_row[Columns.game_number]) else None,
        }

        # Highest scratch pair (two consecutive games Gk+G(k+1)); meaningful mainly for NBM/SBM lane formats.
        pair_best = None
        for stage, gdf in work.groupby(Columns.round_name, dropna=False):
            scores = {
                int(r[Columns.game_number]): int(r[Columns.score])
                for _, r in gdf.iterrows()
                if pd.notna(r[Columns.game_number])
            }
            one_based = sorted([x + 1 for x in scores.keys()])
            for start in one_based:
                if start % 2 == 1 and (start + 1) in one_based:
                    total = int(scores[start - 1] + scores[start])
                    cand = {"score": total, "stage": str(stage or ""), "pair": f"G{start}+G{start+1}"}
                    if pair_best is None or total > pair_best["score"]:
                        pair_best = cand

        # Highest block (stage total)
        block_df = (
            work.groupby(Columns.round_name, dropna=False)[Columns.score]
            .sum()
            .reset_index(name="score")
            .sort_values(by="score", ascending=False)
        )
        highest_block = None
        if not block_df.empty:
            b = block_df.iloc[0]
            highest_block = {"score": int(b["score"]), "stage": str(b.get(Columns.round_name, ""))}

        # Handicap card: per-game pins from data; a priori / reference when present (club import).
        handicap_profile: Optional[Dict[str, Any]] = None
        hcp_game: Optional[int] = None
        if Columns.handicap in work.columns:
            hc_series = pd.to_numeric(work[Columns.handicap], errors="coerce").dropna()
            if not hc_series.empty:
                uniq = {round(float(x), 4) for x in hc_series.unique()}
                if len(uniq) == 1:
                    hcp_game = _arith_round_int(float(hc_series.iloc[0]))
                else:
                    hcp_game = _arith_round_int(float(hc_series.mean()))
        apriori: Optional[float] = None
        if Columns.apriori_average in work.columns:
            ap_s = pd.to_numeric(work[Columns.apriori_average], errors="coerce").dropna()
            if not ap_s.empty:
                apriori = round(float(ap_s.iloc[0]), 1)
        href: Optional[float] = None
        if Columns.handicap_reference in work.columns:
            r_s = pd.to_numeric(work[Columns.handicap_reference], errors="coerce").dropna()
            if not r_s.empty:
                href = round(float(r_s.iloc[0]), 1)
        if apriori is not None or hcp_game is not None or href is not None:
            handicap_profile = {
                "a_priori_average": apriori,
                "handicap_per_game": hcp_game,
                "handicap_reference": href,
            }

        return {
            "highest_game": highest_game,
            "highest_pair": pair_best,
            "highest_block": highest_block,
            "handicap_profile": handicap_profile,
        }

    def _field_progress_query(self, season: str, tournament: str) -> Dict[str, str]:
        return {"season": str(season), "tournament": str(tournament)}

    def _field_progress_public(self, field: Dict[str, Any]) -> Dict[str, Any]:
        """Chart overlay fields shared by every player (omit internal / per-player maps)."""
        omit = {"player_rank_series", "game_slots", "round_length_map"}
        return {k: v for k, v in field.items() if k not in omit}

    def _compute_field_progress(
        self,
        season: str,
        tournament: str,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """Cut-line, tournament leader, and all player ranks — identical for every participant."""
        _fp_t0 = time.perf_counter() if tournament_benchmark_enabled() else None
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {
                "labels": [],
                "tournament_leader_avg_series": [],
                "tournament_lowest_avg_series": [],
                "cut_lines_avg": [],
                "cut_lines_position": [],
                "cut_position_at_game": [],
                "participant_count": 0,
                "cut_line_series": [],
                "cut_lines_avg_dynamic": {},
                "player_rank_series": {},
            }

        all_df = df.copy()
        config_event = self._config_event_name(season, tournament, all_df)
        all_df[Columns.score] = pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0)
        all_df[Columns.round_number] = pd.to_numeric(all_df[Columns.round_number], errors="coerce").astype("Int64")
        all_df[Columns.game_number] = pd.to_numeric(all_df[Columns.game_number], errors="coerce").astype("Int64")
        use_net = self._tournament_df_has_meaningful_handicap(all_df) and Columns.handicap in all_df.columns
        all_df = _with_progress_pins(all_df, use_net)
        participant_count = len(_progress_player_names(all_df))

        round_meta = (
            all_df[[Columns.round_number, Columns.round_name, Columns.game_number]]
            .dropna(subset=[Columns.round_number, Columns.game_number])
            .groupby([Columns.round_number, Columns.round_name], dropna=False)[Columns.game_number]
            .max()
            .reset_index()
            .sort_values(by=Columns.round_number)
        )
        round_lengths: List[RoundLengthRow] = [
            (int(r[Columns.round_number]), str(r.get(Columns.round_name, "")), int(r[Columns.game_number]) + 1)
            for _, r in round_meta.iterrows()
        ]
        round_name_map = {rn: name for rn, name, _ in round_lengths}
        round_length_map = {rn: length for rn, _, length in round_lengths}
        schedule_games = sum(length for _, _, length in round_lengths)
        field_max_games = _field_max_games_played(all_df)
        total_games = min(field_max_games, schedule_games) if field_max_games > 0 else 0
        game_slots = _progress_game_slots(round_lengths, total_games)
        labels = [f"G{i}" for i in range(1, total_games + 1)] if total_games else []

        cut_rank = self._gesamt_leaderboard_cut_line_rank(season, tournament) or 6
        cfg_span = self._ko_qualifying_cut_span_config(season, tournament, df=all_df)
        stage_items = public_stage_summary(season, config_event)
        has_stage_cuts = bool(stage_items)
        if stage_items:
            cut_rounds_sorted = [int(st["round_number"]) for st in stage_items]
        elif cfg_span:
            cut_rounds_sorted = list(
                range(int(cfg_span["first_round"]), int(cfg_span["through_round"]) + 1)
            )
        else:
            cut_rounds_sorted = [rn for rn, _, _ in round_lengths]

        field_players = sorted(_progress_player_names(all_df))
        player_rank_series: Dict[str, List[int]] = {name: [] for name in field_players}
        tournament_leader_avg_series: List[Optional[float]] = []
        tournament_lowest_avg_series: List[Optional[float]] = []
        cut_lines_avg: List[float] = []
        cut_lines_position: List[int] = []
        cut_position_at_game: List[Optional[int]] = []
        dynamic_cut_series: Dict[int, List[Optional[float]]] = {rn: [] for rn in cut_rounds_sorted}

        per_game_pins = _field_progress_prepare_game_pins(all_df)
        player_round_games = _field_progress_prepare_round_games(all_df)
        cum_pins: Dict[str, float] = defaultdict(float)
        cum_games: Dict[str, int] = defaultdict(int)

        last_cut_avg: Optional[float] = None
        last_cut_pos: Optional[int] = None

        _fp_loop_t0 = time.perf_counter() if tournament_benchmark_enabled() else None
        prev_slot: Optional[Tuple[int, int]] = None
        for rn, g in game_slots:
            for rno, gg in _field_progress_delta_games(prev_slot, (rn, g), round_lengths):
                for player, pins in per_game_pins.get((rno, gg), {}).items():
                    cum_pins[player] += pins
                    cum_games[player] += 1
            prev_slot = (rn, g)

            score_rows = _field_progress_snapshot_from_cumulative(cum_pins, cum_games)
            rank_map = {name: idx + 1 for idx, (name, _, _, _) in enumerate(score_rows)}
            default_rank = len(score_rows) + 1 if score_rows else participant_count + 1
            for name in field_players:
                prev = player_rank_series[name][-1] if player_rank_series[name] else default_rank
                player_rank_series[name].append(int(rank_map.get(name, prev)))

            if score_rows:
                tournament_leader_avg_series.append(round(score_rows[0][2], 2))
                tournament_lowest_avg_series.append(round(min(r[2] for r in score_rows), 2))
            else:
                tournament_leader_avg_series.append(None)
                tournament_lowest_avg_series.append(None)

            round_stage_cut = stage_cut_rank_for_round(season, config_event, int(rn))
            if has_stage_cuts:
                in_cut_span = round_stage_cut is not None
            else:
                in_cut_span = cfg_span is None or (
                    int(cfg_span["first_round"]) <= rn <= int(cfg_span["through_round"])
                )
            round_cut_rank = round_stage_cut
            if round_cut_rank is None and cfg_span and in_cut_span:
                round_cut_rank = int(cfg_span["rank"])
            if round_cut_rank is None and in_cut_span:
                round_cut_rank = cut_rank
            cut_avg_game: Optional[float] = last_cut_avg
            if in_cut_span:
                eligible = _field_progress_eligible_at_snapshot(
                    field_players, rn, g, round_lengths, player_round_games
                )
                pace = _pace_cut_from_cumulative(eligible, cum_pins, cum_games, round_cut_rank)
                if pace is not None:
                    last_cut_avg, last_cut_pos = pace
                    cut_avg_game = last_cut_avg

            for cut_rn in cut_rounds_sorted:
                dynamic_cut_series[cut_rn].append(cut_avg_game if rn == cut_rn else None)

            length = round_length_map.get(rn, 0)
            if g == length - 1:
                cut_pos_round = self._resolved_cut_position_for_round(
                    all_df, int(rn), season, tournament, config_event=config_event
                )
                show_cut_marker = (
                    not has_stage_cuts
                    or round_stage_cut is not None
                    or self._cut_line_score_for_round(all_df, int(rn)) is not None
                )
                if show_cut_marker:
                    if cut_pos_round is not None:
                        if last_cut_avg is not None:
                            cut_lines_avg.append(last_cut_avg)
                        cut_lines_position.append(cut_pos_round)
                    elif not has_stage_cuts and in_cut_span and last_cut_pos is not None:
                        cut_lines_position.append(last_cut_pos)

            if in_cut_span and last_cut_pos is not None:
                cut_position_at_game.append(int(last_cut_pos))
            else:
                cut_position_at_game.append(None)

        if _fp_t0 is not None and _fp_loop_t0 is not None:
            loop_sec = time.perf_counter() - _fp_loop_t0
            setup_sec = _fp_loop_t0 - _fp_t0
            print(
                f"  field_progress detail: participants={participant_count} "
                f"game_slots={len(game_slots)} setup={setup_sec:.3f}s loop={loop_sec:.3f}s",
                flush=True,
            )

        cut_line_series = [
            {
                "key": f"round_{rn}",
                "round_number": rn,
                "label": round_name_map.get(rn) or f"Round {rn}",
                "data": dynamic_cut_series[rn],
            }
            for rn in cut_rounds_sorted
        ]

        return {
            "labels": labels,
            "tournament_leader_avg_series": tournament_leader_avg_series,
            "tournament_lowest_avg_series": tournament_lowest_avg_series,
            "cut_lines_avg": cut_lines_avg,
            "cut_lines_position": cut_lines_position,
            "cut_position_at_game": cut_position_at_game,
            "participant_count": participant_count,
            "cut_line_series": cut_line_series,
            "cut_lines_avg_dynamic": {
                f"round_{rn}": dynamic_cut_series[rn] for rn in cut_rounds_sorted
            },
            "player_rank_series": player_rank_series,
            "game_slots": [[int(rn), int(g)] for rn, g in game_slots],
            "round_length_map": {str(rn): int(length) for rn, length in round_length_map.items()},
        }

    def get_field_progress(
        self,
        season: str,
        tournament: str,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        cache_key = self._tournament_cache_key(season, tournament)
        if cache_key in self._field_progress_cache:
            if tournament_benchmark_enabled():
                print("  field_progress: in-request cache HIT", flush=True)
            return self._field_progress_cache[cache_key]

        query = self._field_progress_query(season, tournament)
        cached = league_cache_try_get(
            "get_tournament_field_progress", self.database, query
        )
        if cached is not None:
            if tournament_benchmark_enabled():
                print("  field_progress: disk cache HIT", flush=True)
            self._field_progress_cache[cache_key] = cached
            return cached

        if tournament_benchmark_enabled():
            print("  field_progress: computing (_compute_field_progress)", flush=True)
        computed = self._compute_field_progress(season, tournament, df=df)
        self._field_progress_cache[cache_key] = computed
        league_cache_put(
            "get_tournament_field_progress", self.database, query, computed
        )
        return computed

    def _compute_player_only_progress(
        self,
        player: str,
        df: pd.DataFrame,
        field: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Per-player averages and game scores (cheap once field progress exists)."""
        game_slots = [(int(rn), int(g)) for rn, g in (field.get("game_slots") or [])]
        round_length_map = {
            int(rn): int(length) for rn, length in (field.get("round_length_map") or {}).items()
        }

        player_df = df[df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if player_df.empty or not game_slots:
            rank_map = field.get("player_rank_series") or {}
            return {
                "avg_series": [],
                "position_series": list(rank_map.get(player, [])),
                "game_score_series": [],
                "round_end_lines": [],
            }

        player_df[Columns.score] = pd.to_numeric(player_df[Columns.score], errors="coerce").fillna(0)
        player_df[Columns.round_number] = pd.to_numeric(player_df[Columns.round_number], errors="coerce").astype("Int64")
        player_df[Columns.game_number] = pd.to_numeric(player_df[Columns.game_number], errors="coerce").astype("Int64")

        use_net = self._tournament_df_has_meaningful_handicap(df) and Columns.handicap in df.columns
        if use_net and Columns.handicap in player_df.columns:
            player_df[Columns.handicap] = pd.to_numeric(player_df[Columns.handicap], errors="coerce").fillna(0)
        player_df = _with_progress_pins(player_df, use_net)

        avg_series: List[Optional[float]] = []
        game_score_series: List[Optional[int]] = []
        round_end_lines: List[int] = []
        cum_player_pins = 0.0
        cum_player_games = 0
        current_rn: Optional[int] = None
        player_game_pins: Dict[int, int] = {}

        for rn, g in game_slots:
            if rn != current_rn:
                current_rn = rn
                round_player = player_df[player_df[Columns.round_number].eq(float(rn))].copy()
                player_game_pins = {}
                for g_idx, grp in round_player.groupby(Columns.game_number, dropna=False):
                    scratch = pd.to_numeric(grp[Columns.score], errors="coerce").fillna(0)
                    if not (scratch > 0).any():
                        continue
                    pins = pd.to_numeric(grp["__pins"], errors="coerce").fillna(0)
                    player_game_pins[int(g_idx)] = _arith_round_int(float(pins.sum()))

            game_score_series.append(player_game_pins.get(g))
            if g in player_game_pins:
                cum_player_pins += float(player_game_pins[g])
                cum_player_games += 1
                avg_series.append(round(cum_player_pins / cum_player_games, 2))
            else:
                avg_series.append(None)

            length = round_length_map.get(rn, 0)
            if g == length - 1:
                round_end_lines.append(len(avg_series))

        rank_map = field.get("player_rank_series") or {}
        position_series = list(rank_map.get(player, []))

        return {
            "avg_series": avg_series,
            "position_series": position_series,
            "game_score_series": game_score_series,
            "round_end_lines": round_end_lines,
        }

    def get_player_progress_series(
        self,
        season: str,
        tournament: str,
        player: str,
        df: Optional[pd.DataFrame] = None,
        *,
        include_field: bool = True,
    ) -> Dict[str, Any]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        field = self.get_field_progress(season, tournament, df=df)
        player_part = self._compute_player_only_progress(player, df, field)
        if include_field:
            return {**self._field_progress_public(field), **player_part}
        return {**player_part, "labels": field.get("labels") or []}

    @staticmethod
    def _is_ko_bye_player(name: str) -> bool:
        n = str(name or "").strip().lower()
        if not n:
            return True
        if "(no show)" in n:
            return True
        if "nicht angetreten" in n:
            return True
        if n in {"bye", "freilos", "tbd"}:
            return True
        return False

    @staticmethod
    def _ko_bracket_side_display_name(name: str) -> str:
        """Legacy rows used plain 'Nicht angetreten'; bracket shows '(No show)' for clarity."""
        raw = str(name or "").strip()
        if not raw:
            return raw
        low = raw.lower()
        if "(no show)" in low:
            return raw
        if TournamentService._ko_norm_name(raw) == TournamentService._ko_norm_name("Nicht angetreten"):
            return "Nicht angetreten (No show)"
        return raw

    @staticmethod
    def _ko_norm_name(name: str) -> str:
        return str(name or "").strip().casefold()

    @staticmethod
    def _ko_bracket_match_keys(n_matches: int) -> List[str]:
        if n_matches <= 0:
            return []
        if n_matches == 1:
            return ["F"]
        if n_matches == 2:
            return ["SF1", "F"]
        if n_matches == 3:
            return ["SF1", "SF2", "F"]
        if n_matches == 4:
            return ["QF1", "QF2", "SF1", "F"]
        if n_matches == 5:
            return ["QF1", "QF2", "SF1", "SF2", "F"]
        return [f"M{i + 1}" for i in range(n_matches)]

    @staticmethod
    def _ko_match_winner_name(match: Dict[str, Any]) -> Optional[str]:
        w = match.get("winner")
        if w == "a":
            return str(match.get("side_a", {}).get("name", "") or "")
        if w == "b":
            return str(match.get("side_b", {}).get("name", "") or "")
        return None

    @staticmethod
    def _ko_strip_no_show_suffix(name: str) -> str:
        raw = str(name or "").strip()
        low = raw.lower()
        if low.endswith("(no show)"):
            return raw[: low.rfind("(")].strip()
        return raw

    @staticmethod
    def _ko_find_player_id_in_qf_matches(qf1: Dict[str, Any], qf2: Dict[str, Any], player_name: str) -> str:
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(player_name))
        if not target:
            return ""
        for qm in (qf1, qf2):
            for side in ("side_a", "side_b"):
                s = qm.get(side, {})
                nm = TournamentService._ko_strip_no_show_suffix(str(s.get("name", "") or ""))
                if TournamentService._ko_norm_name(nm) == target:
                    return str(s.get("id", "") or "")
        return ""

    @staticmethod
    def _ko_sf_bye_is_placeholder(name: str) -> bool:
        """True when the sheet only gave a generic absentee label (to be replaced by QF-winner inference)."""
        base = TournamentService._ko_strip_no_show_suffix(str(name or ""))
        if not base:
            return True
        return TournamentService._ko_norm_name(base) == TournamentService._ko_norm_name("Nicht angetreten")

    @staticmethod
    def _ko_sf_match_has_placeholder_bye(sm: Dict[str, Any]) -> bool:
        na = str(sm.get("side_a", {}).get("name", "") or "")
        nb = str(sm.get("side_b", {}).get("name", "") or "")
        return TournamentService._ko_sf_bye_is_placeholder(na) or TournamentService._ko_sf_bye_is_placeholder(nb)

    def _ko_apply_bracket_overrides_json(
        self, season: str, tournament: str, matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optional database/data/ko_bracket_overrides.json — keys "Season||Event Name",
        block.replace_sf_bye: { "SF1": { "name": "…", "id": "…" } } fills a generic bye slot.
        """
        path = Path(__file__).resolve().parents[2] / "database" / "data" / "ko_bracket_overrides.json"
        if not path.is_file():
            return matches
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return matches
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        if not isinstance(block, dict):
            return matches
        rep = block.get("replace_sf_bye") or {}
        if not isinstance(rep, dict):
            return matches
        by_key = {str(m.get("key", "")): m for m in matches}
        for sf_key, spec in rep.items():
            if not isinstance(spec, dict):
                continue
            sm = by_key.get(str(sf_key))
            if not sm:
                continue
            name = str(spec.get("name") or "").strip()
            pid = str(spec.get("id") or "").strip()
            if not name:
                continue
            display = name if "(no show)" in name.lower() else f"{name} (No show)"
            for side in ("side_a", "side_b"):
                sd = sm.get(side) or {}
                nm = str(sd.get("name") or "")
                if not self._ko_sf_bye_is_placeholder(nm):
                    continue
                sd = dict(sd)
                sd["name"] = display
                if pid:
                    sd["id"] = pid
                sm[side] = sd
                break
        return matches

    def _ko_resolve_sf_walkover_absent_from_qfs(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        SF walkover rows often list only 'Nicht angetreten'. Resolve the absent player as the QF winner
        who is not the SF opponent and is not playing in the other semifinal (e.g. Christian Rechenberg).
        """
        by_key = {str(m.get("key", "")): m for m in matches}
        qf1, qf2 = by_key.get("QF1"), by_key.get("QF2")
        if not qf1 or not qf2:
            return matches
        w1 = self._ko_match_winner_name(qf1)
        w2 = self._ko_match_winner_name(qf2)
        if not w1 or not w2:
            return matches
        w1b = self._ko_strip_no_show_suffix(w1)
        w2b = self._ko_strip_no_show_suffix(w2)

        def other_sf_real_norms(sf_key: str) -> set:
            other_key = "SF2" if sf_key == "SF1" else "SF1"
            om = by_key.get(other_key)
            if not om:
                return set()
            out: set = set()
            for side in ("side_a", "side_b"):
                nm = str(om.get(side, {}).get("name") or "")
                if not self._is_ko_bye_player(nm):
                    out.add(self._ko_norm_name(self._ko_strip_no_show_suffix(nm)))
            return out

        def apply(sf_key: str) -> None:
            sm = by_key.get(sf_key)
            if not sm or sm.get("inferred"):
                return
            if not (sm.get("walkover") or self._ko_sf_match_has_placeholder_bye(sm)):
                return
            sa, sb = sm["side_a"], sm["side_b"]
            na, nb = str(sa.get("name") or ""), str(sb.get("name") or "")
            bye_dict = None
            present_dict = None
            if self._ko_sf_bye_is_placeholder(na) and not self._ko_sf_bye_is_placeholder(nb):
                bye_dict, present_dict = sa, sb
            elif self._ko_sf_bye_is_placeholder(nb) and not self._ko_sf_bye_is_placeholder(na):
                bye_dict, present_dict = sb, sa
            else:
                return
            if not bye_dict or not present_dict:
                return
            present_clean = self._ko_strip_no_show_suffix(str(present_dict.get("name") or ""))
            if not present_clean:
                return
            np = self._ko_norm_name(present_clean)
            other_names = other_sf_real_norms(sf_key)

            candidates: List[str] = []
            for wb in (w1b, w2b):
                if not wb:
                    continue
                nwb = self._ko_norm_name(wb)
                if nwb == np:
                    continue
                if nwb in other_names:
                    continue
                candidates.append(wb)

            absent: Optional[str] = None
            if len(candidates) == 1:
                absent = candidates[0]
            elif len(candidates) == 2:
                if np == self._ko_norm_name(w1b):
                    absent = w2b
                elif np == self._ko_norm_name(w2b):
                    absent = w1b
                else:
                    narrowed = [c for c in candidates if self._ko_norm_name(c) not in other_names]
                    if len(narrowed) == 1:
                        absent = narrowed[0]

            if not absent:
                return
            display = f"{absent} (No show)"
            new_id = self._ko_find_player_id_in_qf_matches(qf1, qf2, absent)
            bye_dict["name"] = display
            if new_id:
                bye_dict["id"] = new_id

        apply("SF1")
        apply("SF2")
        return matches

    def _maybe_insert_inferred_sf2(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        When KO-Finale has only four match clusters (QF1, QF2, SF1, Final), the sheet often
        omits rows for SF2 walkover. Infer the finalist who did not play SF1 and insert SF2.
        """
        if len(matches) != 4:
            return matches
        sf1, fin = matches[2], matches[3]
        s1_names = {
            self._ko_norm_name(sf1["side_a"]["name"]),
            self._ko_norm_name(sf1["side_b"]["name"]),
        }
        fa = str(fin["side_a"]["name"] or "")
        fb = str(fin["side_b"]["name"] or "")
        adv: Optional[str] = None
        for cand in (fa, fb):
            if self._ko_norm_name(cand) not in s1_names:
                adv = cand
                break
        if not adv or self._is_ko_bye_player(adv):
            return matches
        wa_id = str(fin["side_a"].get("id", "") or "")
        wb_id = str(fin["side_b"].get("id", "") or "")
        adv_id = wa_id if self._ko_norm_name(adv) == self._ko_norm_name(fa) else wb_id
        syn: Dict[str, Any] = {
            "key": "SF2",
            "label": "SF2",
            "phase": "sf",
            "side_a": {"name": adv, "id": adv_id, "games_won": 2},
            "side_b": {"name": "Nicht angetreten (No show)", "id": "", "games_won": 0},
            "pin_games": [],
            "walkover": True,
            "winner": "a",
            "first_game_number": int(fin.get("first_game_number") or 0),
            "inferred": True,
            "scratch_total_a": 0,
            "scratch_total_b": 0,
            "scratch_series": False,
            "scratch_final": False,
        }
        return matches[:3] + [syn] + [fin]

    def _relabel_ko_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        keys = self._ko_bracket_match_keys(len(matches))
        for i, m in enumerate(matches):
            if i < len(keys):
                m["key"] = keys[i]
                mk = keys[i]
                m["label"] = "Finale" if mk == "F" else mk
                m["phase"] = self._ko_bracket_tree_phase(i, len(matches))
        return matches

    def _ko_finalist_path_meta(self, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rainbow lane indices + which bracket keys each finalist played in (for UI path)."""
        by_key = {str(m.get("key", "")): m for m in matches}
        f = by_key.get("F")
        if not f:
            return {
                "finalist_a": None,
                "finalist_b": None,
                "path_keys_a": [],
                "path_keys_b": [],
                "palette_index_a": 2,
                "palette_index_b": 8,
            }
        fa = str(f["side_a"]["name"] or "")
        fb = str(f["side_b"]["name"] or "")

        def path_for(name: str) -> List[str]:
            nc = self._ko_norm_name(self._ko_strip_no_show_suffix(name))
            if not nc or self._is_ko_bye_player(name):
                return ["F"]
            p: List[str] = ["F"]
            for sk in ("SF2", "SF1"):
                sm = by_key.get(sk)
                if not sm:
                    continue
                sides = {
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(sm["side_a"].get("name", "") or ""))),
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(sm["side_b"].get("name", "") or ""))),
                }
                if nc in sides:
                    p.insert(0, sk)
            for qk in ("QF2", "QF1"):
                qm = by_key.get(qk)
                if not qm:
                    continue
                sides = {
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(qm["side_a"].get("name", "") or ""))),
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(qm["side_b"].get("name", "") or ""))),
                }
                if nc in sides:
                    p.insert(0, qk)
            return p

        return {
            "finalist_a": fa,
            "finalist_b": fb,
            "path_keys_a": path_for(fa),
            "path_keys_b": path_for(fb),
            "palette_index_a": 2,
            "palette_index_b": 8,
        }

    @staticmethod
    def _ko_bracket_tree_phase(match_index: int, n_matches: int) -> str:
        if n_matches <= 1:
            return "final"
        last = n_matches - 1
        if match_index == last:
            return "final"
        if n_matches == 5:
            return "qf" if match_index < 2 else "sf"
        if n_matches == 3:
            return "sf"
        if n_matches == 2:
            return "sf"
        if n_matches == 4:
            return "qf" if match_index < 2 else "sf"
        return "early" if match_index < last - 1 else "late"

    def _ko_bracket_empty_meta(self) -> Dict[str, Any]:
        return {
            "matches": [],
            "placements": [],
            "finalist_a": None,
            "finalist_b": None,
            "path_keys_a": [],
            "path_keys_b": [],
            "palette_index_a": 2,
            "palette_index_b": 8,
            "ko_finale_series": KO_FINALE_SERIES_BO3,
        }

    def _load_tournament_ko_config(self) -> Dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "database" / "data" / "tournament_ko_config.json"
        if not path.is_file():
            return {}
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _ko_finale_series_mode(self, season: str, tournament: str) -> str:
        raw = self._load_tournament_ko_config()
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        if not isinstance(block, dict):
            return KO_FINALE_SERIES_BO3
        v = str(block.get("ko_finale_series", "") or "").strip().lower()
        if v in ("scratch_total_2g", "scratch_total", "scratch_2g", "2g_scratch"):
            return KO_FINALE_SERIES_SCRATCH_2G
        if v in ("bo3_pins", "bo3", "pins"):
            return KO_FINALE_SERIES_BO3
        return KO_FINALE_SERIES_BO3

    def _ko_bracket_empty_payload(self, season: str, tournament: str) -> Dict[str, Any]:
        return {**self._ko_bracket_empty_meta(), "ko_finale_series": self._ko_finale_series_mode(season, tournament)}

    def _ko_config_entry(
        self, season: str, tournament: str, *, df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        raw = self._load_tournament_ko_config()
        event = self._config_event_name(season, tournament, df)
        key = f"{str(season).strip()}||{event}"
        block = raw.get(key)
        if isinstance(block, dict):
            return block
        tournament_norm = str(tournament).strip()
        if event != tournament_norm:
            block = raw.get(f"{str(season).strip()}||{tournament_norm}")
            return block if isinstance(block, dict) else {}
        return {}

    @staticmethod
    def _event_name_suggests_nbm_sbm_lane_pairs(tournament: str) -> bool:
        """
        Highest consecutive-pair scratch is meaningful when players change lanes across adjacent games
        (regional Nord/Süd Bayerische Meisterschaft). State-wide Bayerische events use other formats.
        """
        t = str(tournament or "")
        if re.search(r"(?i)nordbayerische\s+meisterschaft", t):
            return True
        if re.search(r"(?i)südbayerische\s+meisterschaft", t) or re.search(r"(?i)sudbayerische\s+meisterschaft", t):
            return True
        return False

    def _tournament_df_has_meaningful_handicap(self, df: pd.DataFrame) -> bool:
        if df.empty:
            return False
        if Columns.handicap in df.columns:
            s = pd.to_numeric(df[Columns.handicap], errors="coerce").fillna(0.0)
            if bool(s.abs().gt(0).any()):
                return True
        if Columns.apriori_average in df.columns:
            ap = pd.to_numeric(df[Columns.apriori_average], errors="coerce").dropna()
            if not ap.empty:
                return True
        return False

    def _tournament_pins_series(self, df: pd.DataFrame) -> pd.Series:
        """Scratch pins, or scratch + handicap when the event uses net scoring."""
        work = _with_progress_pins(df, self._tournament_df_has_meaningful_handicap(df))
        return pd.to_numeric(work["__pins"], errors="coerce").fillna(0.0)

    def _cumulative_pins_totals_through_round(
        self,
        df: pd.DataFrame,
        through_round: int,
        *,
        include_club: bool = False,
    ) -> pd.DataFrame:
        """Per-player cumulative pins through ``through_round`` (score + handicap when allowed)."""
        if df.empty or Columns.round_number not in df.columns:
            return pd.DataFrame()
        work = df.copy()
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        work = work[work[Columns.round_number].le(float(through_round))].copy()
        if work.empty:
            return pd.DataFrame()
        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)
        work = work.assign(cumulative_pins=self._tournament_pins_series(work))
        return (
            work.groupby(group_keys, dropna=False)["cumulative_pins"]
            .sum()
            .reset_index()
        )

    def _cumulative_totals_ranked(
        self,
        df: pd.DataFrame,
        through_round: int,
        *,
        include_club: bool = False,
    ) -> pd.DataFrame:
        totals = self._cumulative_pins_totals_through_round(
            df, int(through_round), include_club=include_club
        )
        if totals.empty:
            return totals
        totals = totals.sort_values(
            by=["cumulative_pins", Columns.player_name], ascending=[False, True]
        ).reset_index(drop=True)
        totals["rank"] = totals["cumulative_pins"].rank(method="min", ascending=False).astype(int)
        return totals

    def _gesamt_scratch_net_pivot(
        self,
        df: pd.DataFrame,
        *,
        through_round: Optional[int] = None,
        include_club: bool = False,
    ) -> pd.DataFrame:
        """Gesamtwertung pivot with ``total_net`` / ``avg_net`` (optional round cap)."""
        if df.empty:
            return pd.DataFrame()
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        if through_round is not None:
            work = work[work[Columns.round_number].le(float(through_round))].copy()
        if work.empty:
            return pd.DataFrame()
        work[Columns.round_number] = work[Columns.round_number].astype("Int64")

        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)

        round_numbers = sorted(
            {int(x) for x in work[Columns.round_number].dropna().unique().tolist()}
        )
        grouped = (
            work.groupby([Columns.player_name, id_col, Columns.club, Columns.round_number], dropna=False)[
                Columns.score
            ]
            .sum()
            .reset_index(name="round_total")
        )
        pivot = grouped.pivot_table(
            index=[Columns.player_name, id_col, Columns.club],
            columns=Columns.round_number,
            values="round_total",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        for rn in round_numbers:
            if rn not in pivot.columns:
                pivot[rn] = 0
        pivot["total_score"] = pivot[round_numbers].sum(axis=1) if round_numbers else 0
        games_per_player_all = (
            work[work[Columns.score].gt(0)]
            .groupby([Columns.player_name, id_col], dropna=False)
            .size()
            .reset_index(name="games_played")
        )
        pivot = pivot.merge(games_per_player_all, on=[Columns.player_name, id_col], how="left")
        pivot["games_played"] = pd.to_numeric(pivot["games_played"], errors="coerce").fillna(1)

        if not self._tournament_df_has_meaningful_handicap(df):
            pivot["total_avg"] = (pivot["total_score"] / pivot["games_played"]).round(1)
            return pivot

        work["_row_net"] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        if Columns.handicap in work.columns:
            work["_row_net"] = work["_row_net"] + pd.to_numeric(
                work[Columns.handicap], errors="coerce"
            ).fillna(0)
        tot_net = (
            work.groupby([Columns.player_name, id_col, Columns.club], dropna=False)["_row_net"]
            .sum()
            .reset_index(name="total_net")
        )
        pivot = pivot.merge(tot_net, on=[Columns.player_name, id_col, Columns.club], how="left")
        pivot["total_net"] = pd.to_numeric(pivot["total_net"], errors="coerce").fillna(0).round(0).astype(int)
        pivot["avg_scratch"] = (pivot["total_score"] / pivot["games_played"]).round(1)
        pivot["avg_net"] = (pivot["total_net"] / pivot["games_played"]).round(1)
        return pivot

    def _avg_net_standings_from_gesamt_pivot(
        self,
        df: pd.DataFrame,
        *,
        through_round: Optional[int] = None,
        include_club: bool = False,
    ) -> pd.DataFrame:
        """
        Standings matching Gesamtwertung when sorted by average (``avg_net`` rank).
        """
        if not self._tournament_df_has_meaningful_handicap(df):
            if through_round is None:
                max_rn = pd.to_numeric(df[Columns.round_number], errors="coerce").max()
                through_round = int(max_rn) if pd.notna(max_rn) else None
            if through_round is None:
                return pd.DataFrame()
            ranked = self._cumulative_averages_ranked(
                df, int(through_round), include_club=include_club
            )
            if ranked.empty:
                return ranked
            return (
                ranked.rename(
                    columns={"cumulative_avg": "avg_net", "cumulative_pins": "total_score"}
                )
                .sort_values(by=["avg_net", Columns.player_name], ascending=[False, True])
                .reset_index(drop=True)
            )

        pivot = self._gesamt_scratch_net_pivot(
            df, through_round=through_round, include_club=include_club
        )
        if pivot.empty or "avg_net" not in pivot.columns:
            return pd.DataFrame()
        out = pivot[[Columns.player_name, "total_net", "avg_net", "games_played"]].copy()
        out = out.sort_values(by=["avg_net", Columns.player_name], ascending=[False, True]).reset_index(
            drop=True
        )
        out["rank"] = out["avg_net"].rank(method="min", ascending=False).astype(int)
        return out

    def _cumulative_averages_ranked(
        self,
        df: pd.DataFrame,
        through_round: int,
        *,
        include_club: bool = False,
    ) -> pd.DataFrame:
        """Per-player cumulative average (net when handicap applies) through ``through_round``."""
        totals = self._cumulative_pins_totals_through_round(
            df, int(through_round), include_club=include_club
        )
        if totals.empty:
            return totals
        work = df.copy()
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        work = work[work[Columns.round_number].le(float(through_round))].copy()
        if work.empty:
            return pd.DataFrame()
        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)
        played = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0).gt(0)
        games_df = (
            work.loc[played]
            .groupby(group_keys, dropna=False)
            .size()
            .reset_index(name="games_played")
        )
        merged = totals.merge(games_df, on=group_keys, how="left")
        merged["games_played"] = pd.to_numeric(merged["games_played"], errors="coerce").fillna(0).astype(int)
        merged = merged[merged["games_played"].gt(0)].copy()
        if merged.empty:
            return merged
        merged["cumulative_avg"] = (
            pd.to_numeric(merged["cumulative_pins"], errors="coerce").fillna(0.0)
            / merged["games_played"].astype(float)
        ).round(1)
        merged = merged.sort_values(
            by=["cumulative_avg", Columns.player_name], ascending=[False, True]
        ).reset_index(drop=True)
        merged["rank"] = merged["cumulative_avg"].rank(method="min", ascending=False).astype(int)
        return merged

    def _best_set_winner_in_scope(
        self,
        df: pd.DataFrame,
        *,
        round_number: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Player with the highest set total (scratch + handicap when applicable) in scope."""
        if df.empty or Columns.round_number not in df.columns:
            return None
        work = df.copy()
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        if round_number is not None:
            work = work[work[Columns.round_number].eq(float(round_number))].copy()
        if work.empty:
            return None
        played = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0).gt(0)
        work = work.loc[played].copy()
        if work.empty:
            return None
        work = work.assign(__pins=self._tournament_pins_series(work))
        set_totals = (
            work.groupby([Columns.player_name, Columns.round_number], dropna=False)["__pins"]
            .sum()
            .reset_index(name="set_total")
        )
        if set_totals.empty:
            return None
        best = set_totals.sort_values(
            by=["set_total", Columns.player_name], ascending=[False, True]
        ).iloc[0]
        rn = int(best[Columns.round_number])
        round_name = f"Round {rn}"
        if Columns.round_name in work.columns:
            names = (
                work.loc[work[Columns.round_number].eq(float(rn)), Columns.round_name]
                .dropna()
                .astype(str)
                .str.strip()
            )
            names = [n for n in names.unique().tolist() if n]
            if names:
                round_name = names[0]
        return {
            "player": str(best[Columns.player_name]),
            "set_total": int(round(float(best["set_total"]), 0)),
            "round_number": rn,
            "round_name": round_name,
        }

    def _default_player_card_layout(self, season: str, tournament: str) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        want_pair = self._event_name_suggests_nbm_sbm_lane_pairs(tournament)
        want_hc = self._tournament_df_has_meaningful_handicap(df)
        out: List[str] = []
        for cid in TOURNAMENT_PLAYER_CARD_ORDER:
            if cid == "best_highest_pair" and not want_pair:
                continue
            if cid == "handicap_profile" and not want_hc:
                continue
            out.append(cid)
        return out if out else [
            "summary_final_position",
            "summary_average",
            "summary_best_position",
            "best_highest_game",
            "best_highest_block",
        ]

    def _resolve_player_card_layout(self, season: str, tournament: str) -> List[str]:
        block = self._ko_config_entry(season, tournament)
        raw = block.get("player_cards")
        if isinstance(raw, list) and raw:
            cleaned: List[str] = []
            for item in raw:
                if not isinstance(item, str):
                    continue
                cid = item.strip()
                if cid in TOURNAMENT_PLAYER_VALID_CARDS:
                    cleaned.append(cid)
            if cleaned:
                return cleaned
        return self._default_player_card_layout(season, tournament)

    def _ko_qualifying_cut_pair(
        self, season: str, tournament: str, *, df: Optional[pd.DataFrame] = None
    ) -> Optional[tuple[int, int]]:
        """
        Optional (round_number, cut_rank) from tournament_ko_config.json when the export has no Cut Line column.
        """
        block = self._ko_config_entry(season, tournament, df=df)
        rank = self._ko_optional_int(block.get("ko_qualifying_cut_rank"))
        if rank is None or rank < 1:
            return None
        rnd = self._ko_optional_int(block.get("ko_qualifying_cut_round"))
        if rnd is None or rnd < 1:
            rnd = 1
        return (rnd, rank)

    def _ko_qualifying_cut_span_config(
        self, season: str, tournament: str, *, df: Optional[pd.DataFrame] = None
    ) -> Optional[Dict[str, int]]:
        """
        Qualifying cut rank applied from first_round through through_round (inclusive) for charts and shading
        when the CSV has no Cut Line. Optional ko_qualifying_cut_through_round (default: first round only).
        """
        block = self._ko_config_entry(season, tournament, df=df)
        rank = self._ko_optional_int(block.get("ko_qualifying_cut_rank"))
        if rank is None or rank < 1:
            return None
        first_r = self._ko_optional_int(block.get("ko_qualifying_cut_round"))
        if first_r is None or first_r < 1:
            first_r = 1
        through_r = self._ko_optional_int(block.get("ko_qualifying_cut_through_round"))
        if through_r is None:
            through_r = first_r
        through_r = max(int(first_r), int(through_r))
        return {"rank": int(rank), "first_round": int(first_r), "through_round": through_r}

    def _gesamt_leaderboard_cut_line_rank(self, season: str, tournament: str) -> Optional[int]:
        """
        Single cut-line rank for Gesamtwertung # column shading (from ``ko_qualifying_cut_rank``).

        Compared against the table's **# column ladder before KO merge**: net rank when the
        scratch+net layout is active, otherwise scratch rank.
        """
        pair = self._ko_qualifying_cut_pair(season, tournament)
        if not pair:
            return None
        _rnd, crank = pair
        return int(crank) if int(crank) >= 1 else None

    @staticmethod
    def _overall_cumulative_total_at_rank(all_df: pd.DataFrame, upto_round: int, rank_k: int) -> Optional[float]:
        """Total pins up to and including upto_round for the player at overall place rank_k (1-based)."""
        if all_df.empty or rank_k < 1 or Columns.round_number not in all_df.columns:
            return None
        scope = all_df[pd.to_numeric(all_df[Columns.round_number], errors="coerce").le(float(upto_round))].copy()
        if scope.empty or Columns.player_name not in scope.columns:
            return None
        scope[Columns.score] = pd.to_numeric(scope[Columns.score], errors="coerce").fillna(0)
        totals = scope.groupby(Columns.player_name, dropna=False)[Columns.score].sum()
        ranked = sorted(totals.items(), key=lambda t: (-float(t[1]), str(t[0])))
        if len(ranked) < rank_k:
            return None
        return float(ranked[rank_k - 1][1])

    def _ko_finale_round_number(self, df: pd.DataFrame) -> Optional[int]:
        if df.empty or Columns.round_number not in df.columns or Columns.round_name not in df.columns:
            return None
        ko_rows = df[df[Columns.round_name].astype(str).str.contains("KO", case=False, na=False)]
        if ko_rows.empty:
            return None
        return int(pd.to_numeric(ko_rows[Columns.round_number], errors="coerce").max())

    @staticmethod
    def _tournament_gender_key(tournament: str) -> Optional[str]:
        t = str(tournament or "")
        if "Frauen" in t:
            return "f"
        if "Männer" in t:
            return "m"
        return None

    def _cut_position_for_score(
        self,
        df: pd.DataFrame,
        through_round: int,
        cut_score: float,
        *,
        include_club: bool = False,
    ) -> Optional[int]:
        ranked = self._cumulative_totals_ranked(df, int(through_round), include_club=include_club)
        if ranked.empty:
            return None
        at_cut = ranked[ranked["cumulative_pins"].eq(float(cut_score))]
        if not at_cut.empty:
            return int(at_cut["rank"].min())
        ge = ranked[ranked["cumulative_pins"].ge(float(cut_score))]
        if not ge.empty:
            return int(ge["rank"].max())
        return None

    def _cut_player_for_score(
        self,
        df: pd.DataFrame,
        through_round: int,
        cut_score: float,
        *,
        include_club: bool = False,
    ) -> Optional[str]:
        ranked = self._cumulative_totals_ranked(df, int(through_round), include_club=include_club)
        if ranked.empty:
            return None
        at_cut = ranked[ranked["cumulative_pins"].eq(float(cut_score))]
        if at_cut.empty:
            return None
        row = at_cut.sort_values(by="rank", ascending=False).iloc[0]
        name = str(row.get(Columns.player_name, "") or "").strip()
        return name or None

    @staticmethod
    def _cut_line_score_for_round(df: pd.DataFrame, target_round: int) -> Optional[float]:
        if (
            df.empty
            or Columns.cut_line not in df.columns
            or Columns.round_number not in df.columns
            or Columns.game_number not in df.columns
        ):
            return None
        stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(target_round))].copy()
        if stage_df.empty:
            return None
        max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
        snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
        cut_vals = pd.to_numeric(snap[Columns.cut_line], errors="coerce").dropna()
        if cut_vals.empty:
            return None
        return float(cut_vals.iloc[0])

    @staticmethod
    def _games_upto_round_in_df(df: pd.DataFrame, target_round: int) -> int:
        if (
            df.empty
            or Columns.round_number not in df.columns
            or Columns.game_number not in df.columns
        ):
            return 0
        upto = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(target_round))].copy()
        if upto.empty:
            return 0
        meta = (
            upto[[Columns.round_number, Columns.game_number]]
            .dropna(subset=[Columns.round_number, Columns.game_number])
            .groupby(Columns.round_number, dropna=False)[Columns.game_number]
            .max()
            .reset_index()
        )
        if meta.empty:
            return 0
        return int(meta[Columns.game_number].apply(lambda g: int(g) + 1).sum())

    def _build_cut_line_card(
        self,
        df: pd.DataFrame,
        season: str,
        tournament: str,
        target_round: int,
        *,
        gesamt_view: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Cut-Line card: player at configured cut rank on the Gesamtwertung average ladder."""
        cut_pos = self._resolved_cut_position_for_round(df, int(target_round), season, tournament)
        if cut_pos is None:
            return None
        include_club = self._has_any_club_value(df)
        standings_through: Optional[int] = None if gesamt_view else int(target_round)
        ranked = self._avg_net_standings_from_gesamt_pivot(
            df, through_round=standings_through, include_club=include_club
        )
        if ranked.empty:
            return None
        at_cut = ranked[ranked["rank"].eq(int(cut_pos))]
        if at_cut.empty:
            return None
        row = at_cut.sort_values(by="rank", ascending=False).iloc[0]
        cut_player = str(row.get(Columns.player_name, "") or "").strip()
        if not cut_player:
            return None
        cut_avg = float(row["avg_net"])
        use_net_pins = self._tournament_df_has_meaningful_handicap(df)
        total_col = "total_net" if use_net_pins and "total_net" in row else "total_score"
        cut_total = int(round(float(row[total_col])))
        use_net_pins = self._tournament_df_has_meaningful_handicap(df)
        pins_label = "pins (netto)" if use_net_pins else "pins"
        cut_display = f"\u2300{cut_avg:.1f} ({cut_total} {pins_label})"

        return {
            "title": "Cut Line",
            "value": cut_player,
            "subtitle": cut_display,
            "type": "stat",
        }

    def _resolved_cut_position_for_round(
        self,
        source_df: pd.DataFrame,
        target_round: int,
        season: str,
        tournament: str,
        *,
        config_event: Optional[str] = None,
    ) -> Optional[int]:
        """Prefer CSV-derived cut rank; fall back to stage config or ko_qualifying_cut_*."""
        event = config_event or self._config_event_name(season, tournament, source_df)

        def _from_csv() -> Optional[int]:
            cut_score = self._cut_line_score_for_round(source_df, int(target_round))
            if cut_score is None:
                return None
            return self._cut_position_for_score(
                source_df,
                int(target_round),
                cut_score,
                include_club=self._has_any_club_value(source_df),
            )

        base = _from_csv()
        if base is not None:
            return base
        stage_cut = stage_cut_rank_for_round(season, event, int(target_round))
        if stage_cut is not None:
            return int(stage_cut)
        span = self._ko_qualifying_cut_span_config(season, tournament, df=source_df)
        if span is not None and int(span["first_round"]) <= int(target_round) <= int(span["through_round"]):
            return int(span["rank"])
        participant_cut = self._participant_count_for_round(source_df, int(target_round))
        return participant_cut if participant_cut > 0 else None

    @staticmethod
    def _participant_count_for_round(source_df: pd.DataFrame, target_round: int) -> int:
        """Players active in ``target_round`` — default cut when no cut line is configured."""
        if source_df.empty or Columns.round_number not in source_df.columns:
            return 0
        round_df = source_df[
            pd.to_numeric(source_df[Columns.round_number], errors="coerce").eq(float(target_round))
        ]
        if round_df.empty or Columns.player_name not in round_df.columns:
            return 0
        return int(round_df[Columns.player_name].astype(str).str.strip().nunique())

    def _ko_cut_line_card_from_config_rank(
        self, df: pd.DataFrame, season: str, tournament: str
    ) -> Optional[Dict[str, Any]]:
        """Build Cut Line summary card from qualifying-round snapshot at configured cut rank (no Cut Line column)."""
        cfg = self._ko_qualifying_cut_pair(season, tournament)
        if not cfg:
            return None
        crn, crank = cfg
        stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(crn))].copy()
        if stage_df.empty or Columns.game_number not in stage_df.columns:
            return None
        max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
        snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
        if snap.empty or Columns.stage_rank not in snap.columns:
            return None
        ranks = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
        at = snap[ranks.eq(float(crank))].copy()
        if at.empty:
            return None
        if Columns.cumulative_score in at.columns:
            at = at.sort_values(by=Columns.cumulative_score, ascending=False)
        player = str(at.iloc[0].get(Columns.player_name, "") or "").strip()
        if not player:
            return None
        score_col = Columns.cumulative_score
        if "Overall Cumulative Score" in at.columns:
            score_col = "Overall Cumulative Score"
        cut_score = pd.to_numeric(at.iloc[0].get(score_col), errors="coerce")
        if pd.isna(cut_score):
            return None
        games_upto = 0
        if Columns.round_number in df.columns and Columns.game_number in df.columns:
            upto = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(crn))].copy()
            if not upto.empty:
                meta = (
                    upto[[Columns.round_number, Columns.game_number]]
                    .dropna(subset=[Columns.round_number, Columns.game_number])
                    .groupby(Columns.round_number, dropna=False)[Columns.game_number]
                    .max()
                    .reset_index()
                )
                if not meta.empty:
                    games_upto = int(meta[Columns.game_number].apply(lambda g: int(g) + 1).sum())
        cut_display = f"{int(cut_score)} pins (\u2300{(float(cut_score) / max(games_upto, 1)):.1f})" if games_upto > 0 else f"{int(cut_score)} pins"
        return {"title": "Cut Line", "value": player, "subtitle": cut_display, "type": "stat"}

    def _ko_placements_from_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Standard 6-player tree: 1, 2, two 3rd (SF losers), two 5th (QF losers)."""

        def loser_of(m: Dict[str, Any]) -> str:
            w = m.get("winner")
            if w == "a":
                return str(m.get("side_b", {}).get("name", "") or "")
            if w == "b":
                return str(m.get("side_a", {}).get("name", "") or "")
            return ""

        def winner_name_id(m: Dict[str, Any]) -> tuple[str, str]:
            w = m.get("winner")
            if w == "a":
                return str(m.get("side_a", {}).get("name", "") or ""), str(m.get("side_a", {}).get("id", "") or "")
            if w == "b":
                return str(m.get("side_b", {}).get("name", "") or ""), str(m.get("side_b", {}).get("id", "") or "")
            return "", ""

        by_key = {str(m.get("key", "")): m for m in matches}
        out: List[Dict[str, Any]] = []
        fin = by_key.get("F")
        if not fin:
            return out

        wn, wid = winner_name_id(fin)
        ln = loser_of(fin)
        lid = str(fin.get("side_b", {}).get("id", "") or "") if fin.get("winner") == "a" else str(fin.get("side_a", {}).get("id", "") or "")

        if wn and not self._is_ko_bye_player(wn):
            out.append({"place": 1, "player": wn, "player_id": wid})
        if ln and not self._is_ko_bye_player(ln):
            out.append({"place": 2, "player": ln, "player_id": lid})

        for sk in ("SF1", "SF2"):
            sm = by_key.get(sk)
            if not sm:
                continue
            lost = loser_of(sm)
            if lost and not self._is_ko_bye_player(lost):
                pid = str(sm.get("side_b", {}).get("id", "") or "") if sm.get("winner") == "a" else str(sm.get("side_a", {}).get("id", "") or "")
                out.append({"place": 3, "player": lost, "player_id": pid})

        for qk in ("QF1", "QF2"):
            qm = by_key.get(qk)
            if not qm:
                continue
            lost = loser_of(qm)
            if lost and not self._is_ko_bye_player(lost):
                pid = str(qm.get("side_b", {}).get("id", "") or "") if qm.get("winner") == "a" else str(qm.get("side_a", {}).get("id", "") or "")
                out.append({"place": 5, "player": lost, "player_id": pid})

        return out

    def _ko_final_winner_card_subtitle(self, fin_match: Dict[str, Any]) -> str:
        if not fin_match:
            return ""
        w = fin_match.get("winner")
        if fin_match.get("scratch_series"):
            ta = int(fin_match.get("scratch_total_a") or 0)
            tb = int(fin_match.get("scratch_total_b") or 0)
            if w == "a":
                return f"{ta}:{tb} Pins"
            if w == "b":
                return f"{tb}:{ta} Pins"
            return f"{ta}:{tb} Pins"
        sa = fin_match.get("side_a", {})
        sb = fin_match.get("side_b", {})
        wa = int(sa.get("games_won") or 0)
        wb = int(sb.get("games_won") or 0)
        return f"{wa}:{wb} Spiele"

    @staticmethod
    def _table_data_keep_rows_min_place(table: TableData, min_rank: int) -> TableData:
        """Filter tournament total leaderboard rows where scratch ladder rank >= min_rank."""

        def _scratch_ladder_rank(i: int, row: List[Any]) -> int:
            if table.row_metadata and i < len(table.row_metadata):
                sr = table.row_metadata[i].get("scratch_rank")
                if sr is not None:
                    return int(sr)
            return int(row[0])

        if min_rank <= 1 or not table.data:
            return table
        keep_idx = [i for i, row in enumerate(table.data) if row and _scratch_ladder_rank(i, row) >= min_rank]
        if not keep_idx:
            return TableData(columns=[], data=[], title=table.title, config=dict(table.config or {}))
        new_data = [table.data[i] for i in keep_idx]
        new_rm = [table.row_metadata[i] for i in keep_idx] if table.row_metadata and len(table.row_metadata) == len(table.data) else []
        new_cm: Dict[str, Dict[str, Any]] = {}
        if table.cell_metadata:
            for new_i, old_i in enumerate(keep_idx):
                for k, v in table.cell_metadata.items():
                    parts = str(k).split(":")
                    if len(parts) == 2 and int(parts[0]) == old_i:
                        new_cm[f"{new_i}:{parts[1]}"] = v
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=dict(table.metadata or {}),
            default_sort=table.default_sort,
        )

    @staticmethod
    def _table_data_exclude_normalized_player_keys(table: TableData, exclude_keys: Set[str]) -> TableData:
        """Drop rows whose player name (col 1, after KO no-show normalization) is in exclude_keys."""
        if not exclude_keys or not table.data:
            return table
        keep_idx: List[int] = []
        for i, row in enumerate(table.data):
            if not row or len(row) < 2:
                continue
            pk = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(row[1])))
            if pk not in exclude_keys:
                keep_idx.append(i)
        if not keep_idx:
            return TableData(columns=[], data=[], title=table.title, config=dict(table.config or {}))
        new_data = [table.data[i] for i in keep_idx]
        new_rm = (
            [table.row_metadata[i] for i in keep_idx]
            if table.row_metadata and len(table.row_metadata) == len(table.data)
            else []
        )
        new_cm: Dict[str, Dict[str, Any]] = {}
        if table.cell_metadata:
            for new_i, old_i in enumerate(keep_idx):
                for k, v in table.cell_metadata.items():
                    parts = str(k).split(":")
                    if len(parts) == 2 and int(parts[0]) == old_i:
                        new_cm[f"{new_i}:{parts[1]}"] = v
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=dict(table.metadata or {}),
            default_sort=table.default_sort,
        )

    def _ko_placements_table_data(self, _season: str, tournament: str, df: pd.DataFrame, bracket: Dict[str, Any]) -> TableData:
        placements = list(bracket.get("placements") or [])
        include_club = self._has_any_club_value(df)
        club_map: Dict[str, str] = {}
        if include_club and Columns.player_name in df.columns and Columns.club in df.columns:
            for _, r in df[[Columns.player_name, Columns.club]].drop_duplicates().iterrows():
                nm = str(r[Columns.player_name]).strip()
                c = str(r.get(Columns.club, "") or "").strip()
                if nm:
                    club_map.setdefault(nm, c)

        base_cols = [
            Column(title=i18n_service.get_text("position"), field="place", width="70px", align="center", decimal_places=0, frozen="left"),
            Column(title=i18n_service.get_text("player"), field="player", width="144px", align="left", frozen="left"),
        ]
        if include_club:
            base_cols.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="200px", align="left"))
        grouped_columns = [
            ColumnGroup(
                title="",
                style={"backgroundColor": "#f8f9fa"},
                columns=base_cols,
            )
        ]
        rows: List[List[Any]] = []
        for p in placements:
            pname = str(p.get("player", "") or "").strip()
            row = [int(p.get("place", 0)), pname]
            if include_club:
                row.append(club_map.get(pname, ""))
            rows.append(row)

        ko_rn = self._ko_finale_round_number(df)
        stage_lbl = ""
        if ko_rn is not None and Columns.round_name in df.columns:
            meta = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(ko_rn))]
            if not meta.empty:
                stage_lbl = str(meta[Columns.round_name].iloc[0])

        return TableData(
            columns=grouped_columns,
            data=rows,
            title=f"{tournament} — {stage_lbl}".strip(" —"),
            metadata={"kind": "ko_placements", "suppress_cut_styling": True},
            default_sort={"field": "place", "dir": "asc"},
            config={
                "stickyHeader": True,
                "striped": True,
                "hover": True,
                "responsive": True,
                "compact": False,
                "stripedColGroups": True,
            },
        )

    def _integrate_ko_into_total_leaderboard(
        self,
        table: TableData,
        bracket: Dict[str, Any],
        df: pd.DataFrame,
        season: str,
        tournament: str,
    ) -> TableData:
        """
        Gesamt leaderboard: show KO bracket places (1, 2, 3/3, 5/5) in the # column for finalists;
        everyone else keeps the pre-KO # column (scratch rank in scratch-only mode, net rank when
        scratch+net layout is active). Sort: last column average desc (scratch avg or net avg), then # asc.
        Cut-line # column shading matches the latest qualifying stage (same as Gesamtwertung
        before KO reordering): green inside cut, yellow on cut, red outside.
        """
        placements = list(bracket.get("placements") or [])
        if not placements or not table.data:
            return table

        ko_by_key: Dict[str, int] = {}
        for p in placements:
            nm = str(p.get("player", "") or "").strip()
            k = self._ko_norm_name(self._ko_strip_no_show_suffix(nm))
            if k:
                ko_by_key[k] = int(p.get("place", 0))

        latest_qual_rn = self._latest_qualifying_round_number(df)
        cut_pos: Optional[int] = None
        if latest_qual_rn is not None:
            cut_pos = self._resolved_cut_position_for_round(
                df, int(latest_qual_rn), season, tournament
            )

        has_rm = bool(table.row_metadata) and len(table.row_metadata) == len(table.data)

        augmented: List[Dict[str, Any]] = []
        for row_idx, row in enumerate(table.data):
            if not row or len(row) < 3:
                continue
            pre_ko_rank = int(row[0])
            pname = str(row[1]).strip()
            pk = self._ko_norm_name(self._ko_strip_no_show_suffix(pname))
            display_pos = int(ko_by_key.get(pk, pre_ko_rank))
            total_avg = float(row[-1])
            shade_r = pre_ko_rank
            if has_rm:
                shade_r = int(table.row_metadata[row_idx].get("cut_shade_rank") or pre_ko_rank)
            augmented.append(
                {
                    "row": list(row),
                    "display_pos": display_pos,
                    "shade_r": shade_r,
                    "total_avg": total_avg,
                    "old_idx": row_idx,
                }
            )

        if len(augmented) != len(table.data):
            return table

        augmented.sort(key=lambda x: (-x["total_avg"], x["display_pos"]))

        new_data: List[List[Any]] = []
        new_rm: List[Dict[str, Any]] = []
        new_cm: Dict[str, Dict[str, Any]] = {}

        for new_i, item in enumerate(augmented):
            r = item["row"]
            r[0] = item["display_pos"]
            new_data.append(r)

            shade_r = int(item["shade_r"])
            display_pos = int(item["display_pos"])
            style = self._cut_row_style_for_rank(shade_r, cut_pos)
            if display_pos == 1 and style:
                style = {**style, "fontWeight": "700"}
            elif display_pos == 1:
                style = {"fontWeight": "700"}
            if has_rm:
                new_rm.append(dict(table.row_metadata[item["old_idx"]]))
            else:
                new_rm.append({"styling": {}})
            if style:
                new_cm[f"{new_i}:0"] = style

        meta = dict(table.metadata or {})
        sort_field = (
            "avg_net"
            if (table.metadata or {}).get("leaderboard_mode") == "scratch_net_handicap"
            else "total_avg"
        )
        meta["initial_sort"] = [
            {"field": sort_field, "dir": "desc"},
            {"field": "rank", "dir": "asc"},
        ]
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=meta,
            default_sort={"field": sort_field, "dir": "desc"},
        )

    @staticmethod
    def _ko_optional_int(val: Any) -> Optional[int]:
        x = pd.to_numeric(val, errors="coerce")
        if pd.isna(x):
            return None
        return int(x)

    def _ko_series_tiebreak_side(self, cluster: List[tuple], side_a: str, side_b: str) -> Optional[str]:
        """
        When counted pin games are tied (e.g. 1-1 in BO3 but G3 missing from export), derive the
        series winner from Stage Rank on the last game row (tournament placement), then pin totals.
        """
        if not cluster:
            return None
        _last_gn, lp0, lp1 = cluster[-1]

        def sr_for(name: str) -> Optional[int]:
            for px in (lp0, lp1):
                if self._ko_norm_name(px["name"]) == self._ko_norm_name(name):
                    return self._ko_optional_int(px.get("stage_rank"))
            return None

        ra = sr_for(side_a)
        rb = sr_for(side_b)
        if ra is not None and rb is not None and ra != rb:
            return "a" if ra < rb else "b"

        ta = tb = 0
        for _gn, q0, q1 in cluster:
            for q in (q0, q1):
                s = int(q.get("score") or 0)
                if self._ko_norm_name(q["name"]) == self._ko_norm_name(side_a):
                    ta += s
                elif self._ko_norm_name(q["name"]) == self._ko_norm_name(side_b):
                    tb += s
        if ta > tb:
            return "a"
        if tb > ta:
            return "b"
        return None

    def _build_ko_bracket_payload(
        self,
        season: str,
        tournament: str,
        df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Best-effort KO tree from rows whose round name mentions KO (e.g. KO-Finale).
        Groups consecutive game numbers that share the same opponent pair (BO3 series).
        Walkovers use Club KO_WO and/or placeholder opponent 'Nicht angetreten'.
        """
        cache_key = self._tournament_cache_key(season, tournament)
        cached_ko = self._ko_bracket_cache.get(cache_key)
        if cached_ko is not None:
            return cached_ko
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty or Columns.round_name not in df.columns or Columns.game_number not in df.columns:
            return self._store_ko_bracket_cache(
                season, tournament, self._ko_bracket_empty_payload(season, tournament)
            )
        rn = df[Columns.round_name].astype(str).str.strip()
        mask = rn.str.contains("KO", case=False, na=False)
        ko_df = df.loc[mask].copy()
        if ko_df.empty:
            return self._store_ko_bracket_cache(
                season, tournament, self._ko_bracket_empty_payload(season, tournament)
            )
        ko_df["_gn"] = pd.to_numeric(ko_df[Columns.game_number], errors="coerce")
        ko_df = ko_df.dropna(subset=["_gn"])
        if ko_df.empty:
            return self._store_ko_bracket_cache(
                season, tournament, self._ko_bracket_empty_payload(season, tournament)
            )
        ko_df["_gn"] = ko_df["_gn"].astype(int)
        ko_df = ko_df.reset_index(drop=False).rename(columns={"index": "_row_order"})
        ko_df = ko_df.sort_values(by=["_gn", "_row_order"], kind="mergesort")
        finale_mode = self._ko_finale_series_mode(season, tournament)

        games_blocks: List[tuple] = []
        for gn, gdf in ko_df.groupby("_gn", sort=True):
            rows: List[Dict[str, Any]] = []
            for _, r in gdf.iterrows():
                club_v = str(r.get(Columns.club, "") or "").strip()
                sr = None
                if Columns.stage_rank in ko_df.columns:
                    sr = self._ko_optional_int(r.get(Columns.stage_rank))
                rows.append(
                    {
                        "name": str(r.get(Columns.player_name, "") or "").strip(),
                        "id": str(r.get(Columns.player_id, "") or "").strip(),
                        "score": int(pd.to_numeric(r.get(Columns.score), errors="coerce") or 0),
                        "club": club_v,
                        "stage_rank": sr,
                    }
                )
            if len(rows) < 2:
                continue
            if len(rows) > 2:
                by_name: Dict[str, Dict[str, Any]] = {}
                for row in rows:
                    key = row["name"].casefold()
                    prev = by_name.get(key)
                    if prev is None:
                        by_name[key] = dict(row)
                    else:
                        prev["score"] += row["score"]
                        if row.get("stage_rank") is not None:
                            prev["stage_rank"] = row["stage_rank"]
                rows = list(by_name.values())
                if len(rows) < 2:
                    continue
            p0, p1 = rows[0], rows[1]
            pair_key = tuple(sorted([p0["name"], p1["name"]], key=str.casefold))
            games_blocks.append((int(gn), pair_key, p0, p1))

        if not games_blocks:
            return self._store_ko_bracket_cache(
                season, tournament, self._ko_bracket_empty_payload(season, tournament)
            )

        clusters: List[List[tuple]] = []
        cur: List[tuple] = []
        cur_key: Optional[tuple] = None
        for item in games_blocks:
            gn, key, p0, p1 = item
            if not cur:
                cur_key = key
                cur.append((gn, p0, p1))
                continue
            if key == cur_key:
                cur.append((gn, p0, p1))
            else:
                clusters.append(cur)
                cur_key = key
                cur = [(gn, p0, p1)]
        if cur:
            clusters.append(cur)

        n_matches = len(clusters)
        keys = self._ko_bracket_match_keys(n_matches)
        matches_out: List[Dict[str, Any]] = []
        for idx, cluster in enumerate(clusters):
            first_gn, fp0, fp1 = cluster[0]
            side_a = fp0["name"]
            side_b = fp1["name"]
            id_a = fp0["id"]
            id_b = fp1["id"]
            mk = keys[idx] if idx < len(keys) else f"M{idx + 1}"

            walkover = False
            pin_games: List[List[int]] = []
            wins_a = wins_b = 0
            scratch_total_a = scratch_total_b = 0
            for _gn, p0, p1 in cluster:
                c0 = str(p0.get("club") or "")
                c1 = str(p1.get("club") or "")
                if c0 == "KO_WO" or c1 == "KO_WO":
                    walkover = True
                if self._is_ko_bye_player(p0["name"]) or self._is_ko_bye_player(p1["name"]):
                    walkover = True

                if p0["name"] == side_a:
                    sa, sb = p0["score"], p1["score"]
                elif p0["name"] == side_b:
                    sa, sb = p1["score"], p0["score"]
                else:
                    sa, sb = p0["score"], p1["score"]

                if not walkover and (sa > 0 or sb > 0):
                    pin_games.append([sa, sb])
                    scratch_total_a += int(sa)
                    scratch_total_b += int(sb)
                    if sa > sb:
                        wins_a += 1
                    elif sb > sa:
                        wins_b += 1

            scratch_series_match = False
            scratch_final = False
            if walkover:
                if not self._is_ko_bye_player(side_a) and self._is_ko_bye_player(side_b):
                    wins_a, wins_b = 2, 0
                    winner = "a"
                elif self._is_ko_bye_player(side_a) and not self._is_ko_bye_player(side_b):
                    wins_a, wins_b = 0, 2
                    winner = "b"
                else:
                    wins_a, wins_b = 2, 0
                    winner = "a"
            elif finale_mode == KO_FINALE_SERIES_SCRATCH_2G and pin_games:
                # Entire KO bracket is scratch totals (e.g. women): winner = higher combined pins per match.
                scratch_series_match = True
                scratch_final = mk == "F"
                if scratch_total_a > scratch_total_b:
                    winner = "a"
                elif scratch_total_b > scratch_total_a:
                    winner = "b"
                else:
                    winner = None
                    tb_sc = self._ko_series_tiebreak_side(cluster, side_a, side_b)
                    if tb_sc == "a":
                        winner = "a"
                    elif tb_sc == "b":
                        winner = "b"
            else:
                if wins_a > wins_b:
                    winner = "a"
                elif wins_b > wins_a:
                    winner = "b"
                else:
                    winner = None
                    # BO3 at 1-1 when G3 is missing from CSV (not the final: some finals are 2-game scratch only).
                    if (
                        winner is None
                        and pin_games
                        and wins_a == wins_b
                        and wins_a >= 1
                        and mk != "F"
                    ):
                        tb_side = self._ko_series_tiebreak_side(cluster, side_a, side_b)
                        if tb_side == "a":
                            wins_a, wins_b, winner = 2, 1, "a"
                        elif tb_side == "b":
                            wins_a, wins_b, winner = 1, 2, "b"

            matches_out.append(
                {
                    "key": mk,
                    "label": mk.replace("F", "Finale") if mk == "F" else mk,
                    "phase": self._ko_bracket_tree_phase(idx, n_matches),
                    "side_a": {"name": self._ko_bracket_side_display_name(side_a), "id": id_a, "games_won": wins_a},
                    "side_b": {"name": self._ko_bracket_side_display_name(side_b), "id": id_b, "games_won": wins_b},
                    "pin_games": pin_games,
                    "walkover": walkover,
                    "winner": winner,
                    "first_game_number": first_gn,
                    "scratch_total_a": scratch_total_a,
                    "scratch_total_b": scratch_total_b,
                    "scratch_series": scratch_series_match,
                    "scratch_final": scratch_final,
                }
            )

        matches_out = self._maybe_insert_inferred_sf2(matches_out)
        matches_out = self._relabel_ko_matches(matches_out)
        matches_out = self._ko_resolve_sf_walkover_absent_from_qfs(matches_out)
        matches_out = self._ko_apply_bracket_overrides_json(season, tournament, matches_out)
        placements = self._ko_placements_from_matches(matches_out)
        meta = self._ko_finalist_path_meta(matches_out)
        return self._store_ko_bracket_cache(
            season,
            tournament,
            {"matches": matches_out, "placements": placements, **meta, "ko_finale_series": finale_mode},
        )

    @staticmethod
    def _ko_player_in_ko_matches(bracket: Optional[Dict[str, Any]], player: str) -> bool:
        if not bracket or not bracket.get("matches"):
            return False
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(player or "")))
        if not target:
            return False
        for m in bracket["matches"]:
            for side in ("side_a", "side_b"):
                s = m.get(side, {})
                nm = TournamentService._ko_strip_no_show_suffix(str(s.get("name", "") or ""))
                if TournamentService._ko_norm_name(nm) == target:
                    return True
        return False

    @staticmethod
    def _ko_placement_for_player(bracket: Optional[Dict[str, Any]], player: str) -> Optional[int]:
        """Official KO standing (1=champion, 2=finalist, …) when bracket placements list the player."""
        if not bracket:
            return None
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(player or "")))
        if not target:
            return None
        for p in bracket.get("placements") or []:
            nm = TournamentService._ko_strip_no_show_suffix(str(p.get("player", "") or ""))
            if TournamentService._ko_norm_name(nm) != target:
                continue
            pl = int(p.get("place", 0) or 0)
            return pl if pl > 0 else None
        return None

    def _ko_bracket_with_highlights(self, bracket: Dict[str, Any], player: str) -> Dict[str, Any]:
        if not bracket or not bracket.get("matches"):
            return bracket
        pnorm = self._ko_norm_name(self._ko_strip_no_show_suffix(str(player or "")))
        out_matches: List[Dict[str, Any]] = []
        for m in bracket["matches"]:
            mm = dict(m)
            sa = dict(m["side_a"])
            sb = dict(m["side_b"])
            sa["highlight"] = self._ko_norm_name(self._ko_strip_no_show_suffix(str(sa.get("name", "") or ""))) == pnorm
            sb["highlight"] = self._ko_norm_name(self._ko_strip_no_show_suffix(str(sb.get("name", "") or ""))) == pnorm
            mm["side_a"] = sa
            mm["side_b"] = sb
            out_matches.append(mm)
        return {**bracket, "matches": out_matches}

    def get_tournament_section(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        bench = TournamentBenchmark(
            "get_tournament_section",
            context={
                "season": season,
                "tournament": tournament,
                "round": round_number,
                "database": self.database,
            },
        )
        with bench.step("load_df"):
            df = self._get_tournament_df(season=season, tournament=tournament)
            if tournament_benchmark_enabled():
                bench.context["rows"] = len(df)

        with bench.step("ko_bracket"):
            ko_bracket = self._build_ko_bracket_payload(season, tournament, df=df)
        with bench.step("rounds"):
            rounds = self.get_rounds(season, tournament, df=df)
        ko_rn = self._ko_finale_round_number(df)
        is_ko_finale = (
            round_number is not None
            and ko_rn is not None
            and int(round_number) == int(ko_rn)
            and bool(ko_bracket.get("matches"))
        )
        with bench.step("leaderboard"):
            lb_table = self.get_leaderboard_table(
                season, tournament, round_number, df=df, ko_bracket=ko_bracket
            )
        lb_scratch = lb_table
        placements = list(ko_bracket.get("placements") or [])
        if (
            round_number is None
            and ko_rn is not None
            and ko_bracket.get("matches")
            and placements
            and bool(lb_table.data)
        ):
            with bench.step("leaderboard_ko_integrate"):
                lb_table = self._integrate_ko_into_total_leaderboard(
                    lb_table, ko_bracket, df, season, tournament
                )

        ko_excl = {
            self._ko_norm_name(self._ko_strip_no_show_suffix(str(p.get("player", "") or ""))) for p in placements
        }
        ko_excl.discard("")

        with bench.step("summary_cards"):
            cards = self.get_summary_cards(
                season,
                tournament,
                round_number=round_number,
                top_n=top_n,
                df=df,
                ko_bracket=ko_bracket,
                rounds=rounds,
            ).get("cards", [])

        payload: Dict[str, Any] = {
            "cards": cards,
            "leaderboard": lb_table.to_dict(),
            "rounds": rounds,
            "ko_bracket": ko_bracket,
            "tournament_gender": self._tournament_gender_key(tournament),
            "is_ko_finale_round": is_ko_finale,
            "ko_finale_round_number": ko_rn,
        }

        with bench.step("round_results"):
            payload["round_results"] = self.get_round_results_table(
                season, tournament, round_number, df=df
            ).to_dict()

        with bench.step("best_efforts"):
            payload["best_efforts"] = self.get_best_efforts(
                season, tournament, round_number=round_number, top_n=top_n, df=df
            )

        cfg_cut = self._ko_qualifying_cut_pair(season, tournament)
        if (
            round_number is None
            and ko_rn is not None
            and cfg_cut
            and ko_bracket.get("matches")
            and bool(lb_scratch.data)
        ):
            with bench.step("leaderboard_post_qualification"):
                _, crank = cfg_cut
                base_pq = self._table_data_keep_rows_min_place(lb_scratch, crank + 1)
                payload["leaderboard_post_qualification"] = (
                    self._table_data_exclude_normalized_player_keys(base_pq, ko_excl).to_dict()
                )
            with bench.step("round_results_ko"):
                payload["round_results_ko"] = self.get_round_results_table(
                    season, tournament, ko_rn, df=df
                ).to_dict()

        with bench.step("field_progress"):
            field_progress = self.get_field_progress(season, tournament, df=df)
        payload["field_progress"] = self._field_progress_public(field_progress)

        bench.report()
        return payload

    def get_player_section(self, season: str, tournament: str, player: str) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        ko_bracket = self._build_ko_bracket_payload(season, tournament, df=df)
        ko_place = self._ko_placement_for_player(ko_bracket, player)

        progress = self.get_player_progress_series(
            season, tournament, player, df=df, include_field=False
        )
        pos_series = list(progress.get("position_series") or [])
        if ko_place is not None and pos_series:
            pos_series = pos_series[:]
            pos_series[-1] = ko_place
        progress_out = {**progress, "position_series": pos_series}

        player_df = df[df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())]
        player_club = None
        if not player_df.empty and Columns.club in player_df.columns:
            club_vals = player_df[Columns.club].dropna().astype(str).tolist()
            player_club = club_vals[0] if club_vals else None
        avg_series = progress_out.get("avg_series", []) or []
        labels = progress_out.get("labels", []) or []

        played_avgs = [v for v in avg_series if v is not None]
        avg_value = round(float(played_avgs[-1]), 2) if played_avgs else None
        final_position = int(pos_series[-1]) if pos_series else None
        best_position = None
        best_position_game = None
        if pos_series:
            best_position = int(min(pos_series))
            try:
                best_idx = pos_series.index(best_position)
                best_position_game = labels[best_idx] if best_idx < len(labels) else None
            except ValueError:
                best_position_game = None

        if not self._ko_player_in_ko_matches(ko_bracket, player):
            ko_for_player = self._ko_bracket_empty_payload(season, tournament)
        else:
            ko_for_player = {**self._ko_bracket_with_highlights(ko_bracket, player), "focus_player": str(player).strip()}
        player_card_layout = self._resolve_player_card_layout(season, tournament)
        field_progress = self.get_field_progress(season, tournament, df=df)
        return {
            "player": player,
            "player_club": player_club,
            "player_card_layout": player_card_layout,
            "round_table": self.get_player_round_table(season, tournament, player, df=df).to_dict(),
            "best_efforts": self.get_player_best_efforts(season, tournament, player, df=df),
            "progress_series": progress_out,
            "field_progress": self._field_progress_public(field_progress),
            "summary": {
                "average": avg_value,
                "best_position": best_position,
                "best_position_game": best_position_game,
                "final_position": final_position,
            },
            "ko_bracket": ko_for_player,
        }

    def list_tournament_events(
        self,
        season: Optional[str] = None,
        tournament: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        from data_access.competition_schema import competition_event_column

        event_col = competition_event_column(df)
        if df.empty or not event_col or Columns.season not in df.columns:
            return []
        pairs = df[[Columns.season, event_col]].dropna().drop_duplicates()
        out: List[Dict[str, str]] = []
        for _, row in pairs.iterrows():
            season_label = str(row[Columns.season]).strip()
            tournament_label = str(row[event_col]).strip()
            if season_label and tournament_label:
                out.append(
                    {
                        "season": season_label,
                        "tournament": tournament_label,
                        "tournament_group": normalize_tournament_group_name(tournament_label),
                    }
                )
        out.sort(key=lambda item: (item["season"], item["tournament"]), reverse=True)
        return out

    @staticmethod
    def _table_column_fields(table: TableData) -> List[str]:
        fields: List[str] = []
        for group in table.columns:
            for col in group.columns:
                fields.append(str(col.field))
        return fields

    def _leaderboard_top_finishers(
        self,
        season: str,
        tournament: str,
        *,
        top_n: int = 3,
        df: Optional[pd.DataFrame] = None,
    ) -> List[Dict[str, Any]]:
        if df is None:
            df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return []

        ko_bracket = self._build_ko_bracket_payload(season, tournament, df=df)
        lb_table = self.get_leaderboard_table(
            season, tournament, round_number=None, df=df, ko_bracket=ko_bracket
        )
        placements = list(ko_bracket.get("placements") or [])
        ko_rn = self._ko_finale_round_number(df)
        if (
            ko_rn is not None
            and ko_bracket.get("matches")
            and placements
            and bool(lb_table.data)
        ):
            lb_table = self._integrate_ko_into_total_leaderboard(
                lb_table, ko_bracket, df, season, tournament
            )

        col_fields = self._table_column_fields(lb_table)

        def _field_index(field: str) -> Optional[int]:
            try:
                return col_fields.index(field)
            except ValueError:
                return None

        rank_i = _field_index("rank")
        player_i = _field_index("player")
        if rank_i is None or player_i is None:
            return []

        club_i = _field_index("club")
        avg_i = _field_index("total_avg")
        if avg_i is None:
            avg_i = _field_index("avg_scratch")
        if avg_i is None:
            avg_i = _field_index("avg_net")

        finishers: List[Dict[str, Any]] = []
        for row in lb_table.data[: max(top_n, 0)]:
            rank_label = str(row[rank_i]).strip()
            player_name = str(row[player_i]).strip()
            if not player_name:
                continue
            average: Optional[float] = None
            if avg_i is not None:
                try:
                    average = round(float(row[avg_i]), 1)
                except (TypeError, ValueError):
                    average = None
            club = str(row[club_i]).strip() if club_i is not None else ""
            try:
                rank_num = int(float(rank_label.split("/")[0]))
            except (TypeError, ValueError):
                rank_num = len(finishers) + 1
            finishers.append(
                {
                    "rank": rank_num,
                    "rank_label": rank_label,
                    "player": player_name,
                    "club": club or None,
                    "average": average,
                }
            )
        return finishers

    def get_tournament_podiums(
        self,
        *,
        season: Optional[str] = None,
        tournament: Optional[str] = None,
        top_n: int = 3,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(top_n or 3), 10))
        podiums: List[Dict[str, Any]] = []
        for event in self.list_tournament_events(season=season, tournament=tournament):
            season_label = event["season"]
            tournament_label = event["tournament"]
            event_df = self._get_tournament_df(season=season_label, tournament=tournament_label)
            finishers = self._leaderboard_top_finishers(
                season_label,
                tournament_label,
                top_n=limit,
                df=event_df,
            )
            podiums.append(
                {
                    "season": season_label,
                    "tournament": tournament_label,
                    "tournament_group": normalize_tournament_group_name(tournament_label),
                    "finishers": finishers,
                }
            )
        return {"top_n": limit, "podiums": podiums}

    def get_tournament_player_catalog(
        self,
        season: Optional[str] = None,
        tournament: Optional[str] = None,
    ) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty or Columns.player_name not in df.columns:
            return []
        return sorted(
            {
                str(name).strip()
                for name in df[Columns.player_name].dropna().astype(str).tolist()
                if str(name).strip()
            }
        )

    def get_player_tournament_results(
        self,
        player: str,
        *,
        season: Optional[str] = None,
        tournament: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        player_norm = str(player or "").strip()
        if not player_norm:
            return []

        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty or Columns.player_name not in df.columns:
            return []

        from data_access.competition_schema import competition_event_column

        event_col = competition_event_column(df)
        if not event_col or Columns.season not in df.columns:
            return []

        player_df = df[df[Columns.player_name].astype(str).str.strip().eq(player_norm)]
        if player_df.empty:
            return []

        events = player_df[[Columns.season, event_col]].dropna().drop_duplicates()
        results: List[Dict[str, Any]] = []
        for _, event_row in events.iterrows():
            season_label = str(event_row[Columns.season]).strip()
            tournament_label = str(event_row[event_col]).strip()
            if not season_label or not tournament_label:
                continue

            progress = self.get_player_progress_series(
                season_label,
                tournament_label,
                player_norm,
                include_field=False,
            )
            ko_bracket = self._build_ko_bracket_payload(season_label, tournament_label)
            ko_place = self._ko_placement_for_player(ko_bracket, player_norm)
            pos_series = list(progress.get("position_series") or [])
            if ko_place is not None and pos_series:
                pos_series = pos_series[:]
                pos_series[-1] = ko_place

            avg_series = [v for v in (progress.get("avg_series") or []) if v is not None]
            average = round(float(avg_series[-1]), 1) if avg_series else None
            final_position = int(pos_series[-1]) if pos_series else None

            event_player_df = player_df[
                player_df[Columns.season].astype(str).str.strip().eq(season_label)
                & player_df[event_col].astype(str).str.strip().eq(tournament_label)
            ]
            club = None
            if Columns.club in event_player_df.columns:
                club_vals = event_player_df[Columns.club].dropna().astype(str).tolist()
                club = club_vals[0].strip() if club_vals else None

            results.append(
                {
                    "season": season_label,
                    "tournament": tournament_label,
                    "tournament_group": normalize_tournament_group_name(tournament_label),
                    "position": final_position,
                    "average": average,
                    "club": club,
                }
            )

        results.sort(key=lambda item: (item["season"], item["tournament"]), reverse=True)
        return results
