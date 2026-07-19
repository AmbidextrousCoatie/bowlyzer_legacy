"""Clubs registry from league merge."""

from __future__ import annotations

import pandas as pd

from data_access.clubs_registry import (
    apply_clubs_registry,
    build_registry_dataframe_from_league,
    build_alias_to_canonical,
    propose_club_resolution,
    resolve_club_label,
    strip_regional_club_prefix,
)
from data_access.schema import Columns


def test_build_registry_from_league_teams() -> None:
    league = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "League": "LL N1",
                "Team": "Donaubowler Regensburg 2",
                "Opponent": "Castra Regina Regensburg 1",
                "Computed Data": "False",
            },
        ]
    )
    reg = build_registry_dataframe_from_league(league)
    names = set(reg["canonical_name"].tolist())
    assert "Donaubowler Regensburg" in names
    assert "Castra Regina Regensburg" in names


def test_resolve_regional_prefix_via_mapping() -> None:
    league = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "League": "LL N1",
                "Team": "Lechbowler Augsburg 1",
                "Opponent": "Other Club 1",
                "Computed Data": "False",
            },
        ]
    )
    reg = build_registry_dataframe_from_league(league)
    lookup = build_alias_to_canonical(reg)
    canonical, rule = resolve_club_label(
        "AUG - Lechbowler Augsburg",
        lookup,
        reg["canonical_name"].tolist(),
    )
    assert canonical == "Lechbowler Augsburg"
    assert rule in {"exact", "strip_regional_prefix"}


def test_apply_clubs_registry_updates_tournament_rows() -> None:
    league = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "League": "LL N1",
                "Team": "Kings Club Bayreuth Land 1",
                "Opponent": "X 1",
                "Computed Data": "False",
            },
        ]
    )
    reg = build_registry_dataframe_from_league(league)
    tournament = pd.DataFrame(
        [{"Player": "A", "Club": "BAL - Kings Club Bayreuth"}],
    )
    out, stats = apply_clubs_registry(tournament, reg)
    assert out.iloc[0][Columns.club] == "Kings Club Bayreuth Land"
    changed = (
        stats["club_registry_prefix"]
        + stats["club_registry_exact"]
        + stats["club_registry_team_norm"]
        + stats["club_registry_suffix"]
    )
    assert changed >= 1


def test_propose_fuzzy_after_prefix_strip() -> None:
    league = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "League": "LL N1",
                "Team": "Ratisbona Regensburg 2",
                "Opponent": "X 1",
                "Computed Data": "False",
            },
        ]
    )
    reg = build_registry_dataframe_from_league(league)
    lookup = build_alias_to_canonical(reg)
    proposals = propose_club_resolution(
        "REG - Ratisbona",
        lookup,
        reg["canonical_name"].tolist(),
    )
    assert any(canonical == "Ratisbona Regensburg" for canonical, _rule in proposals)


def test_strip_regional_prefix() -> None:
    assert strip_regional_club_prefix("AUG - Lechbowler Augsburg") == "Lechbowler Augsburg"


def test_club_mapping_collapses_alternate_canonical(monkeypatch) -> None:
    """Alias in club_mapping.csv must not remain a second canonical club."""
    from data_access import clubs_registry as mod

    monkeypatch.setattr(
        mod,
        "load_club_mapping_rows",
        lambda: [
            {
                "canonical_name": "SW 77 Würzburg",
                "aliases": ["Schwarz-Weiß 77 Würzburg"],
            }
        ],
    )
    league = pd.DataFrame(
        [
            {
                "Season": "24/25",
                "League": "LL N1",
                "Team": "SW 77 Würzburg 1",
                "Opponent": "Schwarz-Weiß 77 Würzburg 2",
                "Computed Data": "False",
            },
        ]
    )
    reg = build_registry_dataframe_from_league(league)
    names = set(reg["canonical_name"].tolist())
    assert "SW 77 Würzburg" in names
    assert "Schwarz-Weiß 77 Würzburg" not in names
    row = reg.loc[reg["canonical_name"] == "SW 77 Würzburg"].iloc[0]
    assert "Schwarz-Weiß 77 Würzburg" in row["aliases"]
    lookup = build_alias_to_canonical(reg)
    canonical, _rule = resolve_club_label(
        "Schwarz-Weiß 77 Würzburg",
        lookup,
        reg["canonical_name"].tolist(),
    )
    assert canonical == "SW 77 Würzburg"
