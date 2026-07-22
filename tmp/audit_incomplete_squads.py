"""Audit league matches with incomplete squads (partial lineups / byes)."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.league_points_budget import DEFAULT_PLAYERS_PER_TEAM
from data_access.schema import Columns

DATABASE = "db_real_merged"


def position_scheme(positions: list[int]) -> str:
    if not positions:
        return "empty"
    if min(positions) == 0 and max(positions) <= 3:
        return "0-based-0-3"
    if min(positions) == 1 and max(positions) <= 4:
        return "1-based-1-4"
    return "other"


def side_category(count: int, expected: int) -> str:
    if count == 0:
        return "empty"
    if count < expected:
        return "partial"
    if count == expected:
        return "full"
    return "over"


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
            Columns.players_per_team,
            Columns.position,
            Columns.score,
        ],
    )
    if df.empty:
        print("No player rows found.")
        return

    names = df[Columns.player_name].fillna("").astype(str).str.strip()
    players = df.loc[names.ne("") & names.ne("Team Total")].copy()
    rounds = pd.to_numeric(players[Columns.round_number], errors="coerce")
    players = players.loc[rounds.gt(0)].copy()

    # Roster counts per team-match
    group_cols = [
        Columns.season,
        Columns.league_name,
        Columns.week,
        Columns.round_number,
        Columns.team_name,
    ]
    roster_rows = []
    for key, group in players.groupby(group_cols, sort=False):
        season, league, week, rnd, team = key
        ppt = pd.to_numeric(group[Columns.players_per_team], errors="coerce").dropna()
        expected = int(ppt.iloc[0]) if not ppt.empty else DEFAULT_PLAYERS_PER_TEAM
        positions = sorted(int(p) for p in pd.to_numeric(group[Columns.position], errors="coerce").dropna())
        roster_rows.append(
            {
                "season": str(season).strip(),
                "league": str(league).strip(),
                "week": int(week),
                "round": int(rnd),
                "team": str(team).strip(),
                "count": len(group),
                "expected": expected,
                "positions": positions,
                "opponent": str(group[Columns.team_name_opponent].iloc[0] or "").strip(),
            }
        )
    roster_df = pd.DataFrame(roster_rows)
    roster_df["full"] = roster_df["count"] == roster_df["expected"]
    roster_df["shortfall"] = roster_df["expected"] - roster_df["count"]
    roster_df["category"] = roster_df.apply(
        lambda r: side_category(int(r["count"]), int(r["expected"])), axis=1
    )
    roster_df["pos_scheme"] = roster_df["positions"].apply(position_scheme)

    total_team_matches = len(roster_df)
    print(f"Database: {DATABASE}")
    print(f"Team-match sides (round>0, player rows): {total_team_matches:,}")
    print()
    print("Side categories:")
    for cat, n in Counter(roster_df["category"]).most_common():
        print(f"  {cat}: {n:,} ({100*n/total_team_matches:.2f}%)")
    print()

    # Unique fixtures: one per (season, league, week, round, sorted team pair)
    fixture_map: dict[tuple, dict] = {}

    for _, row in roster_df.iterrows():
        a = row["team"]
        b = row["opponent"]
        if not b:
            continue
        pair = tuple(sorted([a, b]))
        fix_key = (row["season"], row["league"], row["week"], row["round"], pair)
        if fix_key not in fixture_map:
            fixture_map[fix_key] = {
                "season": row["season"],
                "league": row["league"],
                "week": row["week"],
                "round": row["round"],
                "team_a": pair[0],
                "team_b": pair[1],
                "sides": {},
            }
        fixture_map[fix_key]["sides"][row["team"]] = {
            "count": row["count"],
            "expected": row["expected"],
            "category": row["category"],
            "positions": row["positions"],
            "pos_scheme": row["pos_scheme"],
        }

    fixtures = list(fixture_map.values())
    total_fixtures = len(fixtures)

    def fixture_status(f: dict) -> str:
        sides = f["sides"]
        if len(sides) < 2:
            return "missing_side"
        cats = [sides.get(f["team_a"], {}).get("category"), sides.get(f["team_b"], {}).get("category")]
        if all(c == "full" for c in cats):
            return "full"
        if all(c in ("partial", "empty", "over") for c in cats) and any(c != "full" for c in cats):
            if cats[0] != "full" and cats[1] != "full":
                return "both_incomplete"
            return "one_incomplete"
        return "mixed"

    status_counts = Counter(fixture_status(f) for f in fixtures)
    print(f"Unique fixtures (deduped team pair): {total_fixtures:,}")
    for status, n in status_counts.most_common():
        print(f"  {status}: {n:,} ({100*n/total_fixtures:.2f}%)")

    affected = [f for f in fixtures if fixture_status(f) != "full"]
    print(f"\nFixtures where at least one side is not full: {len(affected):,} ({100*len(affected)/total_fixtures:.2f}%)")
    print()

    incomplete_teams = roster_df[roster_df["category"] != "full"]
    print("Non-full sides by category detail:")
    print(Counter(incomplete_teams["category"]))
    print()

    # Distribution of shortfalls
    print("Incomplete sides by shortfall (expected - actual):")
    for gap, n in sorted(Counter(incomplete_teams["shortfall"]).items()):
        print(f"  missing {gap} player(s): {n:,}")
    print()

    print("Incomplete sides by actual count:")
    for cnt, n in sorted(Counter(incomplete_teams["count"]).items()):
        print(f"  {cnt} player(s): {n:,}")
    print()

    # Position scheme (separate data-quality issue from roster size)
    print("Position schemes (all team-match sides):")
    for scheme, n in Counter(roster_df["pos_scheme"]).most_common():
        print(f"  {scheme}: {n:,}")
    print()

    scheme_mismatch = []
    for f in fixtures:
        sides = f["sides"]
        if len(sides) < 2:
            continue
        schemes = {t: s.get("pos_scheme", "empty") for t, s in sides.items()}
        vals = {v for v in schemes.values() if v != "empty"}
        if len(vals) > 1:
            scheme_mismatch.append(f)

    print(f"Fixtures with mismatched position schemes: {len(scheme_mismatch):,} ({100*len(scheme_mismatch)/total_fixtures:.2f}%)")
    both_full_mismatch = [
        f for f in scheme_mismatch if fixture_status(f) == "full"
    ]
    print(f"  of which both sides full roster: {len(both_full_mismatch):,}")
    print()

    # By season/league summary
    incomplete_fixture_rows = [
        f for f in fixtures if fixture_status(f) in ("one_incomplete", "both_incomplete", "missing_side", "mixed")
    ]
    by_league = Counter((f["season"], f["league"]) for f in incomplete_fixture_rows)
    print("Top 20 season/league by incomplete fixtures:")
    for (season, league), n in by_league.most_common(20):
        print(f"  {season} · {league}: {n:,}")
    print()

    # Sample incomplete fixtures including the known bye
    print("Sample incomplete fixtures (up to 15):")
    samples = sorted(
        incomplete_fixture_rows,
        key=lambda f: (f["season"], f["league"], f["week"], f["round"]),
    )[:15]
    for f in samples:
        sides = f["sides"]
        a = sides.get(f["team_a"], {})
        b = sides.get(f["team_b"], {})
        print(
            f"  {f['season']} {f['league']} W{f['week']} R{f['round']}: "
            f"{f['team_a']} ({a.get('count','?')}/{a.get('expected','?')} {a.get('category','?')}) vs "
            f"{f['team_b']} ({b.get('count','?')}/{b.get('expected','?')} {b.get('category','?')})"
        )
    print()

    # Known case
    known = [
        f
        for f in fixtures
        if f["season"] == "11/12"
        and f["league"] == "BZL S2"
        and f["week"] == 2
        and f["round"] == 4
        and "7 Schwaben Neu-Ulm 1" in (f["team_a"], f["team_b"])
    ]
    if known:
        f = known[0]
        print("Known bye case (11/12 BZL S2 W2 R4):")
        for team, s in f["sides"].items():
            print(f"  {team}: {s['count']}/{s['expected']} positions={s['positions']}")


if __name__ == "__main__":
    main()
