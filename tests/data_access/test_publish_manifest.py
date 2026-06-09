"""Publish manifest (runs/latest.json)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_access.competition_schema import (
    apply_league_competition_schema_v2,
    apply_tournament_competition_schema_v2,
)
from data_access.publish_manifest import (
    DATA_SCHEMA_VERSION,
    build_publish_manifest,
    columns_hash,
    load_latest_manifest,
    summarize_manifest_for_status,
    write_publish_manifest,
)
from data_access.schema import Columns


def test_columns_hash_stable():
    assert columns_hash(["Event", "Season", "Player"]) == columns_hash(["Player", "Season", "Event"])


def test_build_and_write_manifest_from_summary(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    league_csv = data_dir / "league_results_merged.csv"
    league_df = apply_league_competition_schema_v2(
        pd.DataFrame(
            {
                "Season": ["24/25", "24/25"],
                "League": ["BayL", "BayL"],
                "Team": ["Club 1", "Club 1"],
                "Player": ["A", "B"],
                "Score": [200, 210],
                "Input Data": ["True", "True"],
                "Computed Data": ["False", "False"],
            }
        )
    )
    league_parquet = league_csv.with_suffix(".parquet")
    league_df.to_parquet(league_parquet, index=False)

    tournament_csv = data_dir / "tournaments_postprocessed.csv"
    tournament_df = apply_tournament_competition_schema_v2(
        pd.DataFrame(
            {
                Columns.season: ["25/26"],
                "Event Name": ["Clubmeisterschaft"],
                Columns.event_type: ["tournament"],
                Columns.player_name: ["A"],
                Columns.score: [220],
            }
        )
    )
    tournament_parquet = tournament_csv.with_suffix(".parquet")
    tournament_df.to_parquet(tournament_parquet, index=False)

    summary = {
        "league": {
            "dedupe_keys": ["league", "season"],
            "input_dims": [
                {"path": str(work_dir / "historical.csv"), "priority": 0, "rows": 2},
                {"path": str(work_dir / "gf.csv"), "priority": 1, "rows": 2},
            ],
            "input_unique_dims": [
                {"path": str(work_dir / "historical.csv"), "priority": 0, "unique_rows": 2},
                {"path": str(work_dir / "gf.csv"), "priority": 1, "unique_rows": 2},
            ],
            "merge_conflicts": {"rows_deduped": 0},
            "paths": {
                "output": str(league_csv),
                "parquet_output": str(league_parquet),
            },
            "normalization": {
                "team_name_normalization_applied": True,
                "player_id_name_normalization_applied": True,
                "player_id_name_normalization_fingerprint": "abc",
                "player_name_normalization_applied": True,
                "player_name_normalization_fingerprint": "def",
            },
        },
        "tournaments": {
            "inputs": [str(work_dir / "gf_tournaments.csv")],
            "rows": 1,
            "output": str(tournament_csv),
            "parquet_output": str(tournament_parquet),
        },
        "player_id_name_audit": {
            "report": str(work_dir / "player_id_name_conflicts.csv"),
            "detail_rows": 3,
        },
    }

    manifest = build_publish_manifest(
        summary=summary,
        data_dir=data_dir,
        work_dir=work_dir,
        jobs_run=["league", "tournament"],
        run_id="20260609T120000Z",
        skip_female_league_audit=False,
        deferred_audit_ids=["player_id_name"],
    )
    assert manifest["data_schema_version"] == DATA_SCHEMA_VERSION
    assert manifest["run_id"] == "20260609T120000Z"
    assert len(manifest["artifacts"]) == 2
    league_art = manifest["artifacts"][0]
    assert league_art["job"] == "league_merge"
    assert league_art["row_count"] == 2
    assert "Event" in league_art["columns"]
    assert league_art["schema_version"] == DATA_SCHEMA_VERSION
    assert len(league_art["input_sources"]) == 2
    assert manifest["audits"]["player_id_name"]["status"] == "deferred"
    assert manifest["audits"]["player_id_name"]["deferred_until"] == "players_registry"
    assert manifest["audits"]["player_id_name"]["detail_rows"] == 3

    paths = write_publish_manifest(manifest, data_dir=data_dir)
    loaded = load_latest_manifest(data_dir)
    assert loaded is not None
    assert loaded["run_id"] == "20260609T120000Z"
    assert Path(paths["latest"]).is_file()
    assert Path(paths["run"]).name == "20260609T120000Z.json"

    summary_view = summarize_manifest_for_status(manifest)
    assert summary_view["present"] is True
    assert summary_view["artifact_count"] == 2
    assert summary_view["audit_overall"] == "deferred"
    assert summary_view["deferred_audit_ids"] == ["player_id_name"]
