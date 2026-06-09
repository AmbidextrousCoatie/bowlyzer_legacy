"""Strict publish gate and rollback."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_access.publish_gate import (
    collect_blocking_audit_ids,
    collect_deferred_audit_ids,
    evaluate_publish_gate,
    rollback_published_outputs,
)


def test_player_id_conflicts_deferred_not_blocking():
    summary = {"player_id_name_audit": {"detail_rows": 5}}
    assert collect_blocking_audit_ids(summary, skip_player_id_name_audit=False) == []
    assert collect_deferred_audit_ids(summary, skip_player_id_name_audit=False) == ["player_id_name"]
    assert collect_blocking_audit_ids(summary, skip_player_id_name_audit=True) == []


def test_evaluate_publish_gate_allows_deferred_conflicts():
    summary = {"player_id_name_audit": {"detail_rows": 1}}
    gate = evaluate_publish_gate(
        summary,
        strict_audit=True,
        force_publish=False,
        skip_player_id_name_audit=False,
    )
    assert gate["blocked"] is False
    assert gate["deferred_audit_ids"] == ["player_id_name"]


def test_evaluate_publish_gate_force_publish_allows():
    summary = {"player_id_name_audit": {"detail_rows": 1}}
    gate = evaluate_publish_gate(
        summary,
        strict_audit=True,
        force_publish=True,
        skip_player_id_name_audit=False,
    )
    assert gate["blocked"] is False
    assert gate["deferred_audit_ids"] == ["player_id_name"]


def test_rollback_removes_published_parquets(tmp_path: Path) -> None:
    league_parquet = tmp_path / "league_results_merged.parquet"
    pd.DataFrame({"a": [1]}).to_parquet(league_parquet, index=False)
    summary = {
        "league": {
            "paths": {
                "parquet_output": str(league_parquet),
                "output": str(tmp_path / "league_results_merged.csv"),
            }
        }
    }
    removed = rollback_published_outputs(summary)
    assert str(league_parquet.resolve()) in removed
    assert not league_parquet.is_file()
