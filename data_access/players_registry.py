"""Central players registry — canonical id + display name (Phase 2b)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Set, Tuple

import pandas as pd

from data_access.player_id_name_normalization import (
    load_player_id_name_normalization_config,
    normalize_player_id,
    normalize_player_name,
)
from data_access.player_name_normalization import (
    canonicalize_player_name,
    group_canonical_target,
    normalize_player_label,
    parse_player_name_parts,
)
from data_access.player_name_normalization_config import (
    load_player_name_normalization_config,
)
from data_access.schema import Columns

REGISTRY_COLUMNS = ("player_id", "canonical_name", "source", "updated_at", "aliases")
REGISTRY_FORMAT_VERSION = 1

# Same-given-name typo threshold (SequenceMatcher ratio on normalized full labels).
CLOSE_MATCH_RATIO = 0.85

_SOURCE_PRIORITY: Dict[str, int] = {
    "dbu_id": 100,
    "manual": 80,
    "registry": 75,
    "majority": 50,
    "name_reassembly": 45,
    "autoresolve": 30,
    "same_person_alias": 20,
    "config": 10,
}

# Sources that may set or replace ``canonical_name`` during a registry merge.
_TRUSTED_CANONICAL_SOURCES = frozenset({"dbu_id", "manual", "registry", "same_person_alias"})

# Observed-data heuristics may only add aliases — never pick canonical from row counts.
_ALIAS_ONLY_SOURCES = frozenset({"majority", "autoresolve", "name_reassembly"})


def _source_priority(source: str) -> int:
    key = str(source or "").strip().lower()
    return _SOURCE_PRIORITY.get(key, 5)


def _source_allows_canonical_change(source: str) -> bool:
    key = str(source or "").strip().lower()
    if key in _ALIAS_ONLY_SOURCES:
        return False
    if key in _TRUSTED_CANONICAL_SOURCES:
        return True
    return key not in _ALIAS_ONLY_SOURCES and key != "config"


def _registry_path() -> Path:
    from database.paths import players_registry_csv

    return players_registry_csv()


def _given_token(name: str) -> str:
    _, given = parse_player_name_parts(normalize_player_label(name))
    return given.strip().lower()


def _name_similarity(left: str, right: str) -> float:
    a = normalize_player_label(left).lower()
    b = normalize_player_label(right).lower()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def candidate_names_for_entry(entry: Mapping[str, str]) -> List[str]:
    out: List[str] = []
    canon = normalize_player_label(str(entry.get("canonical_name") or ""))
    if canon:
        out.append(canon)
    for part in str(entry.get("aliases") or "").split("|"):
        label = normalize_player_label(part)
        if label and label not in out:
            out.append(label)
    return out


def candidate_names_normalized(entry: Mapping[str, str]) -> Set[str]:
    return {normalize_player_label(name) for name in candidate_names_for_entry(entry)}


@lru_cache(maxsize=1)
def load_players_registry_df() -> Optional[pd.DataFrame]:
    """Load published registry Parquet/CSV, or ``None`` when absent."""
    from data_access.parquet_sidecar import data_file_exists, resolve_load_path

    logical = _registry_path()
    if not data_file_exists(logical):
        return None
    load_path = resolve_load_path(logical)
    if load_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(load_path)
    else:
        df = pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)
    if df is None or df.empty:
        return None
    missing = [c for c in REGISTRY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"players registry missing columns: {missing}")
    return df


def registry_lookup_by_id(registry: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    """``player_id`` -> registry row fields (canonical_name, aliases, …)."""
    out: Dict[str, Dict[str, str]] = {}
    for row in registry.itertuples(index=False):
        pid = normalize_player_id(getattr(row, "player_id", ""))
        if not pid:
            continue
        out[pid] = {
            "canonical_name": normalize_player_name(getattr(row, "canonical_name", "")),
            "aliases": str(getattr(row, "aliases", "") or "").strip(),
            "source": str(getattr(row, "source", "") or "").strip(),
        }
    return out


def resolve_player_name_for_id(
    raw_name: str,
    player_id: str,
    lookup: Mapping[str, Mapping[str, str]],
    *,
    close_match_ratio: float = CLOSE_MATCH_RATIO,
) -> Tuple[Optional[str], str]:
    """
    Resolve a raw label to the closest registered name (canonical or alias).

    Returns ``(resolved_name, kind)`` where kind is one of:
    ``exact``, ``reassembly``, ``close``, ``unresolved``, ``no_registry``, ``missing``.
    """
    pid = normalize_player_id(player_id)
    raw = normalize_player_label(raw_name)
    if not pid or not raw:
        return None, "missing"

    entry = lookup.get(pid)
    if not entry:
        return None, "no_registry"

    candidates = candidate_names_for_entry(entry)
    if not candidates:
        return None, "no_registry"

    norm_to_display = {normalize_player_label(c): c for c in candidates}
    if raw in norm_to_display:
        return norm_to_display[raw], "exact"

    target = group_canonical_target([raw] + candidates)
    if target:
        for candidate in candidates:
            normalized = normalize_player_label(candidate)
            if normalized == target or canonicalize_player_name(candidate) == target:
                return candidate, "reassembly"
        return target, "reassembly"

    raw_given = _given_token(raw)
    if not raw_given:
        return None, "unresolved"

    same_given = [candidate for candidate in candidates if _given_token(candidate) == raw_given]
    if not same_given:
        return None, "unresolved"

    best = max(same_given, key=lambda candidate: _name_similarity(raw, candidate))
    if _name_similarity(raw, best) >= close_match_ratio:
        return best, "close"

    return None, "unresolved"


def registry_accepts_all_names_for_id(
    player_id: str,
    names: Set[str] | Iterable[str],
    lookup: Mapping[str, Mapping[str, str]],
) -> bool:
    """
    True when every observed name is an exact alias or resolvable (typo/format).

    Legitimate multi-surname players (all names registered) do not conflict.
    """
    pid = normalize_player_id(player_id)
    if not pid:
        return False
    entry = lookup.get(pid)
    if not entry:
        return False

    registered = candidate_names_normalized(entry)
    for name in names:
        normalized = normalize_player_label(name)
        if not normalized:
            continue
        if normalized in registered:
            continue
        resolved, kind = resolve_player_name_for_id(name, pid, lookup)
        if resolved is None or kind == "unresolved":
            return False
    return True


def compute_players_registry_fingerprint(registry: Optional[pd.DataFrame] = None) -> str:
    df = registry if registry is not None else load_players_registry_df()
    if df is None or df.empty:
        return "missing"
    subset = df[list(REGISTRY_COLUMNS)].fillna("").astype(str)
    blob = subset.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _parse_aliases_field(raw: str) -> Set[str]:
    return {normalize_player_label(part) for part in str(raw or "").split("|") if normalize_player_label(part)}


def _join_aliases(aliases: Set[str]) -> str:
    return "|".join(sorted(aliases))


def _upsert_alias_only(
    entries: MutableMapping[str, Dict[str, Any]],
    *,
    player_id: str,
    alias: str,
) -> None:
    """Add an alias to an existing entry; never create a row from low-trust data alone."""
    pid = normalize_player_id(player_id)
    label = normalize_player_label(alias)
    if not pid or not label:
        return
    slot = entries.get(pid)
    if slot is None:
        return
    canonical = normalize_player_label(str(slot.get("canonical_name") or ""))
    if label != canonical:
        slot["aliases"].add(label)


def _upsert_entry(
    entries: MutableMapping[str, Dict[str, Any]],
    *,
    player_id: str,
    canonical_name: str,
    source: str,
    alias: str = "",
    allow_canonical: bool = True,
) -> None:
    pid = normalize_player_id(player_id)
    name = normalize_player_name(canonical_name)
    if not pid or not name:
        return
    source_key = str(source or "config").strip()
    priority = _source_priority(source_key)
    slot = entries.get(pid)

    if not allow_canonical or not _source_allows_canonical_change(source_key):
        if slot is None:
            return
        if alias:
            _upsert_alias_only(entries, player_id=pid, alias=alias)
        if name != normalize_player_label(str(slot.get("canonical_name") or "")):
            _upsert_alias_only(entries, player_id=pid, alias=name)
        return

    if slot is None or priority >= int(slot["priority"]):
        aliases: Set[str] = set(slot.get("aliases") or set()) if slot else set()
        if alias and alias != name:
            aliases.add(normalize_player_label(alias))
        if slot and priority < int(slot["priority"]):
            aliases |= set(slot.get("aliases") or set())
        entries[pid] = {
            "player_id": pid,
            "canonical_name": name,
            "source": source_key or "config",
            "priority": priority,
            "aliases": aliases,
        }
    else:
        if alias and alias != name:
            slot["aliases"].add(normalize_player_label(alias))


def _apply_remap_rule(
    entries: MutableMapping[str, Dict[str, Any]],
    *,
    player_id: str,
    match_name: str,
    replace_name: str,
    source: str,
) -> None:
    final_id = normalize_player_id(player_id)
    match = normalize_player_label(match_name)
    replace = normalize_player_label(replace_name)
    if not final_id or not match:
        return
    source_key = str(source or "config").strip()
    if _source_allows_canonical_change(source_key):
        _upsert_entry(
            entries,
            player_id=final_id,
            canonical_name=replace or match,
            source=source_key,
            alias=match if match != (replace or match) else "",
        )
        return
    slot = entries.get(final_id)
    if slot is None:
        return
    if match:
        _upsert_alias_only(entries, player_id=final_id, alias=match)
    if replace and replace != match:
        _upsert_alias_only(entries, player_id=final_id, alias=replace)


def _collect_from_id_name_config(entries: MutableMapping[str, Dict[str, Any]]) -> None:
    cfg = load_player_id_name_normalization_config()
    for rule in cfg.remap_rules:
        final_id = rule.replace_player_id or rule.match_player_id
        final_name = rule.replace_player_name or rule.match_player_name
        _apply_remap_rule(
            entries,
            player_id=final_id,
            match_name=rule.match_player_name,
            replace_name=final_name,
            source=rule.source or "config",
        )


def _collect_from_name_config(entries: MutableMapping[str, Dict[str, Any]]) -> None:
    cfg = load_player_name_normalization_config()
    for rule in cfg.remap_rules:
        final_id = rule.replace_player_id or rule.match_player_id
        final_name = rule.replace_player_name or rule.match_player_name
        _apply_remap_rule(
            entries,
            player_id=final_id,
            match_name=rule.match_player_name,
            replace_name=final_name,
            source=rule.source or "config",
        )
    for group in cfg.same_person_groups:
        pid = normalize_player_id(group.player_id)
        if not pid:
            continue
        # Preserve JSON list order — operator intent, not alphabetical or row-count dominance.
        names = list(group.player_names)
        if len(names) < 2:
            continue
        slot = entries.get(pid)
        if slot:
            canonical = normalize_player_label(str(slot["canonical_name"]))
            for label in names:
                if label != canonical:
                    _upsert_alias_only(entries, player_id=pid, alias=label)
            continue
        primary = names[0]
        _upsert_entry(
            entries,
            player_id=pid,
            canonical_name=primary,
            source="same_person_alias",
        )
        for alt in names[1:]:
            _upsert_alias_only(entries, player_id=pid, alias=alt)


def _entries_to_dataframe(entries: Mapping[str, Dict[str, Any]], *, updated_at: str) -> pd.DataFrame:
    rows: List[Dict[str, str]] = []
    for pid in sorted(entries):
        slot = entries[pid]
        aliases = sorted(a for a in slot.get("aliases") or set() if a)
        rows.append(
            {
                "player_id": pid,
                "canonical_name": str(slot["canonical_name"]),
                "source": str(slot["source"]),
                "updated_at": updated_at,
                "aliases": _join_aliases(set(aliases)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=list(REGISTRY_COLUMNS))
    return pd.DataFrame(rows, columns=list(REGISTRY_COLUMNS))


def _should_replace_canonical(
    *,
    existing_source: str,
    existing_canonical: str,
    new_source: str,
    new_canonical: str,
) -> bool:
    new_name = normalize_player_label(new_canonical)
    if not new_name:
        return False
    if not _source_allows_canonical_change(new_source):
        return False
    if not normalize_player_label(existing_canonical):
        return True
    return _source_priority(new_source) > _source_priority(existing_source)


def merge_registry_dataframes(
    base: pd.DataFrame,
    updates: pd.DataFrame,
    *,
    updated_at: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Merge config-derived updates into the published registry.

    Published rows are kept; aliases accumulate; canonical changes only on higher-trust source.
    """
    moment = (updated_at or datetime.now(timezone.utc)).isoformat()
    merged: Dict[str, Dict[str, str]] = {}
    for row in base.itertuples(index=False):
        pid = normalize_player_id(getattr(row, "player_id", ""))
        if not pid:
            continue
        merged[pid] = {
            "player_id": pid,
            "canonical_name": normalize_player_name(getattr(row, "canonical_name", "")),
            "source": str(getattr(row, "source", "") or "registry"),
            "updated_at": str(getattr(row, "updated_at", "") or moment),
            "aliases": _join_aliases(_parse_aliases_field(str(getattr(row, "aliases", "") or ""))),
        }

    for row in updates.itertuples(index=False):
        pid = normalize_player_id(getattr(row, "player_id", ""))
        if not pid:
            continue
        new_aliases = _parse_aliases_field(str(getattr(row, "aliases", "") or ""))
        new_canonical = normalize_player_name(getattr(row, "canonical_name", ""))
        new_source = str(getattr(row, "source", "") or "config")

        if pid not in merged:
            merged[pid] = {
                "player_id": pid,
                "canonical_name": new_canonical,
                "source": new_source,
                "updated_at": moment,
                "aliases": _join_aliases(new_aliases),
            }
            continue

        slot = merged[pid]
        existing_aliases = _parse_aliases_field(slot["aliases"])
        all_aliases = existing_aliases | new_aliases
        existing_canonical = normalize_player_label(slot["canonical_name"])
        if existing_canonical:
            all_aliases.discard(existing_canonical)
        if new_canonical and normalize_player_label(new_canonical) != existing_canonical:
            all_aliases.add(normalize_player_label(new_canonical))

        if _should_replace_canonical(
            existing_source=slot["source"],
            existing_canonical=slot["canonical_name"],
            new_source=new_source,
            new_canonical=new_canonical,
        ):
            slot["canonical_name"] = new_canonical
            slot["source"] = new_source
            slot["updated_at"] = moment
            all_aliases.discard(normalize_player_label(new_canonical))

        slot["aliases"] = _join_aliases(all_aliases)

    return pd.DataFrame([merged[pid] for pid in sorted(merged)], columns=list(REGISTRY_COLUMNS))


