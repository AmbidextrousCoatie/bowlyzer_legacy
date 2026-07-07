"""Publish tournaments_postprocessed.parquet for the running app."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from database.paths import gf_tournaments_combined_postprocessed_csv, tournaments_postprocessed_csv
from database.tournament_import.io import MANUAL_TOURNAMENT_CSV


def tournament_publish_inputs() -> List[Path]:
    return [
        p
        for p in (
            gf_tournaments_combined_postprocessed_csv(),
            MANUAL_TOURNAMENT_CSV,
        )
        if p.is_file()
    ]


def publish_tournaments_parquet(*, write_csv: bool = False) -> Dict[str, Any]:
    """
    Merge GF regional + manual tournament CSVs into tournaments_postprocessed.parquet.

    The Flask app reads ``db_tournament_regions_2026_gf`` -> tournaments_postprocessed.parquet,
  not tournament_manual_postprocessed.csv directly.
    """
    from scripts.publish_tournament_parquet import merge_tournament_sources

    inputs = tournament_publish_inputs()
    if not inputs:
        raise FileNotFoundError(
            "No tournament publish inputs found. Expected at least one of: "
            f"{gf_tournaments_combined_postprocessed_csv()}, {MANUAL_TOURNAMENT_CSV}"
        )
    return merge_tournament_sources(
        inputs,
        tournaments_postprocessed_csv(),
        write_csv=write_csv,
    )
