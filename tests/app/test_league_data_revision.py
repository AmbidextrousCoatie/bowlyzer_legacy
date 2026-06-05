"""Per-season league cache revision fingerprints."""

from __future__ import annotations

import pandas as pd

from app.cache.league_data_revision import (
    _index_content_fingerprint,
    _index_on_disk_is_valid,
    build_revision_index_from_dataframe,
    effective_data_revision,
    granular_revision_enabled,
    source_fingerprint,
)
from data_access.schema import Columns


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            Columns.season: ["08/09", "08/09", "25/26", "25/26"],
            Columns.league_name: ["A N1", "A N1", "A N1", "A N1"],
            Columns.week: [1, 2, 1, 2],
            Columns.round_number: [1, 1, 1, 1],
            Columns.match_number: [1, 1, 1, 1],
            Columns.team_name: ["Club 1", "Club 1", "Club 1", "Club 1"],
            Columns.position: [1, 2, 1, 2],
            Columns.player_name: ["P1", "P2", "P1", "P2"],
            Columns.score: [200, 210, 220, 230],
            Columns.points: [1, 1, 1, 1],
        }
    )


def test_granular_enabled_by_default():
    assert granular_revision_enabled() is True


def test_unchanged_season_revision_stable_when_other_season_grows():
    base = _sample_df()
    idx_base = build_revision_index_from_dataframe(base, source_fp="fp1")
    rev_old = idx_base.seasons["08/09"]

    grown = pd.concat(
        [
            base,
            pd.DataFrame(
                {
                    Columns.season: ["25/26"],
                    Columns.league_name: ["A N1"],
                    Columns.week: [3],
                    Columns.round_number: [1],
                    Columns.match_number: [1],
                    Columns.team_name: ["Club 1"],
                    Columns.position: [1],
                    Columns.player_name: ["P9"],
                    Columns.score: [250],
                    Columns.points: [1],
                }
            ),
        ],
        ignore_index=True,
    )
    idx_grown = build_revision_index_from_dataframe(grown, source_fp="fp2")
    assert idx_grown.seasons["08/09"] == rev_old
    assert idx_grown.seasons["25/26"] != rev_old


def test_effective_data_revision_uses_season_slice(monkeypatch):
    df = _sample_df()
    index = build_revision_index_from_dataframe(df, source_fp="test")

    def _fake_ensure(_database_id: str, *, force: bool = False):
        return index

    monkeypatch.setattr(
        "app.cache.league_data_revision.ensure_revision_index",
        _fake_ensure,
    )

    rev_0809 = effective_data_revision("db_x", {"season": "08/09"})
    rev_2526 = effective_data_revision("db_x", {"season": "25/26"})
    assert rev_0809 != rev_2526
    assert rev_0809 == index.seasons["08/09"]
    assert effective_data_revision("db_x", {"season": "08-09"}) == rev_0809


def test_revision_index_invalid_when_published_file_fingerprint_differs():
    index = build_revision_index_from_dataframe(_sample_df(), source_fp="")
    index.source_fingerprint = _index_content_fingerprint(index)
    index.data_file_revision = "stale-file-rev"
    assert not _index_on_disk_is_valid(index, "db_real_merged")


def test_revision_index_valid_when_published_file_fingerprint_matches(monkeypatch):
    index = build_revision_index_from_dataframe(_sample_df(), source_fp="")
    index.source_fingerprint = _index_content_fingerprint(index)
    index.data_file_revision = "current-rev"
    monkeypatch.setattr(
        "app.cache.league_data_revision.compute_data_revision",
        lambda _db: "current-rev",
    )
    assert _index_on_disk_is_valid(index, "db_real_merged")
