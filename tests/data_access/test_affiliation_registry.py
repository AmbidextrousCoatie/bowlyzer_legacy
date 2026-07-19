"""Rangliste affiliation registry."""

from __future__ import annotations

import pandas as pd

from data_access.affiliation_registry import (
    build_affiliation_lookup,
    build_vereine_registry_dataframe,
    neighbor_seasons,
    resolve_rangliste_club_canonical,
)
from data_access.aktive_mitglieder_registry import (
    is_einzelmitglied_club,
    row_to_aktive_player,
)
from data_access.clubs_registry import club_identity_key


def test_row_to_aktive_player_reads_club_and_verein() -> None:
    cols = {
        "edvnr": 0,
        "nachname": 1,
        "vorname": 2,
        "zusatz": 3,
        "club": 4,
        "verein": 5,
    }
    row = row_to_aktive_player(
        ["7879", "Koller", "Alexander", "", "Ratisbona Regensburg", "BV 68 Regensburg"],
        layout="split",
        columns=cols,
    )
    assert row is not None
    assert row.club == "Ratisbona Regensburg"
    assert row.verein == "BV 68 Regensburg"
    assert not row.is_einzelmitglied


def test_is_einzelmitglied_club() -> None:
    assert is_einzelmitglied_club("Einzelmitglied")
    assert not is_einzelmitglied_club("Ratisbona Regensburg")


def test_resolve_rangliste_club_canonical_manual_crosswalk() -> None:
    crosswalk = {club_identity_key("Ratisbona Regensburg"): "Ratisbona Regensburg"}
    canonical, hit = resolve_rangliste_club_canonical("Ratisbona Regensburg", crosswalk)
    assert hit is True
    assert canonical == "Ratisbona Regensburg"


def test_resolve_rangliste_club_canonical_uses_club_mapping() -> None:
    """Historical Rangliste spellings fold via club_mapping.csv (not only crosswalk)."""
    canonical, hit = resolve_rangliste_club_canonical("BC Donau - Bowler", {})
    assert hit is True
    assert canonical == "Donaubowler Regensburg"


def test_build_vereine_registry_from_affiliation_rows() -> None:
    affiliation_df = pd.DataFrame(
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
            },
            {
                "player_id": "9999",
                "season": "14/15",
                "club_raw": "Einzelmitglied",
                "verein_raw": "1. BBV Lindau",
                "club_canonical": "",
                "verein_canonical": "1. BBV Lindau",
                "is_einzelmitglied": "true",
                "source": "rangliste",
                "updated_at": "t",
            },
        ]
    )
    vereine = build_vereine_registry_dataframe(affiliation_df, updated_at="t")
    names = set(vereine["canonical_verein"].tolist())
    assert "BV 68 Regensburg" in names
    assert "1. BBV Lindau" in names
    bv = vereine.loc[vereine["canonical_verein"] == "BV 68 Regensburg"].iloc[0]
    assert "Ratisbona Regensburg" in bv["member_clubs"]


def test_neighbor_seasons() -> None:
    assert neighbor_seasons("14/15") == ["13/14", "15/16"]


def test_build_affiliation_lookup_keyed_by_player_season() -> None:
    df = pd.DataFrame(
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
    lookup = build_affiliation_lookup(df)
    assert lookup[("7879", "11/12")]["club_canonical"] == "Ratisbona Regensburg"


def test_affiliation_index_remaps_legacy_edv_for_early_seasons(monkeypatch, tmp_path) -> None:
    """05/06 Aktive rows use pre-renumber EDVs; index must key by canonical player_id."""
    from data_access.aktive_mitglieder_registry import AktiveParseStats, AktivePlayerRow
    import data_access.affiliation_registry as aff_mod

    raw = [
        AktivePlayerRow(
            player_id="40105",
            canonical_name="Bauhofer, Bernd",
            season="05/06",
            club="BC Berchtesgaden",
            verein="BSV Berchtesgaden",
            pass_nr="54221",
        ),
        AktivePlayerRow(
            player_id="7245",
            canonical_name="Bauhofer, Bernd",
            season="08/09",
            club="BC Berchtesgaden",
            verein="BSV Berchtesgaden",
            pass_nr="54221",
        ),
    ]

    monkeypatch.setattr(
        aff_mod,
        "_collect_affiliation_rows",
        lambda root=None, min_season=None: (raw, AktiveParseStats(seasons_selected=2)),
    )
    bridge_input = [("2005-06", raw[0]), ("2008-09", raw[1])]
    monkeypatch.setattr(
        "data_access.aktive_mitglieder_registry.collect_aktive_rows_with_seasons",
        lambda root=None, min_season=None: (bridge_input, AktiveParseStats(seasons_selected=2)),
    )
    monkeypatch.setattr(
        "data_access.players_registry.build_legacy_player_id_remap",
        lambda: {"40105": "7245"},
    )
    monkeypatch.setattr(aff_mod, "load_rangliste_club_crosswalk", lambda: {})

    df, stats = aff_mod.build_affiliation_index_dataframe(root=tmp_path, updated_at="t")
    assert ("7245", "05/06") in {
        (str(r.player_id), str(r.season)) for r in df.itertuples(index=False)
    }
    row = df.loc[(df["player_id"] == "7245") & (df["season"] == "05/06")].iloc[0]
    assert row["club_raw"] == "BC Berchtesgaden"
    assert "40105" not in set(df["player_id"].astype(str))
    assert stats.unique_player_seasons == 2
