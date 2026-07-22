"""Check whether phantom '0' opponents are byes in odd-sized leagues."""

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

DATABASE = "db_real_merged"


def is_phantom(name: str) -> bool:
    t = str(name or "").strip()
    if not t:
        return True
    if t in {"0", "0 1", "0 0"}:
        return True
    # common scrape bye markers
    if t.replace(" ", "") in {"0", "01", "00"}:
        return True
    if t.startswith("0 ") or t == "0":
        return True
    return False


def main() -> None:
    adapter = DataAdapterFactory.create_adapter(DataAdapterSelector.PANDAS, database=DATABASE)
    df = adapter.get_filtered_data(
        filters={Columns.computed_data: {"value": False, "operator": "eq"}},
        columns=[
            Columns.season,
            Columns.league_name,
            Columns.week,
            Columns.round_number,
            Columns.team_name,
            Columns.team_name_opponent,
            Columns.player_name,
        ],
    )
    names = df[Columns.player_name].fillna("").astype(str).str.strip()
    players = df.loc[names.ne("") & names.ne("Team Total")].copy()
    rounds = pd.to_numeric(players[Columns.round_number], errors="coerce")
    players = players.loc[rounds.gt(0)].copy()

    # League size = distinct real teams in season/league (exclude phantoms)
    league_teams: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (season, league, team), _ in players.groupby(
        [Columns.season, Columns.league_name, Columns.team_name], sort=False
    ):
        team_s = str(team).strip()
        if is_phantom(team_s):
            continue
        league_teams[(str(season).strip(), str(league).strip())].add(team_s)

    league_size = {k: len(v) for k, v in league_teams.items()}

    # Per-week distinct real teams (may be lower if absences)
    week_teams: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for (season, league, week, team), _ in players.groupby(
        [Columns.season, Columns.league_name, Columns.week, Columns.team_name], sort=False
    ):
        team_s = str(team).strip()
        if is_phantom(team_s):
            continue
        week_i = int(week)
        week_teams[(str(season).strip(), str(league).strip(), week_i)].add(team_s)

    # Phantom fixtures: team has opponent phantom, or opponent is phantom name
    # Build unique fixtures with phantom involvement
    phantom_fixtures = []
    seen = set()
    group_cols = [
        Columns.season,
        Columns.league_name,
        Columns.week,
        Columns.round_number,
        Columns.team_name,
        Columns.team_name_opponent,
    ]
    for key, _ in players.groupby(group_cols, sort=False):
        season, league, week, rnd, team, opp = key
        season_s = str(season).strip()
        league_s = str(league).strip()
        team_s = str(team).strip()
        opp_s = str(opp).strip()
        week_i = int(week)
        rnd_i = int(rnd)

        if not (is_phantom(opp_s) or is_phantom(team_s)):
            continue

        # Dedup fixture by sorted pair of labels
        pair = tuple(sorted([team_s, opp_s]))
        fix_key = (season_s, league_s, week_i, rnd_i, pair)
        if fix_key in seen:
            continue
        seen.add(fix_key)

        size = league_size.get((season_s, league_s), 0)
        wsize = len(week_teams.get((season_s, league_s, week_i), set()))
        phantom_fixtures.append(
            {
                "season": season_s,
                "league": league_s,
                "week": week_i,
                "round": rnd_i,
                "team": team_s,
                "opponent": opp_s,
                "league_size": size,
                "week_team_count": wsize,
                "league_odd": size % 2 == 1,
                "week_odd": wsize % 2 == 1,
            }
        )

    pdf = pd.DataFrame(phantom_fixtures)
    print(f"Database: {DATABASE}")
    print(f"Unique phantom-involved fixtures (round>0): {len(pdf):,}\n")

    if pdf.empty:
        print("No phantom fixtures found.")
        return

    print("=== Phantom fixtures by league size ===")
    size_counts = Counter(pdf["league_size"])
    for size, n in sorted(size_counts.items()):
        odd = "ODD" if size % 2 == 1 else "even"
        print(f"  size {size:2} ({odd}): {n:,} fixtures")
    odd_n = int(pdf["league_odd"].sum())
    even_n = len(pdf) - odd_n
    print(f"\n  ODD league size:  {odd_n:,} ({100*odd_n/len(pdf):.1f}%)")
    print(f"  even league size: {even_n:,} ({100*even_n/len(pdf):.1f}%)")
    print()

    print("=== Phantom fixtures by week team count ===")
    w_counts = Counter(pdf["week_team_count"])
    for size, n in sorted(w_counts.items()):
        odd = "ODD" if size % 2 == 1 else "even"
        print(f"  week teams {size:2} ({odd}): {n:,}")
    w_odd = int(pdf["week_odd"].sum())
    print(f"\n  ODD week count:  {w_odd:,} ({100*w_odd/len(pdf):.1f}%)")
    print(f"  even week count: {len(pdf)-w_odd:,} ({100*(len(pdf)-w_odd)/len(pdf):.1f}%)")
    print()

    # Per week: how many phantom fixtures (expect ~1 team * rounds if one bye)
    print("=== Phantom load per (season, league, week) ===")
    week_groups = (
        pdf.groupby(["season", "league", "week", "league_size", "week_team_count"])
        .size()
        .reset_index(name="phantom_fixtures")
    )
    print(f"Weeks with any phantom: {len(week_groups):,}")
    print("Phantom fixtures per week (distribution):")
    for nfix, nweeks in sorted(Counter(week_groups["phantom_fixtures"]).items()):
        print(f"  {nfix} phantom fixture(s)/week: {nweeks:,} weeks")
    print()

    # Odd leagues: expected pattern = 1 team on bye, all rounds that week
    odd_weeks = week_groups[week_groups["league_size"] % 2 == 1]
    even_weeks = week_groups[week_groups["league_size"] % 2 == 0]
    print("=== Odd-sized leagues: phantom fixtures per week ===")
    print(f"Odd-league weeks with phantoms: {len(odd_weeks):,}")
    if not odd_weeks.empty:
        for nfix, nweeks in sorted(Counter(odd_weeks["phantom_fixtures"]).items()):
            print(f"  {nfix}/week: {nweeks:,}")
        # Typical: bye team plays all rounds vs phantom -> often 7 fixtures/week
        print(
            f"  median phantoms/week: {odd_weeks['phantom_fixtures'].median():.0f}, "
            f"mean: {odd_weeks['phantom_fixtures'].mean():.1f}"
        )
    print()
    print("=== Even-sized leagues: phantom fixtures per week ===")
    print(f"Even-league weeks with phantoms: {len(even_weeks):,}")
    if not even_weeks.empty:
        for nfix, nweeks in sorted(Counter(even_weeks["phantom_fixtures"]).items()):
            print(f"  {nfix}/week: {nweeks:,}")
        print(
            f"  median phantoms/week: {even_weeks['phantom_fixtures'].median():.0f}, "
            f"mean: {even_weeks['phantom_fixtures'].mean():.1f}"
        )
        print("\n  Sample even-league weeks with phantoms (up to 12):")
        sample = even_weeks.sort_values(
            ["season", "league", "week"]
        ).head(12)
        for _, r in sample.iterrows():
            print(
                f"    {r['season']} {r['league']} W{r['week']}: "
                f"league_size={r['league_size']} week_teams={r['week_team_count']} "
                f"phantoms={r['phantom_fixtures']}"
            )
    print()

    # How many odd leagues exist vs how many have phantoms
    all_leagues = pd.DataFrame(
        [{"season": s, "league": l, "size": sz} for (s, l), sz in league_size.items()]
    )
    odd_leagues = all_leagues[all_leagues["size"] % 2 == 1]
    phantom_leagues = set(zip(pdf["season"], pdf["league"]))
    odd_with_phantom = odd_leagues[
        odd_leagues.apply(lambda r: (r["season"], r["league"]) in phantom_leagues, axis=1)
    ]
    odd_without = odd_leagues[
        ~odd_leagues.apply(lambda r: (r["season"], r["league"]) in phantom_leagues, axis=1)
    ]
    print("=== League inventory ===")
    print(f"Total season/league combos: {len(all_leagues):,}")
    print(f"  odd-sized:  {len(odd_leagues):,}")
    print(f"  even-sized: {len(all_leagues) - len(odd_leagues):,}")
    print(f"Odd leagues WITH phantoms: {len(odd_with_phantom):,}")
    print(f"Odd leagues WITHOUT phantoms: {len(odd_without):,}")
    if not odd_without.empty:
        print("  Sample odd leagues without phantoms:")
        for _, r in odd_without.sort_values(["season", "league"]).head(10).iterrows():
            print(f"    {r['season']} {r['league']} size={r['size']}")

    # Distinct bye teams (real team facing phantom)
    bye_teams = pdf[~pdf["team"].map(is_phantom)]
    print(f"\nReal teams facing phantom (bye sides): {bye_teams['team'].nunique():,} distinct")
    print(f"Phantom fixture rows involving real team: {len(bye_teams):,}")


if __name__ == "__main__":
    main()
