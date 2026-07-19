"""Resolve tournament club labels via Rangliste affiliations (tournaments only)."""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd

from data_access.affiliation_registry import (
    build_affiliation_lookup,
    build_verein_alias_lookup,
    canonicalize_verein_label,
    load_affiliation_index_df,
    load_vereine_registry_df,
    lookup_tournament_affiliation,
    looks_like_verein_label,
    verein_identity_key,
)
from data_access.aktive_mitglieder_registry import is_einzelmitglied_club
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label

REPORTING_MODE_CLUB = "club"
REPORTING_MODE_VEREIN = "verein"
DEFAULT_REPORTING_MODE = REPORTING_MODE_CLUB

AFFILIATION_SOURCE_INDEX_SAME = "index_same_season"
AFFILIATION_SOURCE_LEAGUE_SAME = "league_same_season"
AFFILIATION_SOURCE_EXTRAPOLATED_PAST = "extrapolated_past"
AFFILIATION_SOURCE_EXTRAPOLATED_FUTURE = "extrapolated_future"
AFFILIATION_SOURCE_EINZELMITGLIED = "einzelmitglied_verein"
AFFILIATION_SOURCE_VEREIN_ONLY = "verein_only"
AFFILIATION_SOURCE_UNRESOLVED = "unresolved"

# Backward-compatible alias used in tests
AFFILIATION_SOURCE_RANGLISTE_SAME = AFFILIATION_SOURCE_INDEX_SAME


def resolve_tournament_reporting_mode(raw: Optional[str] = None) -> str:
    value = normalize_unicode_label(
        raw or os.environ.get("BOWLYZER_TOURNAMENT_AFFILIATION_REPORTING", "")
    )
    if value == REPORTING_MODE_VEREIN:
        return REPORTING_MODE_VEREIN
    return DEFAULT_REPORTING_MODE


def _resolve_verein_label(
    label: object,
    verein_aliases: Mapping[str, str],
) -> str:
    text = normalize_unicode_label(label)
    if not text:
        return ""
    return verein_aliases.get(verein_identity_key(text), canonicalize_verein_label(text))


def _tournament_stated_verein(
    raw_club: object,
    verein_aliases: Mapping[str, str],
) -> str:
    text = normalize_unicode_label(raw_club)
    if not text or is_einzelmitglied_club(text):
        return ""
    if verein_identity_key(text) in verein_aliases or looks_like_verein_label(text):
        return _resolve_verein_label(text, verein_aliases)
    return ""


def _affiliation_history_club(aff: Mapping[str, Any]) -> str:
    if bool(aff.get("is_einzelmitglied")):
        return normalize_unicode_label(aff.get("verein_canonical") or aff.get("verein_raw") or "")
    return normalize_unicode_label(aff.get("club_canonical") or aff.get("club_raw") or "")


def _affiliation_reporting_club(
    aff: Mapping[str, Any],
    *,
    reporting_mode: str,
) -> str:
    verein = normalize_unicode_label(aff.get("verein_canonical") or aff.get("verein_raw") or "")
    history = _affiliation_history_club(aff)
    if reporting_mode == REPORTING_MODE_VEREIN and verein:
        return verein
    return history or verein


def _affiliation_source_tag(rule: str, aff: Mapping[str, Any]) -> str:
    if bool(aff.get("is_einzelmitglied")):
        return AFFILIATION_SOURCE_EINZELMITGLIED
    if rule == "league_same_season":
        return AFFILIATION_SOURCE_LEAGUE_SAME
    if rule == "extrapolated_past":
        return AFFILIATION_SOURCE_EXTRAPOLATED_PAST
    if rule == "extrapolated_future":
        return AFFILIATION_SOURCE_EXTRAPOLATED_FUTURE
    return AFFILIATION_SOURCE_INDEX_SAME


