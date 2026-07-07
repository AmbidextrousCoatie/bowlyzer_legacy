"""Per-event tournament stage definitions (cuts, game ranges) for runtime + postprocess."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_STAGE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "database" / "data" / "tournament_stage_definitions.json"
)


def _event_key(season: str, event_name: str) -> str:
    return f"{str(season or '').strip()}||{str(event_name or '').strip()}"


@lru_cache(maxsize=1)
def load_tournament_stage_definitions() -> Dict[str, Any]:
    if not _STAGE_PATH.is_file():
        return {}
    try:
        raw = json.loads(_STAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def lookup_tournament_stage_block(season: str, event_name: str) -> Optional[Dict[str, Any]]:
    resolved = resolve_stage_event_name(season, event_name)
    block = load_tournament_stage_definitions().get(_event_key(season, resolved))
    return block if isinstance(block, dict) else None


def resolve_stage_event_name(season: str, event_name: str) -> str:
    """
    Map a UI / group label to the canonical event name used in stage definitions.

    Accepts exact DB names (``… Einzel 2018``) and normalized group names
    (``Bayerische Meisterschaft Einzel``) when uniquely identifiable for the season.
    """
    season_s = str(season or "").strip()
    event_s = str(event_name or "").strip()
    if not event_s:
        return event_s
    if _event_key(season_s, event_s) in load_tournament_stage_definitions():
        return event_s

    from app.utils.tournament_utils import normalize_tournament_group_name

    target = normalize_tournament_group_name(event_s)
    prefix = f"{season_s}||"
    matches: List[str] = []
    for key, block in load_tournament_stage_definitions().items():
        if not str(key).startswith(prefix):
            continue
        stored = str(key).split("||", 1)[-1].strip()
        block_event = str((block or {}).get("event_name") or stored).strip()
        if normalize_tournament_group_name(block_event) == target:
            matches.append(block_event)
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    return event_s


def list_tournament_stage_items(season: str, event_name: str) -> List[Dict[str, Any]]:
    block = lookup_tournament_stage_block(season, event_name)
    if not block:
        return []
    stages = block.get("stages")
    if not isinstance(stages, list):
        return []
    return [item for item in stages if isinstance(item, dict)]


def stage_cut_rank_for_round(season: str, event_name: str, round_number: int) -> Optional[int]:
    """Return 1-based cut rank for a qualifying round, or None if not configured."""
    for item in list_tournament_stage_items(season, event_name):
        stage_id = item.get("id")
        if stage_id is None:
            continue
        try:
            sid = int(stage_id)
        except (TypeError, ValueError):
            continue
        if sid != int(round_number):
            continue
        cut_raw = str(item.get("cut") or "").strip().lower()
        if not cut_raw or cut_raw in ("n/a", "na", "none", "-"):
            return None
        try:
            cut_n = int(cut_raw)
        except ValueError:
            return None
        return cut_n if cut_n > 0 else None
    return None


def stage_cut_basis_for_round(season: str, event_name: str, round_number: int) -> str:
    for item in list_tournament_stage_items(season, event_name):
        try:
            if int(item.get("id")) != int(round_number):
                continue
        except (TypeError, ValueError):
            continue
        basis = str(item.get("cut_basis") or "overall_total").strip().lower()
        if basis in ("overall_total", "stage_total"):
            return basis
        return "overall_total"
    return "overall_total"


def public_stage_summary(season: str, event_name: str) -> List[Dict[str, Any]]:
    """Trimmed stage list for API responses."""
    out: List[Dict[str, Any]] = []
    for item in list_tournament_stage_items(season, event_name):
        out.append(
            {
                "round_number": int(item["id"]),
                "name": str(item.get("name") or "").strip(),
                "cut": str(item.get("cut") or "").strip(),
                "cut_basis": stage_cut_basis_for_round(season, event_name, int(item["id"])),
                "game_start": item.get("game_start"),
                "game_end": item.get("game_end"),
            }
        )
    return out
