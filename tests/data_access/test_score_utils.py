"""Tests for pinfall aggregation helpers."""

import pandas as pd

from data_access.score_utils import mean_scores, pinfall_display, pinfall_for_total, sum_scores


def test_sum_scores_uses_absolute_values():
    series = pd.Series([180, -5, 200])
    assert sum_scores(series) == 385


def test_mean_scores_uses_absolute_values():
    series = pd.Series([180, -20])
    assert mean_scores(series, round_places=1) == 100.0


def test_pinfall_for_total():
    assert pinfall_for_total(-12) == 12.0


def test_pinfall_display_keeps_sign():
    assert pinfall_display(-169) == -169
    assert pinfall_display("180") == 180
