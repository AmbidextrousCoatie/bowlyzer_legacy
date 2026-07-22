"""Investigate position offset origins in legacy scrape CSV."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

SEP = ";"
SCRAPE = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\legacy_scrape_extracted.csv")


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


def main() -> None:
    print(f"Loading {SCRAPE} ...")
    df = pd.read_csv(SCRAPE, sep=SEP, dtype=str, keep_default_na=False)
    print(f"Rows: {len(df):,}")
    print(f"Columns: {list(df.columns)}")

    names = df["Player"].fillna("").astype(str).str.strip()
    work = df.loc[names.ne("") & names.str.lower().ne("team total")].copy()
    rounds = pd.to_numeric(work["Round Number"], errors="coerce")
    work = work.loc[rounds.gt(0)].copy()
    work["_pos"] = pd.to_numeric(work["Position"], errors="coerce")

    group_cols = ["Season", "League", "Week", "Round Number", "Team"]
    sides = []
    for key, g in work.groupby(group_cols, sort=False):
        positions = sorted(int(p) for p in g["_pos"].dropna())
        scheme = position_scheme(positions)
        sides.append(
            {
                "key": key,
                "scheme": scheme,
                "positions": positions,
                "players": list(
                    zip(
                        g["Player"].tolist(),
                        [int(p) if pd.notna(p) else None for p in g["_pos"].tolist()],
                    )
                ),
            }
        )

    by_scheme = defaultdict(list)
    for s in sides:
        by_scheme[s["scheme"]].append(s)

    print("\n=== Scheme counts ===")
    for sch, items in sorted(by_scheme.items(), key=lambda x: -len(x[1])):
        print(f"  {sch}: {len(items):,}")

    # Task 1: other-0..4-n4
    target = "other-0..4-n4"
    print(f"\n=== Task1: 5 sides with scheme {target} ===")
    samples = by_scheme.get(target, [])[:5]
    if not samples:
        # show closest
        print(f"  none found; nearby schemes: {[s for s in by_scheme if '0..4' in s or 'n4' in s][:20]}")
        for sch in list(by_scheme)[:30]:
            if "other" in sch:
                print(f"  alt sample {sch}:")
                s = by_scheme[sch][0]
                print(f"    {s['key']} positions={s['positions']}")
                for pl, pos in s["players"]:
                    print(f"      pos={pos} {pl}")
    for s in samples:
        print(f"\n  {s['key']} positions={s['positions']}")
        for pl, pos in s["players"]:
            print(f"    pos={pos} {pl}")

    # Task 2: 1-based-1-4
    print("\n=== Task2: 3 sides with scheme 1-based-1-4 ===")
    samples2 = by_scheme.get("1-based-1-4", [])[:3]
    all_exact = True
    for s in by_scheme.get("1-based-1-4", []):
        if s["positions"] != [1, 2, 3, 4]:
            all_exact = False
            break
    n1 = len(by_scheme.get("1-based-1-4", []))
    print(f"  total 1-based-1-4 sides: {n1}")
    print(f"  always exactly [1,2,3,4]? {all_exact}")
    # also check uniqueness / duplicates
    non_exact = [s for s in by_scheme.get("1-based-1-4", []) if s["positions"] != [1, 2, 3, 4]]
    print(f"  non-exact count: {len(non_exact)}")
    if non_exact[:3]:
        for s in non_exact[:3]:
            print(f"    {s['key']} positions={s['positions']}")
    for s in samples2:
        print(f"\n  {s['key']} positions={s['positions']}")
        for pl, pos in s["players"]:
            print(f"    pos={pos} {pl}")

    # Task 3: 7 Schwaben Neu-Ulm 1 in 11/12 BZL S2
    print("\n=== Task3: 7 Schwaben Neu-Ulm 1 / 11/12 / BZL S2 all weeks ===")
    mask = (
        (work["Season"].astype(str).str.strip() == "11/12")
        & (work["League"].astype(str).str.strip() == "BZL S2")
        & (work["Team"].astype(str).str.strip() == "7 Schwaben Neu-Ulm 1")
    )
    sub = work.loc[mask].copy()
    print(f"  player rows: {len(sub)}")
    weeks = sorted(pd.to_numeric(sub["Week"], errors="coerce").dropna().unique())
    print(f"  weeks present: {weeks}")
    schemes_seen = set()
    for (week, rnd), g in sub.groupby(
        [pd.to_numeric(sub["Week"], errors="coerce"), pd.to_numeric(sub["Round Number"], errors="coerce")],
        sort=True,
    ):
        positions = sorted(int(p) for p in g["_pos"].dropna())
        sch = position_scheme(positions)
        schemes_seen.add(sch)
        players = ", ".join(f"{int(p) if pd.notna(p) else '?'}:{n}" for n, p in zip(g["Player"], g["_pos"]))
        print(f"  W{int(week)} R{int(rnd)}: {positions} ({sch}) | {players}")
    print(f"  schemes across season: {sorted(schemes_seen)}")


if __name__ == "__main__":
    main()
