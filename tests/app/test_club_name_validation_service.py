"""Club name validation API for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

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


def test_save_club_name_validation_mappings_service(tmp_path: Path, monkeypatch) -> None:
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
        lambda: ["Tiger Augsburg"],
    )
    result = save_club_name_validation_mappings(
        [{"unresolved_label": "AUG - Tiger", "canonical_name": "Tiger Augsburg"}]
    )
    assert result["ok"] is True
    assert result["row_count"] == 1
    assert (tmp_path / CLUB_NAME_MAPPING_RESOLVED_CSV).is_file()
