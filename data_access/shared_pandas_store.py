"""
Process-local cache for league CSV data and pandas adapters.

One loaded DataFrame + one DataAdapterPandas per database id (until backing files change).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from data_access.dtype_normalization import normalize_legacy_dataframe_types

_LEGACY_CSV_READ_KWARGS = {"sep": ";", "dtype": str, "low_memory": False}

# abs_path -> {mtime, df}
_DATAFRAME_BY_PATH: Dict[str, dict] = {}

# database_id -> (revision, adapter)
_ADAPTER_BY_DATABASE: Dict[str, Tuple[str, object]] = {}


def _file_mtime(path: Path) -> float:
    if not path.is_file():
        return -1.0
    return os.path.getmtime(path)


def resolve_database_paths(database_id: str) -> Tuple[Path, Tuple[Path, ...]]:
    from app.config.database_config import DATABASE_DATA_DIR, database_config

    config = database_config.get_source_config(database_id)
    if not config:
        raise ValueError(f"Unknown database id: {database_id}")

    if config.file_path:
        primary = Path(config.file_path)
    else:
        primary = Path(DATABASE_DATA_DIR) / database_config.get_filename_for_source(database_id)

    extras = tuple(Path(p) for p in (getattr(config, "merge_file_paths", None) or ()))
    return primary, extras


def compute_database_revision(database_id: str) -> str:
    from app.cache.league_response_cache import compute_data_revision

    return compute_data_revision(database_id)


def load_dataframe_for_paths(primary: Path, extras: Tuple[Path, ...] = ()) -> pd.DataFrame:
    """Load or return cached dataframe for primary CSV, optionally merged with extras."""
    paths: List[Path] = []
    if primary.is_file():
        paths.append(primary)
    for extra in extras:
        if extra.is_file():
            paths.append(extra)

    if not paths:
        raise FileNotFoundError(f"No data files found for {primary}")

    if len(paths) == 1:
        return get_dataframe(paths[0])

    frames = [get_dataframe(p) for p in paths]
    merged = pd.concat(frames, ignore_index=True)
    if merged.columns.duplicated().any():
        merged = merged.loc[:, ~merged.columns.duplicated()].copy()
    return merged


def get_dataframe(path: Path) -> pd.DataFrame:
    """Load CSV or newer Parquet sidecar with mtime-based process cache."""
    from data_access.parquet_sidecar import (
        parquet_sidecar_path,
        read_parquet_sidecar,
        should_load_parquet,
    )

    csv_path = path.resolve()
    parquet_path = parquet_sidecar_path(csv_path)
    use_parquet = should_load_parquet(csv_path, parquet_path)

    cache_key = str(parquet_path if use_parquet else csv_path)
    mtime = _file_mtime(parquet_path if use_parquet else csv_path)
    entry = _DATAFRAME_BY_PATH.get(cache_key)
    if entry and entry.get("mtime") == mtime:
        return entry["df"]

    if use_parquet:
        df = read_parquet_sidecar(parquet_path)
    else:
        df = pd.read_csv(csv_path, **_LEGACY_CSV_READ_KWARGS)
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()].copy()
        df = normalize_legacy_dataframe_types(df)

    _DATAFRAME_BY_PATH[cache_key] = {"mtime": mtime, "df": df}
    return df


def invalidate_dataframe_cache(path: Path | None = None) -> None:
    if path is None:
        _DATAFRAME_BY_PATH.clear()
        return
    _DATAFRAME_BY_PATH.pop(str(path.resolve()), None)


def invalidate_adapter_cache(database_id: str | None = None) -> None:
    if database_id is None:
        _ADAPTER_BY_DATABASE.clear()
        return
    _ADAPTER_BY_DATABASE.pop(database_id, None)


def get_shared_pandas_adapter(database_id: str):
    """Return a cached DataAdapterPandas for ``database_id``."""
    from data_access.adapters.data_adapter_pandas import DataAdapterPandas

    revision = compute_database_revision(database_id)
    cached = _ADAPTER_BY_DATABASE.get(database_id)
    if cached and cached[0] == revision:
        return cached[1]

    primary, extras = resolve_database_paths(database_id)
    df = load_dataframe_for_paths(primary, extras)
    adapter = DataAdapterPandas(df=df)
    adapter.database = database_id
    _ADAPTER_BY_DATABASE[database_id] = (revision, adapter)
    return adapter


@dataclass
class LeagueMetadataIndex:
    seasons_all: List[str] = field(default_factory=list)
    leagues_by_season: Dict[str, List[str]] = field(default_factory=dict)
    weeks_by_season_league: Dict[Tuple[str, str], List[int]] = field(default_factory=dict)
    teams_all: List[str] = field(default_factory=list)


def _player_input_rows_mask(df: pd.DataFrame) -> pd.Series:
    from data_access.schema import Columns

    mask = pd.Series(True, index=df.index)
    if Columns.input_data in df.columns:
        mask &= df[Columns.input_data].fillna("").astype(str).str.strip().str.lower().isin(
            {"true", "1", "yes", "y", "on"}
        )
    if Columns.computed_data in df.columns:
        mask &= df[Columns.computed_data].fillna("").astype(str).str.strip().str.lower().isin(
            {"false", "0", "no", "n", "off", ""}
        )
    return mask


def build_league_metadata_index(df: pd.DataFrame) -> LeagueMetadataIndex:
    from data_access.adapters.data_adapter_pandas import _unique_clean_str_labels
    from data_access.schema import Columns
    from data_access.text_norm import normalize_unicode_label

    if df is None or df.empty:
        return LeagueMetadataIndex()

    meta = LeagueMetadataIndex()
    meta.seasons_all = _unique_clean_str_labels(df[Columns.season]) if Columns.season in df.columns else []

    if Columns.team_name in df.columns:
        team_rows = df[_player_input_rows_mask(df)] if len(df.columns) else df
        meta.teams_all = _unique_clean_str_labels(team_rows[Columns.team_name])

    if Columns.season not in df.columns or Columns.league_name not in df.columns:
        return meta

    league_frame = df[[Columns.season, Columns.league_name]].dropna()
    for season, group in league_frame.groupby(Columns.season, sort=False):
        season_key = normalize_unicode_label(str(season))
        if not season_key:
            continue
        meta.leagues_by_season[season_key] = _unique_clean_str_labels(group[Columns.league_name])

    if Columns.week in df.columns:
        week_frame = df[[Columns.season, Columns.league_name, Columns.week]].dropna(
            subset=[Columns.season, Columns.league_name]
        )
        weeks_numeric = pd.to_numeric(week_frame[Columns.week], errors="coerce")
        week_frame = week_frame.assign(_week_int=weeks_numeric).dropna(subset=["_week_int"])
        for (season, league), group in week_frame.groupby([Columns.season, Columns.league_name], sort=False):
            season_key = normalize_unicode_label(str(season))
            league_key = normalize_unicode_label(str(league))
            if not season_key or not league_key:
                continue
            weeks = sorted({int(w) for w in group["_week_int"].unique()})
            meta.weeks_by_season_league[(season_key, league_key)] = weeks

    return meta
