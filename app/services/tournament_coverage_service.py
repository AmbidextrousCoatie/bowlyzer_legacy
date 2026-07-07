"""Tournament coverage matrix for Diagnose UI."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from data_access.tournament_coverage import build_tournament_coverage_matrix


def get_tournament_coverage() -> Dict[str, Any]:
    matrix = build_tournament_coverage_matrix()
    matrix["generated_at_utc"] = dt.datetime.now(tz=dt.timezone.utc).isoformat()
    return matrix
