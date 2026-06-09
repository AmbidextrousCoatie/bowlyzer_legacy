"""Pipeline status snapshot for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

from app.services.pipeline_status_service import (
    get_pipeline_status,
    pipeline_expose_operator_paths,
)


def test_pipeline_status_includes_published_league(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    league_csv = data_dir / "league_results_merged.csv"
    league_csv.write_text("Season;Player\n24/25;A\n", encoding="utf-8")

    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BOWLYZER_PIPELINE_EXPOSE_PATHS", "1")

    status = get_pipeline_status()
    league = next(a for a in status["published_artifacts"] if a["id"] == "league_merged")
    assert league["exists"] is True
    assert league["status"] in {"ok", "warn"}
    assert status["expose_operator_paths"] is True
    assert status["paths"]["published_data_dir"] == str(data_dir.resolve())
    assert status["latest_manifest"] is None
    assert status["manifest_summary"]["present"] is False


def test_pipeline_status_includes_latest_manifest(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    runs = data_dir / "runs"
    runs.mkdir(parents=True)
    manifest = {
        "run_id": "20260609T120000Z",
        "published_at": "2026-06-09T12:00:00+00:00",
        "artifacts": [{"job": "league_merge", "row_count": 1}],
    }
    (runs / "latest.json").write_text(
        __import__("json").dumps(manifest),
        encoding="utf-8",
    )

    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BOWLYZER_PIPELINE_EXPOSE_PATHS", "1")

    status = get_pipeline_status()
    assert status["latest_manifest"]["run_id"] == "20260609T120000Z"
    assert "latest_manifest" in status["paths"]
    assert status["manifest_summary"]["present"] is True
    assert status["manifest_summary"]["run_id"] == "20260609T120000Z"
    assert status["manifest_summary"]["artifact_count"] == 1
    assert "deferred_audits" in status["source_registry"]


def test_pipeline_status_redacts_paths_in_container_layout(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "app" / "database" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "league_results_merged.csv").write_text("Season;Player\n24/25;A\n", encoding="utf-8")

    monkeypatch.setenv("BOWLYZER_DATA_DIR", str(data_dir))
    monkeypatch.delenv("BOWLYZER_PIPELINE_EXPOSE_PATHS", raising=False)

    assert pipeline_expose_operator_paths() is False

    status = get_pipeline_status()
    assert status["expose_operator_paths"] is False
    assert "published_data_dir" not in status["paths"]
    assert status["paths"]["work_dir_readable"] in {True, False}
    assert "latest_manifest" not in status
    league = next(a for a in status["published_artifacts"] if a["id"] == "league_merged")
    assert league["logical_path"] == ""
    assert league["load_path"] == ""
    audit = status["audits"]["player_id_name_conflicts"]
    assert "path" not in audit
