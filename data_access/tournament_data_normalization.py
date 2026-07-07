"""Normalize tournament rows after Excel/PDF extraction (mirrors league merge steps)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

import pandas as pd

from data_access.clubs_registry import apply_clubs_registry
from data_access.player_id_name_normalization import (
    apply_player_id_name_normalization,
    load_player_id_only_remapping_rules,
)
from data_access.players_registry import apply_players_registry, load_players_registry_df
from data_access.schema import Columns


def normalize_tournament_dataframe(
    df: pd.DataFrame,
    *,
    normalize_clubs: bool = True,
    normalize_player_ids: bool = True,
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
    }

    if normalize_clubs and Columns.club in out.columns:
        out, club_stats = apply_clubs_registry(out)
        stats["club_registry_rule_hits"] = dict(club_stats)
        stats["club_registry_rows_changed"] = int(
            club_stats.get("club_registry_exact", 0)
            + club_stats.get("club_registry_prefix", 0)
            + club_stats.get("club_registry_team_norm", 0)
            + club_stats.get("club_registry_suffix", 0)
            + club_stats.get("club_registry_legal_strip", 0)
        )
        stats["club_registry_unresolved"] = int(club_stats.get("club_registry_unresolved", 0))

    if normalize_player_ids:
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
    reg = int(stats.get("registry_rows_changed") or 0)
    if reg:
        lines.append(f"Players registry: {reg} row(s)")
    if not lines:
        return "Tournament normalization: 0 cells changed"
    return "Tournament normalization: " + "; ".join(lines)
