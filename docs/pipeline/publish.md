# Pipeline: publish & cache

See also [`../DATA_PIPELINE.md`](../DATA_PIPELINE.md).

## Orchestrator

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv
```

### Defaults (important)

| Behavior | Default |
|----------|---------|
| Include legacy scrape league CSV | **Yes** (when file exists) |
| Opt out of scrape | `--skip-legacy-scrape` |
| `--with-legacy-scrape` | Deprecated no-op |
| Auto `players_registry` + affiliation before league/tournament | **Yes** (`--skip-players-registry` to skip) |
| Rebuild `clubs_registry` after league | **Yes** (`--skip-clubs-registry` to skip) |
| Extend affiliation from league (pass 2) | **Yes** after league job |
| Apply `team_name_normalization.json` during league merge | **Yes** |
| Apply `club_mapping.csv` / `clubs_registry` on tournament Club | **Yes** during tournament normalize |
| Player hybrid single-file artifact | Deprecated (`--with-player-hybrid`) |

### Useful flags

| Flag | Meaning |
|------|---------|
| `--write-csv` | Also write CSV sidecars next to Parquet |
| `--force-publish` | Publish despite blocking audits |
| `--skip-female-league-audit` | Skip Damen-collapse gate on scrape |
| `--tournament-affiliation-reporting club\|verein` | Reporting mode for tournament Club column |

Manifest: `database/data/runs/latest.json`.

## Cache

```powershell
# Full invalidate + warm (after identity / club / full publish)
uv run python scripts/rebuild_league_caches.py --all-published --workers 8

# Incremental warm (new weeks; unchanged seasons keep disk entries)
uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8
```

Published DB ids: `db_real_merged` (league), tournament GF DB, optional player hybrid.

## Deploy

```powershell
.\deploy\deploy.ps1 -SyncDatabase
.\deploy\deploy.ps1 -SyncDatabase -SyncCache
```

Paths / mounts: [`../../database/README.md`](../../database/README.md), [`../../deploy/README.md`](../../deploy/README.md).
