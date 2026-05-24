"""Parquet sidecar read/write preference."""

from pathlib import Path

import pandas as pd

from data_access.parquet_sidecar import parquet_sidecar_path, should_load_parquet, write_parquet_sidecar
from data_access.shared_pandas_store import get_dataframe, invalidate_dataframe_cache


def test_should_prefer_parquet_when_newer(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    df = pd.DataFrame({"Season": ["10/11"], "League": ["BayL"], "Team": ["A 1"]})
    df.to_csv(csv_path, sep=";", index=False)
    write_parquet_sidecar(df, csv_path)
    pq = parquet_sidecar_path(csv_path)
    assert pq.is_file()
    assert should_load_parquet(csv_path, pq)


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
    df.to_csv(csv_path, sep=";", index=False)
    write_parquet_sidecar(df, csv_path)
    invalidate_dataframe_cache()
    loaded = get_dataframe(csv_path)
    assert len(loaded) == 1
    assert str(loaded.iloc[0]["Team"]) == "A 1"
