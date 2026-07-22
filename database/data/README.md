# Published data (`database/data/`)

Runtime **Parquet** + config JSON + publish manifests for the Flask app. VPS bind-mount: see [`../README.md`](../README.md).

**Full operator guide:** [`../../docs/DATA_PIPELINE.md`](../../docs/DATA_PIPELINE.md).

## Layout (Parquet-first)

| Location | Contents |
|----------|----------|
| `database/data/*.parquet` | Published datasets (deployed to VPS) |
| `database/data/runs/` | Publish manifests (`latest.json`) |
| `database/data/*.json` | KO config, stage definitions |
| `database/published_csv/` | CSV mirrors (`--write-csv`; local only, gitignored) |
| `database/work/` | All pipeline intermediates (gitignored) |

| Dataset | Parquet |
|---------|---------|
| League | `league_results_merged.parquet` |
| Tournaments | `tournaments_postprocessed.parquet` |
| Players | `players_registry.parquet` |
| Clubs | `clubs_registry.parquet` |
| Affiliations | `affiliation_index.parquet` |

## Build

Legacy scrape league data is **included by default** when `legacy_scrape_extracted.csv` exists under `database/work/legacy_scrape/`.

```powershell
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

CSV mirrors land in `database/published_csv/` when `--write-csv` is set.

Migrate from the old scattered layout:

```powershell
.\scripts\migrate_data_layout.ps1
```

## Deploy

```powershell
.\deploy\deploy.ps1 -SyncDatabase
.\deploy\deploy.ps1 -SyncDatabase -SyncCache
```

Manifest: `runs/latest.json`. Artifact contract: [`ARTIFACTS.md`](ARTIFACTS.md).
