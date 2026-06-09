from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING
from data_access.adapters.data_adapter import DataAdapter
from enum import Enum
from database.config import path_to_csv_data
from abc import ABC, abstractmethod
from data_access.models.league_models import TeamSeasonPerformance
import pathlib

if TYPE_CHECKING:
    from app.config.database_config import DataSourceConfig

class DataAdapterSelector(Enum):
    """Enum for selecting data adapter type"""
    PANDAS = "pandas"
    MYSQL = "mysql"
    SQLITE = "sqlite"

class DataAdapterFactory:
    @staticmethod
    def _pandas_from_source_config(config: "DataSourceConfig"):
        """Build a pandas adapter from a data source, optionally merging supplemental CSVs."""
        from data_access.adapters.data_adapter_pandas import DataAdapterPandas
        import pandas as pd

        merge_paths = getattr(config, "merge_file_paths", None) or ()
        if merge_paths and config.file_path:
            from data_access.shared_pandas_store import load_dataframe_for_paths

            primary = pathlib.Path(config.file_path)
            extras = tuple(pathlib.Path(p) for p in merge_paths)
            df = load_dataframe_for_paths(primary, extras)
            return DataAdapterPandas(df=df)

        if config.file_path:
            return DataAdapterPandas(path_to_csv_data=pathlib.Path(config.file_path))
        return None

    @staticmethod
    def create_adapter(adapter_type: DataAdapterSelector, database: str = None) -> DataAdapter:
        if adapter_type == DataAdapterSelector.PANDAS:
            from data_access.adapters.data_adapter_pandas import DataAdapterPandas
            if database:
                from data_access.shared_pandas_store import get_shared_pandas_adapter

                return get_shared_pandas_adapter(database)
            else:
                # Fallback to current DataManager logic
                try:
                    from app.services.data_manager import DataManager
                    from app.config.database_config import database_config, DATABASE_DATA_DIR
                    data_manager = DataManager()
                    current_source = data_manager.current_source

                    # Create path to current data source using database_config
                    config = database_config.get_source_config(current_source)
                    if config:
                        adapter = DataAdapterFactory._pandas_from_source_config(config)
                        if adapter is not None:
                            return adapter
                    filename = database_config.get_filename_for_source(current_source)
                    current_path = pathlib.Path(DATABASE_DATA_DIR) / filename
                    return DataAdapterPandas(path_to_csv_data=current_path)
                except ImportError:
                    # Fallback to config if DataManager not available

                    return DataAdapterPandas(path_to_csv_data=path_to_csv_data)
        elif adapter_type == DataAdapterSelector.MYSQL:
            from data_access.adapters.data_adapter_mysql import MySQLAdapter
            return MySQLAdapter()
        elif adapter_type == DataAdapterSelector.SQLITE:
            from data_access.adapters.data_adapter_sqlite import SQLiteAdapter
            return SQLiteAdapter()
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")

class DataAdapter(ABC):
    """Abstract base class for data adapters"""
    
    @abstractmethod
    def get_filtered_data(self, filters: Optional[Dict[str, Any]] = None, 
                         columns: Optional[List[str]] = None,
                         sort_by: Optional[Union[str, List[str]]] = None,
                         ascending: bool = True,
                         limit: Optional[int] = None):
        """Get filtered data"""
        pass
    
    @abstractmethod
    def get_weeks(self, season: str, league: str) -> List[int]:
        """Get available weeks for a season and league"""
        pass
    
    @abstractmethod
    def get_league_standings(self, season: str, league: str, week: Optional[int] = None) -> List[TeamSeasonPerformance]:
        """Get league standings for a specific season, league, and week"""
        pass 