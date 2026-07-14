"""Tournament data quality API for Diagnose UI."""

from __future__ import annotations

from pathlib import Path

from app.services.tournament_data_quality_service import (
    get_tournament_data_quality,
    load_tournament_quality_report_csv,
)


def test_load_tournament_quality_report_csv(tmp_path: Path) -> None:
    report = tmp_path / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "23/24;BM 2024;BM M;10;8;0;1;0;0;0;0;0;yellow;missing_club: 1;\n",
        encoding="utf-8",
    )
    rows = load_tournament_quality_report_csv(report)
    assert len(rows) == 1
    assert rows[0]["event_name"] == "BM 2024"
    assert rows[0]["status"] == "yellow"
    assert rows[0]["findings"] == ["missing_club: 1"]


def test_get_tournament_data_quality_from_report(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "23/24;BM 2024;BM M;10;8;0;0;0;0;0;0;0;green;;\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_tournament_data_quality()
    assert payload["source"] == "report"
    assert payload["row_count"] == 1
    assert payload["summary"]["green"] == 1


def test_get_tournament_data_quality_attaches_source_pdf(tmp_path: Path, monkeypatch) -> None:
    from database.tournament_import.source_registry import TournamentSourceRow, write_source_registry

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    registry_path = tmp_path / "registry.csv"
    write_source_registry(
        [
            TournamentSourceRow(
                file_basename="bm2014_nb_he_erg.pdf",
                file_fingerprint="abc",
                file_path="bm2014_nb_he_erg.pdf",
                season="13/14",
                calendar_year=2014,
                category_id="nordbayerische-herren",
                tournament_id="NBM M",
                event_name="Nordbayerische Meisterschaft",
                gender="male",
                format="legacy_pdf_erg_2016",
                enabled=True,
            )
        ],
        registry_path,
    )
    report = work_dir / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "13/14;Nordbayerische Meisterschaft;NBM M;10;8;0;0;0;0;0;0;0;green;;\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))
    monkeypatch.setattr(
        "database.tournament_import.source_registry.DEFAULT_REGISTRY_PATH",
        registry_path,
    )
    from database.tournament_import import source_registry as registry_mod

    registry_mod.load_source_registry.cache_clear()
    registry_mod.registry_by_basename.cache_clear()
    registry_mod.registry_by_fingerprint.cache_clear()
    registry_mod.registry_by_season_event.cache_clear()

    payload = get_tournament_data_quality()
    row = payload["rows"][0]
    assert row["source_pdf_basename"] == "bm2014_nb_he_erg.pdf"


def test_resolve_tournament_source_pdf_path_accepts_xls(tmp_path: Path, monkeypatch) -> None:
    from app.services.tournament_data_quality_service import resolve_tournament_source_pdf_path

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    xls_path = input_dir / "bm2007_einz_erg.xls"
    xls_path.write_bytes(b"xls-bytes")
    monkeypatch.setattr(
        "app.services.tournament_data_quality_service.tournaments_input_dir",
        lambda: input_dir,
    )
    assert resolve_tournament_source_pdf_path("bm2007_einz_erg.xls") == xls_path


def test_get_tournament_data_quality_includes_source_exceptions(tmp_path: Path, monkeypatch) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_tournament_data_quality()
    assert "source_exceptions" in payload
    assert any(item["id"] == "bm-2007-einz-dual-xls" for item in payload["source_exceptions"])


def test_get_tournament_data_quality_attaches_exception_source_sheet(
    tmp_path: Path, monkeypatch
) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    report = work_dir / "tournament_data_quality.csv"
    report.write_text(
        "season;event_name;tournament_group;row_count;player_count;missing_player_id;"
        "missing_club;club_names_normalized;player_id_remap_rows;registry_rows_changed;"
        "same_name_different_ids;same_id_different_names;status;findings;notes\n"
        "06/07;Bayerische Meisterschaft Einzel 2007;BM M;10;8;0;0;0;0;0;0;0;green;;\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work_dir))

    payload = get_tournament_data_quality()
    row = payload["rows"][0]
    assert row["source_pdf_basename"] == "bm2007_einz_erg.xls"
    assert row["source_sheet"] == "Herren"
    assert row["source_format"] == "legacy_bm_einz_xls_dual"