def build_registry_dataframe(*, updated_at: Optional[datetime] = None) -> pd.DataFrame:
    """Build registry update rows from normalization JSON configs (not a full replace)."""
    moment = (updated_at or datetime.now(timezone.utc)).isoformat()
    entries: Dict[str, Dict[str, Any]] = {}
    _collect_from_id_name_config(entries)
    _collect_from_name_config(entries)

    return _entries_to_dataframe(entries, updated_at=moment)


def write_players_registry(
    df: pd.DataFrame,
    *,
    write_csv: bool = False,
) -> Dict[str, str]:
    """Publish registry to ``database/data/players_registry.parquet``."""
    from data_access.parquet_sidecar import publish_dataframe

    out_path = _registry_path()
    published = publish_dataframe(df, out_path, write_csv=write_csv, sep=";")
    load_players_registry_df.cache_clear()
    return published


def build_and_publish_players_registry(
    *,
    write_csv: bool = False,
    from_scratch: bool = False,
    aktive_root: Optional[Path] = None,
    skip_aktive_import: bool = False,
) -> Dict[str, Any]:
    """
    Publish registry updates.

    Import order (each step merges into the prior result):

    1. Existing published registry (unless ``from_scratch``)
    2. *Aktive Mitglieder* season workbooks from legacy scrape (unless skipped)
    3. Normalization JSON configs (manual / same_person overrides)

    ``from_scratch=True`` omits the existing published file but still imports Aktive
    workbooks and configs unless ``skip_aktive_import`` is set.
    """
    from data_access.aktive_mitglieder_registry import (
        build_registry_dataframe_from_aktive,
        format_aktive_import_summary,
    )

    moment = datetime.now(timezone.utc)
    moment_iso = moment.isoformat()
    layers: List[pd.DataFrame] = []

    if not from_scratch:
        existing = load_players_registry_df()
        if existing is not None and not existing.empty:
            layers.append(existing)

    aktive_stats = None
    if not skip_aktive_import:
        aktive_df, aktive_stats = build_registry_dataframe_from_aktive(
            aktive_root,
            updated_at=moment_iso,
        )
        if aktive_df is not None and not aktive_df.empty:
            layers.append(aktive_df)

    config_updates = build_registry_dataframe(updated_at=moment)
    if config_updates is not None and not config_updates.empty:
        layers.append(config_updates)

    if not layers:
        merged = pd.DataFrame(columns=list(REGISTRY_COLUMNS))
    else:
        merged = layers[0]
        for layer in layers[1:]:
            merged = merge_registry_dataframes(merged, layer, updated_at=moment)

    published = write_players_registry(merged, write_csv=write_csv)
    logical = _registry_path()
    summary: Dict[str, Any] = {
        "row_count": int(len(merged)),
        "update_rows_from_config": int(len(config_updates)),
        "from_scratch": bool(from_scratch),
        "merged": not from_scratch,
        "aktive_import": {
            "skipped": bool(skip_aktive_import),
            "seasons_selected": int(getattr(aktive_stats, "seasons_selected", 0) or 0),
            "workbooks_parsed": int(getattr(aktive_stats, "workbooks_parsed", 0) or 0),
            "workbooks_failed": int(getattr(aktive_stats, "workbooks_failed", 0) or 0),
            "player_rows": int(getattr(aktive_stats, "player_rows", 0) or 0),
            "unique_player_ids": int(getattr(aktive_stats, "unique_player_ids", 0) or 0),
            "failures": list(getattr(aktive_stats, "failures", []) or []),
            "seasons": list(getattr(aktive_stats, "seasons", []) or []),
        },
        "paths": {
            "output": str(logical.resolve()),
            "parquet_output": str(published["parquet"]),
            "csv_output": str(published.get("csv") or ""),
        },
        "fingerprint": compute_players_registry_fingerprint(merged),
    }
    if aktive_stats is not None:
        summary["aktive_import_summary"] = format_aktive_import_summary(aktive_stats)
    return summary


