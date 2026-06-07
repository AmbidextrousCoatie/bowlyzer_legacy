"""
Per-season / per-league content revisions for league response disk cache.

Whole-file mtime revision invalidates every endpoint when the merged CSV grows
(e.g. new 25/26 weeks) even though 08/09 … 24/25 rows are unchanged. This module
fingerprints each season (and each league for league-wide endpoints) so cache keys
stay stable for untouched slices.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import pandas as pd

from app.cache.league_response_cache import (
    compute_data_revision,
    league_cache_read_roots,
    league_cache_write_root,
)
from app.config.database_config import database_config
from app.utils.season_query import normalize_season_query_value
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label

_ENV_GRANULAR = "LEAGUE_CACHE_GRANULAR_REVISION"
_INDEX_VERSION = "granular-v2"

# Stable row identity (aligned with merge_league_sources dedupe keys).
_REVISION_COLUMNS: tuple[str, ...] = (
    Columns.season,
    Columns.league_name,
    Columns.week,
    Columns.round_number,
    Columns.match_number,
    Columns.team_name,
    Columns.position,
    Columns.player_name,
    Columns.score,
    Columns.points,
)

_INDEX_LOCK = threading.Lock()
_INDEX_BY_DATABASE: Dict[str, "LeagueRevisionIndex"] = {}


def granular_revision_enabled() -> bool:
    v = (os.environ.get(_ENV_GRANULAR) or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def _index_content_fingerprint(index: "LeagueRevisionIndex") -> str:
    """Stable fingerprint from index payload (survives CSV mtime changes after deploy)."""
    material = {
        "version": index.version,
        "global_revision": index.global_revision,
        "seasons": index.seasons,
        "leagues": index.leagues,
        "clubs": index.clubs,
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def source_fingerprint(database_id: str) -> str:
    """Legacy mtime fingerprint (whole-file invalidation)."""
    return compute_data_revision(database_id)


def _index_matches_published_data_file(index: LeagueRevisionIndex, database_id: str) -> bool:
    """True when revision_index.json was built from the current parquet/CSV on disk."""
    on_disk = (index.data_file_revision or "").strip()
    if not on_disk:
        return False
    return on_disk == compute_data_revision(database_id)


def _index_on_disk_is_valid(index: LeagueRevisionIndex, database_id: str) -> bool:
    if index.version != _INDEX_VERSION:
        return False
    if not _index_matches_published_data_file(index, database_id):
        return False
    return index.source_fingerprint == _index_content_fingerprint(index)


def _sanitize_db_id(database_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(database_id).strip())
    return s[:120] or "default"


def _index_relative_path(database_id: str) -> Path:
    return Path(_sanitize_db_id(database_id)) / "revision_index.json"


def _index_write_path(database_id: str) -> Path:
    return league_cache_write_root() / _index_relative_path(database_id)


def _index_read_paths(database_id: str) -> List[Path]:
    rel = _index_relative_path(database_id)
    return [root / rel for root in league_cache_read_roots()]


def _revision_columns(df: pd.DataFrame) -> List[str]:
    return [c for c in _REVISION_COLUMNS if c in df.columns]


def _frame_content_revision(frame: pd.DataFrame) -> str:
    if frame is None or frame.empty:
        return "empty"
    cols = _revision_columns(frame)
    if not cols:
        return "empty"
    view = frame[cols].copy()
    for col in cols:
        if view[col].dtype == object or str(view[col].dtype) == "string":
            view[col] = view[col].fillna("").astype(str).str.strip().map(normalize_unicode_label)
    view = view.sort_values(by=cols, kind="mergesort").reset_index(drop=True)
    digest = pd.util.hash_pandas_object(view, index=False).values.tobytes()
    return hashlib.sha256(digest).hexdigest()[:12]


def _split_club_from_team(team_name: str) -> str:
    text = str(team_name or "").strip()
    if not text:
        return ""
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", text)
    if not match:
        return text
    return str(match.group(1) or "").strip()


@dataclass
class LeagueRevisionIndex:
    source_fingerprint: str
    global_revision: str
    seasons: Dict[str, str] = field(default_factory=dict)
    leagues: Dict[str, str] = field(default_factory=dict)
    clubs: Dict[str, str] = field(default_factory=dict)
    version: str = _INDEX_VERSION
    # Mtime/size fingerprint of published league file(s); invalidates index when data is replaced.
    data_file_revision: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "source_fingerprint": self.source_fingerprint,
            "global_revision": self.global_revision,
            "data_file_revision": self.data_file_revision,
            "seasons": dict(sorted(self.seasons.items())),
            "leagues": dict(sorted(self.leagues.items())),
            "clubs": dict(sorted(self.clubs.items())),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "LeagueRevisionIndex":
        return cls(
            version=str(raw.get("version") or ""),
            source_fingerprint=str(raw.get("source_fingerprint") or ""),
            global_revision=str(raw.get("global_revision") or "unknown"),
            data_file_revision=str(raw.get("data_file_revision") or ""),
            seasons={str(k): str(v) for k, v in (raw.get("seasons") or {}).items()},
            leagues={str(k): str(v) for k, v in (raw.get("leagues") or {}).items()},
            clubs={str(k): str(v) for k, v in (raw.get("clubs") or {}).items()},
        )


def build_revision_index_from_dataframe(df: pd.DataFrame, *, source_fp: str) -> LeagueRevisionIndex:
    idx = LeagueRevisionIndex(source_fingerprint=source_fp, global_revision=_frame_content_revision(df))

    if df is None or df.empty or Columns.season not in df.columns:
        return idx

    season_labels = df[Columns.season].fillna("").astype(str).map(normalize_unicode_label)
    for season, group in df.groupby(season_labels, sort=False):
        key = str(season).strip()
        if not key:
            continue
        idx.seasons[key] = _frame_content_revision(group)

    if Columns.league_name in df.columns:
        league_labels = df[Columns.league_name].fillna("").astype(str).map(normalize_unicode_label)
        for league, group in df.groupby(league_labels, sort=False):
            key = str(league).strip()
            if not key:
                continue
            idx.leagues[key] = _frame_content_revision(group)

    if Columns.team_name in df.columns:
        club_labels = df[Columns.team_name].fillna("").astype(str).map(_split_club_from_team)
        club_labels = club_labels.map(normalize_unicode_label)
        for club, group in df.groupby(club_labels, sort=False):
            key = str(club).strip()
            if not key:
                continue
            idx.clubs[key] = _frame_content_revision(group)

    return idx


def build_revision_index(database_id: str) -> LeagueRevisionIndex:
    from data_access.shared_pandas_store import get_shared_pandas_adapter

    adapter = get_shared_pandas_adapter(database_id)
    df = getattr(adapter, "df", None)
    if df is None:
        empty = LeagueRevisionIndex(source_fingerprint="empty", global_revision="empty")
        empty.source_fingerprint = _index_content_fingerprint(empty)
        empty.data_file_revision = compute_data_revision(database_id)
        return empty
    index = build_revision_index_from_dataframe(df, source_fp="")
    index.source_fingerprint = _index_content_fingerprint(index)
    index.data_file_revision = compute_data_revision(database_id)
    return index


def _load_index_from_disk(database_id: str) -> Optional[LeagueRevisionIndex]:
    for path in _index_read_paths(database_id):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            idx = LeagueRevisionIndex.from_dict(raw)
            if idx.version != _INDEX_VERSION:
                continue
            return idx
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _save_index_to_disk(index: LeagueRevisionIndex, database_id: str) -> None:
    path = _index_write_path(database_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        print(
            f"Warning: revision index save skipped for {database_id!r}: {exc}",
            flush=True,
        )


def ensure_revision_index(database_id: str, *, force: bool = False) -> LeagueRevisionIndex:
    """Load or build per-season/league revision index (cached in-process)."""
    db = database_config.get_source_config(database_id)
    if not db:
        empty = LeagueRevisionIndex(source_fingerprint="unknown", global_revision="unknown")
        return empty

    with _INDEX_LOCK:
        if not force:
            cached = _INDEX_BY_DATABASE.get(database_id)
            if cached and _index_on_disk_is_valid(cached, database_id):
                return cached
            disk = _load_index_from_disk(database_id)
            if disk and _index_on_disk_is_valid(disk, database_id):
                _INDEX_BY_DATABASE[database_id] = disk
                return disk

        index = build_revision_index(database_id)
        _INDEX_BY_DATABASE[database_id] = index
        _save_index_to_disk(index, database_id)
        return index


def invalidate_revision_index(database_id: str | None = None) -> None:
    with _INDEX_LOCK:
        if database_id is None:
            _INDEX_BY_DATABASE.clear()
        else:
            _INDEX_BY_DATABASE.pop(database_id, None)
    if database_id is None:
        return
    for path in _index_read_paths(database_id):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def effective_data_revision(
    database_id: str,
    query_args: Mapping[str, object],
) -> str:
    """
    Revision string embedded in cache payload hash.

    Prefers per-season / per-league / per-club fingerprints when granular mode is on.
    """
    if not granular_revision_enabled():
        return compute_data_revision(database_id)

    q = query_args or {}
    season_raw = str(q.get("season") or "").strip()
    season = normalize_season_query_value(season_raw) or season_raw
    league = str(q.get("league") or "").strip()
    club = str(q.get("club") or "").strip()

    try:
        index = ensure_revision_index(database_id)
    except Exception:
        return compute_data_revision(database_id)

    if season:
        return index.seasons.get(season) or index.global_revision
    if club:
        return index.clubs.get(club) or index.global_revision
    if league:
        return index.leagues.get(league) or index.global_revision
    return index.global_revision


def revision_index_summary(database_id: str) -> str:
    index = ensure_revision_index(database_id)
    return (
        f"seasons={len(index.seasons)}, leagues={len(index.leagues)}, "
        f"clubs={len(index.clubs)}, global={index.global_revision}"
    )
