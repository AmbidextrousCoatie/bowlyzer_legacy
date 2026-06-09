"""Published competition row schema v2 helpers (see docs/planning/DATA_PIPELINE_PLAN.md §2.6)."""

from __future__ import annotations

import re

import pandas as pd

from data_access.schema import Columns

LEAGUE_EVENT_TYPE = "league"
TOURNAMENT_EVENT_TYPE = "tournament"

_LEGACY_LEAGUE_COLUMN = "League"
_LEGACY_EVENT_NAME_COLUMN = "Event Name"


def competition_event_column(df: pd.DataFrame) -> str | None:
    """Return the best available competition label column (v2 ``Event`` or legacy names)."""
    if df is None or df.empty:
        return None
    for col in (Columns.event, _LEGACY_EVENT_NAME_COLUMN, _LEGACY_LEAGUE_COLUMN):
        if col in df.columns:
            return col
    return None


def club_name_from_team(team_name: object) -> str:
    """Strip trailing team number from a full team label (e.g. ``Donaubowler Regensburg 2``)."""
    text = str(team_name or "").strip()
    if not text:
        return ""
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", text)
    if not match:
        return text
    return str(match.group(1) or "").strip()


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().eq("")


def _tournament_row_mask(df: pd.DataFrame) -> pd.Series:
    if Columns.event_type not in df.columns:
        return pd.Series(False, index=df.index)
    return (
        df[Columns.event_type].fillna("").astype(str).str.strip().str.lower().eq(TOURNAMENT_EVENT_TYPE)
    )


