"""
Database Configuration
Manages available data sources and their settings
"""

import csv
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from database.paths import (
    get_data_dir,
    historical_league_results_csv,
    tournaments_postprocessed_csv,
)

# Get the league_analyzer_v1 directory (parent of app directory)
APP_DIR = Path(__file__).parent.parent
LEGACY_V1_DIR = APP_DIR.parent if APP_DIR.name == 'app' else APP_DIR

DATABASE_DATA_DIR = get_data_dir()
PIPELINE_GF_LEGACY_CSV = (
    LEGACY_V1_DIR / "database" / "pipeline" / "bowling_bayern" / "legacy_out" / "latest.csv"
)
GF_TOURNAMENT_EXPORT_DIR = LEGACY_V1_DIR / "database" / "input" / "gf_tables_export"
GF_SBM_CANONICAL_CSV = GF_TOURNAMENT_EXPORT_DIR / "gf_table_124__sbm_suedbayerische_meisterschaft_2026__canonical_clean.csv"
GF_NBM_CANONICAL_CSV = GF_TOURNAMENT_EXPORT_DIR / "gf_table_125__nbm_nordbayerische_meisterschaft_2026__canonical_clean.csv"
GF_REGIONAL_COMBINED_POSTPROCESSED_CSV = GF_TOURNAMENT_EXPORT_DIR / "gf_tournaments_2026__combined_postprocessed.csv"
# Club / Excel imports that are not produced by the GF tables export pipeline (keeps GF CSV overwrite-safe).
MANUAL_TOURNAMENT_POSTPROCESSED_CSV = DATABASE_DATA_DIR / "tournament_manual_postprocessed.csv"
GF_PLAYER_COMBINED_CSV = GF_TOURNAMENT_EXPORT_DIR / "gf_player_stats__league_plus_tournaments.csv"
HISTORICAL_LEAGUE_RESULTS_CSV = historical_league_results_csv()
MERGED_LEAGUE_RESULTS_CSV = DATABASE_DATA_DIR / "league_results_merged.csv"
TOURNAMENTS_POSTPROCESSED_CSV = tournaments_postprocessed_csv()
MERGED_PLAYER_HYBRID_CSV = DATABASE_DATA_DIR / "player_stats_merged_plus_tournaments.csv"


def _ensure_pipeline_gf_legacy_csv_stub() -> None:
    """
    If the GF pipeline has never been run, latest.csv is missing and validation would
    drop the source from the UI. Create legacy_out/ and a header-only CSV once so the
    selector always lists Pipeline GF; the pipeline overwrites this file on ingest.
    """
    path = PIPELINE_GF_LEGACY_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    from database.conversion.bowlingbayern_legacy_core import OUTPUT_HEADERS

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS, delimiter=";")
        writer.writeheader()


def _ensure_tournament_postprocessed_csv_stub(path: Path) -> None:
    """
    Keep configured tournament sources visible in the UI even before the
    GF tournament export has been run; real export overwrites this file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    headers = [
        "Season",
        "Date",
        "Location",
        "Event Type",
        "Event Name",
        "Round Number",
        "Round Name",
        "Player",
        "Player ID",
        "Club",
        "Game Number",
        "Score",
        "Handicap",
        "Cumulative Score",
        "Stage Rank",
        "Cut Line",
        "Cut Basis",
        "Overall Cumulative Score",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        writer.writeheader()


def _ensure_historical_league_csv_stub(path: Path) -> None:
    """
    Keep historical league source visible in UI before first ingest run by
    creating a header-only legacy CSV if missing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    from database.conversion.bowlingbayern_legacy_core import OUTPUT_HEADERS

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS, delimiter=";")
        writer.writeheader()


