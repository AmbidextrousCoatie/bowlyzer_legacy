"""Pass-Nr ↔ EDV bridge for legacy player IDs."""

from __future__ import annotations

from data_access.aktive_mitglieder_registry import (
    AktivePlayerRow,
    build_pass_nr_edv_bridge,
    is_legacy_edv_season,
    legacy_edv_to_canonical_remap,
    normalize_pass_nr,
)
from data_access.players_registry import (
    apply_legacy_player_id_remapping,
    build_legacy_player_id_remap,
)
from data_access.schema import Columns
import pandas as pd


def test_is_legacy_edv_season_app_and_folder() -> None:
    assert is_legacy_edv_season("05/06") is True
    assert is_legacy_edv_season("06/07") is False
    assert is_legacy_edv_season("2005-06") is True
    assert is_legacy_edv_season("2006-07") is False


def test_normalize_pass_nr() -> None:
    assert normalize_pass_nr("D  131530") == "D 131530"
    assert normalize_pass_nr("") == ""


def test_build_pass_nr_edv_bridge_maps_legacy_to_modern() -> None:
    rows = [
        (
            "2005-06",
            AktivePlayerRow("10225", "Barchmann, Jens", "05/06", pass_nr="884879"),
        ),
        (
            "2007-08",
            AktivePlayerRow("7042", "Barchmann, Jens", "07/08", pass_nr="884879"),
        ),
        (
            "2010-11",
            AktivePlayerRow("7042", "Barchmann, Jens", "10/11", pass_nr="884879"),
        ),
    ]
    bridges = build_pass_nr_edv_bridge(rows)
    assert "884879" in bridges
    bridge = bridges["884879"]
    assert bridge.player_id == "7042"
    assert bridge.player_id_legacy == ("10225",)
    remap = legacy_edv_to_canonical_remap(bridges)
    assert remap["10225"] == "7042"


def test_apply_legacy_player_id_remapping() -> None:
    registry = pd.DataFrame(
        [
            {
                "player_id": "7042",
                "player_id_legacy": "10107|10225",
                "player_id_pass": "884879",
                "canonical_name": "Barchmann, Jens",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            }
        ]
    )
    remap = build_legacy_player_id_remap(registry)
    assert remap["10107"] == "7042"
    assert remap["10225"] == "7042"

    frame = pd.DataFrame(
        [
            {Columns.player_id: "10225", Columns.player_name: "Barchmann, Jens"},
            {Columns.player_id: "7042", Columns.player_name: "Barchmann, Jens"},
        ]
    )
    out, stats = apply_legacy_player_id_remapping(frame, remap)
    assert out.iloc[0][Columns.player_id] == "7042"
    assert out.iloc[1][Columns.player_id] == "7042"
    assert stats["legacy_id_remapped"] == 1
