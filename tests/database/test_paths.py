"""database.paths — work vs published data directories."""

import os
from pathlib import Path

from database.paths import (
    REPO_DATA_DIR,
    REPO_WORK_DIR,
    default_work_data_dir,
    get_data_dir,
    get_published_csv_dir,
    get_work_data_dir,
    legacy_scrape_dir,
)


def test_default_work_dir_is_repo_local(monkeypatch):
    monkeypatch.delenv("BOWLYZER_WORK_DATA_DIR", raising=False)
    assert default_work_data_dir() == REPO_WORK_DIR


def test_work_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))
    assert get_work_data_dir() == (tmp_path / "work").resolve()


def test_data_dir_defaults_to_repo(monkeypatch):
    monkeypatch.delenv("BOWLYZER_DATA_DIR", raising=False)
    assert get_data_dir() == REPO_DATA_DIR


def test_published_csv_dir_defaults_to_repo(monkeypatch):
    monkeypatch.delenv("BOWLYZER_PUBLISHED_CSV_DIR", raising=False)
    assert get_published_csv_dir().name == "published_csv"


def test_legacy_scrape_prefers_work_dir(monkeypatch, tmp_path):
    work = tmp_path / "work"
    legacy = work / "legacy_scrape"
    legacy.mkdir(parents=True)
    (legacy / "marker.txt").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work))
    assert legacy_scrape_dir() == legacy
