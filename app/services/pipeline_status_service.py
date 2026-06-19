"""Read-only pipeline / publish status for the Diagnose UI."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from app.config.database_config import database_config
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from database.paths import (
    get_data_dir,
    get_work_data_dir,
    league_results_merged_csv,
    manual_tournament_postprocessed_csv,
    players_registry_csv,
    publish_latest_manifest,
    tournaments_postprocessed_csv,
)


def _looks_like_container_data_dir(data_dir: Path) -> bool:
    parts = [p.lower() for p in data_dir.resolve().parts]
    return any(parts[i] == "app" and parts[i + 1] == "database" for i in range(len(parts) - 1))


def pipeline_expose_operator_paths() -> bool:
    """Whether Diagnose may show absolute filesystem paths.

    Prod containers (``…/app/database/data``) hide paths by default. Set
    ``BOWLYZER_PIPELINE_EXPOSE_PATHS=1`` on a dev machine to force show, or
    ``=0`` to force hide locally.
    """
    raw = (os.environ.get("BOWLYZER_PIPELINE_EXPOSE_PATHS") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not _looks_like_container_data_dir(get_data_dir())


def _basename_only(path_str: str) -> str:
    if not path_str:
        return ""
    return Path(path_str).name


def _redact_path_fields(row: Dict[str, Any]) -> None:
    filename = row.get("filename") or _basename_only(str(row.get("logical_path") or ""))
    row["logical_path"] = ""
    row["load_path"] = ""
    if filename:
        row["filename"] = filename


def _sanitize_pipeline_status_for_client(
    status: Dict[str, Any],
    *,
    expose_paths: bool,
) -> Dict[str, Any]:
    if expose_paths:
        status["expose_operator_paths"] = True
        return status

    out = dict(status)
    out["expose_operator_paths"] = False
    out.pop("latest_manifest", None)

    paths = dict(out.get("paths") or {})
    out["paths"] = {
        "work_dir_readable": bool(paths.get("work_dir_readable")),
    }

    published: List[Dict[str, Any]] = []
    for row in out.get("published_artifacts") or []:
        item = dict(row)
        _redact_path_fields(item)
        published.append(item)
    out["published_artifacts"] = published

    app_sources: List[Dict[str, Any]] = []
    for row in out.get("app_sources") or []:
        item = dict(row)
        _redact_path_fields(item)
        app_sources.append(item)
    out["app_sources"] = app_sources

    audits: Dict[str, Any] = {}
    for key, row in (out.get("audits") or {}).items():
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.pop("path", None)
        audits[key] = item
    out["audits"] = audits

    fingerprints: Dict[str, Any] = {}
    for key, value in (out.get("config_fingerprints") or {}).items():
        if isinstance(value, dict):
            fp = dict(value)
            fp.pop("path", None)
            fingerprints[key] = fp
        else:
            fingerprints[key] = value
    out["config_fingerprints"] = fingerprints

    return out


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
            artifact_id="player_runtime_merge",
            label="Spieler (league + tournament runtime)",
            logical_path=league_results_merged_csv(),
            source_id="db_player_merged_hybrid",
            required=False,
            stream="player",
        ),
        _describe_artifact(
            artifact_id="players_registry",
            label="Players registry",
            logical_path=players_registry_csv(),
            source_id="players_registry",
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
    from data_access.data_sources_registry import load_data_sources_registry

    source_registry = load_data_sources_registry()

    audits = {
        "player_id_name_conflicts": _audit_report(work_dir / "player_id_name_conflicts.csv"),
        "league_standings_validation": _audit_report(work_dir / "league_standings_validation.csv"),
    }

    latest_mtime = max(
        (a["mtime_utc"] for a in published if a.get("mtime_utc")),
        default=None,
    )

    manifest_path = publish_latest_manifest()
    latest_manifest: Optional[Dict[str, Any]] = None
    manifest_summary: Dict[str, Any] = {"present": False}
    if manifest_path.is_file():
        try:
            import json

            from data_access.publish_manifest import summarize_manifest_for_status

            latest_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_summary = summarize_manifest_for_status(latest_manifest)
            manifest_mtime = _iso_mtime(manifest_path)
            if manifest_mtime and (latest_mtime is None or manifest_mtime > latest_mtime):
                latest_mtime = manifest_mtime
        except (OSError, ValueError, json.JSONDecodeError):
            latest_manifest = None
            manifest_summary = {"present": False}

    status = {
        "generated_at_utc": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "paths": {
            "published_data_dir": str(data_dir.resolve()),
            "work_data_dir": str(work_dir.resolve()),
            "work_dir_readable": work_dir.is_dir(),
            "latest_manifest": str(manifest_path.resolve()),
        },
        "last_publish_mtime_utc": latest_mtime,
        "latest_manifest": latest_manifest,
        "manifest_summary": manifest_summary,
        "published_artifacts": published,
        "app_sources": app_sources,
        "config_fingerprints": {
            "player_id_name_normalization": compute_player_id_name_normalization_fingerprint(),
            "player_name_normalization": compute_player_name_normalization_fingerprint(),
            "team_name_normalization": _config_fingerprint(config_dir / "team_name_normalization.json"),
            "league_week_schema": _config_fingerprint(config_dir / "league_week_schema.json"),
        },
        "audits": audits,
        "docs": {
            "pipeline_plan": "docs/planning/DATA_PIPELINE_PLAN.md",
            "publish_runbook": "database/data/README.md",
            "artifacts_contract": "database/data/ARTIFACTS.md",
        },
        "source_registry": source_registry,
    }
    return _sanitize_pipeline_status_for_client(
        status,
        expose_paths=pipeline_expose_operator_paths(),
    )
