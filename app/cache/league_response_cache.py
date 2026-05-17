"""
Persistent JSON cache for expensive league read endpoints.

Invalidation is driven by a data revision derived from the backing CSV
(mtime + size + path) plus optional LEAGUE_CACHE_REVISION. Responses that
embed i18n strings are keyed by current language and translations_version.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from app.config.database_config import database_config
from app.services.i18n_service import i18n_service

_ENV_ENABLED = "LEAGUE_CACHE_ENABLED"
_ENV_DIR = "LEAGUE_CACHE_DIR"
_ENV_REVISION = "LEAGUE_CACHE_REVISION"

# Bump per endpoint when response shape changes (invalidates disk cache without CSV edits).
_ENDPOINT_PAYLOAD_VERSION: Dict[str, str] = {
    "get_team_performance_table": "pos-rank-v2",
    "get_team_win_percentage_table": "pos-rank-v2",
    "get_week_matrix": "league-long-names-v1",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def league_cache_dir() -> Path:
    raw = (os.environ.get(_ENV_DIR) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_repo_root() / ".cache" / "league").resolve()


def is_league_cache_enabled() -> bool:
    v = (os.environ.get(_ENV_ENABLED) or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def _sanitize_db_id(database_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(database_id).strip())
    return s[:120] or "default"


def compute_data_revision(database_id: str) -> str:
    """
    Short hash so when the CSV changes (replace or edit), revision changes.
    """
    cfg = database_config.get_source_config(database_id)
    if not cfg or not cfg.file_path:
        return "unknown"
    p = Path(cfg.file_path)
    if not p.is_file():
        return "missing"
    st = p.stat()
    parts = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime_ns)}"
    extra = (os.environ.get(_ENV_REVISION) or "").strip()
    if extra:
        parts += f"|{extra}"
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:12]


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
        q[str(k)] = str(v)
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


def cache_file_path(endpoint: str, database_id: str, query_args: Mapping[str, Any]) -> Tuple[Path, str]:
    db = effective_database_id(database_id)
    rev = compute_data_revision(db)
    qnorm = normalize_query_for_key(query_args, db)
    lang = i18n_service.get_current_language().value
    i18n_ver = i18n_service.get_translations_version()
    h = _payload_hash(endpoint, db, rev, lang, i18n_ver, qnorm)
    base = league_cache_dir() / _sanitize_db_id(db) / rev
    return base / f"{endpoint}__{h}.json", rev


def league_cache_try_get(endpoint: str, database_id: Optional[str], query_args: Mapping[str, Any]) -> Optional[Any]:
    if not is_league_cache_enabled():
        return None
    db = effective_database_id(database_id)
    path, _rev = cache_file_path(endpoint, db, query_args)
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None


def league_cache_put(endpoint: str, database_id: Optional[str], query_args: Mapping[str, Any], payload: Any) -> None:
    if not is_league_cache_enabled():
        return
    db = effective_database_id(database_id)
    path, _rev = cache_file_path(endpoint, db, query_args)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def league_cache_invalidate_database(database_id: Optional[str] = None) -> int:
    """
    Remove all cached entries for a database id (all revisions). Returns files deleted.
    """
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
