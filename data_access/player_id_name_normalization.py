"""
Curated player name / Player ID fixes applied during league merge, player hybrid
build, and the player ID/name audit.

Config: ``database/config/player_id_name_normalization.json``

Blocks:
  - ``manual_resolutions.dbu_id`` — official-list remaps (name + id -> assigned id)
  - ``manual_resolutions.different_person`` — same display name, distinct individuals
  - ``autoresolve_remappings`` — majority / placeholder suggestions from audit CSV
  - ``remappings`` — legacy flat list (still supported)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, MutableMapping, Optional, Set, Tuple

from data_access.schema import Columns

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "database" / "config" / "player_id_name_normalization.json"
)


@dataclass(frozen=True)
class PlayerIdNameRemapRule:
    match_player_id: str
    match_player_name: str
    replace_player_id: Optional[str] = None
    replace_player_name: Optional[str] = None
    note: str = ""
    source: str = ""

    def label(self) -> str:
        src = f" [{self.source}]" if self.source else ""
        return (
            f"{self.match_player_name!r} id={self.match_player_id}"
            f" -> {self.replace_player_name or '*'} id={self.replace_player_id or '*'}{src}"
        )


@dataclass(frozen=True)
class DifferentPersonGroup:
    player_name: str
    player_ids: FrozenSet[str]


@dataclass(frozen=True)
class PlayerIdNameNormalizationConfig:
    remap_rules: Tuple[PlayerIdNameRemapRule, ...]
    different_person_groups: Tuple[DifferentPersonGroup, ...]


def normalize_player_id(value: object) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw or raw.lower() in {"nan", "none"}:
        return ""
    try:
        return str(int(float(raw)))
    except ValueError:
        return raw


def normalize_player_name(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _config_path(path: Path | None = None) -> Path:
    return (path or DEFAULT_CONFIG_PATH).resolve()


def _parse_remap_entry(entry: Mapping[str, Any], *, idx: int, cfg_path: Path, block: str) -> PlayerIdNameRemapRule:
    match = entry.get("match")
    if not isinstance(match, Mapping):
        raise ValueError(f"{cfg_path}: {block}[{idx}].match must be an object")
    match_id = normalize_player_id(match.get("player_id"))
    match_name = normalize_player_name(match.get("player_name"))
    if not match_id or not match_name:
        raise ValueError(f"{cfg_path}: {block}[{idx}].match requires player_id and player_name")

    replace = entry.get("replace") or {}
    if replace and not isinstance(replace, Mapping):
        raise ValueError(f"{cfg_path}: {block}[{idx}].replace must be an object")

    replace_id_raw = replace.get("player_id") if isinstance(replace, Mapping) else None
    replace_name_raw = replace.get("player_name") if isinstance(replace, Mapping) else None
    replace_id = normalize_player_id(replace_id_raw) if replace_id_raw not in (None, "") else None
    replace_name = normalize_player_name(replace_name_raw) if replace_name_raw not in (None, "") else None
    if replace_id is None and replace_name is None:
        raise ValueError(f"{cfg_path}: {block}[{idx}].replace needs player_id and/or player_name")

    return PlayerIdNameRemapRule(
        match_player_id=match_id,
        match_player_name=match_name,
        replace_player_id=replace_id,
        replace_player_name=replace_name,
        note=str(entry.get("note") or "").strip(),
        source=str(entry.get("source") or block).strip(),
    )


def load_player_id_name_normalization_config(path: Path | None = None) -> PlayerIdNameNormalizationConfig:
    cfg_path = _config_path(path)
    if not cfg_path.is_file():
        return PlayerIdNameNormalizationConfig(remap_rules=(), different_person_groups=())

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, MutableMapping):
        raise ValueError(f"{cfg_path}: root must be a JSON object")

    rules: List[PlayerIdNameRemapRule] = []
    seen: Set[Tuple[str, str]] = set()

    def _add_rule(rule: PlayerIdNameRemapRule) -> None:
        key = (rule.match_player_name, rule.match_player_id)
        if key in seen:
            return
        seen.add(key)
        rules.append(rule)

    for idx, entry in enumerate(raw.get("remappings") or []):
        if isinstance(entry, Mapping):
            _add_rule(_parse_remap_entry(entry, idx=idx, cfg_path=cfg_path, block="remappings"))

    manual = raw.get("manual_resolutions") or {}
    if isinstance(manual, Mapping):
        for idx, entry in enumerate(manual.get("dbu_id") or []):
            if isinstance(entry, Mapping):
                _add_rule(_parse_remap_entry(entry, idx=idx, cfg_path=cfg_path, block="manual_resolutions.dbu_id"))

    for idx, entry in enumerate(raw.get("autoresolve_remappings") or []):
        if isinstance(entry, Mapping):
            _add_rule(_parse_remap_entry(entry, idx=idx, cfg_path=cfg_path, block="autoresolve_remappings"))

    different_groups: List[DifferentPersonGroup] = []
    if isinstance(manual, Mapping):
        for idx, entry in enumerate(manual.get("different_person") or []):
            if not isinstance(entry, Mapping):
                raise ValueError(f"{cfg_path}: different_person[{idx}] must be an object")
            name = normalize_player_name(entry.get("player_name"))
            ids_raw = entry.get("player_ids") or []
            if not name or not isinstance(ids_raw, list) or not ids_raw:
                raise ValueError(f"{cfg_path}: different_person[{idx}] needs player_name and player_ids")
            ids = frozenset(normalize_player_id(x) for x in ids_raw if normalize_player_id(x))
            if not ids:
                raise ValueError(f"{cfg_path}: different_person[{idx}] has no valid player_ids")
            different_groups.append(DifferentPersonGroup(player_name=name, player_ids=ids))

    return PlayerIdNameNormalizationConfig(
        remap_rules=tuple(rules),
        different_person_groups=tuple(different_groups),
    )


def load_player_id_name_remapping_rules(path: Path | None = None) -> List[PlayerIdNameRemapRule]:
    return list(load_player_id_name_normalization_config(path).remap_rules)


def different_person_id_sets_for_name(
    player_name: str,
    config: PlayerIdNameNormalizationConfig | None = None,
    *,
    config_path: Path | None = None,
) -> List[FrozenSet[str]]:
    cfg = config or load_player_id_name_normalization_config(config_path)
    name = normalize_player_name(player_name)
    return [group.player_ids for group in cfg.different_person_groups if group.player_name == name]


def is_different_person_name_group(player_name: str, player_ids: Set[str], *, config_path: Path | None = None) -> bool:
    """True when this exact name+id set is a registered different-person group."""
    if len(player_ids) < 2:
        return False
    normalized = {normalize_player_id(pid) for pid in player_ids if normalize_player_id(pid)}
    for group_ids in different_person_id_sets_for_name(player_name, config_path=config_path):
        if group_ids == frozenset(normalized):
            return True
    return False


def compute_player_id_name_normalization_fingerprint(path: Path | None = None) -> str:
    cfg_path = _config_path(path)
    if not cfg_path.is_file():
        return "missing"
    digest = hashlib.sha256(cfg_path.read_bytes()).hexdigest()
    return digest[:12]


def apply_player_id_name_normalization(
    df,
    rules: List[PlayerIdNameRemapRule] | None = None,
    *,
    config_path: Path | None = None,
) -> Tuple[Any, Dict[str, int]]:
    """
    Apply curated remappings in file order. Returns (df, rows_changed_per_rule_label).
    """
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return df, {}

    if rules is None:
        rules = load_player_id_name_remapping_rules(config_path)
    rules = list(rules)
    if not rules:
        return df, {}

    id_col = Columns.player_id
    name_col = Columns.player_name
    if id_col not in df.columns or name_col not in df.columns:
        return df, {}

    out = df.copy()
    stats: Dict[str, int] = {}
    pid_series = out[id_col].map(normalize_player_id)
    name_series = out[name_col].map(normalize_player_name)

    for rule in rules:
        mask = pid_series.eq(rule.match_player_id) & name_series.eq(rule.match_player_name)
        changed = int(mask.sum())
        if changed <= 0:
            stats[rule.label()] = 0
            continue
        if rule.replace_player_id is not None:
            out.loc[mask, id_col] = rule.replace_player_id
            pid_series = out[id_col].map(normalize_player_id)
        if rule.replace_player_name is not None:
            out.loc[mask, name_col] = rule.replace_player_name
            name_series = out[name_col].map(normalize_player_name)
        stats[rule.label()] = changed

    return out, stats


def format_normalization_summary(stats: Mapping[str, int]) -> str:
    if not stats:
        return "Player ID/name normalization: no rules configured"
    applied = {k: v for k, v in stats.items() if v > 0}
    if not applied:
        return f"Player ID/name normalization: {len(stats)} rule(s), 0 rows changed"
    lines = [f"Player ID/name normalization: {sum(applied.values())} row(s) changed"]
    for label, count in sorted(applied.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"  {count:5d}  {label}")
    unchanged = len(stats) - len(applied)
    if unchanged:
        lines.append(f"  ({unchanged} rule(s) matched 0 rows)")
    return "\n".join(lines)
