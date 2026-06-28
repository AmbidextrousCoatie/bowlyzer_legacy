"""Clubmeisterschaft importer workbook fingerprint."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTER_PATH = REPO_ROOT / "database" / "input" / "import_clubmeisterschaft_donaubowler_xlsx.py"
SAMPLE_XLSX = REPO_ROOT / "database/input/clubmeisterschaft_donaubowler/Clubpokal DB 2026.xlsx"
OLDER_XLSX = REPO_ROOT / "database/input/clubmeisterschaft_donaubowler/Clubpokal DB 2026_05_21.xlsx"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_clubmeisterschaft_donaubowler_xlsx", IMPORTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _rewrite_zip(src: Path, *, mutate: str | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if mutate and info.filename == mutate:
                data = data.replace(b"2026", b"2099", 1)
            zout.writestr(info, data)
    return out.getvalue()


@pytest.fixture(scope="module")
def importer():
    return _load_importer()


def test_fingerprint_stable_for_same_workbook(importer) -> None:
    if not SAMPLE_XLSX.is_file():
        pytest.skip(f"missing sample workbook: {SAMPLE_XLSX}")

    kwargs = dict(season="25/26", event_date="2026-05-15")
    first = importer.compute_workbook_fingerprint(SAMPLE_XLSX, **kwargs)
    second = importer.compute_workbook_fingerprint(SAMPLE_XLSX, **kwargs)
    assert first == second
    assert len(first) == 64


def test_fingerprint_ignores_zip_metadata_drift(importer, tmp_path: Path) -> None:
    if not SAMPLE_XLSX.is_file():
        pytest.skip(f"missing sample workbook: {SAMPLE_XLSX}")

    repacked = tmp_path / "repacked.xlsx"
    repacked.write_bytes(_rewrite_zip(SAMPLE_XLSX, mutate="docProps/core.xml"))

    kwargs = dict(season="25/26", event_date="2026-05-15")
    assert importer.compute_workbook_fingerprint(SAMPLE_XLSX, **kwargs) == importer.compute_workbook_fingerprint(
        repacked, **kwargs
    )


def test_fingerprint_changes_when_sheet_data_changes(importer, tmp_path: Path) -> None:
    if not OLDER_XLSX.is_file() or not SAMPLE_XLSX.is_file():
        pytest.skip("missing dated Clubpokal sample workbooks")

    kwargs = dict(season="25/26", event_date="2026-05-15")
    older = importer.compute_workbook_fingerprint(OLDER_XLSX, **kwargs)
    current = importer.compute_workbook_fingerprint(SAMPLE_XLSX, **kwargs)
    assert older != current


def test_fingerprint_cli_flag(importer, capsys) -> None:
    if not SAMPLE_XLSX.is_file():
        pytest.skip(f"missing sample workbook: {SAMPLE_XLSX}")

    expected = importer.compute_workbook_fingerprint(
        SAMPLE_XLSX,
        season="25/26",
        event_date="2026-05-15",
    )

    argv = [
        "import_clubmeisterschaft_donaubowler_xlsx.py",
        "--fingerprint",
        "--xlsx",
        str(SAMPLE_XLSX),
        "--season",
        "25/26",
        "--date",
        "2026-05-15",
    ]
    import sys

    old_argv = sys.argv
    try:
        sys.argv = argv
        importer.main()
    finally:
        sys.argv = old_argv

    assert capsys.readouterr().out.strip() == expected
