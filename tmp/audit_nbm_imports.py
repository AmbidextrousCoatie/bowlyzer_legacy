"""Audit NBM parse vs publish counts."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from database.tournament_import.adapters.legacy_pdf_erg_2009 import parse_legacy_pdf_erg_2009
from database.tournament_import.adapters.legacy_pdf_erg_2012 import parse_legacy_pdf_erg_2012
from database.tournament_import.adapters.legacy_pdf_erg_2016 import parse_legacy_pdf_erg_2016
from database.tournament_import.adapters.legacy_pdf_shared import pdf_text
from database.tournament_import.config import ImportEntry

PDF_DIR = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
REGISTRY = {
    2005: ("bm2005_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2006: ("bm2006_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2007: ("bm2007_nb_h_erg.pdf", "legacy_pdf_erg_2009"),
    2008: ("bm2008_nb_he_erg.pdf", "legacy_pdf_erg_2009"),
    2009: ("bm2009_nb_he_erg.pdf", "legacy_pdf_erg_2009"),
    2010: ("bm2010_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2011: ("bm2011_nbm_h_erg_neu.pdf", "legacy_pdf_erg_2009"),
    2012: ("bm2012_nbm_h_erg.pdf", "legacy_pdf_erg_2009"),
    2013: ("bm2013_nb_herren_erg.pdf", "legacy_pdf_erg_2016"),
    2014: ("bm2014_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2015: ("bm2015_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2016: ("bm2016_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2017: ("bm2017_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2018: ("bm2018_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
    2019: ("bm2019_akt_nb_he_erg.pdf", "legacy_pdf_erg_2016"),
}
PARSERS = {
    "legacy_pdf_erg_2009": parse_legacy_pdf_erg_2009,
    "legacy_pdf_erg_2012": parse_legacy_pdf_erg_2012,
    "legacy_pdf_erg_2016": parse_legacy_pdf_erg_2016,
}


def expected_comma_names(pdf: Path) -> int:
    lines = [ln.strip() for ln in pdf_text(pdf).splitlines() if ln.strip()]
    return sum(
        1
        for ln in lines
        if "," in ln and re.match(r"^[A-Za-z]", ln) and "Meisterschaft" not in ln
    )


def main() -> None:
    parq = Path("database/data/tournaments_postprocessed.parquet")
    pub = pd.read_parquet(parq)
    nbm = pub[pub["Event Name"].str.contains("Nordbayerische", case=False, na=False)]
    pub_by_season = nbm.groupby("Season")["Player ID"].nunique().to_dict()

    print("year  fmt      parsed  exp_comma  published  status")
    for year in sorted(REGISTRY):
        fname, fmt = REGISTRY[year]
        pdf = PDF_DIR / fname
        season = f"{(year-1) % 100:02d}/{year % 100:02d}"
        if not pdf.is_file():
            print(f"{year}  MISSING FILE")
            continue
        entry = ImportEntry(
            id="x",
            format=fmt,
            source=str(pdf),
            options={"event_name": "Nordbayerische Meisterschaft", "season": season},
        )
        try:
            rows = PARSERS[fmt](pdf, entry)
            parsed = len({r["Player ID"] for r in rows})
            status = "ok" if parsed >= expected_comma_names(pdf) * 0.9 else "partial"
            if parsed == 0:
                status = "fail"
        except Exception as exc:
            parsed = 0
            status = f"fail: {exc}"[:60]
        exp = expected_comma_names(pdf)
        published = pub_by_season.get(season, 0)
        print(f"{year}  {fmt:18s}  {parsed:4d}  {exp:4d}  {published:4d}  {status}")


if __name__ == "__main__":
    main()
