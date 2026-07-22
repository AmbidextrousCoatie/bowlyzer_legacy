"""Parquet-first storage for published league/tournament datasets.

Config and paths still use the historical ``*.csv`` logical names under
``database/data/``; runtime Parquet lives in ``database/data/*.parquet`` and
optional CSV mirrors in ``database/published_csv/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pandas as pd

from data_access.dtype_normalization import normalize_legacy_dataframe_types
from database.paths import (
    _uses_published_layout,
    published_csv_mirror_path,
    published_parquet_path,
)


def parquet_sidecar_path(logical_csv_path: Path) -> Path:
    return published_parquet_path(logical_csv_path)


def data_file_exists(logical_csv_path: Path) -> bool:
    """True when Parquet, published CSV mirror, or legacy co-located CSV exists."""
    logical = Path(logical_csv_path)
    if published_parquet_path(logical).is_file():
        return True
    if _uses_published_layout(logical) and published_csv_mirror_path(logical).is_file():
        return True
    return logical.is_file()


def resolve_load_path(logical_csv_path: Path) -> Path:
    """Path passed to readers/cache keys: Parquet when present, else CSV mirror."""
    logical = Path(logical_csv_path)
    parquet_path = published_parquet_path(logical)
    if parquet_path.is_file():
        return parquet_path.resolve()
    if _uses_published_layout(logical):
        csv_mirror = published_csv_mirror_path(logical)
        if csv_mirror.is_file():
            return csv_mirror.resolve()
    return logical.resolve()


def should_load_parquet(csv_path: Path, parquet_path: Path) -> bool:
    return parquet_path.is_file()


def read_parquet_sidecar(parquet_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet_path)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    return normalize_legacy_dataframe_types(df)


def write_parquet_sidecar(df: pd.DataFrame, logical_csv_path: Path) -> Path:
    """Write ``<stem>.parquet`` under ``database/data/`` (atomic replace)."""
    out = published_parquet_path(logical_csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(out)
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
    """Write Parquet to ``database/data/``. Optionally mirror CSV to ``published_csv/``."""
    logical_csv_path = Path(logical_csv_path)
    parquet_path = write_parquet_sidecar(df, logical_csv_path)
    csv_path: Path | None = None
    if write_csv:
        mirror = published_csv_mirror_path(logical_csv_path)
        mirror.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(mirror, sep=sep, index=False)
        csv_path = mirror.resolve()
    return {"parquet": parquet_path.resolve(), "csv": csv_path}
