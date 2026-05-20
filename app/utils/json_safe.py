"""Recursively replace NaN/NA and unsupported values for Flask ``jsonify`` / JSON."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(obj, "item"):
        try:
            return json_safe(obj.item())
        except (ValueError, AttributeError):
            return None
    return obj


def _is_nullish(x: Any) -> bool:
    try:
        if x is None:
            return True
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return True
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def to_json_float(value: Any, *, default: float | None = None) -> float | None:
    """Finite float for JSON payloads; NaN/NA/invalid -> default."""
    if _is_nullish(value):
        return default
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError, OverflowError):
        return default


def to_json_int(value: Any, *, default: int | None = None) -> int | None:
    """Finite int for JSON payloads; NaN/NA/invalid -> default."""
    if _is_nullish(value):
        return default
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return int(round(v))
    except (TypeError, ValueError, OverflowError):
        return default
