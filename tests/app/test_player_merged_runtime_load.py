"""db_player_merged_hybrid loads league + tournament without a hybrid Parquet file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.data_manager import DataManager
from data_access.schema import Columns


def test_data_manager_merges_league_and_tournament_parquets(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    league_csv = data_dir / "league_results_merged.csv"
    tournament_csv = data_dir / "tournaments_postprocessed.csv"

    league_df = pd.DataFrame(
        {
            Columns.season: ["24/25"],
            Columns.event: ["BayL"],
            Columns.event_type: ["league"],
            Columns.team_name: ["Club 1"],
            Columns.club: ["Club"],
            Columns.player_name: ["League Player"],
            Columns.input_data: ["True"],
            Columns.computed_data: ["False"],
        }
    )
    tournament_df = pd.DataFrame(
        {
            Columns.season: ["24/25"],
            Columns.event: ["Test Tournament"],
            Columns.event_type: ["tournament"],
            Columns.player_name: ["Tournament Player"],
            Columns.club: ["Club"],
            Columns.input_data: ["True"],
            Columns.computed_data: ["False"],
        }
    )
    league_df.to_parquet(league_csv.with_suffix(".parquet"), index=False)
    tournament_df.to_parquet(tournament_csv.with_suffix(".parquet"), index=False)

    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))
    from importlib import reload

    import app.config.database_config as db_cfg

    reload(db_cfg)
    dm = DataManager(source="db_player_merged_hybrid")
    names = set(dm.df[Columns.player_name].astype(str).tolist())
    assert names == {"League Player", "Tournament Player"}
