"""
CSV data paths: published runtime files vs pipeline intermediates.

Published CSVs (merged league, player hybrid, tournament configs) default to
``database/data`` in the repo (Docker bind-mount). Pipeline intermediates
(legacy scrape tree, dedupe reports, historical extract, analysis log) default
to ``C:\\tmp\\bowlyzer\\data`` on Windows or ``database/data`` on Linux unless
``BOWLYZER_WORK_DATA_DIR`` is set.

Environment:
  BOWLYZER_DATA_DIR       — override published/runtime data directory
  BOWLYZER_WORK_DATA_DIR  — override intermediate/work data directory
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_DATA_DIR = REPO_ROOT / "database" / "data"


def _env_path(name: str) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def default_work_data_dir() -> Path:
    if os.name == "nt":
        return Path(r"C:\tmp\bowlyzer\data")
    return REPO_DATA_DIR


def get_data_dir() -> Path:
    """Runtime / published CSVs consumed by the app (and deployed to VPS)."""
    return _env_path("BOWLYZER_DATA_DIR") or REPO_DATA_DIR


def get_work_data_dir() -> Path:
    """Pipeline intermediates (legacy scrape, dedupe reports, historical extract)."""
    return _env_path("BOWLYZER_WORK_DATA_DIR") or default_work_data_dir()


def _prefer_existing(primary: Path, fallback: Path) -> Path:
    if primary.exists():
        return primary
    if fallback.exists():
        return fallback
    return primary


def legacy_scrape_dir() -> Path:
    primary = get_work_data_dir() / "legacy_scrape"
    return _prefer_existing(primary, REPO_DATA_DIR / "legacy_scrape")


def work_tmp_dir() -> Path:
    primary = get_work_data_dir() / "tmp"
    return _prefer_existing(primary, REPO_DATA_DIR / "tmp")


def analysis_log_path() -> Path:
    primary = get_work_data_dir() / "extract_excel_analysis_log.json"
    return _prefer_existing(primary, REPO_DATA_DIR / "extract_excel_analysis_log.json")


def historical_league_results_csv() -> Path:
    primary = get_work_data_dir() / "historical_league_results.csv"
    return _prefer_existing(primary, REPO_DATA_DIR / "historical_league_results.csv")


def unique_team_names_after_merge_csv() -> Path:
    primary = get_work_data_dir() / "unique_team_names_after_merge.csv"
    return _prefer_existing(primary, REPO_DATA_DIR / "unique_team_names_after_merge.csv")


def merge_duplicates_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or (get_data_dir() / "league_results_merged.csv")
    primary = get_work_data_dir() / f"{base.stem}_duplicates.csv"
    fallback = base.parent / f"{base.stem}_duplicates.csv"
    return _prefer_existing(primary, fallback)


def merge_duplicates_non_exact_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or (get_data_dir() / "league_results_merged.csv")
    primary = get_work_data_dir() / f"{base.stem}_duplicates_non_exact.csv"
    fallback = base.parent / f"{base.stem}_duplicates_non_exact.csv"
    return _prefer_existing(primary, fallback)
