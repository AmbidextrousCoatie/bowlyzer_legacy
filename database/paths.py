"""
Data path layout: published Parquet vs work intermediates vs CSV mirrors.

Published runtime artifacts (Parquet + config JSON + publish manifests) live in
``database/data`` (Docker bind-mount on VPS).

CSV exports of published datasets mirror the Parquet stems under
``database/published_csv`` (local inspection; not deployed by default).

All pipeline intermediates (scrape tree, tournament staging, GF exports,
historical extracts, audit reports) live in ``database/work`` (gitignored).

Environment:
  BOWLYZER_DATA_DIR            — override published Parquet directory
  BOWLYZER_PUBLISHED_CSV_DIR   — override published CSV mirror directory
  BOWLYZER_WORK_DATA_DIR       — override intermediate/work directory
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_DATA_DIR = REPO_ROOT / "database" / "data"
REPO_PUBLISHED_CSV_DIR = REPO_ROOT / "database" / "published_csv"
REPO_WORK_DIR = REPO_ROOT / "database" / "work"

# Logical dataset stems (Parquet in data/, CSV mirror in published_csv/).
PUBLISHED_DATASET_STEMS = frozenset(
    {
        "league_results_merged",
        "tournaments_postprocessed",
        "players_registry",
        "affiliation_index",
        "clubs_registry",
        "vereine_registry",
        "player_stats_merged_plus_tournaments",
    }
)

# Legacy repo paths kept for one-release fallback during migration.
_LEGACY_INPUT_DIR = REPO_ROOT / "database" / "input"
_LEGACY_PIPELINE_DIR = REPO_ROOT / "database" / "pipeline"


def _env_path(name: str) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def default_work_data_dir() -> Path:
    return REPO_WORK_DIR


def get_data_dir() -> Path:
    """Published Parquet + config JSON + publish manifests (VPS bind-mount)."""
    return _env_path("BOWLYZER_DATA_DIR") or REPO_DATA_DIR


def get_published_csv_dir() -> Path:
    """CSV mirrors of published datasets (local inspection; not synced to VPS)."""
    return _env_path("BOWLYZER_PUBLISHED_CSV_DIR") or REPO_PUBLISHED_CSV_DIR


def get_work_data_dir() -> Path:
    """Pipeline intermediates (legacy scrape, staging, GF exports, audits)."""
    return _env_path("BOWLYZER_WORK_DATA_DIR") or default_work_data_dir()


def _prefer_existing(primary: Path, fallback: Path) -> Path:
    if primary.is_file():
        return primary
    if fallback.is_file():
        return fallback
    return primary


def _prefer_existing_dir(primary: Path, fallback: Path) -> Path:
    if primary.is_dir():
        return primary
    if fallback.is_dir():
        return fallback
    return primary


def logical_dataset_csv(stem: str) -> Path:
    """Logical CSV path used by config and runtime (file may live in published_csv/)."""
    return get_data_dir() / f"{stem}.csv"


def published_parquet_path(logical_csv_path: Path) -> Path:
    """Parquet artifact for a logical dataset CSV path."""
    logical = Path(logical_csv_path)
    if _uses_published_layout(logical):
        return get_data_dir() / f"{logical.stem}.parquet"
    return logical.with_suffix(".parquet")


def published_csv_mirror_path(logical_csv_path: Path) -> Path:
    """CSV mirror for a logical dataset path."""
    logical = Path(logical_csv_path)
    if _uses_published_layout(logical):
        return get_published_csv_dir() / logical.name
    return logical


def _uses_published_layout(logical_csv_path: Path) -> bool:
    logical = Path(logical_csv_path)
    if logical.stem in PUBLISHED_DATASET_STEMS:
        return True
    try:
        return logical.parent.resolve() == get_data_dir().resolve()
    except OSError:
        return False


def work_or_published_file(relative_path: str) -> Path:
    """Resolve a work-dir input that may still exist at a legacy repo path."""
    work = get_work_data_dir() / relative_path
    legacy_data = REPO_DATA_DIR / Path(relative_path).name
    legacy_flat = REPO_DATA_DIR / relative_path
    for candidate in (work, legacy_flat, legacy_data):
        if candidate.is_file():
            return candidate
    return work


def _resolve_work_first(
    relative_path: str,
    *,
    repo_fallback: Path | None = None,
    label: str = "",
) -> Path:
    """
    Prefer work dir for pipeline inputs.

    Falls back to ``repo_fallback`` only when the work copy is missing (logs a note).
    """
    import sys

    work = get_work_data_dir() / relative_path
    if work.is_file():
        return work
    fallback = repo_fallback
    if fallback and fallback.is_file():
        name = label or relative_path
        print(
            f"Note: using repo fallback for {name} (not in work dir {get_work_data_dir()}):\n"
            f"       {fallback}",
            file=sys.stderr,
        )
        return fallback
    return work


def legacy_scrape_dir() -> Path:
    primary = get_work_data_dir() / "legacy_scrape"
    return _prefer_existing_dir(primary, REPO_DATA_DIR / "legacy_scrape")


def tournaments_input_dir() -> Path:
    """Flat intake folder for legacy tournament PDFs (import_tournaments.py)."""
    return get_work_data_dir() / "tournaments" / "input"


def tournament_staging_dir() -> Path:
    """Per-import tournament postprocessed CSVs before merge into published Parquet."""
    return get_work_data_dir() / "tournaments" / "staging"


def legacy_scrape_league_csv() -> Path:
    """Postprocessed league rows from the bowling-bayern.de scrape pipeline (08/09–18/19)."""
    candidates = (
        legacy_scrape_dir() / "legacy_scrape_extracted.csv",
        get_work_data_dir() / "legacy_scrape" / "legacy_scrape_extracted.csv",
        get_work_data_dir() / "legacy_scrape_extracted.csv",
    )
    existing = [path.resolve() for path in candidates if path.is_file()]
    if not existing:
        return candidates[0].resolve()
    if len(existing) == 1:
        return existing[0]
    return max(existing, key=_female_league_row_count)


def _female_league_row_count(csv_path: Path) -> int:
    try:
        import pandas as pd

        df = pd.read_csv(csv_path, sep=";", dtype=str, usecols=["League"])
        leagues = df["League"].fillna("").astype(str)
        return int(leagues.str.endswith("(D)").sum())
    except Exception:
        return 0


def work_tmp_dir() -> Path:
    return get_work_data_dir() / "tmp"


def work_audits_dir() -> Path:
    return get_work_data_dir() / "audits"


def raw_input_dir() -> Path:
    """Raw source files (xlsx workbooks, static liga CSV snapshots)."""
    return _prefer_existing_dir(get_work_data_dir() / "raw", _LEGACY_INPUT_DIR)


def analysis_log_path() -> Path:
    primary = get_work_data_dir() / "league" / "extract_excel_analysis_log.json"
    legacy = get_work_data_dir() / "extract_excel_analysis_log.json"
    legacy_data = REPO_DATA_DIR / "extract_excel_analysis_log.json"
    for candidate in (primary, legacy, legacy_data):
        if candidate.is_file():
            return candidate
    return primary


def historical_league_results_csv() -> Path:
    return _resolve_work_first(
        "league/historical_league_results.csv",
        repo_fallback=REPO_DATA_DIR / "historical_league_results.csv",
        label="historical league",
    )


def unique_team_names_after_merge_csv() -> Path:
    primary = get_work_data_dir() / "league" / "unique_team_names_after_merge.csv"
    return _prefer_existing(primary, REPO_DATA_DIR / "unique_team_names_after_merge.csv")


def merge_duplicates_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or league_results_merged_csv()
    primary = get_work_data_dir() / "league" / f"{base.stem}_duplicates.csv"
    fallback = base.parent / f"{base.stem}_duplicates.csv"
    return _prefer_existing(primary, fallback)


def merge_duplicates_non_exact_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or league_results_merged_csv()
    primary = get_work_data_dir() / "league" / f"{base.stem}_duplicates_non_exact.csv"
    fallback = base.parent / f"{base.stem}_duplicates_non_exact.csv"
    return _prefer_existing(primary, fallback)


def pipeline_gf_league_csv() -> Path:
    """GF pipeline legacy league export (current-season GF ingest)."""
    primary = get_work_data_dir() / "pipeline" / "bowling_bayern" / "legacy_out" / "latest.csv"
    fallback = _LEGACY_PIPELINE_DIR / "bowling_bayern" / "legacy_out" / "latest.csv"
    return _prefer_existing(primary, fallback)


def gf_tournament_export_dir() -> Path:
    primary = get_work_data_dir() / "gf"
    return _prefer_existing_dir(primary, _LEGACY_INPUT_DIR / "gf_tables_export")


def gf_tournaments_combined_postprocessed_csv() -> Path:
    return gf_tournament_export_dir() / "gf_tournaments_2026__combined_postprocessed.csv"


def manual_tournament_postprocessed_csv() -> Path:
    return _resolve_work_first(
        "tournaments/tournament_manual_postprocessed.csv",
        repo_fallback=REPO_DATA_DIR / "tournament_manual_postprocessed.csv",
        label="manual tournament",
    )


def league_results_merged_csv() -> Path:
    return logical_dataset_csv("league_results_merged")


def tournaments_postprocessed_csv() -> Path:
    return logical_dataset_csv("tournaments_postprocessed")


def player_stats_merged_hybrid_csv() -> Path:
    return logical_dataset_csv("player_stats_merged_plus_tournaments")


def players_registry_csv() -> Path:
    return logical_dataset_csv("players_registry")


def affiliation_index_csv() -> Path:
    return logical_dataset_csv("affiliation_index")


def vereine_registry_csv() -> Path:
    return logical_dataset_csv("vereine_registry")


def clubs_registry_csv() -> Path:
    return logical_dataset_csv("clubs_registry")


def publish_runs_dir() -> Path:
    return get_data_dir() / "runs"


def publish_latest_manifest() -> Path:
    return publish_runs_dir() / "latest.json"
