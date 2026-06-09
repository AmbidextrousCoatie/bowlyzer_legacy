"""Publish gate: strict audits block Parquet unless ``--force-publish``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


AUDIT_PLAYER_ID_NAME = "player_id_name"
AUDIT_FEMALE_LEAGUE_SPLIT = "female_league_split"
DEFERRED_UNTIL_PLAYERS_REGISTRY = "players_registry"


def _player_id_name_conflict_count(summary: Mapping[str, Any]) -> int:
    audit = summary.get("player_id_name_audit") or {}
    return int(audit.get("detail_rows") or 0)


def collect_deferred_audit_ids(
    summary: Mapping[str, Any],
    *,
    skip_player_id_name_audit: bool,
) -> List[str]:
    """
    Audits with findings that do not block publish (resolved in a later pipeline phase).

    Player ID/name conflicts are deferred until ``players_registry.parquet`` (Phase 2b).
    """
    from data_access.data_sources_registry import audit_blocks_publish

    deferred: List[str] = []
    if skip_player_id_name_audit or _player_id_name_conflict_count(summary) <= 0:
        return deferred
    if not audit_blocks_publish(AUDIT_PLAYER_ID_NAME):
        deferred.append(AUDIT_PLAYER_ID_NAME)
    return deferred


def collect_blocking_audit_ids(
    summary: Mapping[str, Any],
    *,
    skip_player_id_name_audit: bool,
) -> List[str]:
    """Return audit ids that block publish under strict mode."""
    from data_access.data_sources_registry import audit_blocks_publish

    blocks: List[str] = []
    if skip_player_id_name_audit or _player_id_name_conflict_count(summary) <= 0:
        return blocks
    if audit_blocks_publish(AUDIT_PLAYER_ID_NAME):
        blocks.append(AUDIT_PLAYER_ID_NAME)
    return blocks


def published_paths_from_summary(summary: Mapping[str, Any]) -> List[Path]:
    """All Parquet/CSV paths written during this publish run."""
    seen: set[str] = set()
    out: List[Path] = []

    def add(path_str: str) -> None:
        if not path_str:
            return
        resolved = str(Path(path_str).resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        out.append(Path(resolved))

    for key in ("league", "tournaments", "player_hybrid"):
        block = summary.get(key)
        if not isinstance(block, dict):
            continue
        paths = block.get("paths")
        if isinstance(paths, dict):
            add(str(paths.get("parquet_output") or ""))
            add(str(paths.get("csv_output") or ""))
            add(str(paths.get("output") or ""))
        add(str(block.get("parquet_output") or ""))
        add(str(block.get("csv_output") or ""))
        add(str(block.get("output") or ""))

    return out


def rollback_published_outputs(summary: Mapping[str, Any]) -> List[str]:
    """Remove artifacts from a blocked publish run. Returns deleted paths."""
    removed: List[str] = []
    for path in published_paths_from_summary(summary):
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    return removed


def evaluate_publish_gate(
    summary: Mapping[str, Any],
    *,
    strict_audit: bool,
    force_publish: bool,
    skip_player_id_name_audit: bool,
) -> Dict[str, Any]:
    """
    Decide whether publish is allowed and whether outputs should be rolled back.

    Female league split is checked before merge in the orchestrator (pre-publish).
    """
    blocking = collect_blocking_audit_ids(
        summary, skip_player_id_name_audit=skip_player_id_name_audit
    )
    deferred = collect_deferred_audit_ids(
        summary, skip_player_id_name_audit=skip_player_id_name_audit
    )
    blocked = bool(blocking) and strict_audit and not force_publish
    return {
        "strict_audit": strict_audit,
        "force_publish": force_publish,
        "blocking_audit_ids": blocking,
        "deferred_audit_ids": deferred,
        "blocked": blocked,
        "allowed": not blocked,
    }
