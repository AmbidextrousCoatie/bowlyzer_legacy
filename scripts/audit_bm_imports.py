#!/usr/bin/env python3
"""Audit BM Einzel (Herren + Damen) parse vs publish; try all parsers on gap years."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from database.tournament_import.adapters.legacy_bm_einz_xls_dual import LegacyBmEinzXlsDualAdapter
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
from database.tournament_import.source_registry import (
    event_name_for_category,
    load_source_registry,
    lookup_source_row,
)

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
PDF_PARSERS = {
    "legacy_pdf_erg_2009": parse_legacy_pdf_erg_2009,
    "legacy_pdf_erg_2012": parse_legacy_pdf_erg_2012,
    "legacy_pdf_erg_2015": parse_legacy_pdf_erg_2015,
    "legacy_pdf_erg_2016": parse_legacy_pdf_erg_2016,
    "legacy_pdf_erg_edv_grid": parse_legacy_pdf_erg_edv_grid,
}
CATEGORIES = {
    "M": "bayerische-einzel-herren",
    "D": "bayerische-einzel-frauen",
}
XLS_ADAPTER = LegacyBmEinzXlsDualAdapter()


def registry_source_for(year: int, gender: str) -> tuple[Path | None, str, str]:
    category_id = CATEGORIES[gender]
    rows = [
        row
        for row in load_source_registry()
        if row.enabled
        and row.calendar_year == year
        and row.category_id == category_id
    ]
    if not rows:
        return None, "?", "?"
    row = rows[0]
    source = PDF_DIR / row.file_basename
    if not source.is_file():
        source = ROOT / "database" / "input" / row.file_basename
    if not source.is_file() and row.file_path:
        alt = PDF_DIR / Path(row.file_path).name
        source = alt if alt.is_file() else source
    return (source if source.is_file() else None), row.format, row.file_basename


def expected_from_pdf_ranks(pdf: Path) -> int:
    lines = [ln.strip() for ln in pdf_text(pdf).splitlines()]
    return expected_participant_count(collect_block_start_ranks(lines)) or 0


def parse_pdf(pdf: Path, fmt: str, *, season: str, event_name: str) -> tuple[int, str]:
    options: dict = {"event_name": event_name, "season": season}
    if fmt == "legacy_pdf_erg_2016":
        options.setdefault("skip_line_patterns", ["Keine Teilnahme BM!"])
    entry = ImportEntry(id="x", format=fmt, source=str(pdf), options=options)
    try:
        rows = PDF_PARSERS[fmt](pdf, entry)
        return len({row["Player ID"] for row in rows}), "ok"
    except Exception as exc:
        return 0, str(exc)[:60]


def parse_xls(xls: Path, *, season: str, event_name: str, sheet: str) -> tuple[int, str]:
    entry = ImportEntry(
        id="x",
        format="legacy_bm_einz_xls_dual",
        source=str(xls),
        options={
            "sheet": sheet,
            "season": season,
            "event_name": event_name,
            "calendar_year": int(season.split("/")[1]) + 2000 if "/" in season else 2007,
        },
    )
    try:
        rows = XLS_ADAPTER.parse(xls, entry)
        return len({row["Player ID"] for row in rows}), "ok"
    except Exception as exc:
        return 0, str(exc)[:60]


def published_count(pub_by_event: dict[str, int], season: str, event_name: str) -> int:
    return int(pub_by_event.get((season, event_name), 0))


def main() -> None:
    manual = ROOT / "database/data/tournament_manual_postprocessed.csv"
    pub = pd.read_csv(manual, sep=";", dtype=str, usecols=["Season", "Event Name", "Player ID"])
    bm = pub[pub["Event Name"].str.contains("Bayerische Meisterschaft Einzel", case=False, na=False)]
    pub_by_event = bm.groupby(["Season", "Event Name"])["Player ID"].nunique().to_dict()

    print("year gender file                              assigned           parsed  exp  published  best        status")
    gaps: list[tuple[int, str, Path | None, str]] = []

    for year in range(2005, 2020):
        season = f"{(year - 1) % 100:02d}/{year % 100:02d}"
        for gender, label in (("M", "H"), ("D", "D")):
            source, assigned, basename = registry_source_for(year, gender)
            category_id = CATEGORIES[gender]
            event_name = event_name_for_category(category_id, year)

            if source is None:
                print(f"{year}  {label}   MISSING {basename:30s}  {'?':18s}     0     0     0  {'?':12s}  MISSING")
                continue

            if source.suffix.lower() in {".xls", ".xlsx"}:
                sheet = "Herren" if gender == "M" else "Damen"
                parsed, note = parse_xls(source, season=season, event_name=event_name, sheet=sheet)
                exp = 0
                best_fmt = assigned
                best_n = parsed
                published = published_count(pub_by_event, season, event_name)
                status = "ok" if published >= best_n * 0.85 and best_n > 0 else "needs-import"
                if best_n == 0:
                    status = "GAP"
                    gaps.append((year, label, source, assigned))
                print(
                    f"{year}  {label}   {basename:30s}  {assigned:18s}  {parsed:4d}  {exp:4d}  {published:4d}  "
                    f"{best_fmt:12s}  {status} {note if parsed == 0 else ''}"
                )
                continue

            exp = expected_from_pdf_ranks(source)
            published = published_count(pub_by_event, season, event_name)
            assigned_n, note = (
                parse_pdf(source, assigned, season=season, event_name=event_name)
                if assigned in PDF_PARSERS
                else (0, "unknown")
            )
            best_fmt, best_n = assigned, assigned_n
            for fmt in PDF_PARSERS:
                parsed, _ = parse_pdf(source, fmt, season=season, event_name=event_name)
                if parsed > best_n:
                    best_n, best_fmt = parsed, fmt

            if best_n == 0 or (exp > 20 and best_n < exp * 0.85):
                status = "GAP"
                gaps.append((year, label, source, assigned))
            elif published < best_n * 0.85:
                status = "needs-import"
            elif assigned != best_fmt:
                status = "wrong-parser"
            else:
                status = "ok"

            print(
                f"{year}  {label}   {basename:30s}  {assigned:18s}  {assigned_n:4d}  {exp:4d}  {published:4d}  "
                f"{best_fmt:12s}  {status} {note if assigned_n == 0 else ''}"
            )

    if gaps:
        print("\n--- try all parsers on GAP entries ---")
        for year, gender, source, _assigned in gaps:
            if source is None or source.suffix.lower() in {".xls", ".xlsx"}:
                continue
            season = f"{(year - 1) % 100:02d}/{year % 100:02d}"
            category_id = CATEGORIES["M" if gender == "H" else "D"]
            event_name = event_name_for_category(category_id, year)
            print(f"\n{year} {gender} {source.name}:")
            for fmt in PDF_PARSERS:
                parsed, note = parse_pdf(source, fmt, season=season, event_name=event_name)
                print(f"  {fmt}: {parsed} {note if parsed == 0 else ''}")


if __name__ == "__main__":
    main()