def apply_tournament_affiliation_resolution(
    df: pd.DataFrame,
    *,
    affiliation_lookup: Optional[Mapping[Tuple[str, str], Mapping[str, str]]] = None,
    verein_aliases: Optional[Mapping[str, str]] = None,
    reporting_mode: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Enrich tournament rows from ``affiliation_index`` (pass 1 + pass 2).

    Extrapolation runs only for tournament rows with no same-season index hit.
    Past/future club reuse requires the tournament label to resolve to the same Verein.
    """
    if df is None or df.empty:
        return df, {}

    if Columns.club not in df.columns:
        return df, {}

    lookup = affiliation_lookup
    if lookup is None:
        lookup = build_affiliation_lookup(load_affiliation_index_df())

    verein_map = verein_aliases
    if verein_map is None:
        verein_map = build_verein_alias_lookup(load_vereine_registry_df())

    mode = resolve_tournament_reporting_mode(reporting_mode)
    out = df.copy()

    for col in (Columns.verein, Columns.history_club, Columns.affiliation_source):
        if col not in out.columns:
            out[col] = ""

    stats: Dict[str, Any] = {
        "index_same_season": 0,
        "league_same_season": 0,
        "extrapolated_past": 0,
        "extrapolated_future": 0,
        "einzelmitglied_verein": 0,
        "verein_only": 0,
        "unresolved": 0,
        "rows_changed": 0,
        "extrapolation_gaps": [],
        "unresolved_gaps": [],
    }

    is_tournament = pd.Series(True, index=out.index)
    if Columns.event_type in out.columns:
        is_tournament = out[Columns.event_type].fillna("").astype(str).str.strip().str.lower().eq(
            "tournament"
        )

    for idx, row in out.loc[is_tournament].iterrows():
        raw_club = normalize_unicode_label(row.get(Columns.club))
        season = normalize_unicode_label(row.get(Columns.season))
        player_id = normalize_unicode_label(row.get(Columns.player_id))
        tournament_verein = _tournament_stated_verein(raw_club, verein_map)

        aff, rule = lookup_tournament_affiliation(
            player_id,
            season,
            lookup,
            tournament_verein=tournament_verein,
        )

        if aff:
            history_club = _affiliation_history_club(aff)
            reporting_club = _affiliation_reporting_club(aff, reporting_mode=mode)
            verein = normalize_unicode_label(aff.get("verein_canonical") or aff.get("verein_raw") or "")
            source = _affiliation_source_tag(rule, aff)

            if rule in {"extrapolated_past", "extrapolated_future"}:
                stats[rule] += 1
                stats["extrapolation_gaps"].append(
                    {
                        "player_id": player_id,
                        "season": season,
                        "raw_club": raw_club,
                        "reason": rule,
                        "extrapolated_from_season": aff.get("extrapolated_from_season", ""),
                        "tournament_verein": tournament_verein,
                    }
                )
            elif rule == "league_same_season":
                stats["league_same_season"] += 1
            else:
                stats["index_same_season"] += 1

            if source == AFFILIATION_SOURCE_EINZELMITGLIED:
                stats["einzelmitglied_verein"] += 1

            changed = (
                raw_club != reporting_club
                or normalize_unicode_label(row.get(Columns.verein)) != verein
                or normalize_unicode_label(row.get(Columns.history_club)) != history_club
            )
            if changed:
                stats["rows_changed"] += 1
            out.at[idx, Columns.club] = reporting_club
            out.at[idx, Columns.verein] = verein
            out.at[idx, Columns.history_club] = history_club
            out.at[idx, Columns.affiliation_source] = source
            continue

        if is_einzelmitglied_club(raw_club):
            stats["einzelmitglied_verein"] += 1
            stats["unresolved"] += 1
            stats["unresolved_gaps"].append(
                {
                    "player_id": player_id,
                    "season": season,
                    "raw_club": raw_club,
                    "reason": "einzelmitglied_no_index",
                }
            )
            out.at[idx, Columns.history_club] = raw_club
            out.at[idx, Columns.affiliation_source] = AFFILIATION_SOURCE_EINZELMITGLIED
            continue

        if tournament_verein:
            stats["verein_only"] += 1
            stats["unresolved_gaps"].append(
                {
                    "player_id": player_id,
                    "season": season,
                    "raw_club": raw_club,
                    "reason": "verein_no_extrapolation_match",
                    "verein": tournament_verein,
                }
            )
            reporting = tournament_verein if mode == REPORTING_MODE_VEREIN else tournament_verein
            out.at[idx, Columns.club] = reporting
            out.at[idx, Columns.verein] = tournament_verein
            out.at[idx, Columns.history_club] = tournament_verein
            out.at[idx, Columns.affiliation_source] = AFFILIATION_SOURCE_VEREIN_ONLY
            continue

        stats["unresolved"] += 1
        stats["unresolved_gaps"].append(
            {
                "player_id": player_id,
                "season": season,
                "raw_club": raw_club,
                "reason": "no_index_or_verein",
            }
        )
        out.at[idx, Columns.history_club] = raw_club
        out.at[idx, Columns.affiliation_source] = AFFILIATION_SOURCE_UNRESOLVED

    stats["extrapolation_gap_count"] = len(stats["extrapolation_gaps"])
    stats["unresolved_gap_count"] = len(stats["unresolved_gaps"])
    # Backward-compatible aggregate keys
    stats["rangliste_same_season"] = int(stats["index_same_season"])
    stats["rangliste_neighbor_season"] = int(stats["extrapolated_past"]) + int(stats["extrapolated_future"])
    return out, stats


def format_tournament_affiliation_summary(stats: Mapping[str, Any]) -> str:
    if not stats:
        return "Tournament affiliation: not applied"
    parts = [
        f"{int(stats.get('index_same_season') or 0)} index same-season",
        f"{int(stats.get('league_same_season') or 0)} league same-season",
        f"{int(stats.get('extrapolated_past') or 0)} Verein-gated past",
        f"{int(stats.get('extrapolated_future') or 0)} Verein-gated future",
        f"{int(stats.get('einzelmitglied_verein') or 0)} Einzelmitglied→Verein",
        f"{int(stats.get('verein_only') or 0)} Verein-only",
        f"{int(stats.get('unresolved') or 0)} unresolved",
    ]
    return "Tournament affiliation: " + ", ".join(parts)
