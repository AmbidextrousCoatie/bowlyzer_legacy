#!/usr/bin/env python3
"""Compare registry parser assignments vs heuristic PDF layout detection.

Use this to decide which ``format`` value to set in
``database/config/tournament_source_registry.csv`` for each PDF.

Registry ``format`` is authoritative at import time; detection here is advisory only.

Usage:
  uv run python scripts/audit_tournament_pdf_formats.py
  uv run python scripts/audit_tournament_pdf_formats.py --mismatch-only
  uv run python scripts/audit_tournament_pdf_formats.py --input-dir C:\\tmp\\bowlyzer\\data\\tournaments\\input
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.paths import tournaments_input_dir
from database.tournament_import.legacy_pdf_format import (
    LEGACY_PDF_FORMAT_IDS,
    detect_legacy_pdf_format,
)
from database.tournament_import.source_registry import (
    DEFAULT_REGISTRY_PATH,
    TournamentSourceRow,
    load_source_registry,
)


def _resolve_pdf_path(row: TournamentSourceRow, input_dir: Path) -> Path | None:
    if row.file_path:
        candidate = (input_dir / row.file_path).resolve()
        if candidate.is_file():
            return candidate
        alt = Path(row.file_path)
        if alt.is_file():
            return alt.resolve()
    candidate = (input_dir / row.file_basename).resolve()
    if candidate.is_file():
        return candidate
    return None


def audit_rows(
    rows: list[TournamentSourceRow],
    input_dir: Path,
    *,
    mismatch_only: bool,
) -> int:
    mismatches = 0
    missing_pdf = 0
    missing_format = 0

    print(
        f"{'basename':<36} {'season':<6} {'assigned':<22} {'detected':<22} status",
        flush=True,
    )
    print("-" * 100, flush=True)

    for row in sorted(rows, key=lambda item: (item.calendar_year, item.file_basename)):
        if not row.enabled:
            continue
        assigned = (row.format or "").strip()
        if not assigned:
            missing_format += 1
            if not mismatch_only:
                print(
                    f"{row.file_basename:<36} {row.season:<6} {'':<22} {'':<22} missing format",
                    flush=True,
                )
            continue

        pdf_path = _resolve_pdf_path(row, input_dir)
        if pdf_path is None:
            missing_pdf += 1
            if not mismatch_only:
                print(
                    f"{row.file_basename:<36} {row.season:<6} {assigned:<22} {'':<22} pdf missing",
                    flush=True,
                )
            continue

        detected = detect_legacy_pdf_format(pdf_path)
        if assigned == detected:
            status = "ok"
        else:
            status = "MISMATCH"
            mismatches += 1

        if mismatch_only and status == "ok":
            continue

        print(
            f"{row.file_basename:<36} {row.season:<6} {assigned:<22} {detected:<22} {status}",
            flush=True,
        )

    print("-" * 100, flush=True)
    print(
        f"Known formats: {', '.join(sorted(LEGACY_PDF_FORMAT_IDS))}",
        flush=True,
    )
    print(
        f"Summary: mismatches={mismatches} missing_format={missing_format} missing_pdf={missing_pdf}",
        flush=True,
    )
    return mismatches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Registry CSV path",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="PDF input directory (default: work_dir/tournaments/input)",
    )
    parser.add_argument(
        "--mismatch-only",
        action="store_true",
        help="Only print rows where assigned format != detected format",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_dir = (args.input_dir or tournaments_input_dir()).resolve()
    rows = load_source_registry(args.registry)
    if not rows:
        print(f"No registry rows in {args.registry}", file=sys.stderr)
        return 1
    mismatches = audit_rows(rows, input_dir, mismatch_only=args.mismatch_only)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
