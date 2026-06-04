"""Parquet-first storage for published league/tournament datasets.

Config and paths still use the historical ``*.csv`` names; runtime loads
``<stem>.parquet`` when present and falls back to CSV only if Parquet is missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pandas as pd

from data_access.dtype_normalization import normalize_legacy_dataframe_types


def parquet_sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(".parquet")


def data_file_exists(logical_csv_path: Path) -> bool:
    """True when Parquet or the logical CSV path exists on disk."""
    logical = Path(logical_csv_path)
    if parquet_sidecar_path(logical).is_file():
        return True
    return logical.is_file()


def resolve_load_path(logical_csv_path: Path) -> Path:
    """Path passed to readers/cache keys: Parquet when present, else CSV."""
    logical = Path(logical_csv_path).resolve()
    parquet_path = parquet_sidecar_path(logical)
    if parquet_path.is_file():
        return parquet_path.resolve()
    return logical


def should_load_parquet(csv_path: Path, parquet_path: Path) -> bool:
    return parquet_path.is_file()


def read_parquet_sidecar(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    return normalize_legacy_dataframe_types(df)


def write_parquet_sidecar(df: pd.DataFrame, logical_csv_path: Path) -> Path:
    """Write ``<csv_stem>.parquet`` next to the logical CSV path."""
    out = parquet_sidecar_path(logical_csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


class PublishPaths(TypedDict):
    parquet: Path
    csv: Path | None


def publish_dataframe(
    df: pd.DataFrame,
    logical_csv_path: Path,
    *,
    write_csv: bool = False,
    sep: str = ";",
) -> PublishPaths:
    """Write Parquet (always). Optionally export CSV for inspection or legacy tools."""
    logical_csv_path = Path(logical_csv_path)
    logical_csv_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path = write_parquet_sidecar(df, logical_csv_path)
    csv_path: Path | None = None
    if write_csv:
        logical_csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(logical_csv_path, sep=sep, index=False)
        csv_path = logical_csv_path.resolve()
    return {"parquet": parquet_path.resolve(), "csv": csv_path}
