#!/usr/bin/env python3
"""
Build ``players_registry.parquet`` from scraped *Aktive Mitglieder* workbooks,
then merge normalization JSON updates on top.

By default the published registry is the source of truth: later seasons refresh
DBU canonical names; config changes add aliases and may upgrade canonical only
from trusted sources (``dbu_id``, manual, ``same_person``).

Use ``--from-scratch`` only for a deliberate full rebuild from configs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.players_registry import build_and_publish_players_registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Also write players_registry.csv sidecar",
    )
    parser.add_argument(
        "--from-scratch",
        action="store_true",
        help="Replace registry entirely from configs (not the normal publish path)",
    )
    args = parser.parse_args()

    summary = build_and_publish_players_registry(
        write_csv=args.write_csv,
        from_scratch=args.from_scratch,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
