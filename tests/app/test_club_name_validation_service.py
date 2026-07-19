"""Club name validation API for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.club_name_validation_service import (
    get_club_name_validation,
    save_club_name_validation_mappings,
)
from data_access.club_name_validation import (
    CLUB_NAME_CONFLICTS_CSV,
    CLUB_NAME_MAPPING_RESOLVED_CSV,
    build_club_name_validation_rows,
    write_club_name_mapping_resolved,
)


def test_build_rows_default_to_proposal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "data_access.club_name_validation.load_registry_canonical_names",
        lambda: ["Ratisbona Regensburg", "Other Club"],
    )
    rows = build_club_name_validation_rows(
        [
            {
                "club_label": "REG - Ratisbona",
                "row_count": 10,
                "proposed_canonical": "Ratisbona Regensburg",
                "proposed_rule": "fuzzy_after_prefix_strip",
            }
        ]
    )
    assert rows[0]["default_canonical"] == "Ratisbona Regensburg"


def test_save_and_load_mappings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "data_access.club_name_validation.get_work_data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "data_access.club_name_validation.load_registry_canonical_names",
        lambda: ["Lechbowler Augsburg"],
    )
    out = write_club_name_mapping_resolved(
        [{"unresolved_label": "AUG - Lechbowler Augsburg", "canonical_name": "Lechbowler Augsburg"}],
        merge_existing=False,
    )
    assert out.name == CLUB_NAME_MAPPING_RESOLVED_CSV
    text = out.read_text(encoding="utf-8")
    assert "AUG - Lechbowler Augsburg" in text
    assert "Lechbowler Augsburg" in text


def test_get_club_name_validation_from_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.club_name_validation_service.get_work_data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "data_access.club_name_validation.get_work_data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "data_access.club_name_validation.load_registry_canonical_names",
        lambda: ["Ratisbona Regensburg"],
    )
    monkeypatch.setattr(
        "app.services.club_name_validation_service.audit_unresolved_tournament_clubs",
        lambda: [],
    )
    report = tmp_path / CLUB_NAME_CONFLICTS_CSV
    report.write_text(
        "issue_type;source_file;club_label;row_count;proposed_canonical;proposed_rule;peer_labels\n"
        "tournament_club_unknown;tournaments_postprocessed.csv;REG - Ratisbona;5;Ratisbona Regensburg;fuzzy_after_prefix_strip;\n",
        encoding="utf-8",
    )
    payload = get_club_name_validation()
    assert payload["source"] == "report"
    assert payload["row_count"] == 1
    assert payload["rows"][0]["club_label"] == "REG - Ratisbona"
    assert payload["rows"][0]["default_canonical"] == "Ratisbona Regensburg"
    assert "club_mapping" in payload


def test_save_club_name_validation_mappings_service(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.club_name_validation_service.get_work_data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "data_access.club_name_validation.get_work_data_dir",
        lambda: tmp_path,
    )
    mapping_csv = tmp_path / "club_mapping.csv"
    monkeypatch.setattr(
        "app.services.club_name_validation_service._club_mapping_path",
        lambda: mapping_csv,
    )
    monkeypatch.setattr(
        "data_access.club_mapping_import._club_mapping_path",
        lambda: mapping_csv,
    )
    monkeypatch.setattr(
        "data_access.clubs_registry._club_mapping_path",
        lambda: mapping_csv,
    )
    monkeypatch.setattr(
        "data_access.clubs_registry.load_club_mapping_rows",
        lambda: [],
    )

    registry_df = pd.DataFrame(
        [
            {
                "canonical_name": "Tiger Augsburg",
                "aliases": "",
                "team_labels": "Tiger Augsburg 1",
                "source": "league_merge",
                "updated_at": "t",
            }
        ]
    )
    monkeypatch.setattr(
        "data_access.clubs_registry.load_clubs_registry_df",
        lambda: registry_df.copy(),
    )
    published: dict = {}

    def _fake_write(df, *, write_csv=False):
        published["df"] = df.copy()
        published["write_csv"] = write_csv
        return {"parquet": tmp_path / "clubs_registry.parquet", "csv": None}

    monkeypatch.setattr("data_access.clubs_registry.write_clubs_registry", _fake_write)

    result = save_club_name_validation_mappings(
        [{"unresolved_label": "AUG - Tiger", "canonical_name": "Tiger Augsburg"}]
    )
    assert result["ok"] is True
    assert result["row_count"] == 1
    assert (tmp_path / CLUB_NAME_MAPPING_RESOLVED_CSV).is_file()
    assert mapping_csv.is_file()
    assert "AUG - Tiger" in mapping_csv.read_text(encoding="utf-8")
    assert result["club_mapping"]["aliases_added"] == 1
    assert result["clubs_registry"]["aliases_added"] == 1
    assert "AUG - Tiger" in str(published["df"].iloc[0]["aliases"])
