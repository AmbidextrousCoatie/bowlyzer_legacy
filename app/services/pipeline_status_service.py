"""Read-only pipeline / publish status for the Diagnose UI."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from app.config.database_config import database_config
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from database.paths import (
    get_data_dir,
    get_work_data_dir,
    league_results_merged_csv,
    manual_tournament_postprocessed_csv,
    player_stats_merged_hybrid_csv,
    tournaments_postprocessed_csv,
)


def _iso_mtime(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat()


def _file_size(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    return int(path.stat().st_size)


def _row_count(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    try:
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as pq

            return int(pq.read_metadata(path).num_rows)
        import pandas as pd

        return int(len(pd.read_csv(path, sep=";", dtype=str, usecols=[0])))
    except Exception:
        return None


def _artifact_status(*, exists: bool, mtime_iso: Optional[str], required: bool) -> str:
    if not exists:
        return "missing" if required else "absent"
    if not mtime_iso:
        return "ok"
    try:
        mtime = dt.datetime.fromisoformat(mtime_iso)
        age_days = (dt.datetime.now(tz=dt.timezone.utc) - mtime).days
        if age_days > 30:
            return "warn"
    except ValueError:
        pass
    return "ok"


def _describe_artifact(
    *,
    artifact_id: str,
    label: str,
    logical_path: Path,
    source_id: str = "",
    required: bool = False,
    stream: str = "",
) -> Dict[str, Any]:
    exists = data_file_exists(logical_path)
    load_path = resolve_load_path(logical_path) if exists else logical_path
    mtime = _iso_mtime(load_path) if exists else None
    return {
        "id": artifact_id,
        "label": label,
        "stream": stream,
        "source_id": source_id,
        "logical_path": str(logical_path.resolve()),
        "load_path": str(load_path.resolve()) if exists else "",
        "format": load_path.suffix.lstrip(".").lower() if exists else "",
        "exists": exists,
        "required": required,
        "status": _artifact_status(exists=exists, mtime_iso=mtime, required=required),
        "mtime_utc": mtime,
        "size_bytes": _file_size(load_path) if exists else None,
        "row_count": _row_count(load_path) if exists else None,
    }


def _config_fingerprint(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "exists": True,
        "mtime_utc": _iso_mtime(path),
        "size_bytes": int(stat.st_size),
    }


def _audit_report(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    row_count: Optional[int] = None
    try:
        import pandas as pd

        row_count = int(len(pd.read_csv(path, sep=",", dtype=str)))
        if row_count > 0:
            row_count -= 1
    except Exception:
        pass
    return {
        "path": str(path.resolve()),
        "exists": True,
        "mtime_utc": _iso_mtime(path),
        "size_bytes": _file_size(path),
        "detail_rows": row_count,
    }


def get_pipeline_status() -> Dict[str, Any]:
    """Snapshot of published artifacts, app sources, and optional work-dir audits."""
    from data_access.player_id_name_normalization import compute_player_id_name_normalization_fingerprint
    from data_access.player_name_normalization_config import compute_player_name_normalization_fingerprint

    data_dir = get_data_dir()
    work_dir = get_work_data_dir()

    published: List[Dict[str, Any]] = [
        _describe_artifact(
            artifact_id="league_merged",
            label="Merged league",
            logical_path=league_results_merged_csv(),
            source_id="db_real_merged",
            required=True,
            stream="league",
        ),
        _describe_artifact(
            artifact_id="tournaments",
            label="Tournaments (published)",
            logical_path=tournaments_postprocessed_csv(),
            source_id="db_tournament_regions_2026_gf",
            required=False,
            stream="tournament",
        ),
        _describe_artifact(
            artifact_id="player_hybrid",
            label="Player hybrid",
            logical_path=player_stats_merged_hybrid_csv(),
            source_id="db_player_merged_hybrid",
            required=False,
            stream="player",
        ),
        _describe_artifact(
            artifact_id="tournament_manual",
            label="Manual tournament imports",
            logical_path=manual_tournament_postprocessed_csv(),
            required=False,
            stream="tournament",
        ),
    ]

    ko_config = data_dir / "tournament_ko_config.json"
    if ko_config.is_file():
        published.append(
            _describe_artifact(
                artifact_id="tournament_ko_config",
                label="Tournament KO config",
                logical_path=ko_config,
                stream="tournament",
            )
        )

    app_sources: List[Dict[str, Any]] = []
    for source_id, config in sorted(database_config._sources.items()):
        path = Path(config.file_path) if config.file_path else data_dir / config.filename
        artifact = _describe_artifact(
            artifact_id=source_id,
            label=config.display_name,
            logical_path=path,
            source_id=source_id,
            required=source_id == "db_real_merged",
        )
        app_sources.append(
            {
                "source_id": source_id,
                "display_name": config.display_name,
                "description": config.description,
                "is_default": config.is_default,
                "is_enabled": config.is_enabled,
                "filename": config.filename,
                **artifact,
            }
        )

    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "database" / "config"

    audits = {
        "player_id_name_conflicts": _audit_report(work_dir / "player_id_name_conflicts.csv"),
    }

    latest_mtime = max(
        (a["mtime_utc"] for a in published if a.get("mtime_utc")),
        default=None,
    )

    return {
        "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "paths": {
            "published_data_dir": str(data_dir.resolve()),
            "work_data_dir": str(work_dir.resolve()),
            "work_dir_readable": work_dir.is_dir(),
        },
        "last_publish_mtime_utc": latest_mtime,
        "published_artifacts": published,
        "app_sources": app_sources,
        "config_fingerprints": {
            "player_id_name_normalization": compute_player_id_name_normalization_fingerprint(),
            "player_name_normalization": compute_player_name_normalization_fingerprint(),
            "team_name_normalization": _config_fingerprint(config_dir / "team_name_normalization.json"),
        },
        "audits": audits,
        "docs": {
            "pipeline_plan": "docs/planning/DATA_PIPELINE_PLAN.md",
            "publish_runbook": "database/data/README.md",
        },
    }
