#!/usr/bin/env python3
"""Find Pass-Nr entries with multiple EDV IDs across Aktive Mitglieder seasons."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.aktive_mitglieder_registry import (
    _cell_str,
    _edv_column_index,
    _member_sheet_name,
    discover_local_aktive_workbooks,
    locate_member_header,
)
from data_access.player_id_name_normalization import normalize_player_id
from database.paths import legacy_scrape_dir
from extract_excel_data import get_sheet_names_safely, read_excel_safely


def parse_with_pass(path, season):
    try:
        sheets = get_sheet_names_safely(path)
        sheet = _member_sheet_name(sheets)
        raw = read_excel_safely(path, sheet_name=sheet, header=None)
    except Exception as exc:
        return [("__ERROR__", season, str(path.name), str(exc))]

    hi, layout, cols = locate_member_header(raw)
    if hi is None:
        return [("__ERROR__", season, str(path.name), "no header")]

    edv_idx = _edv_column_index(cols)
    pass_idx = cols.get("pass-nr") or cols.get("passnr")
    rows = []
    for i in range(hi + 1, len(raw)):
        r = raw.iloc[i].tolist()
        pid = normalize_player_id(_cell_str(r, edv_idx))
        pass_nr = _cell_str(r, pass_idx).strip()
        if not pid or not pass_nr:
            continue
        if layout == "split":
            fam = _cell_str(r, cols.get("nachname"))
            vor = _cell_str(r, cols.get("vorname"))
            name = f"{fam}, {vor}".strip(", ")
        else:
            name = _cell_str(r, cols.get("name"))
        rows.append((season, pid, pass_nr, name))
    return rows


def main() -> None:
    root = legacy_scrape_dir()
    workbooks = discover_local_aktive_workbooks(root)
    by_pass: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    errors: list[tuple] = []

    for season, wb in workbooks:
        for item in parse_with_pass(wb, season):
            if item[0] == "__ERROR__":
                errors.append(item)
                continue
            season2, pid, pass_nr, name = item
            by_pass[pass_nr].append((season2, pid, name))

    multi = []
    for pass_nr, entries in by_pass.items():
        ids = {pid for _, pid, _ in entries}
        if len(ids) <= 1:
            continue
        names = sorted({n for _, _, n in entries})
        seasons = sorted({s for s, _, _ in entries})
        timeline = {pid: sorted({s for s, p, _ in entries if p == pid}) for pid in ids}
        multi.append(
            {
                "pass_nr": pass_nr,
                "ids": sorted(ids, key=lambda x: timeline[x][0]),
                "names": names,
                "seasons": seasons,
                "timeline": timeline,
            }
        )

    multi.sort(key=lambda x: (len(x["ids"]), x["pass_nr"]), reverse=True)

    print(f"Workbooks: {len(workbooks)}, parse errors: {len(errors)}")
    print(f"Unique Pass-Nr: {len(by_pass)}")
    print(f"Pass-Nr with multiple EDV IDs: {len(multi)}")
    print()

    stale_pattern = []
    overlap_pattern = []
    for m in multi:
        t = m["timeline"]
        ids = m["ids"]
        overlapping = False
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                sa, ea = t[a][0], t[a][-1]
                sb, eb = t[b][0], t[b][-1]
                if not (ea < sb or eb < sa):
                    overlapping = True
        if overlapping:
            overlap_pattern.append(m)
        else:
            stale_pattern.append(m)

    print(f"Non-overlapping renumber handoffs: {len(stale_pattern)}")
    print(f"Overlapping seasons (same pass, 2 IDs at once): {len(overlap_pattern)}")
    print()

    print("=== Sample renumber handoffs (first 30) ===")
    for m in stale_pattern[:30]:
        arrow = " -> ".join(m["ids"])
        print(f"Pass {m['pass_nr']}: {arrow}")
        for pid in m["ids"]:
            ss = m["timeline"][pid]
            print(f"  {pid}: {ss[0]} .. {ss[-1]}")
        print(f"  names: {m['names'][:2]}")
        print()

    # How many stale IDs are still in published registry?
    import pandas as pd

    reg = pd.read_parquet("database/data/players_registry.parquet")
    reg_ids = set(reg["player_id"].astype(str))
    stale_ids_in_registry = 0
    stale_rows = []
    for m in stale_pattern:
        ids = m["ids"]
        old_ids = ids[:-1]
        current = ids[-1]
        for old in old_ids:
            if old in reg_ids and current in reg_ids:
                stale_ids_in_registry += 1
                stale_rows.append(
                    {
                        "pass_nr": m["pass_nr"],
                        "stale_id": old,
                        "current_id": current,
                        "name": m["names"][0] if m["names"] else "",
                    }
                )

    print(f"Stale IDs still in registry (handoff pattern): {stale_ids_in_registry}")
    print("=== First 20 stale registry entries ===")
    for row in stale_rows[:20]:
        print(row)

    out = "tmp/pass_nr_id_renumbers.csv"
    pd.DataFrame(stale_rows).to_csv(out, index=False, sep=";")
    print(f"Wrote {out} ({len(stale_rows)} rows)")


if __name__ == "__main__":
    main()
