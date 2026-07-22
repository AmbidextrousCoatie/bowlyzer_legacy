"""Re-extract 11/12 BZL S2 week 2 and compare positions to scrape CSV."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(r"C:\Users\cfell\repositories\bowlyzer_deploy")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "data"))

from extract_excel_data import extract_pre_2022_file  # noqa: E402

XLSX = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\saison2011-12\suedbereich\LB_BezL_S_2-H-2.xlsx")
XLS = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\saison2011-12\suedbereich\LB_BezL_S_2-H-2.xls")
SCRAPE = Path(r"C:\tmp\bowlyzer\data\legacy_scrape\legacy_scrape_extracted.csv")
TEAM = "7 Schwaben Neu-Ulm 1"
SEP = ";"


def show_side(label: str, df: pd.DataFrame) -> None:
    names = df["Player"].fillna("").astype(str).str.strip()
    work = df.loc[names.ne("") & names.str.lower().ne("team total")].copy()
    work["_pos"] = pd.to_numeric(work["Position"], errors="coerce")
    work["_rnd"] = pd.to_numeric(work["Round Number"], errors="coerce")
    sub = work.loc[work["Team"].astype(str).str.strip() == TEAM].copy()
    print(f"\n=== {label}: {TEAM} rows={len(sub)} ===")
    if sub.empty:
        teams = sorted(work["Team"].astype(str).str.strip().unique())
        print(f"  team not found; teams sample: {teams[:15]}")
        return
    for rnd, g in sub.groupby("_rnd", sort=True):
        positions = sorted(int(p) for p in g["_pos"].dropna())
        players = [(int(p) if pd.notna(p) else None, n) for n, p in zip(g["Player"], g["_pos"])]
        players = sorted(players, key=lambda x: (x[0] is None, x[0] or 0))
        print(f"  R{int(rnd)} positions={positions}")
        for pos, name in players:
            print(f"    {pos}: {name}")


def main() -> None:
    path = XLSX if XLSX.is_file() else XLS
    print(f"Extracting {path}")
    rows = extract_pre_2022_file(
        path,
        league="BZL S2",
        season="11/12",
        week=2,
        location="Unknown",
        players_per_team=4,
        number_of_teams=8,
    )
    fresh = pd.DataFrame(rows)
    print(f"Fresh rows: {len(fresh)}; cols={list(fresh.columns)[:12]}...")
    if "League" in fresh.columns:
        print(f"Leagues: {sorted(fresh['League'].astype(str).unique())[:10]}")
        print(f"Weeks: {sorted(pd.to_numeric(fresh['Week'], errors='coerce').dropna().unique())}")
    show_side("CURRENT extract_pre_2022_file", fresh)

    scrape = pd.read_csv(SCRAPE, sep=SEP, dtype=str, keep_default_na=False)
    mask = (
        (scrape["Season"].astype(str).str.strip() == "11/12")
        & (scrape["League"].astype(str).str.strip() == "BZL S2")
        & (pd.to_numeric(scrape["Week"], errors="coerce") == 2)
        & (scrape["Team"].astype(str).str.strip() == TEAM)
    )
    show_side("legacy_scrape_extracted.csv", scrape.loc[mask])

    # Diff positions per round for the team
    print("\n=== Diff (fresh vs scrape) positions per round ===")
    fresh_p = fresh.copy()
    fresh_p = fresh_p.loc[
        fresh_p["Player"].fillna("").astype(str).str.lower().ne("team total")
        & (fresh_p["Team"].astype(str).str.strip() == TEAM)
    ]
    scrape_p = scrape.loc[mask].copy()
    scrape_p = scrape_p.loc[scrape_p["Player"].fillna("").astype(str).str.lower().ne("team total")]

    for rnd in sorted(pd.to_numeric(fresh_p["Round Number"], errors="coerce").dropna().unique()):
        f = fresh_p.loc[pd.to_numeric(fresh_p["Round Number"], errors="coerce") == rnd]
        s = scrape_p.loc[pd.to_numeric(scrape_p["Round Number"], errors="coerce") == rnd]
        fp = sorted(
            (str(r["Player"]).strip(), int(float(r["Position"])))
            for _, r in f.iterrows()
            if str(r.get("Position", "")).strip() != ""
        )
        sp = sorted(
            (str(r["Player"]).strip(), int(float(r["Position"])))
            for _, r in s.iterrows()
            if str(r.get("Position", "")).strip() != ""
        )
        match = fp == sp
        print(f"  R{int(rnd)} match={match}")
        if not match:
            print(f"    fresh:  {fp}")
            print(f"    scrape: {sp}")


if __name__ == "__main__":
    main()
