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

# KO-Finale last cluster: best-of-3 pin games vs two-game scratch total (see database/data/tournament_ko_config.json).
KO_FINALE_SERIES_BO3 = "bo3_pins"
KO_FINALE_SERIES_SCRATCH_2G = "scratch_total_2g"

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

        if tournament and Columns.event_name in df.columns:
            tournament_norm = str(tournament).strip()
            df = df[df[Columns.event_name].astype(str).str.strip().eq(tournament_norm)]

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

    def get_tournaments(self, season: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=None)
        if df.empty or Columns.event_name not in df.columns:
            return []
        return sorted([x for x in df[Columns.event_name].dropna().astype(str).unique().tolist() if x.strip()])

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

        # Stage winner is specific to selected stage (or latest stage when none selected).
        stage_round_number = round_number if round_number is not None else latest_round.get("round_number")

        # Helper: total games up to a round (for cumulative averages).
        def _games_upto_round(target_round: Optional[int]) -> int:
            if target_round is None or Columns.round_number not in df.columns or Columns.game_number not in df.columns:
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

        # Tournament leader should reflect cumulative totals up to the selected stage.
        # If no stage is selected, use the latest available stage as the cutoff.
        tournament_leader = None
        tournament_leader_avg = None
        if stage_round_number is not None:
            cumulative_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(stage_round_number))].copy()
            if not cumulative_df.empty:
                cumulative_df[Columns.score] = pd.to_numeric(cumulative_df[Columns.score], errors="coerce").fillna(0)
                tournament_totals = (
                    cumulative_df.groupby([Columns.player_name], dropna=False)[Columns.score]
                    .sum()
                    .reset_index(name="total_score")
                    .sort_values(by=["total_score", Columns.player_name], ascending=[False, True])
                    .reset_index(drop=True)
                )
                if not tournament_totals.empty:
                    tournament_leader = tournament_totals.iloc[0]
                    leader_name = str(tournament_leader[Columns.player_name])
                    leader_games = int(
                        self._played_games_count(
                            cumulative_df[cumulative_df[Columns.player_name].astype(str).eq(leader_name)][Columns.score]
                        )
                    )
                    if leader_games > 0:
                        tournament_leader_avg = round(float(tournament_leader["total_score"]) / leader_games, 1)

        # Stage winner remains stage-specific for the selected/latest stage:
        # winner is determined from stage-only scores (not cumulative totals).
        stage_winner = None
        stage_winner_avg = None
        if stage_round_number is not None:
            stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(stage_round_number))].copy()
            stage_df[Columns.score] = pd.to_numeric(stage_df[Columns.score], errors="coerce").fillna(0)
            if not stage_df.empty:
                grouped = (
                    stage_df.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .reset_index(name="total_score")
                    .sort_values(by=["total_score", Columns.player_name], ascending=[False, True])
                    .reset_index(drop=True)
                )
                if not grouped.empty:
                    winner_name = str(grouped.iloc[0][Columns.player_name])
                    winner_total = float(grouped.iloc[0]["total_score"])
                    stage_games = int(
                        self._played_games_count(
                            stage_df[stage_df[Columns.player_name].astype(str).eq(winner_name)][Columns.score]
                        )
                    )
                    stage_winner = {"player": winner_name, "total_score": winner_total}
                    if stage_games > 0:
                        stage_winner_avg = round(winner_total / stage_games, 1)

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
            self._build_cut_line_card(df, season, tournament, card_round) if card_round is not None else None
        )
        if tournament_leader is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
            subtitle = f"{int(tournament_leader['total_score'])} pins"
            if tournament_leader_avg is not None:
                subtitle = f"{subtitle} (\u2300{tournament_leader_avg:.1f})"
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
        if stage_winner is not None and stage_round_number is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
            stage_name = (
                latest_round.get("round_name")
                if round_number is None
                else str(scope_df[Columns.round_name].dropna().iloc[0]) if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                else f"Round {stage_round_number}"
            )
            stage_subtitle = f"{stage_name}: {int(stage_winner['total_score'])} pins"
            if stage_winner_avg is not None:
                # Stage Winner is stage-local: stage total divided by games in this stage.
                stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(stage_round_number))].copy()
                stage_df[Columns.score] = pd.to_numeric(stage_df[Columns.score], errors="coerce").fillna(0)
                stage_winner_name = str(stage_winner["player"])
                stage_total = float(stage_winner["total_score"])
                stage_games = int(stage_df[stage_df[Columns.player_name].astype(str).eq(stage_winner_name)][Columns.score].count())
                stage_games = int(
                    self._played_games_count(
                        stage_df[stage_df[Columns.player_name].astype(str).eq(stage_winner_name)][Columns.score]
                    )
                )
                if stage_games > 0:
                    stage_winner_avg = round(stage_total / stage_games, 1)
                stage_subtitle = f"{stage_subtitle} (\u2300{stage_winner_avg:.1f})"
            cards.append(
                {
                    "title": "Stage Winner",
                    "value": stage_winner["player"],
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
        """Cumulative scratch-pin rank through ``through_round`` (overall-total / cut ladder)."""
        if df.empty:
            return {}
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        if through_round is not None and Columns.round_number in work.columns:
            work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
            work = work[work[Columns.round_number].le(float(through_round))].copy()
        if work.empty:
            return {}
        group_keys, id_col = self._leaderboard_group_keys(work, include_club=include_club)
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)
        totals = (
            work.groupby(group_keys, dropna=False)[Columns.score]
            .sum()
            .reset_index(name="total_pins")
        )
        totals = totals.sort_values(
            by=["total_pins", Columns.player_name], ascending=[False, True]
        ).reset_index(drop=True)
        totals["rank"] = totals["total_pins"].rank(method="min", ascending=False).astype(int)
        out: Dict[Tuple[Any, ...], int] = {}
        for _, row in totals.iterrows():
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
                    by=["round_net", Columns.player_name], ascending=[False, True]
                ).reset_index(drop=True)
                leaderboard["rank"] = leaderboard["round_net"].rank(method="min", ascending=False).astype(int)
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
                base_columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))

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
            default_sort_field = "round_net" if use_hc_round else "total_score"
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
                by=["avg_net", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)
            pivot["rank"] = pivot["avg_net"].rank(method="min", ascending=False).astype(int)
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
            avg_sc = i18n_service.get_text("ui.tournament.lb_avg_scratch")
            tot_n = i18n_service.get_text("ui.tournament.lb_total_net")
            avg_n = i18n_service.get_text("ui.tournament.lb_avg_net")
            spieler_columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0, frozen="left"),
                Column(title=i18n_service.get_text("player"), field="player", width="132px", align="left", frozen="left"),
                Column(title=hcp_short, field="handicap_display", width="100px", align="center", tooltip=hcp_tip),
            ]
            if include_club:
                spieler_columns.append(
                    Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left")
                )
            scratch_columns: List[Column] = []
            for rn in round_numbers:
                title = round_name_map.get(rn) or f"Round {rn}"
                scratch_columns.append(
                    Column(title=title, field=f"round_{rn}", width="94px", align="center", decimal_places=0)
                )
            scratch_columns.extend(
                [
                    Column(title=tot_sc, field="total_score", width="100px", align="center", decimal_places=0),
                    Column(title=avg_sc, field="avg_scratch", width="100px", align="center", decimal_places=1),
                ]
            )
            net_columns = [
                Column(title=tot_n, field="total_net", width="100px", align="center", decimal_places=0),
                Column(title=avg_n, field="avg_net", width="100px", align="center", decimal_places=1),
            ]
            grouped_columns = [
                ColumnGroup(
                    title=sp_grp,
                    style={"backgroundColor": "#f8f9fa"},
                    header_style={"fontWeight": "bold"},
                    columns=spieler_columns,
                ),
                ColumnGroup(
                    title=sc_grp,
                    style={"backgroundColor": get_theme_color("surface_alt")},
                    header_style={"fontWeight": "bold"},
                    columns=scratch_columns,
                ),
                ColumnGroup(
                    title=nt_grp,
                    style={"backgroundColor": "#f0f4f8"},
                    header_style={"fontWeight": "bold"},
                    columns=net_columns,
                ),
            ]
            default_sort_field = "avg_net"
            table_metadata: Dict[str, Any] = {"leaderboard_mode": "scratch_net_handicap"}
        else:
            columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0, frozen="left"),
                Column(title=i18n_service.get_text("player"), field="player", width="132px", align="left", frozen="left"),
            ]
            if include_club:
                columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))
            for rn in round_numbers:
                title = round_name_map.get(rn) or f"Round {rn}"
                columns.append(Column(title=title, field=f"round_{rn}", width="94px", align="center", decimal_places=0))
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
        # Gesamtwertung cut shading: cut rank from CSV at end of qualifying; row colors by
        # cumulative scratch pins through qualifying (overall total), not single-stage results.
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
                for rn in round_numbers:
                    entry.append(int(row.get(rn, 0)))
                entry.append(int(row.get("total_score", 0)))
                entry.append(float(row.get("avg_scratch", 0.0)))
                entry.append(int(row.get("total_net", 0)))
                entry.append(float(row.get("avg_net", 0.0)))
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

                pivot["overall_rank"] = pivot["stage_net"].rank(method="min", ascending=False).astype(int)

            pivot = pivot.sort_values(
                by=["overall_rank", "round_total", Columns.player_name],
                ascending=[True, False, True],
            ).reset_index(drop=True)

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
                rank_cols.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))

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

            default_sort_field = "stage_net" if use_hc_rr else "overall_rank"
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

        rows = []
        running_total = 0
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
            round_total = int(round_player[Columns.score].sum())
            round_games = int(self._played_games_count(round_player[Columns.score]))
            round_avg = round(round_total / max(round_games, 1), 1)

            # Rank within round by total pins.
            round_totals = (
                round_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
            )
            round_rank = int(round_totals.rank(method="min", ascending=False).get(player, float("nan"))) if player in round_totals.index else None

            running_total += round_total
            running_games += round_games
            cum_avg = round(running_total / max(running_games, 1), 1)

            # Cumulative rank up to current round.
            upto_all = all_df[all_df[Columns.round_number].le(float(rn))].copy()
            cum_totals = (
                upto_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
            )
            cum_rank = int(cum_totals.rank(method="min", ascending=False).get(player, float("nan"))) if player in cum_totals.index else None

            row = [round_name_map.get(rn, f"Round {rn}")]
            for g in game_cols:
                row.append(int(player_game_scores.get(g, 0)) if g in player_game_scores else "")
            row.extend(
                [
                    round_total,
                    round_avg,
                    round_rank if round_rank is not None else "",
                    running_total,
                    cum_avg,
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
                "participant_count": 0,
                "cut_line_series": [],
                "cut_lines_avg_dynamic": {},
                "player_rank_series": {},
            }

        all_df = df.copy()
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
        cfg_span = self._ko_qualifying_cut_span_config(season, tournament)
        if cfg_span:
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

            in_cut_span = cfg_span is None or (
                int(cfg_span["first_round"]) <= rn <= int(cfg_span["through_round"])
            )
            cut_avg_game: Optional[float] = last_cut_avg
            if in_cut_span:
                eligible = _field_progress_eligible_at_snapshot(
                    field_players, rn, g, round_lengths, player_round_games
                )
                pace = _pace_cut_from_cumulative(eligible, cum_pins, cum_games, cut_rank)
                if pace is not None:
                    last_cut_avg, last_cut_pos = pace
                    cut_avg_game = last_cut_avg

            for cut_rn in cut_rounds_sorted:
                dynamic_cut_series[cut_rn].append(cut_avg_game if rn == cut_rn else None)

            length = round_length_map.get(rn, 0)
            if g == length - 1:
                cut_pos_round = self._resolved_cut_position_for_round(
                    all_df, int(rn), season, tournament
                )
                if in_cut_span and last_cut_avg is not None:
                    cut_lines_avg.append(last_cut_avg)
                if cut_pos_round is not None:
                    cut_lines_position.append(cut_pos_round)
                elif in_cut_span and last_cut_pos is not None:
                    cut_lines_position.append(last_cut_pos)

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
                    player_game_pins[int(g_idx)] = _arith_round_int(float(grp[Columns.score].sum()))

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

    def _ko_config_entry(self, season: str, tournament: str) -> Dict[str, Any]:
        raw = self._load_tournament_ko_config()
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        return block if isinstance(block, dict) else {}

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

    def _ko_qualifying_cut_pair(self, season: str, tournament: str) -> Optional[tuple[int, int]]:
        """
        Optional (round_number, cut_rank) from tournament_ko_config.json when the export has no Cut Line column.
        """
        block = self._ko_config_entry(season, tournament)
        rank = self._ko_optional_int(block.get("ko_qualifying_cut_rank"))
        if rank is None or rank < 1:
            return None
        rnd = self._ko_optional_int(block.get("ko_qualifying_cut_round"))
        if rnd is None or rnd < 1:
            rnd = 1
        return (rnd, rank)

    def _ko_qualifying_cut_span_config(self, season: str, tournament: str) -> Optional[Dict[str, int]]:
        """
        Qualifying cut rank applied from first_round through through_round (inclusive) for charts and shading
        when the CSV has no Cut Line. Optional ko_qualifying_cut_through_round (default: first round only).
        """
        block = self._ko_config_entry(season, tournament)
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

    @staticmethod
    def _cut_score_column_for_snapshot(snap: pd.DataFrame) -> Optional[str]:
        if Columns.cumulative_score not in snap.columns:
            return None
        score_col = Columns.cumulative_score
        if "Cut Basis" in snap.columns:
            basis_vals = [str(x).strip().lower() for x in snap["Cut Basis"].dropna().tolist() if str(x).strip()]
            if basis_vals and basis_vals[0] == "overall_total" and "Overall Cumulative Score" in snap.columns:
                score_col = "Overall Cumulative Score"
        return score_col

    @staticmethod
    def _cut_position_from_cumulative_snapshot(snap: pd.DataFrame, cut_score: float) -> Optional[int]:
        """
        Map export cut-line pin total to overall place after the stage ends.

        Uses cumulative totals in the last game snapshot — not per-game stage_rank.
        """
        score_col = TournamentService._cut_score_column_for_snapshot(snap)
        if score_col is None or Columns.player_name not in snap.columns:
            return None
        scores = pd.to_numeric(snap[score_col], errors="coerce")
        work = snap.assign(_cs=scores).dropna(subset=["_cs"])
        if work.empty:
            return None
        work = work.sort_values(by="_cs", ascending=False)
        work["_cum_rank"] = work["_cs"].rank(method="min", ascending=False).astype(int)
        at_cut = work[work["_cs"].eq(float(cut_score))]
        if not at_cut.empty:
            return int(at_cut["_cum_rank"].min())
        ge = work[work["_cs"].ge(float(cut_score))]
        if not ge.empty:
            return int(ge["_cum_rank"].max())
        return None

    @staticmethod
    def _cut_player_from_cumulative_snapshot(snap: pd.DataFrame, cut_score: float) -> Optional[str]:
        score_col = TournamentService._cut_score_column_for_snapshot(snap)
        if score_col is None or Columns.player_name not in snap.columns:
            return None
        scores = pd.to_numeric(snap[score_col], errors="coerce")
        work = snap.assign(_cs=scores).dropna(subset=["_cs"])
        if work.empty:
            return None
        work = work.sort_values(by="_cs", ascending=False)
        work["_cum_rank"] = work["_cs"].rank(method="min", ascending=False).astype(int)
        at_cut = work[work["_cs"].eq(float(cut_score))]
        if at_cut.empty:
            return None
        row = at_cut.sort_values(by="_cum_rank", ascending=False).iloc[0]
        name = str(row.get(Columns.player_name, "") or "").strip()
        return name or None

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

    def _player_cumulative_pins_through(
        self, df: pd.DataFrame, player_name: str, through_round: int
    ) -> Optional[float]:
        if df.empty or Columns.round_number not in df.columns:
            return None
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
        scope = work[work[Columns.round_number].le(float(through_round))].copy()
        scope = scope[scope[Columns.player_name].astype(str).eq(str(player_name).strip())]
        if scope.empty:
            return None
        return float(scope[Columns.score].sum())

    def _build_cut_line_card(
        self, df: pd.DataFrame, season: str, tournament: str, target_round: int
    ) -> Optional[Dict[str, Any]]:
        """
        Cut-Line summary card for the selected stage.

        Player matches leaderboard cut shading: cumulative scratch rank at end of
        ``target_round``, not stage_rank from an earlier qualifying round.
        """
        cut_pos = self._resolved_cut_position_for_round(df, int(target_round), season, tournament)
        include_club = self._has_any_club_value(df)
        cut_player: Optional[str] = None
        cut_score: Optional[float] = None

        if Columns.cut_line in df.columns and Columns.game_number in df.columns:
            stage_df = df[
                pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(target_round))
            ].copy()
            if not stage_df.empty:
                max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
                snap = stage_df[
                    pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)
                ].copy()
                cut_vals = pd.to_numeric(snap[Columns.cut_line], errors="coerce").dropna()
                if not cut_vals.empty:
                    cut_score = float(cut_vals.iloc[0])
                    cut_player = self._cut_player_from_cumulative_snapshot(snap, cut_score)

        if cut_player is None and cut_pos is not None:
            rank_map = self._leaderboard_rank_map_qualifying_total_pins(
                df, include_club=include_club, through_round=int(target_round)
            )
            for key, rank in rank_map.items():
                if rank == cut_pos:
                    cut_player = str(key[0]).strip()
                    break
            if cut_player:
                pins = self._player_cumulative_pins_through(df, cut_player, int(target_round))
                if pins is not None:
                    cut_score = pins

        if not cut_player:
            return None

        games_upto = self._games_upto_round_in_df(df, int(target_round))
        if cut_score is not None and games_upto > 0:
            cut_display = f"{int(cut_score)} pins (\u2300{(cut_score / games_upto):.1f})"
        elif cut_score is not None:
            cut_display = f"{int(cut_score)} pins"
        else:
            cut_display = ""

        return {
            "title": "Cut Line",
            "value": cut_player,
            "subtitle": cut_display,
            "type": "stat",
        }

    def _resolved_cut_position_for_round(
        self, source_df: pd.DataFrame, target_round: int, season: str, tournament: str
    ) -> Optional[int]:
        """Prefer CSV-derived cut rank; fall back to ko_qualifying_cut_* config for the configured round."""

        def _from_csv() -> Optional[int]:
            if (
                source_df.empty
                or Columns.cut_line not in source_df.columns
                or Columns.round_number not in source_df.columns
                or Columns.game_number not in source_df.columns
            ):
                return None
            stage_df = source_df[pd.to_numeric(source_df[Columns.round_number], errors="coerce").eq(float(target_round))].copy()
            if stage_df.empty:
                return None
            max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
            snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
            if snap.empty:
                return None
            cut_vals = pd.to_numeric(snap[Columns.cut_line], errors="coerce").dropna()
            if cut_vals.empty:
                return None
            cut_score = float(cut_vals.iloc[0])

            pos = self._cut_position_from_cumulative_snapshot(snap, cut_score)
            if pos is not None:
                return pos

            if Columns.score in snap.columns and Columns.player_name in snap.columns:
                work = snap.copy()
                work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
                ranked = work.groupby(Columns.player_name, dropna=False)[Columns.score].sum().sort_values(ascending=False)
                rank_series = ranked.rank(method="min", ascending=False)
                candidates = rank_series[ranked.ge(cut_score)]
                if not candidates.empty:
                    return int(candidates.max())
            return None

        base = _from_csv()
        if base is not None:
            return base
        span = self._ko_qualifying_cut_span_config(season, tournament)
        if span is not None and int(span["first_round"]) <= int(target_round) <= int(span["through_round"]):
            return int(span["rank"])
        return None

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
        return {
            "player": player,
            "player_club": player_club,
            "player_card_layout": player_card_layout,
            "round_table": self.get_player_round_table(season, tournament, player, df=df).to_dict(),
            "best_efforts": self.get_player_best_efforts(season, tournament, player, df=df),
            "progress_series": progress_out,
            "summary": {
                "average": avg_value,
                "best_position": best_position,
                "best_position_game": best_position_game,
                "final_position": final_position,
            },
            "ko_bracket": ko_for_player,
        }
