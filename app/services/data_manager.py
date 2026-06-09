import pandas as pd
from data_access.pd_dataframes import fetch_column
from flask import session
import os
import json
from typing import Optional
from pathlib import Path
from app.config.database_config import database_config, DATABASE_DATA_DIR

class DataManager:
    _server_instances = []
    _session_key = 'selected_database'
    # Process-local cache: source_id -> {"file_path": str, "mtime": float, "df": DataFrame}
    _dataframe_cache = {}

    def __init__(self, source=None):
        # Always load data from session, don't rely on singleton
        self._load_data(source)

    def _load_data(self, source=None):
        # Prioritize explicit source parameter over session
        if source and database_config.validate_source(source):
            self._current_source = source
        else:
            # Try to get from session
            session_source = self._get_session_source()
            if session_source and database_config.validate_source(session_source):
                self._current_source = session_source
            else:
                # Use default from config
                self._current_source = database_config.get_default_source()
        
        # Save to session for consistency
        self._save_session_source(self._current_source)
        
        try:
            config = database_config.get_source_config(self._current_source)
            self._df = self._load_df_for_config(config, self._current_source)

        except Exception as e:
            print(f"Error loading data from {self._current_source}: {e}")
            # Fallback to default if current source fails
            default_source = database_config.get_default_source()
            if self._current_source != default_source:
                self._current_source = default_source
                self._save_session_source(self._current_source)
                config = database_config.get_source_config(self._current_source)
                self._df = self._load_df_for_config(config, self._current_source)
                print(f"Fallback to default data source: {self._current_source}")
            else:
                return False

    def reload_data(self, source=None):
        """Reload data with better error handling and state management"""
        if source and not database_config.validate_source(source):
            raise ValueError(f"Invalid data source: {source}. Available sources: {database_config.get_available_sources()}")
        
        # Store previous source for rollback if needed
        previous_source = self._current_source
        
        try:
            # Force reload even if singleton exists
            if source:
                self._current_source = source
            
    
            
            # Save to session before loading data
            self._save_session_source(self._current_source)
            
            # Load the new data
            config = database_config.get_source_config(self._current_source)
            self._df = self._load_df_for_config(config, self._current_source)
            
            # Data source switched successfully
            
            # Refresh all server instances
    
            self._refresh_server_instances()
            
            return True
            
        except Exception as e:
            print(f"❌ Error switching to {self._current_source}: {e}")
            # Rollback to previous source
            self._current_source = previous_source
            self._save_session_source(self._current_source)
            try:
                config = database_config.get_source_config(self._current_source)
                self._df = self._load_df_for_config(config, self._current_source)
                print(f"✅ Rolled back to: {self._current_source}")
            except Exception as rollback_error:
                print(f"❌ Critical error: Could not rollback to {self._current_source}: {rollback_error}")
                # Last resort: try default source
                self._current_source = database_config.get_default_source()
                self._save_session_source(self._current_source)
                config = database_config.get_source_config(self._current_source)
                self._df = self._load_df_for_config(config, self._current_source)
            
            return False

    def _get_session_source(self) -> Optional[str]:
        """Get the selected database source from Flask session"""
        try:
            from flask import has_request_context
            if has_request_context():
                source = session.get(self._session_key)
                return source
            else:
                return None
        except Exception as e:
            print(f"Warning: Could not access session: {e}")
            return None

    def _save_session_source(self, source: str):
        """Save the selected database source to Flask session"""
        try:
            from flask import has_request_context
            if has_request_context():
                session[self._session_key] = source
                session.modified = True
            else:
                pass
        except Exception as e:
            print(f"Warning: Could not save to session: {e}")

    def force_reload_from_session(self):
        """Force reload data from session - useful for production with multiple workers"""
        # Reload from session, but leverage file-mtime cache to avoid heavy
        # CSV re-parsing on every request when data is unchanged.
        self._load_data()
    
    def reset_to_default(self):
        """Reset to the current default source, clearing session"""
        self._clear_session_source()
        self._current_source = database_config.get_default_source()
        self._save_session_source(self._current_source)
        self._load_data()
        return True
    
    def _clear_session_source(self):
        """Clear the database source from Flask session"""
        try:
            from flask import has_request_context
            if has_request_context():
                session.pop(self._session_key, None)
                session.modified = True
            else:
                pass
        except Exception as e:
            print(f"Warning: Could not clear session: {e}")

    def get_available_sources(self) -> list:
        """Get list of available data sources"""
        return database_config.get_available_sources()

    def validate_source(self, source: str) -> bool:
        """Validate if a data source exists and is accessible"""
        return database_config.validate_source(source)

    def get_source_display_name(self, source: str) -> str:
        """Get display name for a data source"""
        return database_config.get_source_display_name(source)

    def get_default_source(self) -> str:
        """Get the default data source"""
        return database_config.get_default_source()
    
    def get_sources_info(self) -> dict:
        """Get detailed information about all available sources"""
        return database_config.get_sources_info()

    def register_server_instance(self, server_instance):
        """Register a server instance to be refreshed when data source changes"""
        if server_instance not in self._server_instances:
            self._server_instances.append(server_instance)
    

    def _refresh_server_instances(self):
        """Refresh all registered server instances"""
        for server in self._server_instances:
            if hasattr(server, 'refresh_data_adapter'):
                try:
    
                    server.refresh_data_adapter()
                except Exception as e:
                    print(f"Warning: Error refreshing server instance: {e}")

    @property
    def df(self):
        return self._df
    
    @property
    def current_source(self):
        return self._current_source
    
    def force_source(self, source: str) -> bool:
        """Force a specific data source and reload data"""
        if not database_config.validate_source(source):
            print(f"❌ Invalid source: {source}")
            return False
        
        print(f"🔄 Forcing data source to: {source}")
        self._current_source = source
        self._save_session_source(source)
        
        # Reload data with the new source
        try:
            config = database_config.get_source_config(source)
            self._df = self._load_df_for_config(config, source)
            print(f"✅ Successfully switched to: {source}")
            return True
        except Exception as e:
            print(f"❌ Error forcing source {source}: {e}")
            return False 

    @staticmethod
    def _load_df_for_config(config, source_id: str) -> pd.DataFrame:
        from data_access.shared_pandas_store import load_dataframe_for_paths, resolve_database_paths

        if config and getattr(config, "merge_file_paths", None):
            primary, extras = resolve_database_paths(source_id)
            return load_dataframe_for_paths(primary, extras)

        file_path = (
            config.file_path
            if config
            else str(DATABASE_DATA_DIR / database_config.get_filename_for_source(source_id))
        )
        from data_access.shared_pandas_store import get_dataframe

        return get_dataframe(Path(file_path))