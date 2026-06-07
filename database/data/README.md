# Published data (`database/data/`)



Runtime CSV/Parquet/JSON consumed by the Flask app. On the VPS this directory is **bind-mounted** into the container (`deploy/docker-compose.prod.yml`).



Full layout (repo vs VPS, three mount points): **`database/README.md`**.



## Parquet-first (default)



The app loads **`*.parquet`** when present (config paths still use the historical `*.csv` names).



| Logical dataset | Config filename | Typical Parquet | Typical CSV (optional) |

|-----------------|-----------------|-----------------|------------------------|

| Merged league | `league_results_merged.csv` | ~0.3–8 MB | varies |

| Tournaments | `tournaments_postprocessed.csv` | small | varies |

| Player hybrid | `player_stats_merged_plus_tournaments.csv` | ~5–15 MB | up to ~120 MB |



### Build on your PC (no legacy scrape)



**Inputs** (historical extract) come from the **work dir**; **outputs** go to `database/data/`. Run `--dry-run` first to see resolved paths.

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/build_published_dataset.py
# optional: --with-player-hybrid
# optional: --with-legacy-scrape  (merge legacy_scrape_extracted.csv from work dir)
# optional: --extra-league C:\path\to\other.csv  (repeatable; before GF in priority)
```



Writes `league_results_merged.parquet`, `tournaments_postprocessed.parquet` by default. Add `--write-csv` only for debugging.



### Full published rebuild (scrape + tournaments + player hybrid)



```powershell
uv run python scripts/build_published_dataset.py --with-legacy-scrape --with-player-hybrid
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```



Warms `db_real_merged` (liga + clubs), `db_player_merged_hybrid` (Spieler dropdown), and `db_tournament_regions_2026_gf` (Turnier). Then deploy data + cache together.



### League API disk cache (incremental warm)



After merging new rows into `league_results_merged`, run warm **without** `--rebuild` so unchanged seasons keep their cache entries:



```powershell
uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8
# optional: where time goes (GIL, slow endpoints)
uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8 --benchmark
```



Use `--rebuild` only after payload/schema bumps or a full cache reset. Per-season fingerprints live in `.cache/league/<database>/revision_index.json`.



### Deploy to VPS



```powershell

.\deploy\deploy.ps1 -SyncDatabase

# optional huge CSVs:  -SyncDatabaseCsv

```



## What not to keep on the VPS



Safe to remove from `~/bowlyzer/database/data/` after backup (not used by default sources):



- `bowling_ergebnisse*.csv`, `extract_excel_analysis_log.json`

- `league_results_merged_duplicates*.csv`

- Old test / fantasy tournament CSVs unless you still select those DBs in the UI



Pipeline intermediates belong in **`BOWLYZER_WORK_DATA_DIR`** on the build machine, not on the VPS.


