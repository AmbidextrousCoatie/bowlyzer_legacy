"""Central players registry — canonical id + display name (Phase 2b)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

import pandas as pd

from data_access.player_id_name_normalization import (
    load_player_id_name_normalization_config,
    normalize_player_id,
    normalize_player_name,
)
from data_access.player_name_normalization import (
    canonicalize_player_name,
    given_names_substring_equivalent,
    group_canonical_target,
    name_identity_key,
    names_share_identity,
    normalize_player_label,
    parse_player_name_parts,
)
from data_access.player_name_normalization_config import (
    load_player_name_normalization_config,
)
from data_access.schema import Columns

REGISTRY_COLUMNS = (
    "player_id",
    "player_id_legacy",
    "player_id_pass",
    "canonical_name",
    "source",
    "updated_at",
    "aliases",
)
REGISTRY_FORMAT_VERSION = 2

# Same-given-name typo threshold (SequenceMatcher ratio on normalized full labels).
CLOSE_MATCH_RATIO = 0.85

# Dual typo: family and given may each be slightly off (``Pafford, Mark`` / ``Paffort, Marc``).
DUAL_TYPO_FAMILY_RATIO = 0.85
DUAL_TYPO_GIVEN_RATIO = 0.75

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


def _family_token(name: str) -> str:
    family, _ = parse_player_name_parts(normalize_player_label(name))
    return family.strip().lower()


def _given_similarity(left: str, right: str) -> float:
    a = _given_token(left)
    b = _given_token(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _family_similarity(left: str, right: str) -> float:
    a = _family_token(left)
    b = _family_token(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _given_is_short_form(raw_given: str, candidate_given: str) -> bool:
    """True when one given name is a prefix substring of the other (incl. ``Hans`` / ``Hans-Jürgen``)."""
    return given_names_substring_equivalent(raw_given, candidate_given)


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


def should_normalize_alias_to_canonical(raw_name: str, entry: Mapping[str, str]) -> bool:
    """
    True when ``raw_name`` is a registered alias that is only a format/spelling
    variant of ``canonical_name`` (not a distinct person such as a marriage name).
    """
    raw = normalize_player_label(raw_name)
    canonical = normalize_player_label(str(entry.get("canonical_name") or ""))
    if not raw or not canonical or raw == canonical:
        return False
    if raw not in candidate_names_normalized(entry):
        if names_share_identity(raw, canonical):
            return True
        return False
    target = group_canonical_target([raw, canonical])
    return bool(target and normalize_player_label(target) == canonical)


def _pick_reassembly_display(
    target: str,
    candidates: Sequence[str],
    canonical_display: str,
) -> str:
    norm_target = normalize_player_label(target)
    if canonical_display and names_share_identity(target, canonical_display):
        return canonical_display
    matches: List[str] = []
    for candidate in candidates:
        normalized = normalize_player_label(candidate)
        if normalized == norm_target or canonicalize_player_name(candidate) == norm_target:
            matches.append(candidate)
        elif names_share_identity(target, candidate):
            matches.append(candidate)
    if canonical_display in matches:
        return canonical_display
    comma_matches = [match for match in matches if "," in match]
    if comma_matches:
        return sorted(comma_matches, key=lambda label: label.lower())[0]
    if matches:
        return matches[0]
    return target


def _resolve_pairwise_reassembly(
    raw: str,
    candidates: Sequence[str],
    canonical_display: str,
) -> Optional[str]:
    """Match ``Given Family`` / reversed labels against one registry candidate at a time."""
    hits: List[str] = []
    for candidate in candidates:
        target = group_canonical_target([raw, candidate])
        if not target:
            continue
        hits.append(_pick_reassembly_display(target, candidates, canonical_display))
    if not hits:
        return None
    return max(hits, key=lambda label: _name_similarity(raw, label))


def _resolve_identity_match(
    raw: str,
    candidates: Sequence[str],
    canonical_display: str,
) -> Optional[str]:
    """
    Match after von/van particle normalization and sen/jun stripping (same person, different eras).
    """
    raw_key = name_identity_key(raw)
    if not raw_key[0] and not raw_key[1]:
        return None
    matches = [candidate for candidate in candidates if name_identity_key(candidate) == raw_key]
    if not matches and canonical_display and name_identity_key(canonical_display) == raw_key:
        return canonical_display
    if not matches:
        return None
    if canonical_display in matches:
        return canonical_display
    comma_matches = [match for match in matches if "," in match]
    if comma_matches:
        return sorted(comma_matches, key=lambda label: label.lower())[0]
    return matches[0]


def _resolve_substring_given(
    raw: str,
    candidates: Sequence[str],
    canonical_display: str,
) -> Optional[str]:
    """Same family + bidirectional given substring (``Alex`` / ``Alexander``, ``Carina`` / ``Carina Mareen``)."""
    raw_family = _family_token(raw)
    raw_given = _given_token(raw)
    if not raw_family or not raw_given:
        return None
    matches = [
        candidate
        for candidate in candidates
        if _family_token(candidate) == raw_family
        and given_names_substring_equivalent(raw_given, _given_token(candidate))
    ]
    if not matches:
        return None
    if canonical_display in matches:
        return canonical_display
    return max(matches, key=lambda label: (len(_given_token(label)), _name_similarity(raw, label)))


def _resolve_abbreviated_given(
    raw: str,
    candidates: Sequence[str],
    canonical_display: str,
) -> Optional[str]:
    """Same family + shortened given (``Hans`` for ``Hans-Jürgen``) when ID is already known."""
    raw_family = _family_token(raw)
    raw_given = _given_token(raw)
    if not raw_family or not raw_given:
        return None
    matches = [
        candidate
        for candidate in candidates
        if _family_token(candidate) == raw_family
        and _given_is_short_form(raw_given, _given_token(candidate))
    ]
    if not matches:
        return None
    if canonical_display in matches:
        return canonical_display
    return max(matches, key=lambda label: (len(_given_token(label)), _name_similarity(raw, label)))


def _resolve_close_match(
    raw: str,
    candidates: Sequence[str],
    *,
    close_match_ratio: float,
) -> Optional[str]:
    """Typo tolerance: same given name, dual family+given typos, or similar given (Dominic/Dominik)."""
    dual_matches = [
        candidate
        for candidate in candidates
        if _family_similarity(raw, candidate) >= DUAL_TYPO_FAMILY_RATIO
        and _given_similarity(raw, candidate) >= DUAL_TYPO_GIVEN_RATIO
    ]
    if dual_matches:
        return max(
            dual_matches,
            key=lambda candidate: (
                _family_similarity(raw, candidate),
                _given_similarity(raw, candidate),
                _name_similarity(raw, candidate),
            ),
        )

    raw_given = _given_token(raw)
    if raw_given:
        same_given = [candidate for candidate in candidates if _given_token(candidate) == raw_given]
        if same_given:
            best = max(same_given, key=lambda candidate: _name_similarity(raw, candidate))
            if _name_similarity(raw, best) >= close_match_ratio:
                return best

    raw_family = _family_token(raw)
    if raw_family:
        same_family = [candidate for candidate in candidates if _family_token(candidate) == raw_family]
        if same_family:
            best = max(
                same_family,
                key=lambda candidate: (
                    _given_similarity(raw, candidate),
                    _name_similarity(raw, candidate),
                ),
            )
            if (
                _given_similarity(raw, best) >= close_match_ratio
                or _name_similarity(raw, best) >= close_match_ratio
            ):
                return best

    best_overall = max(candidates, key=lambda candidate: _name_similarity(raw, candidate))
    if _name_similarity(raw, best_overall) >= close_match_ratio:
        return best_overall
    return None


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
    for col in REGISTRY_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[list(REGISTRY_COLUMNS)]


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
            "player_id_legacy": str(getattr(row, "player_id_legacy", "") or "").strip(),
            "player_id_pass": str(getattr(row, "player_id_pass", "") or "").strip(),
        }
    return out


def build_legacy_player_id_remap(
    registry: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """
    Map ``player_id_legacy`` values → canonical ``player_id``.

    Used for id-only remapping of historical league/tournament rows.
    """
    df = registry if registry is not None else load_players_registry_df()
    out: Dict[str, str] = {}
    if df is None or df.empty or "player_id_legacy" not in df.columns:
        return out
    for row in df.itertuples(index=False):
        canonical = normalize_player_id(getattr(row, "player_id", ""))
        if not canonical:
            continue
        for legacy in str(getattr(row, "player_id_legacy", "") or "").split("|"):
            lid = normalize_player_id(legacy)
            if lid and lid != canonical and lid not in out:
                out[lid] = canonical
    return out


def apply_legacy_player_id_remapping(
    df: pd.DataFrame,
    remap: Optional[Mapping[str, str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Rewrite ``Player ID`` from legacy EDVs to canonical registry ``player_id``."""
    if df is None or df.empty or Columns.player_id not in df.columns:
        return df, {}
    mapping = remap if remap is not None else build_legacy_player_id_remap()
    if not mapping:
        return df, {"legacy_id_remapped": 0}

    out = df.copy()
    changed = 0
    for idx, raw in out[Columns.player_id].items():
        pid = normalize_player_id(raw)
        target = mapping.get(pid)
        if not target or target == pid:
            continue
        out.at[idx, Columns.player_id] = target
        changed += 1
    return out, {"legacy_id_remapped": changed}


