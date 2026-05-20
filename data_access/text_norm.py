"""Unicode normalization for comparing league/team/player labels from mixed sources (CSV, URLs)."""

from __future__ import annotations

import math
import unicodedata


def normalize_unicode_label(value: object) -> str:
    """Strip and normalize to NFC so NFD vs NFC spellings (e.g. ``ö``) compare equal."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    return unicodedata.normalize("NFC", s)


def safe_rank_int(value: object) -> int:
    """``pandas`` ranks may be NaN when points are missing; ``int(nan)`` raises."""
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if math.isnan(v) or math.isinf(v):
        return 0
    try:
        return int(v)
    except (ValueError, OverflowError):
        return 0
