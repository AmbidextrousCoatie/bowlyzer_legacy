#!/usr/bin/env python3
"""
Build ``database/config/player_name_normalization.json`` from an annotated
``report_names_annotated.csv`` (manual_rule + assigned name / assigned id).

Manual rules:
  - ``dbu_id`` — official display name in ``assigned name`` / ``assigned_name``
  - ``missing_id`` — name OK; official id in ``assigned_id`` / ``assigned id``
  - ``same_person`` / ``same person`` — multiple valid names for one player id

Unmarked rows with ``autoresolve_rule`` + ``proposed_name`` become autoresolve remappings.

Usage:
  uv run python scripts/import_player_name_normalization_from_audit.py report_names_annotated.csv
  uv run python scripts/import_player_name_normalization_from_audit.py report_names_annotated.csv --write
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

from data_access.player_id_name_normalization import normalize_player_id
from data_access.player_name_normalization import normalize_player_label
from data_access.player_name_normalization_config import DEFAULT_CONFIG_PATH

ISSUE_MULTI_NAME = "same_id_name_variants"
MANUAL_DBU_ID = "dbu_id"
MANUAL_MISSING_ID = "missing_id"
MANUAL_SAME_PERSON = {"same_person", "same person"}


def _field(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _remap_entry(
    *,
    player_name: str,
    player_id: str,
    assigned_name: str = "",
    assigned_id: str = "",
    source: str,
    note: str = "",
) -> Dict[str, Any]:
    replace: Dict[str, str] = {}
    if assigned_name:
        replace["player_name"] = assigned_name
    if assigned_id:
        replace["player_id"] = assigned_id
    entry: Dict[str, Any] = {
        "match": {"player_name": player_name, "player_id": player_id},
        "replace": replace,
        "source": source,
    }
    if note:
        entry["note"] = note
    return entry


def build_config_from_audit_csv(csv_path: Path) -> Dict[str, Any]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig", newline="")))
    name_rows = [r for r in rows if (r.get("issue_type") or "").strip() == ISSUE_MULTI_NAME]

    dbu_by_id: DefaultDict[str, List[dict]] = defaultdict(list)
    missing_id_rows: List[dict] = []
    same_person_by_id: DefaultDict[str, Set[str]] = defaultdict(set)
    manual_keys: Set[Tuple[str, str]] = set()

    for row in name_rows:
        name = normalize_player_label(row.get("player_name"))
        pid = normalize_player_id(row.get("player_id"))
        if not name or not pid:
            continue

        manual = _field(row, "manual_rule").lower()
        assigned_name = normalize_player_label(_field(row, "assigned name", "assigned_name"))
        assigned_id = normalize_player_id(_field(row, "assigned_id", "assigned id"))

        if manual in MANUAL_SAME_PERSON:
            same_person_by_id[pid].add(name)
            manual_keys.add((name, pid))
            continue

        if manual == MANUAL_DBU_ID:
            dbu_by_id[pid].append(
                {
                    "player_name": name,
                    "assigned_name": assigned_name,
                }
            )
            manual_keys.add((name, pid))
            continue

        if manual == MANUAL_MISSING_ID:
            if not assigned_id:
                raise ValueError(
                    f"missing_id row requires assigned_id: {row.get('player_name')!r} id={pid}"
                )
            missing_id_rows.append(
                {
                    "player_name": name,
                    "player_id": pid,
                    "assigned_id": assigned_id,
                }
            )
            manual_keys.add((name, pid))
            continue

    dbu_id_remappings: List[Dict[str, Any]] = []
    seen_remap: Set[Tuple[str, str, str, str]] = set()

    for pid, entries in sorted(dbu_by_id.items()):
        assigned_candidates = [e["assigned_name"] for e in entries if e.get("assigned_name")]
        if not assigned_candidates:
            continue
        canonical_name = assigned_candidates[0]
        if len(set(assigned_candidates)) > 1:
            raise ValueError(
                f"dbu_id group id={pid} has conflicting assigned name values: {assigned_candidates}"
            )
        for entry in entries:
            match_name = entry["player_name"]
            if match_name == canonical_name:
                continue
            key = (match_name, pid, canonical_name, "")
            if key in seen_remap:
                continue
            seen_remap.add(key)
            dbu_id_remappings.append(
                _remap_entry(
                    player_name=match_name,
                    player_id=pid,
                    assigned_name=canonical_name,
                    source=MANUAL_DBU_ID,
                )
            )

    missing_id_remappings: List[Dict[str, Any]] = []
    for entry in missing_id_rows:
        match_name = entry["player_name"]
        match_id = entry["player_id"]
        assigned_id = entry["assigned_id"]
        if match_id == assigned_id:
            continue
        key = (match_name, match_id, "", assigned_id)
        if key in seen_remap:
            continue
        seen_remap.add(key)
        missing_id_remappings.append(
            _remap_entry(
                player_name=match_name,
                player_id=match_id,
                assigned_id=assigned_id,
                source=MANUAL_MISSING_ID,
            )
        )

    same_person = [
        {
            "player_id": pid,
            "player_names": sorted(names, key=lambda n: n.lower()),
        }
        for pid, names in sorted(same_person_by_id.items())
        if len(names) >= 2
    ]

    autoresolve_remappings: List[Dict[str, Any]] = []
    for row in name_rows:
        name = normalize_player_label(row.get("player_name"))
        pid = normalize_player_id(row.get("player_id"))
        if not name or not pid:
            continue
        if _field(row, "manual_rule"):
            continue
        if (name, pid) in manual_keys:
            continue

        autoresolve = _field(row, "autoresolve_rule").lower()
        proposed_name = normalize_player_label(_field(row, "proposed_name"))
        if autoresolve not in {"majority", "name_reassembly"} or not proposed_name:
            continue
        if name == proposed_name:
            continue
        key = (name, pid, proposed_name, "")
        if key in seen_remap:
            continue
        seen_remap.add(key)
        autoresolve_remappings.append(
            _remap_entry(
                player_name=name,
                player_id=pid,
                assigned_name=proposed_name,
                source=autoresolve,
            )
        )

    return {
        "version": 1,
        "manual_resolutions": {
            "dbu_id": dbu_id_remappings,
            "missing_id": missing_id_remappings,
            "same_person": same_person,
        },
        "autoresolve_remappings": autoresolve_remappings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import player name normalization JSON from audit CSV.")
    parser.add_argument("csv", type=Path, help="Annotated report_names_annotated.csv")
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
        print(f"  dbu_id remappings: {len(config['manual_resolutions']['dbu_id'])}")
        print(f"  missing_id remappings: {len(config['manual_resolutions']['missing_id'])}")
        print(f"  same_person groups: {len(config['manual_resolutions']['same_person'])}")
        print(f"  autoresolve remappings: {len(config['autoresolve_remappings'])}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