def registry_name_index(registry: pd.DataFrame) -> Dict[str, str]:
    """Normalized display label -> ``player_id`` (first registry row wins on collision)."""
    lookup_by_id = registry_lookup_by_id(registry)
    out: Dict[str, str] = {}
    for pid, entry in lookup_by_id.items():
        for label in candidate_names_for_entry(entry):
            norm = normalize_player_label(label)
            if norm and norm not in out:
                out[norm] = pid
    return out


def resolve_player_id_for_name(
    raw_name: str,
    name_index: Mapping[str, str],
    lookup_by_id: Mapping[str, Mapping[str, str]],
    *,
    close_match_ratio: float = CLOSE_MATCH_RATIO,
) -> Tuple[Optional[str], str]:
    """
    Find a registry ``player_id`` for a raw label (exact, identity, or unique close match).

    Used for placeholder-ID rows where the observed EDV number is not trustworthy.
    """
    raw = normalize_player_label(raw_name)
    if not raw:
        return None, "missing"

    exact_pid = name_index.get(raw)
    if exact_pid:
        return exact_pid, "exact"

    identity_hits: List[Tuple[str, str, float]] = []
    close_hits: List[Tuple[str, str, float]] = []
    for pid, entry in lookup_by_id.items():
        for label in candidate_names_for_entry(entry):
            if names_share_identity(raw, label):
                identity_hits.append((pid, label, _name_similarity(raw, label)))
            elif _name_similarity(raw, label) >= close_match_ratio:
                close_hits.append((pid, label, _name_similarity(raw, label)))

    if identity_hits:
        best_pid, _, best_score = max(identity_hits, key=lambda item: item[2])
        same_pid = {pid for pid, _, _ in identity_hits}
        if len(same_pid) == 1 or best_score >= close_match_ratio:
            return best_pid, "identity"

    if not close_hits:
        return None, "unresolved"

    close_hits.sort(key=lambda item: (-item[2], item[0]))
    best_pid, _, best_score = close_hits[0]
    if len(close_hits) == 1:
        return best_pid, "close"
    second_score = close_hits[1][2]
    if best_score - second_score >= 0.05:
        return best_pid, "close"
    same_best = [pid for pid, _, score in close_hits if score >= best_score - 0.01]
    if len(set(same_best)) == 1:
        return best_pid, "close"
    canonicals = {
        normalize_player_label(str(lookup_by_id[pid].get("canonical_name") or ""))
        for pid in same_best
        if pid in lookup_by_id
    }
    canonicals.discard("")
    if len(canonicals) == 1:
        return sorted(same_best)[0], "close"
    return None, "unresolved"


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
    ``exact``, ``reassembly``, ``abbrev``, ``identity``, ``substring``, ``close``,
    ``unresolved``, ``no_registry``, ``missing``.
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

    canonical_display = str(entry.get("canonical_name") or "")
    reassembled = _resolve_pairwise_reassembly(raw, candidates, canonical_display)
    if reassembled and normalize_player_label(reassembled) != raw:
        return reassembled, "reassembly"

    abbrev = _resolve_abbreviated_given(raw, candidates, canonical_display)
    if abbrev and normalize_player_label(abbrev) != raw:
        return abbrev, "abbrev"

    identity = _resolve_identity_match(raw, candidates, canonical_display)
    if identity and normalize_player_label(identity) != raw:
        return identity, "identity"

    substring = _resolve_substring_given(raw, candidates, canonical_display)
    if substring and normalize_player_label(substring) != raw:
        return substring, "substring"

    close = _resolve_close_match(raw, candidates, close_match_ratio=close_match_ratio)
    if close:
        return close, "close"

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
    registry_names = candidate_names_for_entry(entry)
    for name in names:
        normalized = normalize_player_label(name)
        if not normalized:
            continue
        if normalized in registered:
            continue
        if any(
            name_identity_key(name) == name_identity_key(candidate) for candidate in registry_names
        ):
            continue
        if any(
            _family_token(name) == _family_token(candidate)
            and given_names_substring_equivalent(_given_token(name), _given_token(candidate))
            for candidate in registry_names
        ):
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
                "player_id_legacy": str(slot.get("player_id_legacy") or ""),
                "player_id_pass": str(slot.get("player_id_pass") or ""),
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
            "player_id_legacy": str(getattr(row, "player_id_legacy", "") or ""),
            "player_id_pass": str(getattr(row, "player_id_pass", "") or ""),
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
        new_legacy = str(getattr(row, "player_id_legacy", "") or "")
        new_pass = str(getattr(row, "player_id_pass", "") or "")

        if pid not in merged:
            merged[pid] = {
                "player_id": pid,
                "player_id_legacy": new_legacy,
                "player_id_pass": new_pass,
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

        if new_pass and not slot.get("player_id_pass"):
            slot["player_id_pass"] = new_pass
        if new_legacy:
            legacy = _parse_aliases_field(slot.get("player_id_legacy") or "") | _parse_aliases_field(
                new_legacy
            )
            slot["player_id_legacy"] = _join_aliases(legacy)

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
    aktive_min_season: Optional[str] = None,
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

    ``aktive_min_season=None`` uses :data:`~data_access.aktive_mitglieder_registry.DEFAULT_AKTIVE_MIN_SEASON`
    (``2008-09``). Pass ``""`` to import every Aktive season.
    """
    from data_access.aktive_mitglieder_registry import (
        build_registry_dataframe_from_aktive,
        format_aktive_import_summary,
        resolve_aktive_min_season,
    )

    season_floor = resolve_aktive_min_season(aktive_min_season)

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
            min_season=season_floor,
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
        "aktive_min_season": season_floor or "",
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
        "registry_abbrev": 0,
        "registry_identity": 0,
        "registry_substring": 0,
        "registry_close": 0,
        "registry_alias_to_canonical": 0,
        "registry_unchanged": 0,
    }

    for idx, row in out.iterrows():
        pid = normalize_player_id(row[Columns.player_id])
        raw = normalize_player_label(row[Columns.player_name])
        if not pid or not raw:
            continue
        entry = lookup.get(pid) or {}
        resolved, kind = resolve_player_name_for_id(raw, pid, lookup)
        if resolved is None or kind == "unresolved":
            stats["registry_unchanged"] += 1
            continue
        if kind == "exact" and should_normalize_alias_to_canonical(raw, entry):
            canonical_display = str(entry.get("canonical_name") or "")
            if canonical_display and normalize_player_label(canonical_display) != raw:
                out.at[idx, Columns.player_name] = canonical_display
                stats["registry_alias_to_canonical"] += 1
                continue
        if normalize_player_label(resolved) == raw:
            stats["registry_unchanged"] += 1
            continue
        out.at[idx, Columns.player_name] = resolved
        if kind == "exact":
            stats["registry_exact"] += 1
        elif kind == "reassembly":
            stats["registry_reassembly"] += 1
        elif kind == "abbrev":
            stats["registry_abbrev"] += 1
        elif kind == "identity":
            stats["registry_identity"] += 1
        elif kind == "substring":
            stats["registry_substring"] += 1
        elif kind == "close":
            stats["registry_close"] += 1

    return out, stats


def format_registry_apply_summary(stats: Mapping[str, int]) -> str:
    if not stats:
        return "Players registry: not applied"
    changed = (
        int(stats.get("registry_exact", 0))
        + int(stats.get("registry_reassembly", 0))
        + int(stats.get("registry_abbrev", 0))
        + int(stats.get("registry_identity", 0))
        + int(stats.get("registry_substring", 0))
        + int(stats.get("registry_close", 0))
        + int(stats.get("registry_alias_to_canonical", 0))
    )
    if changed <= 0:
        return "Players registry: 0 row(s) changed"
    lines = [f"Players registry: {changed} row(s) changed"]
    for key in (
        "registry_exact",
        "registry_reassembly",
        "registry_abbrev",
        "registry_identity",
        "registry_substring",
        "registry_close",
        "registry_alias_to_canonical",
    ):
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