def _ensure_merged_league_csv_stub(path: Path) -> None:
    """
    Keep merged league source selectable before first merge run by creating
    a header-only legacy CSV.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return
    from database.conversion.bowlingbayern_legacy_core import OUTPUT_HEADERS

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS, delimiter=";")
        writer.writeheader()


def _should_build_player_merged_hybrid_csv() -> bool:
    """
    Deprecated: Spieler loads league + tournament Parquets at runtime via merge_file_paths.

    Set BOWLYZER_BUILD_PLAYER_HYBRID=1 to regenerate the legacy single-file artifact.
    """
    if (os.environ.get("BOWLYZER_BUILD_PLAYER_HYBRID") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    if (os.environ.get("BOWLYZER_SKIP_HYBRID_BUILD") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return False
    return True


def _build_player_merged_hybrid_csv() -> None:
    """
    Build a player hybrid source from merged league rows + tournament postprocessed rows.
    This keeps player routes aligned with the selected merged league scope while still
    exposing tournament history in lifetime views.
    """
    league_rows: List[Dict[str, str]] = []
    if MERGED_LEAGUE_RESULTS_CSV.is_file():
        with MERGED_LEAGUE_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            league_rows = [{str(k): str(v or "") for k, v in row.items()} for row in reader]

    tournament_rows: List[Dict[str, str]] = []
    if GF_REGIONAL_COMBINED_POSTPROCESSED_CSV.is_file():
        with GF_REGIONAL_COMBINED_POSTPROCESSED_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            tournament_rows.extend([{str(k): str(v or "") for k, v in row.items()} for row in reader])
    if MANUAL_TOURNAMENT_POSTPROCESSED_CSV.is_file():
        with MANUAL_TOURNAMENT_POSTPROCESSED_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            tournament_rows.extend([{str(k): str(v or "") for k, v in row.items()} for row in reader])

    headers = sorted({k for r in (league_rows + tournament_rows) for k in r.keys()})
    if not headers:
        from database.conversion.bowlingbayern_legacy_core import OUTPUT_HEADERS
        headers = list(OUTPUT_HEADERS)

    out_rows: List[Dict[str, str]] = []
    for row in league_rows:
        merged = {h: str(row.get(h, "")) for h in headers}
        if not str(merged.get("Event Type", "")).strip():
            merged["Event Type"] = "league"
        if not str(merged.get("Event Name", "")).strip():
            merged["Event Name"] = str(merged.get("Event", merged.get("League", ""))).strip()
        out_rows.append(merged)

    for row in tournament_rows:
        merged = {h: str(row.get(h, "")) for h in headers}
        merged["Input Data"] = "True"
        merged["Computed Data"] = "False"
        out_rows.append(merged)

    MERGED_PLAYER_HYBRID_CSV.parent.mkdir(parents=True, exist_ok=True)
    with MERGED_PLAYER_HYBRID_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)


@dataclass
class DataSourceConfig:
    """Configuration for a data source"""
    filename: str
    display_name: str
    description: str
    is_default: bool = False
    is_enabled: bool = True
    file_path: Optional[str] = None
    # Optional extra CSVs (same schema) concatenated after the primary file_path when loading pandas.
    merge_file_paths: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.file_path is None:
            # Use absolute path relative to league_analyzer_v1 directory
            self.file_path = str(DATABASE_DATA_DIR / self.filename)

class DatabaseConfig:
    """Centralized database configuration management"""
    
    def __init__(self):
        self._sources = {
            'db_real': DataSourceConfig(
                filename='bowling_ergebnisse_real.csv',
                display_name='Real Data (2024/25)',
                description='Bowling league export CSV (2024/25 season snapshot)',
                is_default=False,
                is_enabled=True
            ),
            'db_real_pipeline_gf': DataSourceConfig(
                filename='latest.csv',
                display_name='Real Data (Pipeline GF)',
                description='Legacy CSV produced by the Gravity Forms pipeline (merged GF results)',
                is_default=False,
                is_enabled=True,
                file_path=str(PIPELINE_GF_LEGACY_CSV),
            ),
            'db_real_historical_league': DataSourceConfig(
                filename='historical_league_results.csv',
                display_name='Real Data (Historical League)',
                description='Continuous historical league results aggregated from legacy Excel imports',
                is_default=False,
                is_enabled=True,
                file_path=str(HISTORICAL_LEAGUE_RESULTS_CSV),
            ),
            'db_real_merged': DataSourceConfig(
                filename='league_results_merged.csv',
                display_name='Real Data (Merged League)',
                description='Merged league source (historical + pipeline GF), with duplicate conflicts resolved by source priority',
                is_default=True,
                is_enabled=True,
                file_path=str(MERGED_LEAGUE_RESULTS_CSV),
            ),
            'db_tournament_sbm_2026_gf': DataSourceConfig(
                filename='gf_table_124__sbm_suedbayerische_meisterschaft_2026__canonical_clean.csv',
                display_name='Tournament Data (SBM 2026, GF)',
                description='Südbayerische Meisterschaft 2026 transformed from GF export into canonical tournament format',
                is_default=False,
                is_enabled=False,
                file_path=str(GF_SBM_CANONICAL_CSV),
            ),
            'db_tournament_nbm_2026_gf': DataSourceConfig(
                filename='gf_table_125__nbm_nordbayerische_meisterschaft_2026__canonical_clean.csv',
                display_name='Tournament Data (NBM 2026, GF)',
                description='Nordbayerische Meisterschaft 2026 transformed from GF export into canonical tournament format',
                is_default=False,
                is_enabled=False,
                file_path=str(GF_NBM_CANONICAL_CSV),
            ),
            'db_tournament_regions_2026_gf': DataSourceConfig(
                filename='tournaments_postprocessed.csv',
                display_name='Tournament Data (published)',
                description='Published tournament merge (GF regional + manual club imports). Built by scripts/build_published_dataset.py; deploy with -SyncDatabase.',
                is_default=False,
                is_enabled=True,
                file_path=str(TOURNAMENTS_POSTPROCESSED_CSV),
            ),
            'db_player_combined_gf': DataSourceConfig(
                filename='gf_player_stats__league_plus_tournaments.csv',
                display_name='Player Data (League+Tournament GF)',
                description='Combined player source with league pipeline rows plus tournament rows (SBM+NBM)',
                is_default=False,
                is_enabled=True,
                file_path=str(GF_PLAYER_COMBINED_CSV),
            ),
            'db_player_merged_hybrid': DataSourceConfig(
                filename='league_results_merged.csv',
                display_name='Player Data (League+Tournament)',
                description=(
                    'Merged league Parquet plus tournaments_postprocessed at load time '
                    '(replaces deprecated player_stats_merged_plus_tournaments artifact)'
                ),
                is_default=False,
                is_enabled=True,
                file_path=str(MERGED_LEAGUE_RESULTS_CSV),
                merge_file_paths=(str(TOURNAMENTS_POSTPROCESSED_CSV),),
            ),
        }

        for label, fn in (
            ("pipeline GF legacy stub", _ensure_pipeline_gf_legacy_csv_stub),
            ("tournament SBM stub", lambda: _ensure_tournament_postprocessed_csv_stub(GF_SBM_CANONICAL_CSV)),
            ("tournament NBM stub", lambda: _ensure_tournament_postprocessed_csv_stub(GF_NBM_CANONICAL_CSV)),
            (
                "tournament published stub",
                lambda: _ensure_tournament_postprocessed_csv_stub(TOURNAMENTS_POSTPROCESSED_CSV),
            ),
            (
                "tournament GF combined stub",
                lambda: _ensure_tournament_postprocessed_csv_stub(GF_REGIONAL_COMBINED_POSTPROCESSED_CSV),
            ),
            (
                "tournament manual stub",
                lambda: _ensure_tournament_postprocessed_csv_stub(MANUAL_TOURNAMENT_POSTPROCESSED_CSV),
            ),
            ("player GF combined stub", lambda: _ensure_tournament_postprocessed_csv_stub(GF_PLAYER_COMBINED_CSV)),
            ("historical league stub", lambda: _ensure_historical_league_csv_stub(HISTORICAL_LEAGUE_RESULTS_CSV)),
            ("merged league stub", lambda: _ensure_merged_league_csv_stub(MERGED_LEAGUE_RESULTS_CSV)),
        ):
            try:
                fn()
            except (ImportError, OSError) as exc:
                print(f"Warning: could not create {label}: {exc}")

        # Spieler uses runtime merge (league + tournament Parquets). Legacy hybrid CSV is
        # opt-in only via BOWLYZER_BUILD_PLAYER_HYBRID=1 and build_published_dataset --job player_hybrid.

        # Validate sources on initialization
        self._validate_sources()
    
    def _validate_sources(self):
        """Validate that all enabled sources exist and are accessible"""
        try:
            from data_access.parquet_sidecar import data_file_exists as _data_exists
        except ImportError:
            _data_exists = None

        for source_id, config in self._sources.items():
            if config.is_enabled:
                path = Path(config.file_path)
                exists = _data_exists(path) if _data_exists else path.is_file()
                if not exists:
                    print(f"Warning: Data source file not found: {config.file_path}")
                    config.is_enabled = False
    
    def get_available_sources(self) -> List[str]:
        """Get list of available (enabled) data source filenames"""
        return [source_id for source_id, config in self._sources.items() 
                if config.is_enabled]
    
    def get_source_config(self, source_id: str) -> Optional[DataSourceConfig]:
        """Get configuration for a specific data source"""
        return self._sources.get(source_id)
    
    def get_default_source(self) -> str:
        """Get the default data source ID"""
        for source_id, config in self._sources.items():
            if config.is_default and config.is_enabled:
                return source_id
        # Fallback to first available source
        available = self.get_available_sources()
        return available[0] if available else 'db_sim'
    
    def get_filename_for_source(self, source_id: str) -> str:
        """Get the actual filename for an abstract source ID"""
        config = self.get_source_config(source_id)
        return config.filename if config else source_id
    
    def get_current_source(self) -> str:
        """Get the currently active data source"""
        # This should be determined by the request context or session
        # For now, return the default source
        return self.get_default_source()
    
    def set_current_source(self, source_id: str) -> bool:
        """Set the current active data source"""
        if not self.validate_source(source_id):
            return False
        
        # Update the default source to the selected one
        for config in self._sources.values():
            config.is_default = False
        
        config = self.get_source_config(source_id)
        if config:
            config.is_default = True
            return True
        return False
    
    def validate_source(self, source_id: str) -> bool:
        """Validate if a data source exists and is accessible"""
        config = self.get_source_config(source_id)
        if not config or not config.is_enabled:
            return False
        
        path = Path(config.file_path)
        try:
            from data_access.parquet_sidecar import data_file_exists

            return data_file_exists(path)
        except ImportError:
            return path.is_file()
    
    def get_source_display_name(self, source_id: str) -> str:
        """Get display name for a data source"""
        config = self.get_source_config(source_id)
        return config.display_name if config else 'Unknown Data Source'
    
    def get_source_description(self, source_id: str) -> str:
        """Get description for a data source"""
        config = self.get_source_config(source_id)
        return config.description if config else ''
    
    def get_sources_info(self) -> Dict:
        """Get information about all available sources"""
        selector_visible_sources = {"db_real_merged"}
        return {
            source_id: {
                'filename': config.filename,
                'display_name': config.display_name,
                'description': config.description,
                'is_default': config.is_default,
                'is_enabled': config.is_enabled,
                'file_path': config.file_path
            }
            for source_id, config in self._sources.items()
            if config.is_enabled and source_id in selector_visible_sources
        }

# Global instance
database_config = DatabaseConfig() 