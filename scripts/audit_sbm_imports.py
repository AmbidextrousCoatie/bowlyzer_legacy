#!/usr/bin/env python3
"""Audit SBM parse vs publish counts; try all parsers on gap years."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from database.tournament_import.adapters.legacy_pdf_erg_2009 import parse_legacy_pdf_erg_2009
from database.tournament_import.adapters.legacy_pdf_erg_edv_grid import parse_legacy_pdf_erg_edv_grid
from database.tournament_import.adapters.legacy_pdf_erg_2015 import parse_legacy_pdf_erg_2015
from database.tournament_import.adapters.legacy_pdf_erg_2012 import parse_legacy_pdf_erg_2012
from database.tournament_import.adapters.legacy_pdf_erg_2016 import parse_legacy_pdf_erg_2016
from database.tournament_import.adapters.legacy_pdf_shared import pdf_text
from database.tournament_import.adapters.legacy_pdf_validation import (
    collect_block_start_ranks,
    expected_participant_count,
)
from database.tournament_import.config import ImportEntry
from database.tournament_import.source_registry import lookup_source_row

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
PARSERS = {
    "legacy_pdf_erg_2009": parse_legacy_pdf_erg_2009,
    "legacy_pdf_erg_2012": parse_legacy_pdf_erg_2012,
    "legacy_pdf_erg_2015": parse_legacy_pdf_erg_2015,
    "legacy_pdf_erg_2016": parse_legacy_pdf_erg_2016,
    "legacy_pdf_erg_edv_grid": parse_legacy_pdf_erg_edv_grid,
}


def sbm_pdf_for_year(year: int) -> Path | None:
    hits = sorted(PDF_DIR.glob(f"bm{year}*sb*.pdf"))
    herren = [
        path
        for path in hits
        if "_da_" not in path.name.lower() and "sen_" not in path.name.lower()
    ]
    if not herren:
        return None
    return max(herren, key=lambda path: path.stat().st_size)


def expected_from_pdf_ranks(pdf: Path) -> int:
    lines = [ln.strip() for ln in pdf_text(pdf).splitlines()]
    return expected_participant_count(collect_block_start_ranks(lines)) or 0


def parse_count(pdf: Path, fmt: str) -> tuple[int, str]:
    year = int(re.search(r"(20\d{2})", pdf.name).group(1))  # type: ignore[union-attr]
    season = f"{(year - 1) % 100:02d}/{year % 100:02d}"
    registry = lookup_source_row(pdf)
    options: dict = {"event_name": "Südbayerische Meisterschaft", "season": season}
    if registry and registry.event_name:
        options["event_name"] = registry.event_name
    if fmt == "legacy_pdf_erg_2016":
        options.setdefault("skip_line_patterns", ["Keine Teilnahme BM!"])
    entry = ImportEntry(
        id="x",
        format=fmt,
        source=str(pdf),
        options=options,
    )
    try:
        rows = PARSERS[fmt](pdf, entry)
        return len({row["Player ID"] for row in rows}), "ok"
    except Exception as exc:
        return 0, str(exc)[:60]


def main() -> None:
    manual = ROOT / "database/data/tournament_manual_postprocessed.csv"
    pub = pd.read_csv(manual, sep=";", dtype=str, usecols=["Season", "Event Name", "Player ID"])
    sbm = pub[pub["Event Name"].str.contains("Südbayerische", case=False, na=False)]
    pub_by_season = sbm.groupby("Season")["Player ID"].nunique().to_dict()

    print("year  file                         assigned           parsed  exp  published  best        status")
    gaps: list[tuple[int, Path]] = []
    best_by_year: dict[int, tuple[str, int]] = {}

    for year in range(2005, 2020):
        pdf = sbm_pdf_for_year(year)
        if pdf is None:
            print(f"{year}  MISSING PDF")
            continue
        registry = lookup_source_row(pdf)
        assigned = registry.format if registry else "?"
        season = f"{(year - 1) % 100:02d}/{year % 100:02d}"
        exp = expected_from_pdf_ranks(pdf)
        published = int(pub_by_season.get(season, 0))

        best_fmt = assigned
        best_n = 0
        for fmt in PARSERS:
            parsed, _ = parse_count(pdf, fmt)
            if parsed > best_n:
                best_n = parsed
                best_fmt = fmt

        assigned_n, note = parse_count(pdf, assigned) if assigned in PARSERS else (0, "unknown")
        best_by_year[year] = (best_fmt, best_n)

        if best_n == 0 or (exp > 20 and best_n < exp * 0.85):
            status = "GAP"
            gaps.append((year, pdf))
        elif published < best_n * 0.85:
            status = "needs-import"
        elif assigned != best_fmt:
            status = "wrong-parser"
        else:
            status = "ok"

        print(
            f"{year}  {pdf.name:30s}  {assigned:18s}  {assigned_n:4d}  {exp:4d}  {published:4d}  "
            f"{best_fmt:12s}  {status} {note if assigned_n == 0 else ''}"
        )

    if gaps:
        print("\n--- try all parsers on GAP years ---")
        for year, pdf in gaps:
            print(f"\n{year} {pdf.name}:")
            for fmt in PARSERS:
                parsed, note = parse_count(pdf, fmt)
                print(f"  {fmt}: {parsed} {note if parsed == 0 else ''}")


if __name__ == "__main__":
    main()
