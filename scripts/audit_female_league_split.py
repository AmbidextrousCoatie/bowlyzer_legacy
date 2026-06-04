#!/usr/bin/env python3
"""
Detect male/female league collapse in flat league CSVs.

Flags seasons where a male league id (BayL, LL N1, …) has too many distinct
teams while the paired ``… (D)`` league is missing or suspiciously empty.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MAPPING = REPO_ROOT / "database" / "relational_csv" / "league_mapping.csv"

# Max distinct team-total names before we treat a single-gender league as suspicious.
DEFAULT_HIGH_TEAM_THRESHOLD = 12


@dataclass(frozen=True)
class GenderCollapseIssue:
    season: str
    male_league: str
    female_league: str
    male_teams: int
    female_teams: int
    issue: str

    def format_line(self) -> str:
        return (
            f"{self.season} | {self.male_league}: {self.male_teams} teams, "
            f"{self.female_league}: {self.female_teams} teams — {self.issue}"
        )


def load_female_league_pairs(mapping_path: Path = DEFAULT_MAPPING) -> List[Tuple[str, str]]:
    """Return (male_id, female_id) pairs from league_mapping.csv."""
    if not mapping_path.is_file():
        return []

    male_ids: set[str] = set()
    female_ids: set[str] = set()
    with mapping_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            lid = (row.get("id") or "").strip()
            gender = (row.get("gender_scope") or "").strip().lower()
            if not lid:
                continue
            if gender == "female":
                female_ids.add(lid)
            elif gender == "male":
                male_ids.add(lid)

    special_male_for_female = {
        "LL N (D)": "LL N1",
    }

    pairs: List[Tuple[str, str]] = []
    for female_id in sorted(female_ids):
        male_id = special_male_for_female.get(female_id) or female_id.replace(" (D)", "")
        if male_id in male_ids:
            pairs.append((male_id, female_id))
    return pairs


def audit_league_csv(
    csv_path: Path,
    *,
    pairs: Sequence[Tuple[str, str]] | None = None,
    high_team_threshold: int = DEFAULT_HIGH_TEAM_THRESHOLD,
    sep: str = ";",
) -> List[GenderCollapseIssue]:
    """
    Scan team-total rows for collapsed female leagues.

    Issues:
    - ``missing_female``: male league exceeds threshold, female league absent
    - ``likely_merged``: male count high while female count is zero (same check)
    """
    import pandas as pd

    pairs = list(pairs or load_female_league_pairs())
    if not pairs:
        return []

    if csv_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(csv_path)
    else:
        df = pd.read_csv(
            csv_path,
            sep=sep,
            dtype=str,
            usecols=lambda c: c in {"Season", "League", "Team", "Player", "Position"},
        )
    df = df.fillna("")

    team_totals = df[
        (df["Player"].str.lower() == "team total") & (df["Position"].astype(str) == "0")
    ]
    if team_totals.empty:
        return []

    issues: List[GenderCollapseIssue] = []
    for season in sorted(team_totals["Season"].unique()):
        season_df = team_totals[team_totals["Season"] == season]
        for male_id, female_id in pairs:
            male_teams = int(season_df[season_df["League"] == male_id]["Team"].nunique())
            female_teams = int(season_df[season_df["League"] == female_id]["Team"].nunique())
            if male_teams <= high_team_threshold:
                continue
            if female_teams > 0:
                continue
            issues.append(
                GenderCollapseIssue(
                    season=str(season),
                    male_league=male_id,
                    female_league=female_id,
                    male_teams=male_teams,
                    female_teams=female_teams,
                    issue="missing_female_league (male teams likely include Damen rows)",
                )
            )
    return issues


def format_issue_report(issues: Iterable[GenderCollapseIssue], *, csv_path: Path) -> str:
    issues = list(issues)
    if not issues:
        return f"OK: no female-league collapse detected in {csv_path}"

    by_league: Dict[str, List[GenderCollapseIssue]] = {}
    for issue in issues:
        by_league.setdefault(issue.male_league, []).append(issue)

    lines = [f"Female-league collapse issues in {csv_path} ({len(issues)} season×league hits):"]
    for male_id in sorted(by_league):
        lines.append(f"  {male_id}:")
        for hit in by_league[male_id][:8]:
            lines.append(f"    - {hit.format_line()}")
        extra = len(by_league[male_id]) - 8
        if extra > 0:
            lines.append(f"    ... and {extra} more")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit flat league CSV for male/female league collapse.")
    parser.add_argument("csv", type=Path, help="Semicolon-separated league CSV")
    parser.add_argument(
        "--high-teams-threshold",
        type=int,
        default=DEFAULT_HIGH_TEAM_THRESHOLD,
        help=f"Flag male league when team count exceeds this and female id is absent (default: {DEFAULT_HIGH_TEAM_THRESHOLD})",
    )
    parser.add_argument("--sep", default=";", help="CSV delimiter")
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 2

    issues = audit_league_csv(
        csv_path,
        high_team_threshold=max(1, int(args.high_teams_threshold)),
        sep=args.sep,
    )
    print(format_issue_report(issues, csv_path=csv_path))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