def _is_missing_flag(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.isna()
    return series.isna() | _blank_mask(series)


def _set_flag_values(series: pd.Series, mask: pd.Series, *, value: bool) -> pd.Series:
    out = series.copy()
    if mask.any():
        if pd.api.types.is_bool_dtype(out.dtype):
            out.loc[mask] = value
        else:
            out.loc[mask] = "True" if value else "False"
    return out


def _ensure_tournament_player_row_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tournament per-game rows count as player input rows (legacy hybrid set these at concat).

    Without ``Input Data`` / ``Computed Data``, Spieler filters drop all tournament games
    after runtime merge with league Parquet.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    tmask = _tournament_row_mask(out)
    if not tmask.any():
        return out

    if Columns.input_data not in out.columns:
        out[Columns.input_data] = pd.Series([""] * len(out), index=out.index, dtype="object")
    if Columns.computed_data not in out.columns:
        out[Columns.computed_data] = pd.Series([""] * len(out), index=out.index, dtype="object")

    missing_input = tmask & _is_missing_flag(out[Columns.input_data])
    out[Columns.input_data] = _set_flag_values(out[Columns.input_data], missing_input, value=True)

    missing_computed = tmask & _is_missing_flag(out[Columns.computed_data])
    out[Columns.computed_data] = _set_flag_values(
        out[Columns.computed_data], missing_computed, value=False
    )

    return out


def apply_league_competition_schema_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform league rows to published core schema v2.

    - ``Event Type`` = ``league``
    - ``Event`` from legacy ``League`` (``League`` column dropped)
    - ``Club`` from ``Team`` when empty
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    league_col = None
    if _LEGACY_LEAGUE_COLUMN in out.columns:
        league_col = _LEGACY_LEAGUE_COLUMN
    elif Columns.league_name in out.columns and Columns.league_name != Columns.event:
        league_col = Columns.league_name

    if Columns.event not in out.columns:
        if league_col is not None:
            out[Columns.event] = out[league_col]
        else:
            out[Columns.event] = ""
    elif league_col is not None:
        missing_event = _blank_mask(out[Columns.event])
        out.loc[missing_event, Columns.event] = out.loc[missing_event, league_col]

    if league_col is not None and league_col != Columns.event and league_col in out.columns:
        out = out.drop(columns=[league_col])

    if Columns.event_type not in out.columns:
        out[Columns.event_type] = LEAGUE_EVENT_TYPE
    else:
        missing_type = _blank_mask(out[Columns.event_type])
        out.loc[missing_type, Columns.event_type] = LEAGUE_EVENT_TYPE

    if Columns.team_name in out.columns:
        if Columns.club not in out.columns:
            out[Columns.club] = out[Columns.team_name].map(club_name_from_team)
        else:
            missing_club = _blank_mask(out[Columns.club])
            out.loc[missing_club, Columns.club] = (
                out.loc[missing_club, Columns.team_name].map(club_name_from_team)
            )

    return out


def apply_tournament_competition_schema_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform tournament rows to published core schema v2.

    - ``Event Type`` = ``tournament``
    - ``Event`` from legacy ``Event Name`` (``Event Name`` column dropped)
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    event_name_col = None
    if _LEGACY_EVENT_NAME_COLUMN in out.columns:
        event_name_col = _LEGACY_EVENT_NAME_COLUMN
    elif Columns.event_name in out.columns and Columns.event_name != Columns.event:
        event_name_col = Columns.event_name

    if Columns.event not in out.columns:
        if event_name_col is not None:
            out[Columns.event] = out[event_name_col]
        else:
            out[Columns.event] = ""
    elif event_name_col is not None:
        missing_event = _blank_mask(out[Columns.event])
        out.loc[missing_event, Columns.event] = out.loc[missing_event, event_name_col]

    if event_name_col is not None and event_name_col != Columns.event and event_name_col in out.columns:
        out = out.drop(columns=[event_name_col])

    if Columns.event_type not in out.columns:
        out[Columns.event_type] = TOURNAMENT_EVENT_TYPE
    else:
        missing_type = _blank_mask(out[Columns.event_type])
        out.loc[missing_type, Columns.event_type] = TOURNAMENT_EVENT_TYPE

    return _ensure_tournament_player_row_flags(out)


def ensure_competition_core_columns_for_read(df: pd.DataFrame) -> pd.DataFrame:
    """
    Backward-compat for Parquet/CSV published before schema v2.

    Maps legacy ``League`` / ``Event Name`` → ``Event`` and fills missing core fields.
    Legacy source columns are kept when present so old tools can still read them.
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    has_legacy_league = _LEGACY_LEAGUE_COLUMN in out.columns
    has_legacy_event_name = _LEGACY_EVENT_NAME_COLUMN in out.columns
    has_event = Columns.event in out.columns

    if has_legacy_event_name and not has_event:
        out[Columns.event] = out[_LEGACY_EVENT_NAME_COLUMN]
        has_event = True
    elif has_legacy_event_name and has_event:
        missing_event = _blank_mask(out[Columns.event])
        out.loc[missing_event, Columns.event] = out.loc[missing_event, _LEGACY_EVENT_NAME_COLUMN]

    if has_legacy_league and not has_event:
        out[Columns.event] = out[_LEGACY_LEAGUE_COLUMN]
        has_event = True
    elif has_legacy_league and has_event:
        missing_event = _blank_mask(out[Columns.event])
        out.loc[missing_event, Columns.event] = out.loc[missing_event, _LEGACY_LEAGUE_COLUMN]

    if Columns.event_type not in out.columns:
        if has_legacy_league:
            out[Columns.event_type] = LEAGUE_EVENT_TYPE
        elif has_legacy_event_name:
            out[Columns.event_type] = TOURNAMENT_EVENT_TYPE
        elif Columns.team_name in out.columns and Columns.week in out.columns:
            out[Columns.event_type] = LEAGUE_EVENT_TYPE
        elif has_event:
            out[Columns.event_type] = TOURNAMENT_EVENT_TYPE
    else:
        missing_type = _blank_mask(out[Columns.event_type])
        if missing_type.any():
            if has_legacy_league:
                out.loc[missing_type, Columns.event_type] = LEAGUE_EVENT_TYPE
            elif has_legacy_event_name:
                out.loc[missing_type, Columns.event_type] = TOURNAMENT_EVENT_TYPE
            elif Columns.team_name in out.columns and Columns.week in out.columns:
                out.loc[missing_type, Columns.event_type] = LEAGUE_EVENT_TYPE

    if Columns.team_name in out.columns and Columns.club not in out.columns:
        out[Columns.club] = out[Columns.team_name].map(club_name_from_team)
    elif Columns.team_name in out.columns and Columns.club in out.columns:
        missing_club = _blank_mask(out[Columns.club])
        out.loc[missing_club, Columns.club] = (
            out.loc[missing_club, Columns.team_name].map(club_name_from_team)
        )

    return _ensure_tournament_player_row_flags(out)


# Backward-compatible alias
ensure_league_core_columns_for_read = ensure_competition_core_columns_for_read
