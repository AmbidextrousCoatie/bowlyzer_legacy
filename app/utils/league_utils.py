"""
League Service Utility Functions
Shared utility functions extracted from league_service.py for better organization and reusability.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Union, List, Dict, Any

from app.utils.color_constants import get_heat_map_color


def _load_csv_id_long_pairs(csv_path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not csv_path.is_file():
        return out
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = (row.get("id") or "").strip()
            long_name = (row.get("long_name") or "").strip()
            if lid and long_name:
                # Prefer the more specific label when one id has multiple long_names
                # (e.g. LL N1: "Landesliga Nord 1" over "Landesliga Nord").
                existing = out.get(lid)
                if not existing or len(long_name) > len(existing):
                    out[lid] = long_name
    return out


@lru_cache(maxsize=1)
def get_league_long_name_map() -> Dict[str, str]:
    """
    id -> long_name for UI labels.

    Canonical source is ``database/relational_csv/league_mapping.csv``
    (same file as ingestion / Excel tooling); keep ids in sync there.
    """
    path = Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "league_mapping.csv"
    return _load_csv_id_long_pairs(path)


@lru_cache(maxsize=1)
def get_league_division_map() -> Dict[str, str]:
    """
    id -> division (``state``, ``south``, ``north``) from ``league_mapping.csv``.
    """
    path = Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "league_mapping.csv"
    out: Dict[str, str] = {}
    if not path.is_file():
        return out

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = (row.get("id") or "").strip()
            division = (row.get("division") or "").strip()
            if lid and division:
                out[lid] = division
    return out


@lru_cache(maxsize=1)
def get_league_gender_scope_map() -> Dict[str, str]:
    """
    id -> gender scope (``male``, ``female``, ``mixed``) from ``league_mapping.csv``.
    """
    path = Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "league_mapping.csv"
    out: Dict[str, str] = {}
    if not path.is_file():
        return out

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lid = (row.get("id") or "").strip()
            scope = (row.get("gender_scope") or "").strip().lower()
            if lid and scope:
                out[lid] = scope
    return out


def resolve_league_long_name(short_id: str) -> str:
    """Return display long name for a league short id, or the id if unmapped."""
    if short_id is None or short_id == "":
        return ""
    key = str(short_id).strip()
    return get_league_long_name_map().get(key, key)


def format_float_one_decimal(value: Union[int, float]) -> str:
    """
    Format a number to always show one decimal place, even if it's a whole number.
    Example: 100 -> "100.0", 100.5 -> "100.5"
    
    Args:
        value: The number to format
        
    Returns:
        String representation with exactly one decimal place
    """
    return f"{float(value):.1f}"


def numeric_sort_key(value: Any, *, missing: float = float("-inf")) -> float:
    """Coerce a table cell to float for ranking; non-numeric values sort last when reverse=True."""
    try:
        if value is None or value == "":
            return missing
        number = float(value)
        if number != number:  # NaN
            return missing
        return number
    except (TypeError, ValueError):
        return missing


def get_league_level(league: str) -> int:
    """
    Get the level of a league from ``league_mapping.csv``.
    
    Args:
        league: The league name
        
    Returns:
        League level (integer). Unmapped leagues default to 99.
    """
    if league is None:
        return 99
    key = str(league).strip()
    if not key:
        return 99

    path = Path(__file__).resolve().parent.parent.parent / "database" / "relational_csv" / "league_mapping.csv"
    if not path.is_file():
        return 99

    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lid = (row.get("id") or "").strip()
                if lid == key:
                    try:
                        return int(str(row.get("level") or "").strip())
                    except (TypeError, ValueError):
                        return 99
    except Exception:
        return 99

    return 99


def convert_to_simple_types(data):
    """
    Convert numpy types to simple Python types for JSON serialization.
    
    Args:
        data: Data structure that may contain numpy types
        
    Returns:
        Data structure with numpy types converted to Python native types
    """
    if isinstance(data, dict):
        return {key: convert_to_simple_types(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_simple_types(item) for item in data]
    elif hasattr(data, 'item'):  # numpy scalar
        return data.item()
    elif isinstance(data, (int, float, str, bool)) or data is None:
        return data
    else:
        return str(data)


def apply_heat_map_to_columns(table_data: List[List], cell_metadata: Dict[str, Dict],
                              column_indices: List[int], min_val: float = None, max_val: float = None) -> Dict[str, Dict]:
    """
    Apply heat map coloring to specified column indices.
    
    Args:
        table_data: List of rows, where each row is a list of values
        cell_metadata: Dictionary mapping "row:col" to cell metadata
        column_indices: List of column indices (0-based) to apply coloring to
        min_val: Optional minimum value for color scale. If None, calculated from data
        max_val: Optional maximum value for color scale. If None, calculated from data
        
    Returns:
        Updated cell_metadata dictionary
    """
    if not table_data or not column_indices:
        return cell_metadata
    
    # Extract all values from specified columns
    all_values = []
    for row in table_data:
        for col_idx in column_indices:
            if col_idx < len(row):
                value = row[col_idx]
                # Only include numeric values (skip empty strings, None, etc.)
                if isinstance(value, (int, float)) and value != "":
                    all_values.append(value)
    
    if not all_values:
        return cell_metadata
    
    # Calculate min/max if not provided
    calculated_min = min(all_values) if min_val is None else min_val
    calculated_max = max(all_values) if max_val is None else max_val
    
    # Apply coloring to each cell in specified columns
    for row_idx, row in enumerate(table_data):
        for col_idx in column_indices:
            if col_idx < len(row):
                value = row[col_idx]
                if isinstance(value, (int, float)) and value != "":
                    color = get_heat_map_color(value, calculated_min, calculated_max)
                    cell_metadata[f"{row_idx}:{col_idx}"] = {"backgroundColor": color}
    
    return cell_metadata
