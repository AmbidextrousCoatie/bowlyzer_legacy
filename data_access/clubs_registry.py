"""Canonical club registry built from published league merge output."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

import pandas as pd

from data_access.competition_schema import club_name_from_team
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label
from extract_excel_data import normalize_team_name

REGISTRY_COLUMNS = ("canonical_name", "aliases", "team_labels", "source", "updated_at")
REGISTRY_FORMAT_VERSION = 1

# GF / PDF regional list prefix: ``AUG - Lechbowler Augsburg``
_REGIONAL_PREFIX_RE = re.compile(r"^[A-ZÄÖÜ]{2,5}\s*-\s*", re.UNICODE)
_LEGAL_SUFFIX_RE = re.compile(r"\s+e\.?\s*V\.?\s*$", re.IGNORECASE)


def _registry_path() -> Path:
    from database.paths import clubs_registry_csv

    return clubs_registry_csv()


def _club_mapping_path() -> Path:
    return (
        Path(__file__).resolve().parents[1] / "database" / "relational_csv" / "club_mapping.csv"
    )


def _split_pipe_list(raw: object) -> List[str]:
    return [part.strip() for part in str(raw or "").split("|") if part.strip()]


def _join_pipe(values: Iterable[str]) -> str:
    seen: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return "|".join(seen)


def club_identity_key(label: object) -> str:
    return normalize_unicode_label(label).casefold()


def strip_regional_club_prefix(label: str) -> str:
    text = normalize_unicode_label(label)
    if not text:
        return ""
    return _REGIONAL_PREFIX_RE.sub("", text).strip()


def strip_legal_suffix(label: str) -> str:
    text = normalize_unicode_label(label)
    if not text:
        return ""
    return _LEGAL_SUFFIX_RE.sub("", text).strip()


def club_from_team_label(team_label: object) -> str:
    normalized = normalize_team_name(str(team_label or "").strip()) or str(team_label or "").strip()
    return club_name_from_team(normalized)


@lru_cache(maxsize=1)
def load_club_mapping_rows() -> List[dict]:
    path = _club_mapping_path()
    if not path.is_file():
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: List[dict] = []
    for _, row in df.iterrows():
        canonical = str(row.get("canonical_name") or row.get("name") or "").strip()
        if not canonical:
            continue
        aliases = _split_pipe_list(row.get("aliases") or "")
        rows.append({"canonical_name": canonical, "aliases": aliases})
    return rows


def _league_input_mask(df: pd.DataFrame) -> pd.Series:
    if Columns.computed_data not in df.columns:
        return pd.Series(True, index=df.index)
    normalized = df[Columns.computed_data].fillna("").astype(str).str.strip().str.lower()
    return normalized.isin({"false", "0", "no", ""})


def build_registry_dataframe_from_league(
    league_df: pd.DataFrame,
    *,
    updated_at: Optional[str] = None,
) -> pd.DataFrame:
    """
    Derive canonical clubs from league merge ``Team`` / ``Opponent`` labels.

    Uses the same ``normalize_team_name`` pass as league merge. Each normalized
    full team string becomes a ``team_labels`` alias for its club base.
    """
    if league_df is None or league_df.empty:
        return pd.DataFrame(columns=list(REGISTRY_COLUMNS))

    work = league_df.loc[_league_input_mask(league_df)].copy()
    buckets: Dict[str, Dict[str, Any]] = {}

    def ingest_team_label(raw_team: object) -> None:
        raw = str(raw_team or "").strip()
        if not raw:
            return
        normalized_team = normalize_team_name(raw) or raw
        club = club_name_from_team(normalized_team)
        if not club:
            return
        bucket = buckets.setdefault(
            club,
            {
                "canonical_name": club,
                "aliases": set(),
                "team_labels": set(),
            },
        )
        bucket["team_labels"].add(normalized_team)
        if normalized_team != club:
            bucket["aliases"].add(normalized_team)
        if raw != normalized_team:
            bucket["aliases"].add(raw)

    for col in (Columns.team_name, Columns.team_name_opponent):
        if col not in work.columns:
            continue
        for value in work[col].dropna().astype(str):
            ingest_team_label(value)

    for row in load_club_mapping_rows():
        canonical = str(row["canonical_name"]).strip()
        if not canonical:
            continue
        bucket = buckets.setdefault(
            canonical,
            {"canonical_name": canonical, "aliases": set(), "team_labels": set()},
        )
        for alias in row.get("aliases") or []:
            bucket["aliases"].add(str(alias).strip())

    moment = updated_at or datetime.now(timezone.utc).isoformat()
    out_rows: List[dict] = []
    for club in sorted(buckets):
        item = buckets[club]
        aliases = set(item["aliases"])
        aliases.discard(club)
        team_labels = set(item["team_labels"])
        out_rows.append(
            {
                "canonical_name": club,
                "aliases": _join_pipe(sorted(aliases)),
                "team_labels": _join_pipe(sorted(team_labels)),
                "source": "league_merge",
                "updated_at": moment,
            }
        )
    return pd.DataFrame(out_rows, columns=list(REGISTRY_COLUMNS))


def registry_lookup_by_canonical(df: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    if df is None or df.empty:
        return lookup
    for row in df.itertuples(index=False):
        canonical = str(getattr(row, "canonical_name", "") or "").strip()
        if not canonical:
            continue
        entry = {
            "canonical_name": canonical,
            "aliases": str(getattr(row, "aliases", "") or ""),
            "team_labels": str(getattr(row, "team_labels", "") or ""),
        }
        lookup[club_identity_key(canonical)] = entry
    return lookup


def build_alias_to_canonical(df: pd.DataFrame) -> Dict[str, str]:
    """Normalized alias key -> canonical club name."""
    out: Dict[str, str] = {}
    if df is None or df.empty:
        return out
    for row in df.itertuples(index=False):
        canonical = str(getattr(row, "canonical_name", "") or "").strip()
        if not canonical:
            continue
        keys = {canonical}
        keys.update(_split_pipe_list(getattr(row, "aliases", "")))
        keys.update(_split_pipe_list(getattr(row, "team_labels", "")))
        for label in keys:
            key = club_identity_key(label)
            if key and key not in out:
                out[key] = canonical
            club = club_from_team_label(label)
            if club:
                ck = club_identity_key(club)
                if ck and ck not in out:
                    out[ck] = canonical
    return out


@lru_cache(maxsize=1)
def load_clubs_registry_df() -> Optional[pd.DataFrame]:
    path = _registry_path()
    from data_access.parquet_sidecar import data_file_exists, resolve_load_path

    if not data_file_exists(path):
        return None
    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def compute_clubs_registry_fingerprint(df: Optional[pd.DataFrame]) -> str:
    if df is None or df.empty:
        return "empty"
    canonical = "|".join(sorted(df["canonical_name"].astype(str).tolist()))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:12]


def write_clubs_registry(df: pd.DataFrame, *, write_csv: bool = False) -> Dict[str, str]:
    from data_access.parquet_sidecar import publish_dataframe

    out_path = _registry_path()
    published = publish_dataframe(df, out_path, write_csv=write_csv, sep=";")
    load_clubs_registry_df.cache_clear()
    return published


def build_and_publish_clubs_registry(
    league_df: Optional[pd.DataFrame] = None,
    *,
    write_csv: bool = False,
) -> Dict[str, Any]:
    if league_df is None:
        from data_access.parquet_sidecar import data_file_exists, resolve_load_path
        from database.paths import league_results_merged_csv

        league_path = league_results_merged_csv()
        if not data_file_exists(league_path):
            raise FileNotFoundError(f"League merge output not found: {league_path}")
        load_path = resolve_load_path(league_path)
        if load_path.suffix.lower() == ".parquet":
            league_df = pd.read_parquet(load_path)
        else:
            league_df = pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)

    moment = datetime.now(timezone.utc).isoformat()
    registry_df = build_registry_dataframe_from_league(league_df, updated_at=moment)
    published = write_clubs_registry(registry_df, write_csv=write_csv)
    logical = _registry_path()
    return {
        "row_count": int(len(registry_df)),
        "paths": {
            "output": str(logical.resolve()),
            "parquet_output": str(published["parquet"]),
            "csv_output": str(published.get("csv") or ""),
        },
        "fingerprint": compute_clubs_registry_fingerprint(registry_df),
    }


def _fuzzy_canonical_match(label: str, canonical_names: Sequence[str]) -> Optional[str]:
    """Match label to canonical club by equality, suffix, or word-boundary prefix."""
    needle = club_identity_key(label)
    if not needle:
        return None
    best: Optional[str] = None
    best_len = 0
    for canonical in canonical_names:
        canon_key = club_identity_key(canonical)
        if not canon_key:
            continue
        matched = (
            needle == canon_key
            or needle.endswith(canon_key)
            or canon_key.endswith(needle)
            or canon_key.startswith(f"{needle} ")
            or needle.startswith(f"{canon_key} ")
        )
        if matched and len(canon_key) > best_len:
            best = canonical
            best_len = len(canon_key)
    return best


def resolve_club_label(
    raw_label: object,
    alias_lookup: Mapping[str, str],
    canonical_names: Sequence[str],
) -> Tuple[Optional[str], str]:
    """
    Resolve a raw club label to a registry canonical name.

    Returns ``(canonical, rule)`` or ``(None, "")`` when unresolved.
    """
    text = normalize_unicode_label(raw_label)
    if not text:
        return None, ""

    candidates: List[Tuple[str, str]] = []

    def try_key(label: str, rule: str) -> None:
        key = club_identity_key(label)
        if not key:
            return
        hit = alias_lookup.get(key)
        if hit:
            candidates.append((hit, rule))

    try_key(text, "exact")
    stripped_prefix = strip_regional_club_prefix(text)
    if stripped_prefix and stripped_prefix != text:
        try_key(stripped_prefix, "strip_regional_prefix")
    stripped_legal = strip_legal_suffix(text)
    if stripped_legal and stripped_legal != text:
        try_key(stripped_legal, "strip_legal_suffix")
    if stripped_prefix:
        stripped_both = strip_legal_suffix(stripped_prefix)
        if stripped_both and stripped_both not in {text, stripped_prefix}:
            try_key(stripped_both, "strip_prefix_and_legal")

    team_club = club_from_team_label(text)
    if team_club:
        try_key(team_club, "team_name_normalization")

    if not candidates:
        return None, ""
    return candidates[0]


def propose_club_resolution(
    raw_label: object,
    alias_lookup: Mapping[str, str],
    canonical_names: Sequence[str],
) -> List[Tuple[str, str]]:
    """Return ordered ``(canonical, rule)`` proposals for audit UI / CSV."""
    text = normalize_unicode_label(raw_label)
    if not text:
        return []

    proposals: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def add(canonical: Optional[str], rule: str) -> None:
        if not canonical or not rule:
            return
        key = f"{club_identity_key(canonical)}::{rule}"
        if key in seen:
            return
        seen.add(key)
        proposals.append((canonical, rule))

    resolved, rule = resolve_club_label(text, alias_lookup, canonical_names)
    add(resolved, rule)

    if not resolved:
        fuzzy = _fuzzy_canonical_match(text, canonical_names)
        add(fuzzy, "fuzzy_canonical")
        stripped = strip_regional_club_prefix(text)
        if stripped and stripped != text:
            hit, hit_rule = resolve_club_label(stripped, alias_lookup, canonical_names)
            add(hit, hit_rule or "strip_regional_prefix")
            fuzzy = _fuzzy_canonical_match(stripped, canonical_names)
            add(fuzzy, "fuzzy_after_prefix_strip")
        legal = strip_legal_suffix(text)
        if legal and legal != text:
            fuzzy_legal = _fuzzy_canonical_match(legal, canonical_names)
            add(fuzzy_legal, "fuzzy_after_legal_strip")

    return proposals


def apply_clubs_registry(
    df: pd.DataFrame,
    registry: Optional[pd.DataFrame] = None,
    *,
    club_column: str = Columns.club,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    if df is None or df.empty or club_column not in df.columns:
        return df, {}

    reg = registry if registry is not None else load_clubs_registry_df()
    if reg is None or reg.empty:
        return df, {}

    alias_lookup = build_alias_to_canonical(reg)
    canonical_names = sorted(reg["canonical_name"].astype(str).tolist())
    out = df.copy()
    stats: Dict[str, int] = {
        "club_registry_exact": 0,
        "club_registry_prefix": 0,
        "club_registry_team_norm": 0,
        "club_registry_suffix": 0,
        "club_registry_legal_strip": 0,
        "club_registry_unchanged": 0,
        "club_registry_unresolved": 0,
    }

    for idx, raw in out[club_column].items():
        text = normalize_unicode_label(raw)
        if not text:
            continue
        resolved, rule = resolve_club_label(text, alias_lookup, canonical_names)
        if resolved is None:
            stats["club_registry_unresolved"] += 1
            continue
        if normalize_unicode_label(resolved) == text:
            stats["club_registry_unchanged"] += 1
            continue
        out.at[idx, club_column] = resolved
        if rule == "exact":
            stats["club_registry_exact"] += 1
        elif rule in {"strip_regional_prefix", "strip_prefix_and_legal"}:
            stats["club_registry_prefix"] += 1
        elif rule == "strip_legal_suffix":
            stats["club_registry_legal_strip"] += 1
        elif rule == "team_name_normalization":
            stats["club_registry_team_norm"] += 1
        elif rule == "fuzzy_canonical":
            stats["club_registry_suffix"] += 1
        else:
            stats["club_registry_exact"] += 1

    return out, stats


def audit_league_team_club_consistency(
    league_df: pd.DataFrame,
    registry: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """
    Report normalized league team labels whose club base is absent from the registry.

    When the registry is built from the same league file, this should be empty
    unless manual mapping rows reference unknown canonicals.
    """
    reg = registry if registry is not None else load_clubs_registry_df()
    if league_df is None or league_df.empty or reg is None or reg.empty:
        return []

    canonical_keys = {club_identity_key(name) for name in reg["canonical_name"].astype(str)}
    alias_lookup = build_alias_to_canonical(reg)
    rows: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    work = league_df.loc[_league_input_mask(league_df)]
    for col in (Columns.team_name, Columns.team_name_opponent):
        if col not in work.columns:
            continue
        for raw in work[col].dropna().astype(str).unique():
            normalized_team = normalize_team_name(raw) or raw
            club = club_from_team_label(normalized_team)
            if not club:
                continue
            key = club_identity_key(normalized_team)
            if key in seen:
                continue
            seen.add(key)
            if club_identity_key(club) in canonical_keys:
                continue
            resolved, rule = resolve_club_label(club, alias_lookup, reg["canonical_name"].tolist())
            if resolved:
                continue
            rows.append(
                {
                    "issue_type": "league_team_club_missing",
                    "team_label": normalized_team,
                    "club_base": club,
                    "source_column": col,
                }
            )
    return rows


def format_registry_summary(summary: Mapping[str, Any]) -> str:
    count = int(summary.get("row_count") or 0)
    path = (summary.get("paths") or {}).get("parquet_output") or (summary.get("paths") or {}).get("output")
    return f"Clubs registry: {count} canonical club(s) -> {path}"
