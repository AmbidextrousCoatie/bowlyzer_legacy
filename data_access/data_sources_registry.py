"""Load ``database/config/data_sources.json`` (pipeline source registry)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


def registry_path() -> Path:
    return Path(__file__).resolve().parents[1] / "database" / "config" / "data_sources.json"


@lru_cache(maxsize=1)
def load_data_sources_registry() -> Dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"schema_version": 0, "sources": [], "publish_jobs": [], "deferred_audits": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def deferred_audit_policy(audit_id: str) -> Optional[Dict[str, Any]]:
    registry = load_data_sources_registry()
    policy = (registry.get("deferred_audits") or {}).get(audit_id)
    return policy if isinstance(policy, dict) else None


def audit_blocks_publish(audit_id: str) -> bool:
    """Whether strict mode should block publish on this audit (default: block)."""
    policy = deferred_audit_policy(audit_id)
    if policy is None:
        return True
    return bool(policy.get("blocks_publish", False))


def list_publish_jobs() -> List[Dict[str, Any]]:
    registry = load_data_sources_registry()
    jobs = registry.get("publish_jobs") or []
    return [j for j in jobs if isinstance(j, dict)]
