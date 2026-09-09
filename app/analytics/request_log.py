"""
Append-only JSONL request log for Bowl-A-Lyzer API traffic.

Visitor id: SHA-256(truncated_client_ip + daily_salt)[:16] — no raw IP stored.
Daily salt rotates at UTC midnight so the same IP cannot be linked across days.

Default log path (production): /app/logs/analytics/requests.log
(host bind-mount: ~/logs/analytics/requests.log)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import date, datetime, timezone
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

_ENV_ENABLED = "ANALYTICS_ENABLED"
_ENV_LOG_PATH = "ANALYTICS_REQUEST_LOG"
_ENV_SALT = "ANALYTICS_SALT"

_DEFAULT_LOG_PATH = "/app/logs/analytics/requests.log"

# API routes worth logging (query params carry season/league/database context).
LOGGED_API_PREFIXES = (
    "/league/",
    "/player/",
    "/team/",
    "/tournament/",
    "/pipeline/",
    "/switch-database",
    "/get-data-sources-info",
    "/home/",
    "/data-source-changed",
    "/set-season/",
)

_WRITE_LOCK = threading.Lock()


def analytics_enabled() -> bool:
    v = (os.environ.get(_ENV_ENABLED) or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def analytics_log_path() -> Path:
    raw = (os.environ.get(_ENV_LOG_PATH) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(_DEFAULT_LOG_PATH)


def is_logged_api_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in LOGGED_API_PREFIXES)


def _daily_salt(day: Optional[date] = None) -> str:
    d = day or datetime.now(timezone.utc).date()
    secret = (os.environ.get(_ENV_SALT) or os.environ.get("FLASK_SECRET_KEY") or "bowlyzer-analytics").strip()
    return f"{d.isoformat()}|{secret}"


def truncate_client_ip(raw: str) -> str:
    """
    Reduce identifiability before hashing.

    IPv4 → /24 network; IPv6 → /48 network. Invalid values pass through trimmed.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        addr = ip_address(text)
    except ValueError:
        return text[:64]
    if addr.version == 4:
        return str(ip_network(f"{addr}/24", strict=False).network_address)
    return str(ip_network(f"{addr}/48", strict=False).network_address)


def resolve_client_ip(
    remote_addr: Optional[str],
    forwarded_for: Optional[str],
    real_ip: Optional[str],
) -> str:
    """Prefer nginx ``X-Real-IP``, then first ``X-Forwarded-For`` hop, then ``remote_addr``."""
    for candidate in (
        (real_ip or "").strip(),
        (forwarded_for or "").split(",")[0].strip() if forwarded_for else "",
        (remote_addr or "").strip(),
    ):
        if candidate:
            return candidate
    return ""


def daily_visitor_id(
    client_ip: str,
    *,
    day: Optional[date] = None,
) -> str:
    """Stable within a UTC day per truncated IP; uncorrelated across days."""
    truncated = truncate_client_ip(client_ip)
    material = f"{_daily_salt(day)}|{truncated}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def normalize_query_params(args: Mapping[str, Any]) -> Dict[str, str]:
    """Flatten query args (last value wins for repeated keys)."""
    out: Dict[str, str] = {}
    for key in sorted(args.keys()):
        values = args.getlist(key) if hasattr(args, "getlist") else [args.get(key)]
        if not values:
            continue
        val = values[-1]
        if val is None:
            continue
        out[str(key)] = str(val)
    return out


def build_log_record(
    *,
    method: str,
    path: str,
    query: Mapping[str, Any],
    status_code: int,
    cache_status: Optional[str],
    visitor_id: str,
    duration_ms: Optional[float] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "method": method,
        "path": path,
        "params": normalize_query_params(query),
        "status": status_code,
        "visitor_id": visitor_id,
    }
    if cache_status:
        record["cache_status"] = cache_status
    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 2)
    return record


def append_request_log(record: Mapping[str, Any]) -> None:
    if not analytics_enabled():
        return
    path = analytics_log_path()
    line = json.dumps(dict(record), ensure_ascii=False, separators=(",", ":"), default=str)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            _append_line_locked(path, line)
    except OSError as exc:
        print(f"Warning: analytics log write failed ({path}): {exc}", flush=True)


def _append_line_locked(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        if os.name != "nt":
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
        try:
            handle.write(line + "\n")
            handle.flush()
        finally:
            if os.name != "nt":
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