def apply_players_registry(
    df: pd.DataFrame,
    registry: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Resolve ``Player`` via registry: exact match, format reassembly, or close typo.

    Unresolved rows are left unchanged for the audit report.
    """
    if df is None or df.empty:
        return df, {}
    if Columns.player_id not in df.columns or Columns.player_name not in df.columns:
        return df, {}

    reg = registry if registry is not None else load_players_registry_df()
    if reg is None or reg.empty:
        return df, {}

    lookup = registry_lookup_by_id(reg)
    if not lookup:
        return df, {}

    out = df.copy()
    stats: Dict[str, int] = {
        "registry_exact": 0,
        "registry_reassembly": 0,
        "registry_close": 0,
        "registry_unchanged": 0,
    }

    for idx, row in out.iterrows():
        pid = normalize_player_id(row[Columns.player_id])
        raw = normalize_player_label(row[Columns.player_name])
        if not pid or not raw:
            continue
        resolved, kind = resolve_player_name_for_id(raw, pid, lookup)
        if resolved is None or kind == "unresolved":
            stats["registry_unchanged"] += 1
            continue
        if normalize_player_label(resolved) == raw:
            stats["registry_unchanged"] += 1
            continue
        out.at[idx, Columns.player_name] = resolved
        if kind == "exact":
            stats["registry_exact"] += 1
        elif kind == "reassembly":
            stats["registry_reassembly"] += 1
        elif kind == "close":
            stats["registry_close"] += 1

    return out, stats


def format_registry_apply_summary(stats: Mapping[str, int]) -> str:
    if not stats:
        return "Players registry: not applied"
    changed = int(stats.get("registry_exact", 0)) + int(stats.get("registry_reassembly", 0)) + int(
        stats.get("registry_close", 0)
    )
    if changed <= 0:
        return "Players registry: 0 row(s) changed"
    lines = [f"Players registry: {changed} row(s) changed"]
    for key in ("registry_exact", "registry_reassembly", "registry_close"):
        count = int(stats.get(key, 0))
        if count:
            lines.append(f"  {count:5d}  {key}")
    unchanged = int(stats.get("registry_unchanged", 0))
    if unchanged:
        lines.append(f"  ({unchanged} row(s) left for audit)")
    return "\n".join(lines)


def canonical_name_for_player_id(player_id: str, registry: Optional[pd.DataFrame] = None) -> str:
    """Preferred display label for Spieler catalog (canonical, not alias)."""
    pid = normalize_player_id(player_id)
    if not pid:
        return ""
    reg = registry if registry is not None else load_players_registry_df()
    if reg is None or reg.empty:
        return ""
    lookup = registry_lookup_by_id(reg)
    entry = lookup.get(pid)
    return entry["canonical_name"] if entry else ""
