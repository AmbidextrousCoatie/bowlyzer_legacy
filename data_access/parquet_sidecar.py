"""Parquet sidecar helpers for league CSV sources."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_access.dtype_normalization import normalize_legacy_dataframe_types


def parquet_sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(".parquet")


def should_load_parquet(csv_path: Path, parquet_path: Path) -> bool:
    if not parquet_path.is_file():
        return False
    if not csv_path.is_file():
        return True
    return parquet_path.stat().st_mtime_ns >= csv_path.stat().st_mtime_ns


def read_parquet_sidecar(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    return normalize_legacy_dataframe_types(df)


def write_parquet_sidecar(df: pd.DataFrame, csv_path: Path) -> Path:
    """Write ``<csv_stem>.parquet`` next to the CSV path."""
    out = parquet_sidecar_path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out
