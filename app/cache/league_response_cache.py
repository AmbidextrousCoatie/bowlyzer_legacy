"""
Persistent JSON cache for expensive league read endpoints.

Invalidation uses granular per-season / per-league content fingerprints when
LEAGUE_CACHE_GRANULAR_REVISION=1 (default), so appending rows to the current
season does not invalidate caches for older seasons. Set LEAGUE_CACHE_GLOBAL_REVISION=1
to revert to whole-file mtime revision. Optional LEAGUE_CACHE_REVISION bumps all keys.

Responses that embed i18n strings are keyed by current language and translations_version.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.config.database_config import database_config
from app.services.i18n_service import i18n_service
from app.utils.season_query import normalize_season_query_value

_ENV_ENABLED = "LEAGUE_CACHE_ENABLED"
_ENV_DIR = "LEAGUE_CACHE_DIR"
_ENV_RUNTIME_DIR = "LEAGUE_CACHE_RUNTIME_DIR"
_ENV_REVISION = "LEAGUE_CACHE_REVISION"
_ENV_GLOBAL_REVISION = "LEAGUE_CACHE_GLOBAL_REVISION"
_ENTRIES_SUBDIR = "entries"

# Bump per endpoint when response shape changes (invalidates disk cache without CSV edits).
_ENDPOINT_PAYLOAD_VERSION: Dict[str, str] = {
    "get_team_performance_table": "abs-pinfall-v1",
    "get_team_win_percentage_table": "pos-rank-v2",
    "get_team_analysis": "abs-pinfall-v1",
    "get_individual_averages": "abs-pinfall-v1",
    "get_game_team_details": "abs-pinfall-v1",
    "get_team_week_details_table": "abs-pinfall-v1",
    "get_team_week_head_to_head_table": "abs-pinfall-v1",
    "get_week_matrix": "per-league-weeks-v3-bl-bzol-merge",
    "home_stats": "landing-v1",
    "get_latest_events": "latest-events-v1",
    "get_team_vs_team_comparison": "unplayed-empty-v3",
    "get_club_matrix": "matrix-pos-v2",
    "get_tournament_section": "round-results-net-rank-v15",
    "get_player_section": "player-round-hcp-per-game-v1",
    "get_tournament_field_progress": "field-progress-v4",
    # Added handicap block + round names in payload — bump invalidates old disk cache without `handicap`.
    "get_tournament_format": "format-handicap-v1",
    "get_available_tournaments": "manual-merge-rev-v1",
    "get_available_seasons": "metadata-index-v1",
    "get_available_leagues": "metadata-index-v1",
    "team_get_teams": "metadata-index-v1",
    "player_search": "player-catalog-v1",
    "player_get_available_seasons": "player-subset-v1",
    "get_lifetime_stats": "player-lifetime-v1",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def league_cache_dir() -> Path:
    """Pre-warmed / shipped cache root (read-only on production VPS)."""
    raw = (os.environ.get(_ENV_DIR) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / ".cache" / "league").resolve()


def league_cache_runtime_dir() -> Optional[Path]:
    """
    Optional read-write overlay for cache entries created at runtime.

    When set, ``league_cache_try_get`` checks here before ``LEAGUE_CACHE_DIR``,
    and ``league_cache_put`` writes only here (so a read-only shipped mount still works).
    """
    raw = (os.environ.get(_ENV_RUNTIME_DIR) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def league_cache_read_roots() -> List[Path]:
    """Search order for disk cache hits (runtime overlay first, then shipped)."""
    roots: List[Path] = []
    runtime = league_cache_runtime_dir()
    if runtime is not None:
        roots.append(runtime)
    shipped = league_cache_dir()
    if runtime is None or runtime != shipped:
        roots.append(shipped)
    return roots


def league_cache_write_root() -> Path:
    """Directory for new cache files (runtime overlay when configured)."""
    runtime = league_cache_runtime_dir()
    if runtime is not None:
        return runtime
    return league_cache_dir()


def is_league_cache_enabled() -> bool:
    v = (os.environ.get(_ENV_ENABLED) or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def _sanitize_db_id(database_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(database_id).strip())
    return s[:120] or "default"


def _file_revision_part(path: Path) -> str:
    if not path.is_file():
        return f"{path.resolve()}|missing"
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{int(st.st_mtime_ns)}"


def use_global_file_revision() -> bool:
    v = (os.environ.get(_ENV_GLOBAL_REVISION) or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _resolve_data_revision(database_id: str, query_args: Mapping[str, Any]) -> str:
    if use_global_file_revision():
        return compute_data_revision(database_id)
    from app.cache.league_data_revision import effective_data_revision, granular_revision_enabled

    if granular_revision_enabled():
        return effective_data_revision(database_id, query_args)
    return compute_data_revision(database_id)


def compute_data_revision(database_id: str) -> str:
    """
    Short hash so when backing CSV(s) change (replace or edit), revision changes.

    Includes merge_file_paths (e.g. tournament_manual_postprocessed.csv merged into
    db_tournament_regions_2026_gf) so club Excel imports invalidate tournament cache.
    """
    cfg = database_config.get_source_config(database_id)
    if not cfg:
        return "unknown"
    parts: list[str] = []
    if cfg.file_path:
        csv_path = Path(cfg.file_path)
        parquet_path = csv_path.with_suffix(".parquet")
        if parquet_path.is_file():
            parts.append(_file_revision_part(parquet_path))
        if csv_path.is_file():
            parts.append(_file_revision_part(csv_path))
    for extra in getattr(cfg, "merge_file_paths", None) or ():
        parts.append(_file_revision_part(Path(extra)))
    if not parts:
        return "unknown"
    blob = "|".join(parts)
    extra = (os.environ.get(_ENV_REVISION) or "").strip()
    if extra:
        blob += f"|{extra}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def effective_database_id(explicit_database: Optional[str]) -> str:
    return (explicit_database or "").strip() or database_config.get_default_source()


def normalize_query_for_key(query_args: Mapping[str, Any], database_id: str) -> Dict[str, str]:
    """Stable dict for hashing: database always explicit, sorted keys."""
    q: Dict[str, str] = {}
    for k in sorted(query_args.keys()):
        if k == "database":
            continue
        v = query_args.get(k)
        if v is None:
            continue
        val = str(v)
        if str(k) == "season":
            val = normalize_season_query_value(val) or val
        q[str(k)] = val
    q["database"] = database_id
    return dict(sorted(q.items()))


def _payload_hash(
    endpoint: str,
    database_id: str,
    data_revision: str,
    lang: str,
    i18n_version: str,
    query_normalized: Mapping[str, str],
) -> str:
    material = {
        "endpoint": endpoint,
        "database": database_id,
        "data_revision": data_revision,
        "lang": lang,
        "i18n_version": i18n_version,
        "query": dict(query_normalized),
        "endpoint_payload_version": _ENDPOINT_PAYLOAD_VERSION.get(endpoint, ""),
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:20]


def cache_entry_relative_path(
    endpoint: str,
    database_id: str,
    query_args: Mapping[str, Any],
) -> Tuple[Path, str]:
    """Path relative to any cache root, plus resolved data revision."""
    db = effective_database_id(database_id)
    data_rev = _resolve_data_revision(db, query_args)
    qnorm = normalize_query_for_key(query_args, db)
    lang = i18n_service.get_current_language().value
    i18n_ver = i18n_service.get_translations_version()
    h = _payload_hash(endpoint, db, data_rev, lang, i18n_ver, qnorm)
    if use_global_file_revision():
        rel = Path(_sanitize_db_id(db)) / data_rev / f"{endpoint}__{h}.json"
    else:
        rel = Path(_sanitize_db_id(db)) / _ENTRIES_SUBDIR / f"{endpoint}__{h}.json"
    return rel, data_rev


def cache_file_path(endpoint: str, database_id: str, query_args: Mapping[str, Any]) -> Tuple[Path, str]:
    """Primary cache file path under the write root (for misses / logging)."""
    rel, data_rev = cache_entry_relative_path(endpoint, database_id, query_args)
    return league_cache_write_root() / rel, data_rev


def _legacy_cache_paths_for_root(
    root: Path,
    endpoint: str,
    database_id: str,
    query_args: Mapping[str, Any],
) -> List[Path]:
    """Pre-granular layout: <root>/<db>/<file-rev>/<endpoint>__<hash>.json"""
    db = effective_database_id(database_id)
    rev = compute_data_revision(db)
    qnorm = normalize_query_for_key(query_args, db)
    lang = i18n_service.get_current_language().value
    i18n_ver = i18n_service.get_translations_version()
    h = _payload_hash(endpoint, db, rev, lang, i18n_ver, qnorm)
    base = root / _sanitize_db_id(db)
    if not base.is_dir():
        return []
    return [base / rev / f"{endpoint}__{h}.json"]


def league_cache_read_paths(endpoint: str, database_id: str, query_args: Mapping[str, Any]) -> List[Path]:
    """All candidate paths for a cache lookup (runtime overlay, then shipped)."""
    rel, _rev = cache_entry_relative_path(endpoint, database_id, query_args)
    candidates: List[Path] = []
    seen: set[str] = set()
    for root in league_cache_read_roots():
        for path in (root / rel, *_legacy_cache_paths_for_root(root, endpoint, database_id, query_args)):
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def _warn_stale_disk_cache(endpoint: str, database_id: str, expected_path: Path) -> None:
    """Log once when warmed JSON exists but revision keys no longer match (data changed without re-warm)."""
    if expected_path.is_file():
        return
    entries = league_cache_write_root() / _sanitize_db_id(database_id) / _ENTRIES_SUBDIR
    if not any(entries.glob(f"{endpoint}__*.json")):
        entries = league_cache_dir() / _sanitize_db_id(database_id) / _ENTRIES_SUBDIR
    if not entries.is_dir():
        return
    pattern = f"{endpoint}__*.json"
    if not any(entries.glob(pattern)):
        return
    print(
        f"League cache MISS for {endpoint!r} ({database_id}): "
        f"expected {expected_path.name} — other {pattern} files exist. "
        "Published data likely changed; run scripts/warm_league_cache.py (or deploy -SyncCache).",
        flush=True,
    )


def preload_league_revision_indexes() -> None:
    """Load revision_index.json at startup so first API cache lookup is not ~10s."""
    if not is_league_cache_enabled() or use_global_file_revision():
        return
    try:
        from app.cache.league_data_revision import granular_revision_enabled, ensure_revision_index
    except ImportError:
        return
    if not granular_revision_enabled():
        return
    for db_id in (database_config.get_default_source(),):
        try:
            ensure_revision_index(db_id)
        except Exception as exc:
            print(f"Warning: revision index preload failed for {db_id!r}: {exc}", flush=True)


def league_cache_try_get(endpoint: str, database_id: Optional[str], query_args: Mapping[str, Any]) -> Optional[Any]:
    if not is_league_cache_enabled():
        return None
    db = effective_database_id(database_id)
    candidates = league_cache_read_paths(endpoint, db, query_args)
    primary = cache_file_path(endpoint, db, query_args)[0]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
    _warn_stale_disk_cache(endpoint, db, primary)
    return None


def league_cache_put(endpoint: str, database_id: Optional[str], query_args: Mapping[str, Any], payload: Any) -> None:
    if not is_league_cache_enabled():
        return
    db = effective_database_id(database_id)
    rel, _rev = cache_entry_relative_path(endpoint, db, query_args)
    path = league_cache_write_root() / rel
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        print(
            f"Warning: league cache put skipped for {endpoint!r} ({db}): {exc}",
            flush=True,
        )


def league_cache_clear_runtime(database_id: Optional[str] = None) -> int:
    """Remove runtime overlay JSON (optional wipe after shipping a new pre-warmed cache)."""
    runtime = league_cache_runtime_dir()
    if runtime is None or not runtime.is_dir():
        return 0
    if database_id:
        targets = [runtime / _sanitize_db_id(effective_database_id(database_id))]
    else:
        targets = [runtime]
    n = 0
    for root in targets:
        if not root.is_dir():
            continue
        for p in root.rglob("*.json"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        for p in sorted(root.rglob("*"), reverse=True):
            if p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    pass
    return n


def league_cache_invalidate_database(database_id: Optional[str] = None) -> int:
    """
    Remove all cached entries for a database id (all revisions). Returns files deleted.
    """
    from app.cache.league_data_revision import invalidate_revision_index

    db_id = effective_database_id(database_id) if database_id else None
    if db_id:
        invalidate_revision_index(db_id)
    else:
        invalidate_revision_index(None)

    db = _sanitize_db_id(effective_database_id(database_id))
    root = league_cache_dir() / db
    if not root.is_dir():
        return 0
    n = 0
    for p in root.rglob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    for p in sorted(root.rglob("*"), reverse=True):
        if p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    return n
