#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.tournament_import.adapters.legacy_pdf_shared import pdf_text

PDF = Path(r"C:\tmp\bowlyzer\data\tournaments\input")
files = {
    2005: "bm2005_nb_he_erg.pdf",
    2006: "bm2006_nb_he_erg.pdf",
    2007: "bm2007_nb_h_erg.pdf",
    2008: "bm2008_nb_he_erg.pdf",
    2009: "bm2009_nb_he_erg.pdf",
    2010: "bm2010_nb_he_erg.pdf",
}
out = ROOT / "tmp" / "nbm_layout_samples.txt"
with out.open("w", encoding="utf-8") as f:
    for y, name in files.items():
        lines = [ln.strip() for ln in pdf_text(PDF / name).splitlines() if ln.strip()]
        f.write(f"=== {y} {name} ({len(lines)} lines) ===\n")
        for ln in lines[:45]:
            f.write(ln + "\n")
        f.write("\n")
print(out)
