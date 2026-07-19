"""Normalize tournament rows after Excel/PDF extraction (mirrors league merge steps)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

import pandas as pd

from data_access.clubs_registry import apply_clubs_registry
from data_access.player_id_name_normalization import (
    apply_player_id_name_normalization,
    load_player_id_only_remapping_rules,
)
from data_access.players_registry import (
    apply_legacy_player_id_remapping,
    apply_players_registry,
    load_players_registry_df,
)
from data_access.tournament_club_resolution import (
    apply_tournament_affiliation_resolution,
    format_tournament_affiliation_summary,
    resolve_tournament_reporting_mode,
)
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label


def normalize_tournament_dataframe(
    df: pd.DataFrame,
    *,
    normalize_clubs: bool = True,
    normalize_player_ids: bool = True,
    resolve_affiliations: bool = True,
    reporting_mode: str | None = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Apply club registry resolution, player ID remaps, and players registry.

    Club labels are resolved via ``clubs_registry`` (league-derived canonical names
    + ``club_mapping.csv`` aliases). Team spelling rules apply only when resolving
  through the team-label path inside the registry.
    """
    if df is None or df.empty:
        return df, {}

    out = df.copy()
    stats: Dict[str, Any] = {
        "club_registry_rows_changed": 0,
        "club_registry_unresolved": 0,
        "player_id_rows_changed": 0,
        "registry_rows_changed": 0,
        "affiliation_rows_changed": 0,
        "legacy_id_remapped": 0,
    }

    if normalize_player_ids:
        out, legacy_stats = apply_legacy_player_id_remapping(out)
        stats["legacy_id_remapped"] = int(legacy_stats.get("legacy_id_remapped") or 0)

        player_id_rules = load_player_id_only_remapping_rules()
        if player_id_rules:
            out, batch_stats = apply_player_id_name_normalization(out, player_id_rules, id_only=True)
            stats["player_id_rows_changed"] = int(sum(batch_stats.values()))
            stats["player_id_rule_hits"] = dict(batch_stats)

        registry_df = load_players_registry_df()
        if registry_df is not None and not registry_df.empty:
            out, registry_stats = apply_players_registry(out, registry_df)
            stats["registry_rows_changed"] = int(
                registry_stats.get("registry_exact", 0)
                + registry_stats.get("registry_reassembly", 0)
                + registry_stats.get("registry_close", 0)
                + registry_stats.get("registry_alias_to_canonical", 0)
                + registry_stats.get("registry_abbrev", 0)
                + registry_stats.get("registry_identity", 0)
                + registry_stats.get("registry_substring", 0)
            )
            stats["registry_rule_hits"] = dict(registry_stats)

    if resolve_affiliations and Columns.club in out.columns:
        out, aff_stats = apply_tournament_affiliation_resolution(
            out,
            reporting_mode=reporting_mode or resolve_tournament_reporting_mode(),
        )
        stats["affiliation_rule_hits"] = dict(aff_stats)
        stats["affiliation_rows_changed"] = int(aff_stats.get("rows_changed") or 0)
        stats["affiliation_extrapolation_gaps"] = int(aff_stats.get("extrapolation_gap_count") or 0)
        stats["affiliation_unresolved_gaps"] = int(aff_stats.get("unresolved_gap_count") or 0)

    if normalize_clubs and Columns.club in out.columns:
        # Always fold club aliases (club_mapping / clubs_registry), including
        # affiliation-sourced Rangliste spellings like "BC Donau - Bowler".
        # Previously only ``unresolved`` rows were rewritten, so index hits kept
        # historical Verein/club spellings on the Club column.
        out, club_stats = apply_clubs_registry(out)
        hist_changed = 0
        if Columns.history_club in out.columns:
            out, hist_stats = apply_clubs_registry(out, club_column=Columns.history_club)
            hist_changed = int(
                hist_stats.get("club_registry_exact", 0)
                + hist_stats.get("club_registry_prefix", 0)
                + hist_stats.get("club_registry_team_norm", 0)
                + hist_stats.get("club_registry_suffix", 0)
                + hist_stats.get("club_registry_legal_strip", 0)
            )
            for idx in out.index:
                resolved_club = normalize_unicode_label(out.at[idx, Columns.club])
                if resolved_club and not normalize_unicode_label(out.at[idx, Columns.history_club]):
                    out.at[idx, Columns.history_club] = resolved_club
        stats["club_registry_rule_hits"] = dict(club_stats)
        stats["club_registry_rows_changed"] = int(
            club_stats.get("club_registry_exact", 0)
            + club_stats.get("club_registry_prefix", 0)
            + club_stats.get("club_registry_team_norm", 0)
            + club_stats.get("club_registry_suffix", 0)
            + club_stats.get("club_registry_legal_strip", 0)
            + hist_changed
        )
        stats["club_registry_unresolved"] = int(club_stats.get("club_registry_unresolved", 0))

    return out, stats


def format_clubs_registry_apply_summary(stats: Mapping[str, int]) -> str:
    if not stats:
        return "Clubs registry: not applied"
    changed = int(
        stats.get("club_registry_exact", 0)
        + stats.get("club_registry_prefix", 0)
        + stats.get("club_registry_team_norm", 0)
        + stats.get("club_registry_suffix", 0)
        + stats.get("club_registry_legal_strip", 0)
    )
    unresolved = int(stats.get("club_registry_unresolved", 0))
    if changed == 0 and unresolved == 0:
        return "Clubs registry: 0 row(s) changed"
    parts = [f"{changed} club row(s) resolved"]
    if unresolved:
        parts.append(f"{unresolved} unresolved")
    return "Clubs registry: " + ", ".join(parts)


def format_tournament_normalization_summary(stats: Mapping[str, Any]) -> str:
    if not stats:
        return "Tournament normalization: not applied"
    lines = []
    club = int(stats.get("club_registry_rows_changed") or 0)
    unresolved = int(stats.get("club_registry_unresolved") or 0)
    if club or unresolved:
        lines.append(format_clubs_registry_apply_summary(stats.get("club_registry_rule_hits") or stats))
    pid = int(stats.get("player_id_rows_changed") or 0)
    if pid:
        lines.append(f"Player ID remap: {pid} row(s)")
    legacy = int(stats.get("legacy_id_remapped") or 0)
    if legacy:
        lines.append(f"Legacy EDV remap: {legacy} row(s)")
    reg = int(stats.get("registry_rows_changed") or 0)
    if reg:
        lines.append(f"Players registry: {reg} row(s)")
    aff = int(stats.get("affiliation_rows_changed") or 0)
    if aff or stats.get("affiliation_rule_hits"):
        lines.append(format_tournament_affiliation_summary(stats.get("affiliation_rule_hits") or {}))
    if not lines:
        return "Tournament normalization: 0 cells changed"
    return "Tournament normalization: " + "; ".join(lines)
