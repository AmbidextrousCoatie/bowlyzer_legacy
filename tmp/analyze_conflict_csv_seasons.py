#!/usr/bin/env python3
import csv
from pathlib import Path


def season_start(s: str) -> int:
    part = s.strip().split("/")[0]
    return 2000 + int(part) if len(part) == 2 else int(part)


rows = list(csv.DictReader(Path("tmp/player_id_name_conflicts.csv").open(encoding="utf-8")))

print("Aktive Mitglieder scrape in work dir: 2004-05 .. 2018-19")
print("(legacy scrape hub documents ~2008-09 .. 2018-19 for league workbooks)")
print()

marriage = {
    "38397": ("Schwartz, Janin", "Theisen, Janin"),
    "38539": ("Triebel, Stephanie", "Fischer, Stephanie"),
    "38607": ("Mattern, Sandra", "Jenke, Sandra"),
    "38555": ("Daffner, Regina", "Gahr, Regina"),  # + Gahr Regina
}

print("=== Marriage-like: registered vs missing alias ===")
for pid, (registered, missing) in marriage.items():
    print(f"\nID {pid} (registry has {registered!r}):")
    for r in rows:
        if r["player_id"] != pid:
            continue
        seasons = [s.strip() for s in r["seasons"].split(";") if s.strip()]
        years = [season_start(s) for s in seasons]
        role = "REGISTERED" if r["player_name"] == registered else "MISSING"
        ge2020 = all(y >= 2020 for y in years) if years else None
        print(
            f"  [{role}] {r['player_name']}: {r['seasons']} "
            f"(start years {years}, all>=2020={ge2020})"
        )

other = ["16270", "38114", "7762", "7883", "38309", "16270"]
print("\n=== Other unresolved groups (not marriage) ===")
for pid in other:
    group = [r for r in rows if r["player_id"] == pid]
    if not group:
        continue
    print(f"\nID {pid}:")
    for r in group:
        seasons = [s.strip() for s in r["seasons"].split(";") if s.strip()]
        years = [season_start(s) for s in seasons]
        print(f"  {r['player_name']}: {r['seasons']} (years {years})")

print("\n=== Summary: missing marriage alias only post-2019? ===")
for pid, (registered, missing) in marriage.items():
    for r in rows:
        if r["player_id"] == pid and r["player_name"] == missing:
            years = [season_start(s) for s in r["seasons"].split(";") if s.strip()]
            print(f"{pid} {missing}: min_year={min(years) if years else None}, all>=2020={all(y>=2020 for y in years) if years else None}")
