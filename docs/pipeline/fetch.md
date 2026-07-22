# Pipeline: fetch (intake)

See also [`../DATA_PIPELINE.md`](../DATA_PIPELINE.md).

## League

| Source | Seasons (typical) | How |
|--------|-------------------|-----|
| Legacy web scrape | 08/09–18/19 | `scripts/scrape_legacy_liga.py` → convert/process → `legacy_scrape_extracted.csv` |
| Historical Excel | 19/20–24/25 | `scripts/data/extract_excel_data.py` → `historical_league_results.csv` |
| GF API | current | `scripts/run_gf_pipeline.py --mode incremental\|full` → `pipeline/.../legacy_out/latest.csv` |

Work dir (default): `BOWLYZER_WORK_DATA_DIR` (e.g. `C:\tmp\bowlyzer\data`).

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/scrape_legacy_liga.py --season 2010-11
# then convert + process under extract_excel_data (see Excel_Extraction.md)

uv run python scripts/run_gf_pipeline.py --mode incremental
```

Tool catalog: [`../Excel_Extraction.md`](../Excel_Extraction.md).

## Tournaments

| Source | How |
|--------|-----|
| GF tables | `scripts/export_gf_tables.py` + postprocess → `gf_tournaments_*__combined_postprocessed.csv` |
| Legacy PDFs | `scripts/scrape_legacy_tournaments.py` → `scripts/import_tournaments.py` |
| Clubmeisterschaft XLSX | Dropbox / VPS — [`../CLUBMEISTERSCHAFT_AUTO_IMPORT.md`](../CLUBMEISTERSCHAFT_AUTO_IMPORT.md) |

## Identity (Aktive Mitglieder)

Rangliste workbooks under the legacy scrape tree feed:

```powershell
uv run python scripts/build_players_registry.py --write-csv
uv run python scripts/build_affiliation_registry.py --write-csv
```

(Also run automatically as part of `build_published_dataset` unless `--skip-players-registry`.)
