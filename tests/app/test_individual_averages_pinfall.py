"""Individual averages must count injury rows (negative scores) via abs pinfall."""

import pandas as pd

from data_access.score_utils import mean_scores, pinfall_for_total, sum_scores


def test_week_average_counts_negative_scores_as_abs_pinfall():
    """Mirrors get_individual_averages aggregation after score_utils fix."""
    scores = [180.0, 104.0, -169.0, -169.0]
    series = pd.Series(scores)
    assert mean_scores(series, round_places=1) == round(sum(pinfall_for_total(s) for s in scores) / len(scores), 1)
    assert sum_scores(series) == 180 + 104 + 169 + 169


def test_match_total_pins_includes_injury_rows():
  rows = [180, -169, 200, -169]
  assert sum(int(pinfall_for_total(s)) for s in rows) == 180 + 169 + 200 + 169
