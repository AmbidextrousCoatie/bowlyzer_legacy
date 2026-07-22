"""Reanalyze db_real_merged open issues with correct era semantics.

Pre-2022 (Spielzettel): Position = insignificant column index; densify for API.
Post-2022 (Erfassung): Position = lane 0..ppt-1; holes are vacant lanes.
"""

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
ERA_CUTOFF = 2022  # season start year: <2022 = Spielzettel, >=2022 = Erfassung


def season_start(season: str) -> int:
    part = str(season).split("/")[0].strip()
    try:
        y = int(part)
        return y if y >= 100 else 2000 + y
    except ValueError:
        return -1


def era_label(start: int) -> str:
    if start < 0:
        return "unknown"
    if start < ERA_CUTOFF:
        return "pre-2022"
    return "2022+"


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
    names = df[Columns.player_name].fillna("").astype(str).str.strip()
    players = df.loc[names.ne("") & names.ne("Team Total")].copy()
    rounds = pd.to_numeric(players[Columns.round_number], errors="coerce")
    players = players.loc[rounds.gt(0)].copy()

    group_cols = [
        Columns.season,
        Columns.league_name,
        Columns.week,
        Columns.round_number,
        Columns.team_name,
    ]

    sides = []
    for key, group in players.groupby(group_cols, sort=False):
        season, league, week, rnd, team = key
        ppt = pd.to_numeric(group[Columns.players_per_team], errors="coerce").dropna()
        expected = int(ppt.iloc[0]) if not ppt.empty else DEFAULT_PLAYERS_PER_TEAM
        positions = sorted(
            int(p) for p in pd.to_numeric(group[Columns.position], errors="coerce").dropna()
        )
        count = len(group)
        start = season_start(str(season))
        era = era_label(start)
        max_pos = max(positions) if positions else -1
        min_pos = min(positions) if positions else -1
        # Needs densify for API: any position outside 0..expected-1
        needs_densify = bool(positions) and max_pos >= expected
        # Post-2022 vacant lane: positions in range but count < expected with holes
        in_range = bool(positions) and max_pos < expected and min_pos >= 0
        vacant_lanes = in_range and count < expected and len(set(positions)) < expected
        # True incomplete squad (fewer scorers than expected)
        incomplete = count < expected
        over = count > expected

        sides.append(
            {
                "season": str(season).strip(),
                "league": str(league).strip(),
                "week": int(week),
                "round": int(rnd),
                "team": str(team).strip(),
                "opponent": str(group[Columns.team_name_opponent].iloc[0] or "").strip(),
                "count": count,
                "expected": expected,
                "positions": positions,
                "era": era,
                "season_start": start,
                "needs_densify": needs_densify,
                "vacant_lanes": vacant_lanes,
                "incomplete": incomplete,
                "over": over,
            }
        )

    side_df = pd.DataFrame(sides)
    print(f"Database: {DATABASE}")
    print(f"Team-match sides (round>0): {len(side_df):,}\n")

    # --- Era split ---
    print("=== Era split (team-match sides) ===")
    for era, n in Counter(side_df["era"]).most_common():
        print(f"  {era}: {n:,}")
    print()

    # --- Fixtures ---
    fixture_map: dict[tuple, dict] = {}
    for _, row in side_df.iterrows():
        if not row["opponent"]:
            continue
        pair = tuple(sorted([row["team"], row["opponent"]]))
        fix_key = (row["season"], row["league"], row["week"], row["round"], pair)
        if fix_key not in fixture_map:
            fixture_map[fix_key] = {
                "season": row["season"],
                "league": row["league"],
                "week": row["week"],
                "round": row["round"],
                "era": row["era"],
                "team_a": pair[0],
                "team_b": pair[1],
                "sides": {},
            }
        fixture_map[fix_key]["sides"][row["team"]] = row.to_dict()

    fixtures = list(fixture_map.values())

    def fixture_kind(f: dict) -> str:
        sides = f["sides"]
        if len(sides) < 2:
            return "missing_side"
        counts = [s["count"] for s in sides.values()]
        expected = [s["expected"] for s in sides.values()]
        if all(c == e for c, e in zip(counts, expected)):
            return "full"
        if all(c < e for c, e in zip(counts, expected)):
            return "both_incomplete"
        if any(c < e for c, e in zip(counts, expected)):
            return "one_incomplete"
        return "over_or_mixed"

    print("=== Fixtures by completeness ===")
    print(f"Total fixtures: {len(fixtures):,}")
    by_kind = Counter(fixture_kind(f) for f in fixtures)
    for k, n in by_kind.most_common():
        print(f"  {k}: {n:,} ({100*n/len(fixtures):.2f}%)")
    print()

    print("=== Fixtures by era × completeness ===")
    era_kind = Counter((f["era"], fixture_kind(f)) for f in fixtures)
    for (era, kind), n in sorted(era_kind.items(), key=lambda x: (x[0][0], -x[1])):
        print(f"  {era:8} {kind:18} {n:,}")
    print()

    # --- Issue 1: Incomplete squads (real) ---
    incomplete_sides = side_df[side_df["incomplete"]]
    print("=== OPEN: Incomplete squads (count < expected) ===")
    print(f"Sides: {len(incomplete_sides):,}")
    print("By era:")
    for era, n in Counter(incomplete_sides["era"]).most_common():
        print(f"  {era}: {n:,}")
    print("By player count:")
    for cnt, n in sorted(Counter(incomplete_sides["count"]).items()):
        print(f"  {cnt} player(s): {n:,}")
    print("By era × count (solo=1 is bye-like):")
    for (era, cnt), n in sorted(
        Counter(zip(incomplete_sides["era"], incomplete_sides["count"])).items()
    ):
        if cnt <= 2 or n >= 50:
            print(f"  {era} × {cnt}p: {n:,}")
    print()

    # --- Issue 2: Missing side ---
    missing = [f for f in fixtures if fixture_kind(f) == "missing_side"]
    print("=== OPEN: Missing side (opponent name set, no player rows) ===")
    print(f"Fixtures: {len(missing):,}")
    print("By era:")
    for era, n in Counter(f["era"] for f in missing).most_common():
        print(f"  {era}: {n:,}")
    # Phantom opponents
    phantom = Counter()
    for f in missing:
        present = next(iter(f["sides"].values()))
        opp = present["opponent"]
        if opp in ("0", "0 1") or opp.startswith("0 "):
            phantom["phantom_0"] += 1
        else:
            phantom["named_missing"] += 1
    print(f"  phantom '0' opponents: {phantom['phantom_0']:,}")
    print(f"  named team, no rows: {phantom['named_missing']:,}")
    print()

    # --- Issue 3: Position densify (API concern, not data corruption) ---
    densify_sides = side_df[side_df["needs_densify"]]
    print("=== API: Needs densify (max Position >= ppt) — not a scrape bug ===")
    print(f"Sides: {len(densify_sides):,}")
    print("By era (expect almost all pre-2022):")
    for era, n in Counter(densify_sides["era"]).most_common():
        print(f"  {era}: {n:,} ({100*n/len(side_df[side_df['era']==era]):.1f}% of era)")
    # Patterns
    print("Common position sets (pre-2022 densify, top 10):")
    pre_d = densify_sides[densify_sides["era"] == "pre-2022"]
    set_counts = Counter(tuple(p) for p in pre_d["positions"])
    for pos_set, n in set_counts.most_common(10):
        print(f"  {list(pos_set)}: {n:,}")
    print()

    # --- Issue 4: Post-2022 vacant lanes (legitimate H2H holes) ---
    vacant = side_df[side_df["vacant_lanes"]]
    print("=== INFO: Vacant lanes inside 0..ppt-1 (post-2022 H2H holes / rare pre) ===")
    print(f"Sides: {len(vacant):,}")
    print("By era:")
    for era, n in Counter(vacant["era"]).most_common():
        print(f"  {era}: {n:,}")
    print()

    # --- Issue 5: Over-roster ---
    over = side_df[side_df["over"]]
    print("=== OPEN: Over-roster (count > expected) ===")
    print(f"Sides: {len(over):,}")
    print("By era:")
    for era, n in Counter(over["era"]).most_common():
        print(f"  {era}: {n:,}")
    if not over.empty:
        print("By count:")
        for cnt, n in sorted(Counter(over["count"]).items()):
            print(f"  {cnt} players: {n:,}")
    print()

    # --- Cross-team "scheme mismatch" was a false alarm ---
    # Pre-2022: both sides densify independently — mismatch of raw positions is expected
    # Post-2022: both should use 0..3; raw mismatch only if densify needed (shouldn't)
    post = [f for f in fixtures if f["era"] == "2022+" and len(f["sides"]) == 2]
    post_raw_mismatch = 0
    for f in post:
        schemes = []
        for s in f["sides"].values():
            pos = s["positions"]
            if not pos:
                continue
            schemes.append((min(pos), max(pos)))
        if len(schemes) == 2 and schemes[0] != schemes[1]:
            # only count if one needs densify or different ranges
            sides_list = list(f["sides"].values())
            if any(s["needs_densify"] for s in sides_list):
                post_raw_mismatch += 1
    print("=== RECLASSIFIED: Raw position 'mismatches' ===")
    pre_full = [
        f
        for f in fixtures
        if f["era"] == "pre-2022"
        and fixture_kind(f) == "full"
        and len(f["sides"]) == 2
    ]
    pre_diff_raw = 0
    for f in pre_full:
        a, b = list(f["sides"].values())
        if tuple(a["positions"]) != tuple(b["positions"]):
            pre_diff_raw += 1
    print(f"Pre-2022 full fixtures with different raw Position sets: {pre_diff_raw:,}/{len(pre_full):,}")
    print("  → Expected / harmless (column indices insignificant; API densifies per side)")
    print(f"Post-2022 fixtures with densify-needed on a side: {post_raw_mismatch:,}")
    print()

    # --- Known bye case ---
    print("=== Known case: 11/12 BZL S2 W2 R4 ===")
    for f in fixtures:
        if (
            f["season"] == "11/12"
            and f["league"] == "BZL S2"
            and f["week"] == 2
            and f["round"] == 4
            and "7 Schwaben Neu-Ulm 1" in f["sides"]
        ):
            for team, s in f["sides"].items():
                densify = "densify→0..3" if s["needs_densify"] else "already in 0..3"
                print(
                    f"  {team}: {s['count']}/{s['expected']} pos={s['positions']} "
                    f"[{s['era']}, {densify}, incomplete={s['incomplete']}]"
                )
            print(f"  fixture_kind={fixture_kind(f)}")
            break
    print()

    # --- Summary for discussion ---
    print("=== OPEN ISSUES SUMMARY ===")
    print(
        f"1. Incomplete squads: {len(incomplete_sides):,} sides "
        f"({len([f for f in fixtures if fixture_kind(f) in ('one_incomplete','both_incomplete')]):,} fixtures) "
        f"— exclude from records / special matches"
    )
    print(
        f"2. Missing side: {len(missing):,} fixtures "
        f"({phantom['phantom_0']:,} phantom bye '0', {phantom['named_missing']:,} named gaps)"
    )
    print(
        f"3. Over-roster: {len(over):,} sides — data quality / double-entry?"
    )
    print(
        f"4. Densify for API: {len(densify_sides):,} sides "
        f"(almost all pre-2022) — handled in get_game_team_details; NOT a DB corruption"
    )
    print(
        f"5. Vacant H2H lanes: {len(vacant):,} sides — legitimate post-2022; keep holes"
    )
    print(
        "6. Raw cross-team position mismatch pre-2022: CLOSED as false positive"
    )


if __name__ == "__main__":
    main()
