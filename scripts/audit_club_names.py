#!/usr/bin/env python3
"""
Audit club labels against ``clubs_registry`` (league-derived canonical names).

Reports:
  - ``tournament_club_unknown`` — tournament ``Club`` not resolving to registry
  - ``league_team_club_missing`` — normalized league team club absent from registry

Proposals use prefix stripping and suffix matching (no GF data as registry input).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.clubs_registry import (
    audit_league_team_club_consistency,
    build_alias_to_canonical,
    load_clubs_registry_df,
    propose_club_resolution,
)
from data_access.parquet_sidecar import data_file_exists, resolve_load_path
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label
from database.paths import get_work_data_dir, league_results_merged_csv, tournaments_postprocessed_csv

from data_access.club_name_validation import (
    CLUB_NAME_CONFLICTS_CSV,
    write_club_name_conflicts_report,
)


def _load_frame(path: Path):
    import pandas as pd

    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def _audit_tournament_clubs(
    df,
    *,
    source_file: str,
    alias_lookup,
    canonical_names: Sequence[str],
) -> List[dict]:
    if df is None or df.empty or Columns.club not in df.columns:
        return []
    counts = Counter(
        normalize_unicode_label(value)
        for value in df[Columns.club].fillna("").astype(str)
        if normalize_unicode_label(value)
    )
    rows: List[dict] = []
    for label, row_count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        from data_access.clubs_registry import resolve_club_label

        resolved, rule = resolve_club_label(label, alias_lookup, canonical_names)
        if resolved:
            continue
        proposals = propose_club_resolution(label, alias_lookup, canonical_names)
        proposed_canonical = proposals[0][0] if proposals else ""
        proposed_rule = proposals[0][1] if proposals else ""
        rows.append(
            {
                "issue_type": "tournament_club_unknown",
                "source_file": source_file,
                "club_label": label,
                "row_count": int(row_count),
                "proposed_canonical": proposed_canonical,
                "proposed_rule": proposed_rule,
                "peer_labels": "",
            }
        )
    return rows


def write_report(rows: Sequence[dict], out_path: Path) -> None:
    write_club_name_conflicts_report(rows, out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Rebuild clubs_registry from league merge before auditing",
    )
    parser.add_argument(
        "--tournaments",
        type=Path,
        default=None,
        help="Tournament CSV/Parquet (default: published tournaments_postprocessed)",
    )
    parser.add_argument(
        "--league",
        type=Path,
        default=None,
        help="League CSV/Parquet (default: published league_results_merged)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"Output CSV (default: work dir / {CLUB_NAME_CONFLICTS_CSV})",
    )
    parser.add_argument(
        "--skip-tournament",
        action="store_true",
        help="Only audit league team labels",
    )
    args = parser.parse_args()

    league_path = args.league or league_results_merged_csv()
    if args.registry:
        from data_access.clubs_registry import build_and_publish_clubs_registry

        if not data_file_exists(league_path):
            print(f"Error: league data not found: {league_path}", file=sys.stderr)
            return 2
        build_and_publish_clubs_registry(_load_frame(league_path))

    registry = load_clubs_registry_df()
    if registry is None or registry.empty:
        print(
            "Error: clubs_registry missing. Run: uv run python scripts/build_clubs_registry.py",
            file=sys.stderr,
        )
        return 2

    alias_lookup = build_alias_to_canonical(registry)
    canonical_names = registry["canonical_name"].astype(str).tolist()
    conflicts: List[dict] = []

    if data_file_exists(league_path):
        league_df = _load_frame(league_path)
        for row in audit_league_team_club_consistency(league_df, registry):
            conflicts.append(
                {
                    "issue_type": row["issue_type"],
                    "source_file": league_path.name,
                    "club_label": row["team_label"],
                    "row_count": 1,
                    "proposed_canonical": row.get("club_base", ""),
                    "proposed_rule": "team_name_normalization",
                    "peer_labels": row.get("source_column", ""),
                }
            )

    if not args.skip_tournament:
        tournament_path = args.tournaments or tournaments_postprocessed_csv()
        if data_file_exists(tournament_path):
            tournament_df = _load_frame(tournament_path)
            conflicts.extend(
                _audit_tournament_clubs(
                    tournament_df,
                    source_file=tournament_path.name,
                    alias_lookup=alias_lookup,
                    canonical_names=canonical_names,
                )
            )

    report_path = args.report or (get_work_data_dir() / CLUB_NAME_CONFLICTS_CSV)
    write_club_name_conflicts_report(conflicts, report_path)

    unknown = sum(1 for row in conflicts if row["issue_type"] == "tournament_club_unknown")
    league_miss = sum(1 for row in conflicts if row["issue_type"] == "league_team_club_missing")
    print(f"Club audit: {unknown} tournament label(s), {league_miss} league team mismatch(es)")
    print(f"Report: {report_path.resolve()}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
