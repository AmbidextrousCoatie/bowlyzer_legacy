"""Progress-enabled normalization helpers."""

from __future__ import annotations

import pandas as pd

from scripts.data.extract_excel_data import (
    _map_series_with_progress,
    normalize_extracted_dataframe,
    normalize_team_name,
    reset_team_normalization_stats,
)


def test_map_series_without_progress():
    series = pd.Series(["A", "B"])
    out = _map_series_with_progress(series, str.upper, desc="test", show_progress=False)
    assert out.tolist() == ["A", "B"]


def test_normalize_extracted_dataframe_empty_with_progress():
    df = normalize_extracted_dataframe(pd.DataFrame(), show_progress=True)
    assert df.empty


def test_normalize_team_name_is_deterministic_with_cache():
    reset_team_normalization_stats()
    first = normalize_team_name("PANthers Pfarrk 2")
    second = normalize_team_name("PANthers Pfarrk 2")
    assert first == second
