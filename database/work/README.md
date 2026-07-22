# Pipeline work data (gitignored)

All intermediate pipeline artifacts live here: legacy scrape extracts, tournament
staging CSVs, GF export tables, historical league extracts, audit reports, and
raw source workbooks.

**Do not deploy to VPS.** Only `database/data/*.parquet` (+ config JSON) sync.

## Layout

```text
database/work/
  legacy_scrape/          # bowling-bayern.de scrape tree + legacy_scrape_extracted.csv
  league/                 # historical extract, dedupe reports, analysis log
  tournaments/
    input/                # legacy PDF intake (flat *.pdf folder)
    staging/              # per-import *postprocessed.csv before publish merge
    tournament_manual_postprocessed.csv
  gf/                     # GF table exports (was database/input/gf_tables_export/)
  pipeline/               # GF league pipeline legacy_out (was database/pipeline/)
  raw/                    # xlsx workbooks, static liga CSV snapshots
  audits/                 # player-id conflicts, data-quality reports
  tmp/                    # scratch
```

Override with `BOWLYZER_WORK_DATA_DIR` if needed.

Migrate existing files from the old layout:

```powershell
.\scripts\migrate_data_layout.ps1
```
