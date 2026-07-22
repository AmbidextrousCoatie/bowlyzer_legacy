# Database layout (repo vs VPS)

## Two different “database” meanings

| Location | What it is |
|----------|------------|
| **`database/` Python package** (in the Docker image) | Code: `paths.py`, `conversion/`, `pipeline/`, `input/`, … |
| **`database/data/`** (on disk, bind-mounted on VPS) | **Published CSV/Parquet/JSON** the running app reads |

Production **must not** bind-mount the whole `database/` folder over `/app/database` — that hides `database.paths` from the image. See `deploy/docker-compose.prod.yml`.

---

## VPS folder (what belongs on the server)

Only this tree under `~/bowlyzer/`:

```text
~/bowlyzer/
  docker-compose.prod.yml
  .env
  database/
    data/              ← published league / player / tournament files
    relational_csv/    ← small reference dimension tables
    config/            ← team-name normalization overrides
```

You can **delete** on the VPS (unused with current compose): `database/pipeline/`, `database/input/`, `database/conversion/`, old dev CSVs under `data/` (see below). They are not mounted and only cause confusion.

---

## Why three bind-mounts? (not three files)

Docker mounts **three directories** so live data can change without rebuilding the image:

| Host path | In container | Purpose |
|-----------|--------------|---------|
| `database/data/` | `/app/database/data/` | **Main datasets** — league merge, player hybrid, tournament rows, KO JSON |
| `database/relational_csv/` | `/app/database/relational_csv/` | **Lookup tables** — clubs, venues, league mapping (relational export model) |
| `database/config/` | `/app/database/config/` | **Import/normalization config** — team number overrides, name normalization rules |

Everything else (`paths.py`, GF pipeline paths under `database/input/…`, `database/pipeline/…`) stays **inside the image** from `COPY database ./database` in the Dockerfile.

`-SyncDatabase` uploads `relational_csv/`, `config/`, and `*.parquet` / `*.json` into `data/` (optional `*.csv` with `-SyncDatabaseCsv`).

---

## Minimal `database/data/` for production

Built on your PC with `scripts/build_published_dataset.py`, then synced.

| File | Required? | Used for |
|------|-----------|----------|
| `league_results_merged.parquet` | **Yes** (or `.csv`) | Default **Liga** source (`db_real_merged`) |
| `tournaments_postprocessed.parquet` | Recommended | Tournament pages / merged tournament source |
| `tournament_manual_postprocessed.csv` | If you use club Excel imports | Merged into tournament + player hybrid |
| `tournament_ko_config.json` | For KO tournaments | Bracket UI |
| `ko_bracket_overrides.json` | Optional | Manual bracket tweaks |
| `player_stats_merged_plus_tournaments.parquet` or `.csv` | For **Spieler** lifetime/search | `db_player_merged_hybrid` |

**Not needed on VPS** (dev / pipeline / legacy): `bowling_ergebnisse_real.csv`, `bowling_ergebnisse.csv`, `extract_excel_analysis_log.json`, `*_duplicates*.csv`, `historical_league_results.csv` (only needed on build machine work dir), test tournament CSVs, etc.

If `bowling_ergebnisse_real.csv` is missing, the app logs one warning and disables `db_real` — harmless; default DB is `db_real_merged`.

---

## Build machine vs VPS

| | Windows / dev repo | VPS |
|--|-------------------|-----|
| Work/intermediates | `database/work/` (`BOWLYZER_WORK_DATA_DIR`) | — |
| Published Parquet | `database/data/*.parquet` (`BOWLYZER_DATA_DIR`) | Same paths under `~/bowlyzer/database/data/` |
| Published CSV mirrors | `database/published_csv/` (local inspection) | — |
| Full Python tree | Whole repo | **Image only** (not host mount) |

See `database/data/README.md` for Parquet build and deploy sync commands.

**Operator pipeline guide:** [`docs/DATA_PIPELINE.md`](../docs/DATA_PIPELINE.md). Architecture roadmap (historical): [`docs/planning/DATA_PIPELINE_PLAN.md`](../docs/planning/DATA_PIPELINE_PLAN.md).
