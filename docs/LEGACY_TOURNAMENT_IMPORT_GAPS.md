# Legacy tournament import status (NBM / SBM / BM)

Last updated after BM 2005–2019 import pass (Jul 2026).

## Nordbayerische Meisterschaft (NBM)

| Year | File | Parser | Parsed | Published | Status |
|------|------|--------|--------|-----------|--------|
| 2005 | `bm2005_nb_he_erg.pdf` | — | 0 | 0 | **GAP** — partial totals layout (Finale games only / Vor+Zw partial); needs new parser |
| 2006 | `bm2006_nb_he_erg.pdf` | `legacy_pdf_erg_2009` | 119 | 119 | ok |
| 2007 | `bm2007_nb_h_erg.pdf` | `legacy_pdf_erg_edv_grid` | 130 | 130 | ok |
| 2008 | `bm2008_nb_he_erg.pdf` | `legacy_pdf_erg_2009` | 113 | 113 | ok |
| 2009 | `bm2009_nb_he_erg.pdf` | `legacy_pdf_erg_edv_grid` | 148 | 148 | ok |
| 2010 | `bm2010_nb_he_erg.pdf` | — | 0 | 0 | **GAP** — wide-grid layout; no parser yet |
| 2011 | `bm2011_nbm_h_erg_neu.pdf` | `legacy_pdf_erg_2009` | 146 | 146 | ok |
| 2012 | `bm2012_nbm_h_erg.pdf` | `legacy_pdf_erg_2009` | 108 | 108 | ok |
| 2013 | `bm2013_nb_herren_erg.pdf` | `legacy_pdf_erg_2016` | 96 | 96 | ok |
| 2014 | `bm2014_nb_he_erg.pdf` | `legacy_pdf_erg_2016` | 92 | 92 | ok |
| 2015 | `bm2015_nb_he_erg.pdf` | `legacy_pdf_erg_2015` | 95 | 95 | ok |
| 2016–2019 | various | `legacy_pdf_erg_2016` | 84–99 | match | ok |

**Still to import:** 2005, 2010 (new parsers required).

Audit: `uv run python scripts/audit_nbm_imports.py`

---

## Südbayerische Meisterschaft (SBM)

| Year | File | Parser | Parsed | Published | Status |
|------|------|--------|--------|-----------|--------|
| 2005 | `bm2005_sb_he_erg.pdf` | — | 0 | 108* | **GAP** — inline dual-series layout (Vor block + Zw block per player); *108 stale rows in manual CSV from prior bad import — strip on re-import |
| 2006 | `bm2006_sb_he_erg.pdf` | `legacy_pdf_erg_2009` | 126 | 126 | ok |
| 2007 | `bm2007_sb_h_erg.pdf` | `legacy_pdf_erg_2016` | 114 | 114 | ok (registry assigns 2016; 2009 parser yields 125 — minor parser mismatch) |
| 2008 | `bm2008_sb_he_erg.pdf` | `legacy_pdf_erg_2009` | 122 | 122 | ok |
| 2009–2011 | various | `legacy_pdf_erg_2009` | 119–132 | match | ok |
| 2012 | `bm2012_sbm_h_erg.pdf` | `legacy_pdf_erg_2012` | 72 | 72 | ok |
| 2013–2014, 2016–2019 | various | `legacy_pdf_erg_2016` | 107–120 | match | ok |
| 2015 | `bm2015_sb_he_erg.pdf` | — | 0 | 0 | **GAP** — wide horizontal Sp1–18 grid |

**Still to import:** 2005, 2015 (new parsers required; 2005 also needs stale-row cleanup).

Audit: `uv run python scripts/audit_sbm_imports.py`

---

## Bayerische Meisterschaft Einzel (BM Herren + Damen)

| Year | Gender | File | Parser | Parsed | Published | Status |
|------|--------|------|--------|--------|-----------|--------|
| 2005 | H | `bm2005_einz_h_erg_fi.pdf` | — | 0 | 0 | **GAP** — inline dual-series layout |
| 2005 | D | `bm2005_einz_d_erg_fi.pdf` | — | 0 | 0 | **GAP** — inline dual-series layout |
| 2006 | H/D | `bm2006_einz_erg_he.pdf` / `bm2006_sb_da_erg.pdf` | `legacy_pdf_erg_2009` | 79 / 42 | match | ok |
| 2007 | H | `bm2007_einz_erg.xls` (Herren sheet) | `legacy_bm_einz_xls_dual` | 78 | 78 | ok |
| 2007 | D | `bm2007_einz_erg.xls` (Damen sheet) | `legacy_bm_einz_xls_dual` | 39 | 39 | ok |
| 2008 | H | `bm2008_einz_he_erg.pdf` | `legacy_pdf_erg_2009` | 85 | 85 | ok |
| 2008 | D | `bm2008_sb_da_erg.pdf` | — | 0 | 0 | **GAP** — ranked grid without comma names |
| 2009 | H/D | various | `legacy_pdf_erg_2009` | 72 / 43 | match | ok |
| 2010–2011 | H/D | various | `legacy_pdf_erg_2009` | match | match | ok |
| 2012 | H/D | various | `legacy_pdf_erg_2016` / `2012` | 70 / 27 | match | ok |
| 2013 | H/D | various | `legacy_pdf_erg_2009` | 43 / 59 | match | ok |
| 2014 | H | `bm2014_akt_einz_he_erg.pdf` | — | 0 | 0 | **GAP** — no parser extracts player blocks |
| 2014 | D | `bm2014_akt_einz_da_erg.pdf` | `legacy_pdf_erg_2009` | 16 | 16 | ok (partial field — ~16 players) |
| 2015 | H | `bm2015_einz_he_erg.pdf` | `legacy_pdf_erg_2016` | 75 | 75 | ok |
| 2015 | D | `bm2015_einz_da_erg.pdf` | — | 0 | 0 | **GAP** — wide horizontal grid |
| 2016–2019 | H/D | various | `legacy_pdf_erg_2016` | 37–87 | match | ok |

**Still to import:** 2005 H/D, 2008 D, 2014 H, 2015 D (new parsers required).

Audit: `uv run python scripts/audit_bm_imports.py`

Import Herren + Damen PDFs:

```powershell
uv run python scripts/import_tournaments.py --tournament bm,bm_f --first-year 2004 --last-year 2018
```

2007 uses dual-sheet XLS (not PDF):

```powershell
uv run python scripts/import_tournaments.py --id legacy-bm-2007-xls-herren --id legacy-bm-2007-xls-damen
```

---

## Summary — parsers still needed

| Tournament | Years | Layout issue |
|------------|-------|--------------|
| NBM | 2005, 2010 | partial totals / wide grid |
| SBM | 2005, 2015 | inline dual-series / wide Sp1–18 grid |
| BM | 2005 H+D, 2008 D, 2014 H, 2015 D | dual-series / ranked grid / block layout / wide grid |
