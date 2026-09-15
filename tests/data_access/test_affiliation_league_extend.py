"""League pass-2 affiliation extension and Verein-gated tournament extrapolation."""

from __future__ import annotations

import pandas as pd

from data_access.affiliation_registry import (
    build_affiliation_lookup,
    extend_affiliation_index_from_league,
    lookup_tournament_affiliation,
)
from data_access.schema import Columns
from data_access.tournament_club_resolution import (
    AFFILIATION_SOURCE_EXTRAPOLATED_PAST,
    apply_tournament_affiliation_resolution,
)


def test_extend_affiliation_index_from_league_adds_missing_seasons() -> None:
    rangliste = pd.DataFrame(
        [
            {
                "player_id": "7879",
                "season": "11/12",
                "club_raw": "Ratisbona Regensburg",
                "verein_raw": "BV 68 Regensburg",
                "club_canonical": "Ratisbona Regensburg",
                "verein_canonical": "BV 68 Regensburg",
                "is_einzelmitglied": "false",
                "source": "rangliste",
                "updated_at": "t",
            }
        ]
    )
    league = pd.DataFrame(
        [
            {
                Columns.season: "14/15",
                Columns.player_id: "7879",
                Columns.player_name: "Koller, Alexander",
                Columns.team_name: "Ratisbona Regensburg 2",
                Columns.club: "Ratisbona Regensburg",
                Columns.event_type: "league",
                Columns.computed_data: "False",
            }
        ]
    )
    extended, stats = extend_affiliation_index_from_league(rangliste, league, updated_at="t")
    assert stats["league_rows_added"] == 1
    assert len(extended) == 2
    league_row = extended.loc[extended["season"] == "14/15"].iloc[0]
    assert league_row["source"] == "league"
    assert league_row["club_canonical"] == "Ratisbona Regensburg"
    assert league_row["verein_raw"] == ""


def test_extend_affiliation_index_from_league_does_not_overwrite_rangliste() -> None:
    rangliste = pd.DataFrame(
        [
            {
                "player_id": "7879",
                "season": "14/15",
                "club_raw": "Ratisbona Regensburg",
                "verein_raw": "BV 68 Regensburg",
                "club_canonical": "Ratisbona Regensburg",
                "verein_canonical": "BV 68 Regensburg",
                "is_einzelmitglied": "false",
                "source": "rangliste",
                "updated_at": "t",
            }
        ]
    )
    league = pd.DataFrame(
        [
            {
                Columns.season: "14/15",
                Columns.player_id: "7879",
                Columns.team_name: "Other Club 1",
                Columns.club: "Other Club",
                Columns.event_type: "league",
                Columns.computed_data: "False",
            }
        ]
    )
    extended, stats = extend_affiliation_index_from_league(rangliste, league, updated_at="t")
    assert stats["league_rows_added"] == 0
    assert extended.iloc[0]["source"] == "rangliste"


def test_lookup_tournament_affiliation_extrapolates_past_when_verein_matches() -> None:
    lookup = build_affiliation_lookup(
        pd.DataFrame(
            [
                {
                    "player_id": "7879",
                    "season": "11/12",
                    "club_raw": "Ratisbona Regensburg",
                    "verein_raw": "BV 68 Regensburg",
                    "club_canonical": "Ratisbona Regensburg",
                    "verein_canonical": "BV 68 Regensburg",
                    "is_einzelmitglied": "false",
                    "source": "rangliste",
                    "updated_at": "t",
                }
            ]
        )
    )
    aff, rule = lookup_tournament_affiliation(
        "7879",
        "14/15",
        lookup,
        tournament_verein="BV 68 Regensburg",
    )
    assert rule == "extrapolated_past"
    assert aff is not None
    assert aff["club_canonical"] == "Ratisbona Regensburg"


