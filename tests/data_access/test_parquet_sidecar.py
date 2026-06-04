"""Parquet-first published dataset helpers."""

from pathlib import Path

import pandas as pd

from data_access.parquet_sidecar import (
    data_file_exists,
    parquet_sidecar_path,
    publish_dataframe,
    resolve_load_path,
    should_load_parquet,
    write_parquet_sidecar,
)
from data_access.shared_pandas_store import get_dataframe, invalidate_dataframe_cache


def test_should_prefer_parquet_when_present(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    df = pd.DataFrame({"Season": ["10/11"], "League": ["BayL"], "Team": ["A 1"]})
    write_parquet_sidecar(df, csv_path)
    pq = parquet_sidecar_path(csv_path)
    assert pq.is_file()
    assert should_load_parquet(csv_path, pq)
    assert resolve_load_path(csv_path) == pq.resolve()


def test_parquet_preferred_even_when_csv_is_newer(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    df_old = pd.DataFrame({"Season": ["10/11"], "League": ["BayL"], "Team": ["old"]})
    write_parquet_sidecar(df_old, csv_path)
    df_new = pd.DataFrame({"Season": ["11/12"], "League": ["BayL"], "Team": ["new"]})
    df_new.to_csv(csv_path, sep=";", index=False)
    invalidate_dataframe_cache(csv_path)
    loaded = get_dataframe(csv_path)
    assert str(loaded.iloc[0]["Team"]) == "old"


def test_publish_parquet_only(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    df = pd.DataFrame({"Season": ["10/11"], "League": ["BayL"], "Team": ["A 1"]})
    published = publish_dataframe(df, csv_path, write_csv=False)
    assert published["parquet"].is_file()
    assert published["csv"] is None
    assert not csv_path.is_file()
    assert data_file_exists(csv_path)


def test_get_dataframe_loads_parquet(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    df = pd.DataFrame(
        {
            "Season": ["10/11"],
            "League": ["BayL"],
            "Week": [1],
            "Team": ["A 1"],
            "Position": [1],
            "Player": ["P"],
            "Score": [200],
            "Computed Data": ["False"],
            "Input Data": ["True"],
        }
    )
    publish_dataframe(df, csv_path, write_csv=False)
    invalidate_dataframe_cache(csv_path)
    loaded = get_dataframe(csv_path)
    assert len(loaded) == 1
    assert str(loaded.iloc[0]["Team"]) == "A 1"
