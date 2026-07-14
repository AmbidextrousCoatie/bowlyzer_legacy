#!/usr/bin/env python3
"""Audit NBM parse vs publish counts; try all parsers on gap years."""
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

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
REGISTRY = {
    2005: ("bm2005_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2006: ("bm2006_nb_he_erg.pdf", "legacy_pdf_erg_2009"),
    2007: ("bm2007_nb_h_erg.pdf", "legacy_pdf_erg_edv_grid"),
    2008: ("bm2008_nb_he_erg.pdf", "legacy_pdf_erg_2009"),
    2009: ("bm2009_nb_he_erg.pdf", "legacy_pdf_erg_edv_grid"),
    2010: ("bm2010_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2011: ("bm2011_nbm_h_erg_neu.pdf", "legacy_pdf_erg_2009"),
    2012: ("bm2012_nbm_h_erg.pdf", "legacy_pdf_erg_2009"),
    2013: ("bm2013_nb_herren_erg.pdf", "legacy_pdf_erg_2016"),
    2014: ("bm2014_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2015: ("bm2015_nb_he_erg.pdf", "legacy_pdf_erg_2015"),
    2016: ("bm2016_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2017: ("bm2017_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2018: ("bm2018_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2019: ("bm2019_akt_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
}
PARSERS = {
    "legacy_pdf_erg_2009": parse_legacy_pdf_erg_2009,
    "legacy_pdf_erg_2012": parse_legacy_pdf_erg_2012,
    "legacy_pdf_erg_edv_grid": parse_legacy_pdf_erg_edv_grid,
    "legacy_pdf_erg_2015": parse_legacy_pdf_erg_2015,
    "legacy_pdf_erg_2016": parse_legacy_pdf_erg_2016,
}


def expected_from_pdf_ranks(pdf: Path) -> int:
    lines = [ln.strip() for ln in pdf_text(pdf).splitlines()]
    return expected_participant_count(collect_block_start_ranks(lines)) or 0


def parse_count(pdf: Path, fmt: str) -> tuple[int, str]:
    season_yy = int(re.search(r"bm(20\d{2})", pdf.name).group(1))  # type: ignore[union-attr]
    season = f"{(season_yy - 1) % 100:02d}/{season_yy % 100:02d}"
    entry = ImportEntry(
        id="x",
        format=fmt,
        source=str(pdf),
        options={"event_name": "Nordbayerische Meisterschaft", "season": season},
    )
    try:
        rows = PARSERS[fmt](pdf, entry)
        return len({r["Player ID"] for r in rows}), "ok"
    except Exception as exc:
        return 0, str(exc)[:60]


def main() -> None:
    manual = ROOT / "database/data/tournament_manual_postprocessed.csv"
    pub = pd.read_csv(manual, sep=";", dtype=str, usecols=["Season", "Event Name", "Player ID"])
    nbm = pub[pub["Event Name"].str.contains("Nordbayerische", case=False, na=False)]
    pub_by_season = nbm.groupby("Season")["Player ID"].nunique().to_dict()

    print("year  assigned           parsed  exp  published  status")
    gaps: list[int] = []
    for year in sorted(REGISTRY):
        fname, fmt = REGISTRY[year]
        pdf = PDF_DIR / fname
        season = f"{(year - 1) % 100:02d}/{year % 100:02d}"
        if not pdf.is_file():
            print(f"{year}  MISSING")
            continue
        parsed, note = parse_count(pdf, fmt)
        exp = expected_from_pdf_ranks(pdf)
        published = pub_by_season.get(season, 0)
        if parsed == 0 or (exp > 20 and parsed < exp * 0.85):
            status = "GAP"
            gaps.append(year)
        elif published < parsed * 0.85:
            status = "needs-import"
        else:
            status = "ok"
        print(f"{year}  {fmt:18s}  {parsed:4d}  {exp:4d}  {published:4d}  {status} {note if parsed==0 else ''}")

    if gaps:
        print("\n--- try all parsers on GAP years ---")
        for year in gaps:
            fname, _ = REGISTRY[year]
            pdf = PDF_DIR / fname
            print(f"\n{year} {pdf.name}:")
            for fmt in PARSERS:
                n, note = parse_count(pdf, fmt)
                print(f"  {fmt}: {n} {note if n==0 else ''}")


if __name__ == "__main__":
    main()
