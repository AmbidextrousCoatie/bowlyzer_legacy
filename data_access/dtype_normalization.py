from __future__ import annotations

from typing import Dict, List

import pandas as pd

from data_access.schema import Columns


BOOL_TRUE_TOKENS = {"true", "1", "yes", "y", "on"}
BOOL_FALSE_TOKENS = {"false", "0", "no", "n", "off", ""}


def _to_boolean_nullable(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    mapped = normalized.map(
        lambda v: True if v in BOOL_TRUE_TOKENS else (False if v in BOOL_FALSE_TOKENS else pd.NA)
    )
    return mapped.astype("boolean")


def normalize_legacy_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize core dtypes for league/tournament legacy-style CSVs.

    Strategy:
    - Keep text/identifier columns as strings.
    - Coerce well-known numeric columns to nullable numeric dtypes.
    - Coerce bool-like flags to pandas nullable boolean.
    """
    if df is None or df.empty:
        return df

    out = df.copy()

    numeric_int_cols = [
        Columns.week,
        Columns.round_number,
        Columns.match_number,
        Columns.players_per_team,
        Columns.position,
        Columns.game_number,
        Columns.player_id,
    ]
    if Columns.bonus_points not in out.columns:
        out[Columns.bonus_points] = "0"

    numeric_float_cols = [
        Columns.score,
        Columns.points,
        Columns.bonus_points,
        Columns.handicap,
        Columns.apriori_average,
        Columns.handicap_reference,
        Columns.stage_rank,
        Columns.cumulative_score,
        Columns.cut_line,
    ]
    bool_cols = [Columns.input_data, Columns.computed_data]

    for col in numeric_int_cols:
        if col in out.columns:
            numeric = pd.to_numeric(out[col], errors="coerce")
            out[col] = numeric.round(0).astype("Int64")

    for col in numeric_float_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Float64")

    for col in bool_cols:
        if col in out.columns:
            out[col] = _to_boolean_nullable(out[col])

    return out


def series_to_legacy_str(series: pd.Series) -> pd.Series:
    """Stringify a column for legacy CSV row dicts (nullable Int64-safe)."""
    if pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_extension_array_dtype(
        series.dtype
    ):
        return series.astype("string").fillna("").str.strip()
    return series.fillna("").astype(str).str.strip()


def dataframe_to_str_dict_records(df: pd.DataFrame) -> List[Dict[str, str]]:
    """Convert a normalized dataframe to list-of-dicts with string values (hybrid CSV export)."""
    if df is None or df.empty:
        return []
    frame = df.copy()
    for col in frame.columns:
        frame[col] = series_to_legacy_str(frame[col])
    return [{str(k): str(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]


def summarize_type_normalization(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """
    Optional helper for diagnostics: report NaN/null counts for normalized core fields.
    """
    if df is None or df.empty:
        return {}
    summary: Dict[str, Dict[str, int]] = {}
    for col in df.columns:
        nulls = int(df[col].isna().sum())
        summary[col] = {"null_count": nulls}
    return summary
