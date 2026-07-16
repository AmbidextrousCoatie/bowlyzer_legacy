import csv
from collections import defaultdict
from pathlib import Path

p = Path("database/data/tournament_clubmeisterschaft_donaubowler_2026_postprocessed.csv")
rows = list(csv.DictReader(p.open(encoding="utf-8-sig"), delimiter=";"))
print("rows", len(rows))
print("rounds", sorted({r["Round Name"] for r in rows}))
tot = defaultdict(lambda: {"scratch": 0, "hdc": 0, "games": 0, "id": ""})
for r in rows:
    if not r["Round Name"].startswith("Set"):
        continue
    n = r["Player"]
    tot[n]["scratch"] += int(r["Score"] or 0)
    tot[n]["hdc"] += int(float(r["Handicap"] or 0))
    tot[n]["games"] += 1
    tot[n]["id"] = r["Player ID"]
ranked = sorted(
    tot.items(),
    key=lambda kv: (-(kv[1]["scratch"] + kv[1]["hdc"]), -kv[1]["scratch"], kv[0]),
)
print("Top 10 by scratch+hdc:")
for i, (n, v) in enumerate(ranked[:10], 1):
    comb = v["scratch"] + v["hdc"]
    print(
        f"  {i}. {n}: scratch={v['scratch']} hdc={v['hdc']} "
        f"combined={comb} games={v['games']} id={v['id']}"
    )
