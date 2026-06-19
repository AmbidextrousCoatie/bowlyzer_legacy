"""Publish run manifest (``database/data/runs/latest.json``)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

DATA_SCHEMA_VERSION = 2
MANIFEST_FORMAT_VERSION = 1

JOB_LEAGUE = "league_merge"
JOB_TOURNAMENT = "tournament_merge"
JOB_PLAYER_HYBRID = "player_hybrid"
JOB_PLAYERS_REGISTRY = "players_registry"


def columns_hash(columns: Sequence[str]) -> str:
    blob = "|".join(sorted(str(c) for c in columns))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def new_run_id(when: Optional[datetime] = None) -> str:
    moment = when or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def read_parquet_artifact_metadata(parquet_path: Path) -> Dict[str, Any]:
    import pyarrow.parquet as pq

    path = Path(parquet_path)
    if not path.is_file():
        raise FileNotFoundError(parquet_path)
    meta = pq.read_metadata(path)
    schema = pq.read_schema(path)
    columns = list(schema.names)
    out: Dict[str, Any] = {
        "row_count": int(meta.num_rows),
        "columns": columns,
        "columns_hash": columns_hash(columns),
        "size_bytes": int(path.stat().st_size),
    }
    if "format_era" in columns:
        import pandas as pd

        counts = (
            pd.read_parquet(path, columns=["format_era"])["format_era"]
            .fillna("")
            .astype(str)
            .value_counts()
            .to_dict()
        )
        out["format_era_breakdown"] = {str(k): int(v) for k, v in counts.items()}
    else:
        out["format_era_breakdown"] = None
    return out


def _input_sources_from_league_summary(league_summary: Mapping[str, Any]) -> List[Dict[str, Any]]:
    dims = list(league_summary.get("input_dims") or [])
    unique = {
        int(item.get("priority", idx)): item
        for idx, item in enumerate(league_summary.get("input_unique_dims") or [])
    }
    sources: List[Dict[str, Any]] = []
    for idx, dim in enumerate(dims):
        path = str(dim.get("path") or "")
        hit = unique.get(idx, {})
        sources.append(
            {
                "path": path,
                "priority": idx,
                "input_rows": int(dim.get("rows") or 0),
                "unique_rows_after_dedupe": int(hit.get("unique_rows") or 0),
            }
        )
    return sources


def _audit_status_from_detail_rows(detail_rows: int, *, deferred: bool = False) -> str:
    if detail_rows <= 0:
        return "ok"
    if deferred:
        return "deferred"
    return "warn"


DEFERRED_UNTIL_PLAYERS_REGISTRY = "players_registry"


def build_artifact_entry(
    *,
    job: str,
    stream: str,
    logical_csv_path: Path,
    parquet_path: Path,
    input_sources: List[Dict[str, Any]],
    source_id: str = "",
    deprecated: bool = False,
) -> Dict[str, Any]:
    meta = read_parquet_artifact_metadata(parquet_path)
    return {
        "job": job,
        "stream": stream,
        "source_id": source_id,
        "deprecated": deprecated,
        "logical_path": str(logical_csv_path.resolve()),
        "parquet_path": str(Path(parquet_path).resolve()),
        "row_count": meta["row_count"],
        "columns": meta["columns"],
        "columns_hash": meta["columns_hash"],
        "schema_version": DATA_SCHEMA_VERSION,
        "format_era_breakdown": meta.get("format_era_breakdown"),
        "input_sources": input_sources,
        "size_bytes": meta.get("size_bytes"),
    }


def build_publish_manifest(
    *,
    summary: Mapping[str, Any],
    data_dir: Path,
    work_dir: Path,
    jobs_run: Sequence[str],
    run_id: Optional[str] = None,
    published_at: Optional[datetime] = None,
    forced: bool = False,
    skip_female_league_audit: bool = False,
    blocking_audit_ids: Sequence[str] = (),
    deferred_audit_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    """Build manifest dict from ``build_published_dataset`` summary payload."""
    moment = published_at or datetime.now(timezone.utc)
    rid = run_id or new_run_id(moment)
    artifacts: List[Dict[str, Any]] = []

    league_summary = summary.get("league")
    if league_summary:
        paths = league_summary.get("paths") or {}
        artifacts.append(
            build_artifact_entry(
                job=JOB_LEAGUE,
                stream="league",
                logical_csv_path=Path(str(paths.get("output") or league_summary.get("output") or "")),
                parquet_path=Path(str(paths.get("parquet_output") or "")),
                input_sources=_input_sources_from_league_summary(league_summary),
                source_id="db_real_merged",
            )
        )

    tournament_summary = summary.get("tournaments")
    if tournament_summary:
        artifacts.append(
            build_artifact_entry(
                job=JOB_TOURNAMENT,
                stream="tournament",
                logical_csv_path=Path(str(tournament_summary.get("output") or "")),
                parquet_path=Path(str(tournament_summary.get("parquet_output") or "")),
                input_sources=[
                    {"path": str(p), "priority": idx, "input_rows": None, "unique_rows_after_dedupe": None}
                    for idx, p in enumerate(tournament_summary.get("inputs") or [])
                ],
                source_id="db_tournament_regions_2026_gf",
            )
        )

    registry_summary = summary.get("players_registry")
    if registry_summary:
        paths = registry_summary.get("paths") or {}
        artifacts.append(
            build_artifact_entry(
                job=JOB_PLAYERS_REGISTRY,
                stream="player",
                logical_csv_path=Path(str(paths.get("output") or "")),
                parquet_path=Path(str(paths.get("parquet_output") or "")),
                input_sources=[
                    {
                        "path": "database/config/player_id_name_normalization.json",
                        "priority": 0,
                        "input_rows": None,
                        "unique_rows_after_dedupe": None,
                    },
                    {
                        "path": "database/config/player_name_normalization.json",
                        "priority": 1,
                        "input_rows": None,
                        "unique_rows_after_dedupe": None,
                    },
                ],
                source_id="players_registry",
            )
        )

    hybrid_summary = summary.get("player_hybrid")
    if hybrid_summary:
        artifacts.append(
            build_artifact_entry(
                job=JOB_PLAYER_HYBRID,
                stream="player",
                logical_csv_path=Path(str(hybrid_summary.get("output") or "")),
                parquet_path=Path(str(hybrid_summary.get("parquet_output") or "")),
                input_sources=[],
                source_id="db_player_merged_hybrid",
                deprecated=True,
            )
        )

    player_audit = summary.get("player_id_name_audit") or {}
    detail_rows = int(player_audit.get("detail_rows") or 0)
    player_deferred = "player_id_name" in set(deferred_audit_ids)
    standings_audit = summary.get("league_standings_audit") or {}
    standings_status = str(standings_audit.get("status") or "skipped")
    audits: Dict[str, Any] = {
        "female_league_split": {
            "status": "skipped" if skip_female_league_audit else "ok",
        },
        "player_id_name": {
            "status": _audit_status_from_detail_rows(detail_rows, deferred=player_deferred),
            "report": str(player_audit.get("report") or ""),
            "detail_rows": detail_rows,
            "deferred_until": DEFERRED_UNTIL_PLAYERS_REGISTRY if player_deferred else None,
        },
        "league_standings": {
            "status": standings_status,
            "report": str(standings_audit.get("report") or ""),
            "evaluated": int(standings_audit.get("evaluated") or 0),
            "counts": dict(standings_audit.get("counts") or {}),
        },
    }

    league_summary_dict = league_summary if isinstance(league_summary, dict) else {}
    normalization = league_summary_dict.get("normalization") or {}

    return {
        "manifest_format_version": MANIFEST_FORMAT_VERSION,
        "data_schema_version": DATA_SCHEMA_VERSION,
        "run_id": rid,
        "published_at": moment.isoformat(),
        "forced": bool(forced),
        "blocking_audit_ids": list(blocking_audit_ids) if forced else [],
        "deferred_audit_ids": list(deferred_audit_ids),
        "jobs_run": list(jobs_run),
        "paths": {
            "data_dir": str(Path(data_dir).resolve()),
            "work_dir": str(Path(work_dir).resolve()),
        },
        "artifacts": artifacts,
        "audits": audits,
        "normalization": {
            "team_name_normalization_applied": bool(normalization.get("team_name_normalization_applied")),
            "player_id_name_normalization_applied": bool(
                normalization.get("player_id_name_normalization_applied")
            ),
            "player_id_name_normalization_fingerprint": str(
                normalization.get("player_id_name_normalization_fingerprint") or ""
            ),
            "player_name_normalization_applied": bool(normalization.get("player_name_normalization_applied")),
            "player_name_normalization_fingerprint": str(
                normalization.get("player_name_normalization_fingerprint") or ""
            ),
        },
        "merge": {
            "league_dedupe_keys": list(league_summary_dict.get("dedupe_keys") or []),
            "league_merge_conflicts": league_summary_dict.get("merge_conflicts") or {},
        },
    }


def write_publish_manifest(
    manifest: Mapping[str, Any],
    *,
    data_dir: Path,
    also_write_run_copy: bool = True,
) -> Dict[str, str]:
    """Write ``runs/latest.json`` and optional ``runs/{run_id}.json``."""
    runs_dir = Path(data_dir) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    latest_path = runs_dir / "latest.json"
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    latest_path.write_text(payload, encoding="utf-8")
    out = {"latest": str(latest_path.resolve())}
    if also_write_run_copy:
        run_id = str(manifest.get("run_id") or new_run_id())
        run_path = runs_dir / f"{run_id}.json"
        run_path.write_text(payload, encoding="utf-8")
        out["run"] = str(run_path.resolve())
    return out


def summarize_manifest_for_status(manifest: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compact manifest view for Diagnose /pipeline/status."""
    if not manifest:
        return {"present": False}

    audits = dict(manifest.get("audits") or {})
    blocking_from_audits: List[str] = list(manifest.get("blocking_audit_ids") or [])
    deferred_from_manifest: List[str] = list(manifest.get("deferred_audit_ids") or [])
    if (audits.get("player_id_name") or {}).get("status") == "warn":
        blocking_from_audits.append("player_id_name")
    if (audits.get("player_id_name") or {}).get("status") == "deferred":
        deferred_from_manifest.append("player_id_name")
    if (audits.get("female_league_split") or {}).get("status") == "failed":
        blocking_from_audits.append("female_league_split")

    artifacts_out: List[Dict[str, Any]] = []
    for art in manifest.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        artifacts_out.append(
            {
                "job": art.get("job"),
                "stream": art.get("stream"),
                "source_id": art.get("source_id"),
                "row_count": art.get("row_count"),
                "columns_hash": art.get("columns_hash"),
                "schema_version": art.get("schema_version"),
                "input_source_count": len(art.get("input_sources") or []),
                "deprecated": bool(art.get("deprecated")),
            }
        )

    forced = bool(manifest.get("forced"))
    blocking_ids = list(dict.fromkeys(blocking_from_audits))
    deferred_ids = list(dict.fromkeys(deferred_from_manifest))
    if blocking_from_audits and forced:
        audit_overall = "forced"
    elif deferred_ids:
        audit_overall = "deferred"
    elif blocking_from_audits:
        audit_overall = "warn"
    elif any((a.get("status") == "warn" for a in audits.values() if isinstance(a, dict))):
        audit_overall = "warn"
    else:
        audit_overall = "ok"

    return {
        "present": True,
        "run_id": manifest.get("run_id"),
        "published_at": manifest.get("published_at"),
        "forced": forced,
        "data_schema_version": manifest.get("data_schema_version"),
        "jobs_run": list(manifest.get("jobs_run") or []),
        "artifact_count": len(artifacts_out),
        "artifacts": artifacts_out,
        "audits": audits,
        "blocking_audit_ids": blocking_ids,
        "deferred_audit_ids": deferred_ids,
        "audit_overall": audit_overall,
    }


def load_latest_manifest(data_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    from database.paths import publish_latest_manifest

    path = publish_latest_manifest() if data_dir is None else Path(data_dir) / "runs" / "latest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
