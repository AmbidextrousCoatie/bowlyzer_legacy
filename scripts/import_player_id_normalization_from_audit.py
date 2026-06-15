#!/usr/bin/env python3
"""
Build ``database/config/player_id_name_normalization.json`` from an annotated
``player_id_name_conflicts.csv`` (manual_rule + assigned_id + autoresolve columns).

Usage:
  uv run python scripts/import_player_id_normalization_from_audit.py report_annotated.csv
  uv run python scripts/import_player_id_normalization_from_audit.py report_annotated.csv --write
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.player_id_name_normalization import (
    DEFAULT_CONFIG_PATH,
    normalize_player_id,
    normalize_player_name,
)

ISSUE_SAME_NAME = "same_name_different_ids"
ISSUE_SAME_ID_NAME_VARIANTS = "same_id_name_variants"


def _remap_entry(
    *,
    player_name: str,
    player_id: str,
    assigned_id: str,
    source: str,
    note: str = "",
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "match": {"player_name": player_name, "player_id": player_id},
        "replace": {"player_id": assigned_id},
        "source": source,
    }
    if note:
        entry["note"] = note
    return entry


def build_config_from_audit_csv(csv_path: Path) -> Dict[str, Any]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    same_name = [r for r in rows if (r.get("issue_type") or "").strip() == ISSUE_SAME_NAME]
    same_id_variants = [
        r for r in rows if (r.get("issue_type") or "").strip() == ISSUE_SAME_ID_NAME_VARIANTS
    ]

    autoresolve_remappings: List[Dict[str, Any]] = []
    seen_remap: Set[Tuple[str, str, str]] = set()

    dbu_by_name: DefaultDict[str, List[dict]] = defaultdict(list)
    different_by_name: DefaultDict[str, Set[str]] = defaultdict(set)

    def _add_autoresolve_remap(
        *,
        player_name: str,
        player_id: str,
        assigned_id: str,
        source: str,
    ) -> None:
        key = (player_name, player_id, assigned_id)
        if key in seen_remap:
            return
        seen_remap.add(key)
        autoresolve_remappings.append(
            _remap_entry(
                player_name=player_name,
                player_id=player_id,
                assigned_id=assigned_id,
                source=source,
            )
        )

    for row in same_id_variants:
        name = normalize_player_name(row.get("player_name"))
        pid = normalize_player_id(row.get("player_id"))
        autoresolve = (row.get("autoresolve_rule") or "").strip().lower()
        proposed = normalize_player_id(row.get("proposed_id"))
        if autoresolve == "placeholder" and proposed and name and pid:
            _add_autoresolve_remap(
                player_name=name,
                player_id=pid,
                assigned_id=proposed,
                source=autoresolve,
            )

    for row in same_name:
        name = normalize_player_name(row.get("player_name"))
        pid = normalize_player_id(row.get("player_id"))
        if not name or not pid:
            continue

        manual = (row.get("manual_rule") or "").strip().lower()
        assigned = normalize_player_id(row.get("assigned_id") or row.get("assigned_ID"))
        autoresolve = (row.get("autoresolve_rule") or "").strip().lower()
        proposed = normalize_player_id(row.get("proposed_id"))

        if manual == "different_person":
            different_by_name[name].add(pid)
            continue

        if manual == "dbu_id":
            dbu_by_name[name].append({"player_id": pid, "assigned_id": assigned})
            continue

        if autoresolve in {"majority", "placeholder"} and proposed:
            _add_autoresolve_remap(
                player_name=name,
                player_id=pid,
                assigned_id=proposed,
                source=autoresolve,
            )

    dbu_id_remappings: List[Dict[str, Any]] = []
    for name, entries in sorted(dbu_by_name.items()):
        canonical_candidates = [
            normalize_player_id(e.get("assigned_id"))
            for e in entries
            if normalize_player_id(e.get("assigned_id"))
        ]
        if not canonical_candidates:
            raise ValueError(f"dbu_id group {name!r} has no assigned_id on any row")
        canonical = canonical_candidates[0]
        if len(set(canonical_candidates)) > 1:
            raise ValueError(
                f"dbu_id group {name!r} has conflicting assigned_id values: {canonical_candidates}"
            )
        for entry in entries:
            pid = entry["player_id"]
            if pid == canonical:
                continue
            key = (name, pid, canonical)
            if key in seen_remap:
                continue
            seen_remap.add(key)
            dbu_id_remappings.append(
                _remap_entry(
                    player_name=name,
                    player_id=pid,
                    assigned_id=canonical,
                    source="dbu_id",
                )
            )

    different_person = [
        {
            "player_name": name,
            "player_ids": sorted(ids, key=lambda x: (len(x), x)),
        }
        for name, ids in sorted(different_by_name.items())
        if ids
    ]

    return {
        "version": 2,
        "manual_resolutions": {
            "dbu_id": dbu_id_remappings,
            "different_person": different_person,
        },
        "autoresolve_remappings": autoresolve_remappings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import player ID normalization JSON from audit CSV.")
    parser.add_argument("csv", type=Path, help="Annotated player_id_name_conflicts.csv")
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Write {DEFAULT_CONFIG_PATH}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Output JSON path",
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 2

    config = build_config_from_audit_csv(csv_path)
    payload = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        out = args.output.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Wrote {out}")
        print(
            f"  dbu_id remappings: {len(config['manual_resolutions']['dbu_id'])}",
        )
        print(
            f"  different_person groups: {len(config['manual_resolutions']['different_person'])}",
        )
        print(f"  autoresolve remappings: {len(config['autoresolve_remappings'])}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
