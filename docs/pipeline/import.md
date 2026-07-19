# Pipeline: import

See also [`../DATA_PIPELINE.md`](../DATA_PIPELINE.md).

## Tournament PDF / registry import

```powershell
uv run python scripts/import_tournaments.py --help
# Typical: resolve sources from tournament source registry + flat PDF input dir
```

Gaps / format notes: [`../LEGACY_TOURNAMENT_IMPORT_GAPS.md`](../LEGACY_TOURNAMENT_IMPORT_GAPS.md).

After import, outputs feed `tournament_manual_postprocessed.csv` (or format-specific postprocessed CSVs that the publish merge includes). Then:

```powershell
uv run python scripts/build_published_dataset.py --job tournament --write-csv
```

## Clubmeisterschaft (ongoing)

VPS Dropbox → XLSX → parquet publish: [`../CLUBMEISTERSCHAFT_AUTO_IMPORT.md`](../CLUBMEISTERSCHAFT_AUTO_IMPORT.md).

```powershell
uv run python scripts/publish_tournament_parquet.py
```

## Club alias import (CLI)

UI save already merges into `club_mapping.csv`. From a staging CSV:

```powershell
uv run python scripts/import_club_mapping_from_resolved.py --write
uv run python scripts/build_clubs_registry.py --write-csv
```

## GF column contract

Legacy flat CSV shape: [`../../database/input/INPUT_TO_LEGACY_CSV_MAPPING.md`](../../database/input/INPUT_TO_LEGACY_CSV_MAPPING.md).
