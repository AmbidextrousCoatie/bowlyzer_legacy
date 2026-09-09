"""Alias → canonical bowling-center names (league Location column)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

import pandas as pd

from data_access.text_norm import normalize_unicode_label

_PLACEHOLDER_KEYS = frozenset(
    {
        "",
        "unknown",
        "none",
        "nan",
        "tbd",
        "n/a",
        "na",
        "-",
        "—",
    }
)
_NEU_PREFIX_RE = re.compile(r"^neu:\s*", re.IGNORECASE)
_COMPACT_PUNCT_RE = re.compile(r"[-–—./,]+")


def _venue_mapping_path() -> Path:
    return Path(__file__).resolve().parents[1] / "database" / "relational_csv" / "venue_mapping.csv"


def _split_pipe_list(raw: object) -> List[str]:
    return [part.strip() for part in str(raw or "").split("|") if part.strip()]


def venue_identity_key(label: object) -> str:
    text = normalize_unicode_label(label)
    if not text:
        return ""
    text = _NEU_PREFIX_RE.sub("", text).strip()
    return text.casefold()


def venue_compact_key(label: object) -> str:
    text = venue_identity_key(label)
    if not text:
        return ""
    text = _COMPACT_PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def is_placeholder_venue(label: object) -> bool:
    return venue_identity_key(label) in _PLACEHOLDER_KEYS


@lru_cache(maxsize=1)
def load_venue_mapping_rows() -> List[dict]:
    path = _venue_mapping_path()
    if not path.is_file():
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    rows: List[dict] = []
    for _, row in df.iterrows():
        canonical = str(row.get("canonical_name") or "").strip()
        if not canonical:
            continue
        aliases = _split_pipe_list(row.get("aliases") or "")
        rows.append({"canonical_name": canonical, "aliases": aliases})
    return rows


def _register_key(lookup: Dict[str, str], key: str, canonical: str, collisions: set[str]) -> None:
    if not key:
        return
    existing = lookup.get(key)
    if existing is None:
        lookup[key] = canonical
        return
    if existing != canonical:
        collisions.add(key)


def build_venue_alias_lookup(
    rows: Iterable[Mapping[str, object]] | None = None,
) -> Dict[str, str]:
    """Identity-key and compact-key → canonical. Compact keys that collide are dropped."""
    exact: Dict[str, str] = {}
    compact: Dict[str, str] = {}
    compact_collisions: set[str] = set()
    for row in rows if rows is not None else load_venue_mapping_rows():
        canonical = str(row.get("canonical_name") or "").strip()
        if not canonical:
            continue
        labels = [canonical, *list(row.get("aliases") or [])]
        for label in labels:
            text = str(label or "").strip()
            if not text or is_placeholder_venue(text):
                continue
            exact[venue_identity_key(text)] = canonical
            _register_key(compact, venue_compact_key(text), canonical, compact_collisions)
    for key in compact_collisions:
        compact.pop(key, None)
    out = dict(compact)
    out.update(exact)
    return out


@lru_cache(maxsize=1)
def venue_alias_lookup() -> Dict[str, str]:
    return build_venue_alias_lookup()


def canonicalize_venue_label(label: object, lookup: Mapping[str, str] | None = None) -> str:
    """Map a raw Location string onto its canonical house name when listed."""
    text = normalize_unicode_label(label)
    if not text:
        return ""
    if is_placeholder_venue(text):
        return text
    table = lookup if lookup is not None else venue_alias_lookup()
    identity = venue_identity_key(text)
    hit = table.get(identity)
    if hit:
        return hit
    compact = venue_compact_key(text)
    return table.get(compact, text)


def apply_venue_mapping_to_series(series: pd.Series) -> pd.Series:
    lookup = venue_alias_lookup()

    def _map(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return canonicalize_venue_label(value, lookup)

    return series.map(_map)
