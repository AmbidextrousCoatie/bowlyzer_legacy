"""Tests for legacy PDF target resolution."""

from pathlib import Path
from unittest.mock import patch

import pytest

from database.tournament_import.legacy_pdf_targets import (
    LegacyPdfTarget,
    calendar_years_for_season_range,
    import_entry_for_target,
    resolve_legacy_pdf_targets,
)


def test_calendar_years_for_season_range() -> None:
    assert calendar_years_for_season_range(2016, 2018) == [2017, 2018, 2019]


def test_resolve_legacy_pdf_targets_picks_best_match(tmp_path: Path) -> None:
    (tmp_path / "bm2017_sb_he_erg.pdf").write_bytes(b"%PDF")
    (tmp_path / "bm2017_akt_sb_he_erg.pdf").write_bytes(b"%PDF")
    (tmp_path / "bm2017_nb_he_erg.pdf").write_bytes(b"%PDF")
    (tmp_path / "bm2017_akt_einz_he_erg.pdf").write_bytes(b"%PDF")

    resolved = resolve_legacy_pdf_targets(
        tournaments=["sbm", "nbm", "bm"],
        first_year=2016,
        last_year=2016,
        input_dir=tmp_path,
    )

    assert resolved.missing == []
    assert len(resolved.targets) == 3
    by_code = {target.tournament_code: target for target in resolved.targets}
    assert by_code["sbm"].pdf_path.name == "bm2017_akt_sb_he_erg.pdf"
    assert by_code["nbm"].calendar_year == 2017
    assert by_code["bm"].category_id == "bayerische-einzel-herren"


def test_resolve_legacy_pdf_targets_reports_missing(tmp_path: Path) -> None:
    resolved = resolve_legacy_pdf_targets(
        tournaments=["sbm"],
        first_year=2016,
        last_year=2016,
        input_dir=tmp_path,
    )
    assert resolved.targets == []
    assert resolved.missing == ["sbm:2017 (season 2016-17)"]


def test_import_entry_for_target_sets_distinct_bm_event_names(tmp_path: Path) -> None:
    men = LegacyPdfTarget(
        tournament_code="bm",
        category_id="bayerische-einzel-herren",
        season_start_year=2016,
        calendar_year=2017,
        pdf_path=tmp_path / "bm2017_akt_einz_he_erg.pdf",
    )
    women = LegacyPdfTarget(
        tournament_code="bm_f",
        category_id="bayerische-einzel-frauen",
        season_start_year=2016,
        calendar_year=2017,
        pdf_path=tmp_path / "bm2017_akt_einz_da_erg.pdf",
    )
    men_entry = import_entry_for_target(men)
    women_entry = import_entry_for_target(women)
    assert men_entry.options["event_name"] == "Bayerische Meisterschaft Einzel 2017"
    assert women_entry.options["event_name"] == "Bayerische Meisterschaft Einzel Damen 2017"


def test_import_entry_for_target_uses_legacy_format(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2016_sb_he_erg.pdf"
    pdf.write_bytes(b"%PDF")
    target = LegacyPdfTarget(
        tournament_code="sbm",
        category_id="suedbayerische-herren",
        season_start_year=2015,
        calendar_year=2016,
        pdf_path=pdf,
    )
    with patch(
        "database.tournament_import.legacy_pdf_targets.resolve_legacy_pdf_import_format",
        return_value="legacy_pdf_erg_2016",
    ):
        entry = import_entry_for_target(target)
    assert entry.id == "legacy-sbm-2016"
    assert entry.format == "legacy_pdf_erg_2016"
    assert entry.source == str(pdf)
    assert entry.options.get("skip_line_patterns") == ["Keine Teilnahme BM!"]


def test_resolve_legacy_pdf_targets_skips_doubles_even_when_requested(tmp_path: Path) -> None:
    (tmp_path / "bm2018_akt_dopp_m_erg.pdf").write_bytes(b"%PDF")
    (tmp_path / "bm2018_akt_dopp_f_erg.pdf").write_bytes(b"%PDF")

    resolved = resolve_legacy_pdf_targets(
        tournaments=["bm_md", "bm_dd"],
        first_year=2017,
        last_year=2017,
        input_dir=tmp_path,
    )

    assert resolved.targets == []
    assert resolved.missing == []


def test_import_entry_for_target_detects_2012_grid(tmp_path: Path) -> None:
    pdf = tmp_path / "bm2012_sbm_h_erg.pdf"
    pdf.write_bytes(b"%PDF")
    target = LegacyPdfTarget(
        tournament_code="sbm",
        category_id="suedbayerische-herren",
        season_start_year=2011,
        calendar_year=2012,
        pdf_path=pdf,
    )
    with patch(
        "database.tournament_import.legacy_pdf_targets.resolve_legacy_pdf_import_format",
        return_value="legacy_pdf_erg_2012",
    ):
        entry = import_entry_for_target(target)
    assert entry.format == "legacy_pdf_erg_2012"
