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
    if primary.is_file():
        return primary
    if fallback.is_file():
        return fallback
    return primary


def work_or_published_file(filename: str) -> Path:
    """Resolve an input that may live in work dir (build) or published ``database/data``."""
    return _prefer_existing(get_work_data_dir() / filename, get_data_dir() / filename)


def _resolve_work_first(
    filename: str,
    *,
    repo_fallback: Path | None = None,
    label: str = "",
) -> Path:
    """
    Prefer ``BOWLYZER_WORK_DATA_DIR`` / default work dir for pipeline inputs.

    Falls back to ``repo_fallback`` only when the work copy is missing (logs a note).
    """
    import sys

    work = get_work_data_dir() / filename
    if work.is_file():
        return work
    fallback = repo_fallback or (REPO_DATA_DIR / filename)
    if fallback.is_file():
        name = label or filename
        print(
            f"Note: using repo fallback for {name} (not in work dir {get_work_data_dir()}):\n"
            f"       {fallback}",
            file=sys.stderr,
        )
        return fallback
    return work


def legacy_scrape_dir() -> Path:
    primary = get_work_data_dir() / "legacy_scrape"
    return _prefer_existing(primary, REPO_DATA_DIR / "legacy_scrape")


def legacy_scrape_league_csv() -> Path:
    """Postprocessed league rows from the legacy web-scrape pipeline (optional merge input)."""
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
    # Prefer the extract with the richest female-league coverage (avoids stale copies).
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
    primary = get_work_data_dir() / "tmp"
    return _prefer_existing(primary, REPO_DATA_DIR / "tmp")


def analysis_log_path() -> Path:
    primary = get_work_data_dir() / "extract_excel_analysis_log.json"
    return _prefer_existing(primary, REPO_DATA_DIR / "extract_excel_analysis_log.json")


def historical_league_results_csv() -> Path:
    return _resolve_work_first(
        "historical_league_results.csv",
        repo_fallback=REPO_DATA_DIR / "historical_league_results.csv",
        label="historical league",
    )


def unique_team_names_after_merge_csv() -> Path:
    primary = get_work_data_dir() / "unique_team_names_after_merge.csv"
    return _prefer_existing(primary, REPO_DATA_DIR / "unique_team_names_after_merge.csv")


def merge_duplicates_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or (get_data_dir() / "league_results_merged.csv")
    primary = get_work_data_dir() / f"{base.stem}_duplicates.csv"
    fallback = base.parent / f"{base.stem}_duplicates.csv"
    return _prefer_existing(primary, fallback)


def merge_duplicates_non_exact_report_csv(merged_csv: Path | None = None) -> Path:
    base = merged_csv or league_results_merged_csv()
    primary = get_work_data_dir() / f"{base.stem}_duplicates_non_exact.csv"
    fallback = base.parent / f"{base.stem}_duplicates_non_exact.csv"
    return _prefer_existing(primary, fallback)


def pipeline_gf_league_csv() -> Path:
    """GF pipeline legacy league export (current-season GF ingest)."""
    return REPO_ROOT / "database" / "pipeline" / "bowling_bayern" / "legacy_out" / "latest.csv"


def gf_tournament_export_dir() -> Path:
    return REPO_ROOT / "database" / "input" / "gf_tables_export"


def gf_tournaments_combined_postprocessed_csv() -> Path:
    return gf_tournament_export_dir() / "gf_tournaments_2026__combined_postprocessed.csv"


def manual_tournament_postprocessed_csv() -> Path:
    return work_or_published_file("tournament_manual_postprocessed.csv")


def league_results_merged_csv() -> Path:
    return get_data_dir() / "league_results_merged.csv"


def tournaments_postprocessed_csv() -> Path:
    """Published tournament rows (GF regional export + manual club imports)."""
    return get_data_dir() / "tournaments_postprocessed.csv"


def player_stats_merged_hybrid_csv() -> Path:
    return get_data_dir() / "player_stats_merged_plus_tournaments.csv"


def players_registry_csv() -> Path:
    """Published player identity registry (logical CSV path; Parquet is primary)."""
    return get_data_dir() / "players_registry.csv"


def publish_runs_dir() -> Path:
    """Per-publish manifest directory under published data (synced to VPS)."""
    return get_data_dir() / "runs"


def publish_latest_manifest() -> Path:
    return publish_runs_dir() / "latest.json"
