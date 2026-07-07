"""Import resolved club mappings into club_mapping.csv."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_access.club_mapping_import import merge_resolved_mappings_into_club_mapping


def test_merge_resolved_mappings_into_club_mapping(tmp_path: Path, monkeypatch) -> None:
    mapping_path = tmp_path / "club_mapping.csv"
    mapping_path.write_text(
        "canonical_name,aliases\n"
        "Lechbowler Augsburg,AUG - Lechbowler Augsburg\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "data_access.club_mapping_import._club_mapping_path",
        lambda: mapping_path,
    )
    monkeypatch.setattr(
        "data_access.club_mapping_import.load_club_mapping_rows",
        lambda: [
            {
                "canonical_name": "Lechbowler Augsburg",
                "aliases": ["AUG - Lechbowler Augsburg"],
            }
        ],
    )

    summary = merge_resolved_mappings_into_club_mapping(
        {
            "REG - Ratisbona": "Ratisbona Regensburg",
            "AUG - Tiger": "Tiger Augsburg",
        },
        club_mapping_path=mapping_path,
    )
    assert summary["aliases_added"] == 2
    text = mapping_path.read_text(encoding="utf-8")
    assert "REG - Ratisbona" in text
    assert "Ratisbona Regensburg" in text
