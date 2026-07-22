"""Audit Position field schemes by season and merge source."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns
from database.paths import get_work_data_dir, historical_league_results_csv

DATABASE = "db_real_merged"
SEP = ";"


def season_start(season: str) -> int:
    part = str(season).split("/")[0].strip()
    try:
        y = int(part)
        return y if y >= 100 else 2000 + y
    except ValueError:
        return -1


def position_scheme(positions: list[int]) -> str:
    if not positions:
        return "empty"
    lo, hi = min(positions), max(positions)
    n = len(positions)
    if lo == 0 and hi <= 3 and n <= 4:
        return "0-based-0-3"
    if lo == 1 and hi <= 4 and n <= 4:
        return "1-based-1-4"
    if lo == 0 and hi <= 5:
        return f"other-0..{hi}-n{n}"
    return f"other-{lo}..{hi}-n{n}"


def side_scheme(pos_series: pd.Series) -> str:
    positions = sorted(int(p) for p in pd.to_numeric(pos_series, errors="coerce").dropna())
    return position_scheme(positions)


def load_player_rows_from_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path, sep=SEP, dtype=str, keep_default_na=False)
    rename = {c: c.strip() for c in df.columns}
    df = df.rename(columns=rename)
    player_col = "Player" if "Player" in df.columns else Columns.player_name
    round_col = "Round Number" if "Round Number" in df.columns else Columns.round_number
    names = df[player_col].fillna("").astype(str).str.strip()
    work = df.loc[names.ne("") & names.str.lower().ne("team total")].copy()
    rounds = pd.to_numeric(work[round_col], errors="coerce")
    return work.loc[rounds.gt(0)].copy()


def analyze_frame(label: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"\n=== {label}: (missing/empty) ===")
        return

    pos_col = "Position" if "Position" in df.columns else Columns.position
    season_col = "Season" if "Season" in df.columns else Columns.season
    league_col = "League" if "League" in df.columns else Columns.event
    week_col = "Week" if "Week" in df.columns else Columns.week
    round_col = "Round Number" if "Round Number" in df.columns else Columns.round_number
    team_col = "Team" if "Team" in df.columns else Columns.team_name

    group_cols = [season_col, league_col, week_col, round_col, team_col]
    rows = []
    for key, group in df.groupby(group_cols, sort=False):
        season = str(key[0]).strip()
        scheme = side_scheme(group[pos_col])
        rows.append({"season": season, "season_start": season_start(season), "scheme": scheme})

    side_df = pd.DataFrame(rows)
    print(f"\n=== {label} ===")
    print(f"Sides analyzed: {len(side_df):,}")
    print("Overall schemes:")
    for scheme, n in Counter(side_df["scheme"]).most_common(10):
        print(f"  {scheme}: {n:,}")

    by_season = (
        side_df.groupby(["season", "season_start", "scheme"])
        .size()
        .reset_index(name="count")
    )
    pivot = by_season.pivot_table(
        index=["season", "season_start"],
        columns="scheme",
        values="count",
        fill_value=0,
        aggfunc="sum",
    )
    print("\nBy season (top scheme columns):")
    cols = [c for c in pivot.columns if c in ("0-based-0-3", "1-based-1-4")] + [
        c for c in pivot.columns if c not in ("0-based-0-3", "1-based-1-4")
    ]
    pivot = pivot.reindex(columns=cols, fill_value=0)
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_index(level="season_start")
    print(pivot.to_string())

    # Era rollup: pre-2019 scrape era vs post-2022 GF era
    side_df["era"] = side_df["season_start"].apply(
        lambda y: "pre-2019" if 0 <= y <= 2018 else ("2019-2021" if y <= 2021 else "2022+")
    )
    print("\nBy era:")
    era_pivot = side_df.groupby(["era", "scheme"]).size().unstack(fill_value=0)
    print(era_pivot.to_string())


def trace_team_example(path: Path, label: str, team: str, season: str, league: str, week: int, rnd: int) -> None:
    if not path.is_file():
        return
    df = pd.read_csv(path, sep=SEP, dtype=str, keep_default_na=False)
    mask = (
        (df["Season"].astype(str).str.strip() == season)
        & (df["League"].astype(str).str.strip() == league)
        & (pd.to_numeric(df["Week"], errors="coerce") == week)
        & (pd.to_numeric(df["Round Number"], errors="coerce") == rnd)
        & (df["Team"].astype(str).str.strip() == team)
        & (df["Player"].astype(str).str.lower() != "team total")
    )
    sub = df.loc[mask, ["Team", "Player", "Position", "Score", "Opponent"]]
    print(f"\n--- {label}: {team} {season} {league} W{week} R{rnd} ---")
    if sub.empty:
        print("  (no rows)")
    else:
        print(sub.to_string(index=False))


def main() -> None:
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=DATABASE)
    merged = adapter.get_filtered_data(
        filters={Columns.computed_data: {"value": False, "operator": "eq"}},
        columns=[
            Columns.season,
            Columns.league_name,
            Columns.week,
            Columns.round_number,
            Columns.team_name,
            Columns.player_name,
            Columns.position,
        ],
    )
    names = merged[Columns.player_name].fillna("").astype(str).str.strip()
    merged = merged.loc[names.ne("") & names.ne("Team Total")].copy()
    rounds = pd.to_numeric(merged[Columns.round_number], errors="coerce")
    merged = merged.loc[rounds.gt(0)].copy()
    analyze_frame("MERGED (db_real_merged)", merged)

    historical = historical_league_results_csv()
    work = get_work_data_dir()
    scrape_candidates = [
        work / "legacy_scrape" / "legacy_scrape_extracted.csv",
        work / "legacy_scrape_extracted.csv",
        Path(r"C:\tmp\bowlyzer\data\legacy_scrape\legacy_scrape_extracted.csv"),
    ]
    scrape_path = next((p for p in scrape_candidates if p.is_file()), scrape_candidates[0])

    analyze_frame(f"HISTORICAL ({historical.name})", load_player_rows_from_csv(historical))
    analyze_frame(f"SCRAPE ({scrape_path})", load_player_rows_from_csv(scrape_path))

    # Known example across sources
    for path, label in [
        (historical, "historical"),
        (scrape_path, "scrape"),
    ]:
        trace_team_example(
            path,
            label,
            team="7 Schwaben Neu-Ulm 1",
            season="11/12",
            league="BZL S2",
            week=2,
            rnd=4,
        )
        trace_team_example(
            path,
            label,
            team="City-Bowling Augsburg 2",
            season="11/12",
            league="BZL S2",
            week=2,
            rnd=4,
        )

    # Within-team inconsistency: same team+season uses multiple schemes
    print("\n=== Teams with mixed position schemes within one season ===")
    group_cols = [Columns.season, Columns.league_name, Columns.week, Columns.round_number, Columns.team_name]
    mixed_examples = []
    for key, group in merged.groupby(group_cols, sort=False):
        scheme = side_scheme(group[Columns.position])
        mixed_examples.append((key, scheme))
    team_season_schemes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, scheme in mixed_examples:
        season, league, week, rnd, team = key
        team_season_schemes[(str(season), str(team))].add(scheme)
    mixed_teams = [(k, v) for k, v in team_season_schemes.items() if len(v) > 1]
    print(f"Team-season combos with >1 scheme: {len(mixed_teams):,}")
    for (season, team), schemes in sorted(mixed_teams, key=lambda x: season_start(x[0][0]))[:15]:
        print(f"  {season} {team}: {sorted(schemes)}")


if __name__ == "__main__":
    main()