def test_lookup_tournament_affiliation_skips_past_when_verein_differs() -> None:
    lookup = build_affiliation_lookup(
        pd.DataFrame(
            [
                {
                    "player_id": "7879",
                    "season": "11/12",
                    "club_raw": "Other Club",
                    "verein_raw": "Other Verein",
                    "club_canonical": "Other Club",
                    "verein_canonical": "Other Verein",
                    "is_einzelmitglied": "false",
                    "source": "rangliste",
                    "updated_at": "t",
                }
            ]
        )
    )
    aff, rule = lookup_tournament_affiliation(
        "7879",
        "14/15",
        lookup,
        tournament_verein="BV 68 Regensburg",
    )
    assert aff is None
    assert rule == ""


def test_tournament_extrapolation_from_past_verein_match() -> None:
    lookup = {
        ("7879", "11/12"): {
            "club_raw": "Ratisbona Regensburg",
            "verein_raw": "BV 68 Regensburg",
            "club_canonical": "Ratisbona Regensburg",
            "verein_canonical": "BV 68 Regensburg",
            "is_einzelmitglied": False,
            "source": "rangliste",
        }
    }
    frame = pd.DataFrame(
        [
            {
                Columns.season: "14/15",
                Columns.player_id: "7879",
                Columns.club: "BV 68 Regensburg",
                Columns.event_type: "tournament",
            }
        ]
    )
    out, stats = apply_tournament_affiliation_resolution(
        frame,
        affiliation_lookup=lookup,
        verein_aliases={"bv 68 regensburg": "BV 68 Regensburg"},
    )
    assert out.iloc[0][Columns.club] == "Ratisbona Regensburg"
    assert out.iloc[0][Columns.affiliation_source] == AFFILIATION_SOURCE_EXTRAPOLATED_PAST
    assert stats["extrapolated_past"] == 1


def test_league_empty_verein_extrapolates_via_club_to_verein_seed() -> None:
    """League pass-2 rows lack Verein; seed member_clubs still gates extrapolation."""
    from data_access.affiliation_registry import (
        build_club_to_verein_lookup,
        verein_identity_key,
    )

    vereine = pd.DataFrame(
        [
            {
                "canonical_verein": "1. BSV Ulm/Neu-Ulm",
                "aliases": "1. BSV Ulm/Neu Ulm|1.BSV Ulm/Neu-Ulm|Neu-Ulm",
                "member_clubs": "Falken Neu-Ulm|Murmels Neu-Ulm",
                "source": "seed",
                "updated_at": "t",
            }
        ]
    )
    lookup = build_affiliation_lookup(
        pd.DataFrame(
            [
                {
                    "player_id": "16007",
                    "season": "08/09",
                    "club_raw": "Falken Neu-Ulm",
                    "verein_raw": "",
                    "club_canonical": "Falken Neu-Ulm",
                    "verein_canonical": "",
                    "is_einzelmitglied": "false",
                    "source": "league",
                    "updated_at": "t",
                }
            ]
        ),
        club_to_verein=build_club_to_verein_lookup(vereine),
    )
    frame = pd.DataFrame(
        [
            {
                Columns.season: "06/07",
                Columns.player_id: "16007",
                Columns.club: "1. BSV Ulm/Neu Ulm",
                Columns.event_type: "tournament",
            },
            {
                Columns.season: "05/06",
                Columns.player_id: "16007",
                Columns.club: "Neu-Ulm",
                Columns.event_type: "tournament",
            },
        ]
    )
    aliases = {
        verein_identity_key("1. BSV Ulm/Neu Ulm"): "1. BSV Ulm/Neu-Ulm",
        verein_identity_key("1. BSV Ulm/Neu-Ulm"): "1. BSV Ulm/Neu-Ulm",
        verein_identity_key("Neu-Ulm"): "1. BSV Ulm/Neu-Ulm",
    }
    out, stats = apply_tournament_affiliation_resolution(
        frame,
        affiliation_lookup=lookup,
        verein_aliases=aliases,
    )
    assert out.iloc[0][Columns.club] == "Falken Neu-Ulm"
    assert out.iloc[0][Columns.history_club] == "Falken Neu-Ulm"
    assert out.iloc[0][Columns.verein] == "1. BSV Ulm/Neu-Ulm"
    assert out.iloc[1][Columns.club] == "Falken Neu-Ulm"
    assert out.iloc[1][Columns.history_club] == "Falken Neu-Ulm"
    assert stats["extrapolated_future"] == 2
