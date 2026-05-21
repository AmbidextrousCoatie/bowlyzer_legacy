"""Pinfall aggregation helpers for league input rows.

Negative scores in source data usually mark injury or absence (see
``reconstruct_flat_csv`` team-total logic). Totals and averages use the
absolute value; per-game display keeps the signed value.
"""

from __future__ import annotations

import pandas as pd

from data_access.schema import Columns


def scores_for_totals(series: pd.Series) -> pd.Series:
    """Numeric pinfall series for sum/mean (absolute values)."""
    return pd.to_numeric(series, errors="coerce").abs()


def sum_scores(series: pd.Series) -> int:
    if series is None or len(series) == 0:
        return 0
    return int(scores_for_totals(series).sum())


def sum_scores_float(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return 0.0
    return float(scores_for_totals(series).sum())


def pinfall_for_total(value) -> float:
    """Single score cell for sum/mean accumulation."""
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num):
        return 0.0
    return float(abs(num))


def pinfall_display(value) -> int:
    """Signed pinfall for per-game table cells (injury rows stay negative)."""
    num = pd.to_numeric(value, errors="coerce")
    if pd.isna(num):
        return 0
    return int(num)


def mean_scores(series: pd.Series, round_places: int | None = None) -> float:
    if series is None or len(series) == 0:
        val = 0.0
    else:
        s = scores_for_totals(series)
        val = float(s.mean()) if s.notna().any() else 0.0
    if round_places is not None:
        return round(val, round_places)
    return val


def sum_league_points(df: pd.DataFrame) -> float:
    """Match Points + Bonus Points (legacy CSVs without bonus column use Points only)."""
    if df is None or df.empty:
        return 0.0
    total = pd.to_numeric(df[Columns.points], errors="coerce").fillna(0).sum()
    if Columns.bonus_points in df.columns:
        total += pd.to_numeric(df[Columns.bonus_points], errors="coerce").fillna(0).sum()
    return float(total)


def league_points_cell(row: pd.Series) -> float:
    """Single-row league points (match + weekly placement bonus)."""
    pts = pd.to_numeric(row.get(Columns.points), errors="coerce")
    pts = 0.0 if pd.isna(pts) else float(pts)
    if Columns.bonus_points in row.index:
        bonus = pd.to_numeric(row.get(Columns.bonus_points), errors="coerce")
        if not pd.isna(bonus):
            pts += float(bonus)
    return pts
