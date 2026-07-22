# Published CSV mirrors (gitignored)

CSV exports of published Parquet datasets, written when you pass `--write-csv`
to `scripts/build_published_dataset.py`. Stems mirror `database/data/*.parquet`.

Not synced to VPS by default (`deploy.ps1 -SyncDatabase` uploads Parquet only).

Override with `BOWLYZER_PUBLISHED_CSV_DIR`.
