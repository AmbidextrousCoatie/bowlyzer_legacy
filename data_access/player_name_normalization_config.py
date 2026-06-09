"""
Curated player display-name fixes from annotated MULTI_NAME audit CSV.

Config: ``database/config/player_name_normalization.json``

Blocks:
  - ``manual_resolutions.dbu_id`` — official name (player_id + raw name -> assigned name)
  - ``manual_resolutions.missing_id`` — name OK, official id (player_id -> assigned id)
  - ``manual_resolutions.same_person`` — multiple valid names for one id (e.g. marriage)
  - ``autoresolve_remappings`` — majority / name_reassembly from audit
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, MutableMapping, Optional, Set, Tuple

from data_access.player_id_name_normalization import normalize_player_id
from data_access.player_name_normalization import normalize_player_label
from data_access.schema import Columns

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "database" / "config" / "player_name_normalization.json"
)


@dataclass(frozen=True)
class PlayerNameRemapRule:
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
class SamePersonNameGroup:
    player_id: str
    player_names: Tuple[str, ...]


@dataclass(frozen=True)
class PlayerNameNormalizationConfig:
    remap_rules: Tuple[PlayerNameRemapRule, ...]
    same_person_groups: Tuple[SamePersonNameGroup, ...]


def _config_path(path: Path | None = None) -> Path:
    return (path or DEFAULT_CONFIG_PATH).resolve()


def _parse_remap_entry(entry: Mapping[str, Any], *, idx: int, cfg_path: Path, block: str) -> PlayerNameRemapRule:
    match = entry.get("match")
    if not isinstance(match, Mapping):
        raise ValueError(f"{cfg_path}: {block}[{idx}].match must be an object")
    match_id = normalize_player_id(match.get("player_id"))
    match_name = normalize_player_label(match.get("player_name"))
    if not match_id or not match_name:
        raise ValueError(f"{cfg_path}: {block}[{idx}].match requires player_id and player_name")

    replace = entry.get("replace") or {}
    if replace and not isinstance(replace, Mapping):
        raise ValueError(f"{cfg_path}: {block}[{idx}].replace must be an object")

    replace_id_raw = replace.get("player_id") if isinstance(replace, Mapping) else None
    replace_name_raw = replace.get("player_name") if isinstance(replace, Mapping) else None
    replace_id = normalize_player_id(replace_id_raw) if replace_id_raw not in (None, "") else None
    replace_name = normalize_player_label(replace_name_raw) if replace_name_raw not in (None, "") else None
    if replace_id is None and replace_name is None:
        raise ValueError(f"{cfg_path}: {block}[{idx}].replace needs player_id and/or player_name")

    return PlayerNameRemapRule(
        match_player_id=match_id,
        match_player_name=match_name,
        replace_player_id=replace_id,
        replace_player_name=replace_name,
        note=str(entry.get("note") or "").strip(),
        source=str(entry.get("source") or block).strip(),
    )


def load_player_name_normalization_config(path: Path | None = None) -> PlayerNameNormalizationConfig:
    cfg_path = _config_path(path)
    if not cfg_path.is_file():
        return PlayerNameNormalizationConfig(remap_rules=(), same_person_groups=())

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, MutableMapping):
        raise ValueError(f"{cfg_path}: root must be a JSON object")

    rules: List[PlayerNameRemapRule] = []
    seen: Set[Tuple[str, str]] = set()

    def _add_rule(rule: PlayerNameRemapRule) -> None:
        key = (rule.match_player_name, rule.match_player_id)
        if key in seen:
            return
        seen.add(key)
        rules.append(rule)

    manual = raw.get("manual_resolutions") or {}
    if isinstance(manual, Mapping):
        for block in ("dbu_id", "missing_id"):
            for idx, entry in enumerate(manual.get(block) or []):
                if isinstance(entry, Mapping):
                    _add_rule(_parse_remap_entry(entry, idx=idx, cfg_path=cfg_path, block=f"manual_resolutions.{block}"))

    for idx, entry in enumerate(raw.get("autoresolve_remappings") or []):
        if isinstance(entry, Mapping):
            _add_rule(_parse_remap_entry(entry, idx=idx, cfg_path=cfg_path, block="autoresolve_remappings"))

    same_person_groups: List[SamePersonNameGroup] = []
    if isinstance(manual, Mapping):
        for idx, entry in enumerate(manual.get("same_person") or []):
            if not isinstance(entry, Mapping):
                raise ValueError(f"{cfg_path}: same_person[{idx}] must be an object")
            pid = normalize_player_id(entry.get("player_id"))
            names_raw = entry.get("player_names") or []
            if not pid or not isinstance(names_raw, list) or len(names_raw) < 2:
                raise ValueError(f"{cfg_path}: same_person[{idx}] needs player_id and 2+ player_names")
            seen: Set[str] = set()
            names: List[str] = []
            for raw_name in names_raw:
                label = normalize_player_label(raw_name)
                if not label or label in seen:
                    continue
                seen.add(label)
                names.append(label)
            if len(names) < 2:
                raise ValueError(f"{cfg_path}: same_person[{idx}] has fewer than 2 valid player_names")
            same_person_groups.append(SamePersonNameGroup(player_id=pid, player_names=tuple(names)))

    return PlayerNameNormalizationConfig(
        remap_rules=tuple(rules),
        same_person_groups=tuple(same_person_groups),
    )


def load_player_name_remapping_rules(path: Path | None = None) -> List[PlayerNameRemapRule]:
    return list(load_player_name_normalization_config(path).remap_rules)


def is_same_person_name_group(
    player_id: str,
    player_names: Set[str],
    *,
    config_path: Path | None = None,
) -> bool:
    """True when observed names are a subset of a registered same-person alias set."""
    pid = normalize_player_id(player_id)
    normalized = {normalize_player_label(name) for name in player_names if normalize_player_label(name)}
    if len(normalized) < 2:
        return False
    for group in load_player_name_normalization_config(config_path).same_person_groups:
        if group.player_id == pid and normalized.issubset(frozenset(group.player_names)):
            return True
    return False


def compute_player_name_normalization_fingerprint(path: Path | None = None) -> str:
    cfg_path = _config_path(path)
    if not cfg_path.is_file():
        return "missing"
    return hashlib.sha256(cfg_path.read_bytes()).hexdigest()[:12]


def apply_player_name_normalization(
    df,
    rules: List[PlayerNameRemapRule] | None = None,
    *,
    config_path: Path | None = None,
) -> Tuple[Any, Dict[str, int]]:
    """Apply curated name/id remappings in file order. Returns (df, rows_changed_per_rule_label)."""
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return df, {}

    if rules is None:
        rules = load_player_name_remapping_rules(config_path)
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
    name_series = out[name_col].map(normalize_player_label)

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
            name_series = out[name_col].map(normalize_player_label)
        stats[rule.label()] = changed

    return out, stats


def format_normalization_summary(stats: Mapping[str, int]) -> str:
    if not stats:
        return "Player name normalization: no rules configured"
    applied = {k: v for k, v in stats.items() if v > 0}
    if not applied:
        return f"Player name normalization: {len(stats)} rule(s), 0 rows changed"
    lines = [f"Player name normalization: {sum(applied.values())} row(s) changed"]
    for label, count in sorted(applied.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"  {count:5d}  {label}")
    unchanged = len(stats) - len(applied)
    if unchanged:
        lines.append(f"  ({unchanged} rule(s) matched 0 rows)")
    return "\n".join(lines)
