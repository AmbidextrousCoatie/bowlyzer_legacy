# app/models/table_data.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union

from app.utils.json_safe import json_safe

@dataclass
class Column:
    """Individual column definition."""
    title: str
    field: str
    title_key: Optional[str] = None  # i18n key; React resolves via /league/get_translations
    sortable: bool = True
    filterable: bool = True
    width: Optional[str] = None
    align: Optional[str] = "center"  # "left", "center", "right"
    format: Optional[str] = None  # Format string for numbers, dates, etc.
    decimal_places: Optional[int] = None  # Number of decimal places to display (0, 1, 2, etc.)
    style: Optional[Dict[str, str]] = None  # Custom CSS styles
    tooltip: Optional[str] = None  # Tooltip text for column header
    # When set on one or more columns in a group, renderers freeze those columns only
    # (instead of freezing the entire ColumnGroup).
    frozen: Optional[str] = None  # "left", "right"

@dataclass
class ColumnGroup:
    """Column group with a common header."""
    title: str
    columns: List[Column]
    title_key: Optional[str] = None
    frozen: Optional[str] = None  # 'left', 'right', or None
    style: Optional[Dict[str, str]] = None  # Custom CSS styles for the group
    header_style: Optional[Dict[str, str]] = None  # Custom CSS for header
    width: Optional[str] = None  # Width for the entire group
    highlighted: bool = False  # Whether this group should be visually highlighted
    highlight_header_only: bool = False  # Highlight group/column headers only, not body cells

@dataclass
class TableData:
    """Complete table data structure."""
    columns: Union[List[ColumnGroup], List[Column]]  # Accept either ColumnGroups or bare Columns
    data: List[List[Any]]
    title: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = field(default_factory=dict)  # Table-wide configuration
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)  # Additional metadata for i18n and UI
    # Row-level metadata for styling/semantics.
    # Supported keys include:
    # - styling: inline style overrides (fontWeight, borderBottom, etc.)
    # - separator_before: semantic row break marker consumed by both legacy and React tables
    # - rowType/kind: optional semantic role (e.g. "summary", "team", "total")
    row_metadata: Optional[List[Dict[str, Any]]] = field(default_factory=list)
    cell_metadata: Optional[Dict[str, Dict[str, Any]]] = field(default_factory=dict)  # Cell-level metadata for styling (format: "row:col")
    default_sort: Optional[Dict[str, str]] = None  # Default sort: {"field": "average", "dir": "desc"}
    
    def __post_init__(self):
        """Normalize columns: if bare Columns are provided, wrap them in a ColumnGroup with empty title."""
        if self.columns and len(self.columns) > 0 and isinstance(self.columns[0], Column):
            # Convert List[Column] to List[ColumnGroup] by wrapping in a single group
            self.columns = [ColumnGroup(title="", columns=list(self.columns))]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for JSON serialization"""
        raw: Dict[str, Any] = {
            "columns": [
                {
                    "title": group.title,
                    "columns": [
                        {
                            "title": col.title,
                            "field": col.field,
                            **({"title_key": col.title_key} if col.title_key else {}),
                            **({"sortable": col.sortable} if col.sortable is not None else {}),
                            **({"filterable": col.filterable} if col.filterable is not None else {}),
                            **({"width": col.width} if col.width else {}),
                            **({"align": col.align} if col.align else {}),
                            **({"format": col.format} if col.format else {}),
                            **({"decimal_places": col.decimal_places} if col.decimal_places is not None else {}),
                            **({"style": col.style} if col.style else {}),
                            **({"tooltip": col.tooltip} if col.tooltip else {}),
                            **({"frozen": col.frozen} if col.frozen else {}),
                        }
                        for col in group.columns
                    ],
                    **({"title_key": group.title_key} if group.title_key else {}),
                    **({"frozen": group.frozen} if group.frozen else {}),
                    **({"style": group.style} if group.style else {}),
                    **({"headerStyle": group.header_style} if group.header_style else {}),
                    **({"width": group.width} if group.width else {}),
                    **({"highlighted": group.highlighted} if group.highlighted else {}),
                    **({"highlight_header_only": group.highlight_header_only} if group.highlight_header_only else {}),
                }
                for group in self.columns
            ],
            "data": self.data,
            **({"title": self.title} if self.title else {}),
            **({"description": self.description} if self.description else {}),
            **({"config": self.config} if self.config else {}),
            **({"metadata": self.metadata} if self.metadata else {}),
            **({"row_metadata": self.row_metadata} if self.row_metadata else {}),
            **({"cell_metadata": self.cell_metadata} if self.cell_metadata else {}),
            **({"default_sort": self.default_sort} if self.default_sort else {}),
        }
        return json_safe(raw)

#@dataclass
#class TableDataLeague(TableData):
#    """Table data for a league."""
#    league: str

@dataclass
class PlotData:
    """Data structure for chart/plot visualization."""
    title: str
    series: List[Dict[str, Any]]
    x_axis: Optional[List[Any]] = None
    y_axis_label: Optional[str] = None
    x_axis_label: Optional[str] = None
    plot_type: str = "line"  # line, bar, scatter, pie, etc.
    options: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for JSON serialization"""
        raw = {
            "title": self.title,
            "series": self.series,
            "xAxis": {"categories": self.x_axis} if self.x_axis else {},
            "yAxis": {"title": {"text": self.y_axis_label}} if self.y_axis_label else {},
            "plotType": self.plot_type,
            "options": self.options,
        }
        return json_safe(raw)

@dataclass
class TileData:
    """Data structure for dashboard tiles/cards."""
    title: str
    value: Any  # The primary value to display
    subtitle: Optional[str] = None
    trend: Optional[Dict[str, Any]] = None  # Trend information (value, direction, etc.)
    icon: Optional[str] = None
    color: Optional[str] = None  # Primary color
    size: str = "small"  # small, medium, large, wide
    type: str = "stat"  # stat, trend, progress, chart, info
    chart_data: Optional[List[Union[int, float]]] = None  # For mini charts
    link: Optional[str] = None  # URL to navigate to on click
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for JSON serialization"""
        result = {
            "title": self.title,
            "value": self.value,
            "size": self.size,
            "type": self.type
        }
        
        if self.subtitle:
            result["subtitle"] = self.subtitle
        
        if self.trend:
            result["trend"] = self.trend
            
        if self.icon:
            result["icon"] = self.icon
            
        if self.color:
            result["color"] = self.color
            
        if self.chart_data:
            result["chartData"] = self.chart_data
            
        if self.link:
            result["link"] = self.link

        return json_safe(result)