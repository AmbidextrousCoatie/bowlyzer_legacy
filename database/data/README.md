# Published data (`database/data/`)

Runtime Parquet/CSV/JSON for the Flask app. VPS bind-mount: see [`../README.md`](../README.md).

**Full operator guide:** [`../../docs/DATA_PIPELINE.md`](../../docs/DATA_PIPELINE.md).

## Parquet-first

The app prefers `*.parquet` when present (config paths still use historical `*.csv` names).

| Dataset | Logical name |
|---------|----------------|
| League | `league_results_merged` |
| Tournaments | `tournaments_postprocessed` |
| Players | `players_registry` |
| Clubs | `clubs_registry` |
| Affiliations | `affiliation_index` |

## Build

Legacy scrape league data is **included by default** when `legacy_scrape_extracted.csv` exists under the work dir. Opt out with `--skip-legacy-scrape`.

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

After club / player identity edits, always rebuild caches (and restart Flask) — publish alone does not refresh API disk cache.

## Deploy

```powershell
.\deploy\deploy.ps1 -SyncDatabase
.\deploy\deploy.ps1 -SyncDatabase -SyncCache
```

Manifest: `runs/latest.json`. Artifact contract details: [`ARTIFACTS.md`](ARTIFACTS.md) (prefer DATA_PIPELINE for day-to-day use).
