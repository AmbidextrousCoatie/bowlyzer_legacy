# Data pipeline (Bowl-A-Lyzer)

**Operator guide for fetch → normalize → validate → publish → cache.**  
Detailed tools: [`pipeline/fetch.md`](pipeline/fetch.md), [`pipeline/validate.md`](pipeline/validate.md), [`pipeline/import.md`](pipeline/import.md), [`pipeline/publish.md`](pipeline/publish.md).

Supersedes the scrape-flag and hybrid-player guidance in older planning docs (`docs/planning/DATA_PIPELINE_PLAN.md`, `PIPELINE_STATE_OVERVIEW.md`).

---

## Mental model

```text
┌─────────────────────────── INTAKE ───────────────────────────┐
│  Legacy scrape .xls (08/09–18/19)                             │
│  Historical Excel extract (19/20–24/25)                       │
│  GF league pipeline (current season)                          │
│  GF tournament tables + PDF/manual tournament imports         │
│  Aktive Mitglieder (Rangliste) workbooks                      │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌────────────────────────── NORMALIZE ─────────────────────────┐
│  team_name_normalization.json  → team spelling + numbers      │
│  club_mapping.csv              → alias → canonical Club       │
│  players_registry              → EDV + Pass-Nr / legacy IDs   │
│  affiliation_index             → player×season Club + Verein  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌────────────────────────── PUBLISH ───────────────────────────┐
│  scripts/build_published_dataset.py                           │
│  → database/data/*.parquet (+ optional CSV)                   │
│  → clubs_registry, players_registry, affiliation_index        │
│  → runs/latest.json manifest                                  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌────────────────────── CACHE / SERVE ─────────────────────────┐
│  rebuild_league_caches / warm_league_cache                    │
│  Flask app (db_real_merged, tournament DB, …)                 │
│  deploy.ps1 -SyncDatabase [-SyncCache]                        │
└──────────────────────────────────────────────────────────────┘
```

**Club vs Verein:** the app models **Club** (+ team number). Verein is affiliation metadata (Rangliste), not the Mannschaft selector. See [`planning/VEREIN_CLUB_DISAMBIGUATION.md`](planning/VEREIN_CLUB_DISAMBIGUATION.md).

**“Legacy scrape”** is an *acquisition path* for the same league game rows as later extracts — not a separate data product. Publish **includes** `legacy_scrape_extracted.csv` by default when the file exists (`--skip-legacy-scrape` only for smoke tests).

---

## Published artifacts (`database/data/`)

| Artifact | Role |
|----------|------|
| `league_results_merged.parquet` | All league seasons (scrape + historical + GF) |
| `tournaments_postprocessed.parquet` | GF + manual/PDF tournament rows |
| `players_registry.parquet` | Canonical `player_id` (+ legacy / Pass-Nr) |
| `affiliation_index.parquet` | `(player_id, season)` → Club / Verein |
| `clubs_registry.parquet` | Canonical Club names + aliases / team labels |
| `vereine_registry.parquet` | Verein catalog from Rangliste |
| `runs/latest.json` | Last publish manifest |

Hand-edited (repo, not regenerated blindly):

| File | Role |
|------|------|
| `database/relational_csv/club_mapping.csv` | Durable alias → **canonical Club** |
| `database/config/team_name_normalization.json` | Regex team spelling / number fixes |
| `database/relational_csv/rangliste_club_crosswalk.csv` | Rangliste club label → league Club (optional) |

Diagnose UI for unmapped tournament clubs: `/diagnose/validierung/clubs` (saves into `club_mapping.csv`).

Rangliste historical spellings (e.g. `BC Donau - Bowler`) are folded through the same `club_mapping.csv` when building `affiliation_index` and again after tournament affiliation resolution — otherwise **Spiele nach Club** can show the old label while **Clubzugehörigkeit** (league-first) shows the canonical Club.

---

## Correct publish commands (club names fixed)

After editing `club_mapping.csv` and/or `team_name_normalization.json`:

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"

# 1) Rebuild published Parquets + registries (scrape included by default)
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv

# 2) Rebuild API disk caches (required — otherwise UI keeps old club matrices)
uv run python scripts/rebuild_league_caches.py --all-published --workers 8

# 3) Restart the Flask app process so in-memory registry caches reload
```

Optional checks:

```powershell
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/audit_club_names.py
# UI: /diagnose/validierung/clubs?database=db_real_merged
```

**Why `--job league,tournament` alone felt broken:** publish updates Parquet/registries, but **league/club API responses stay cached** until step 2. Step 3 matters if the long-running Flask process still holds an old `clubs_registry` LRU.

---

## Scenario cheatsheet

### A. Full republish (all seasons)

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --write-csv
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

### B. Update player DB (Aktive / Pass-Nr bridge) and republish

```powershell
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv
# players_registry + affiliation rebuild automatically unless --skip-players-registry
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

Players-only registry refresh (no league merge):

```powershell
uv run python scripts/build_players_registry.py --write-csv
uv run python scripts/build_affiliation_registry.py --write-csv
```

### C. Club alias fix (e.g. Schwarz-Weiß → SW 77 Würzburg)

1. Prefer UI `/diagnose/validierung/clubs` **or** edit `database/relational_csv/club_mapping.csv`:
   ```csv
   SW 77 Würzburg,Schwarz-Weiß 77 Würzburg
   ```
2. If both spellings appear as **league Team** strings, also map in `team_name_normalization.json` (regex → majority spelling).
3. Run **Correct publish commands** above.

### D. Add / refresh tournaments

```powershell
# PDF / registry imports (see pipeline/import.md)
uv run python scripts/import_tournaments.py …

# or GF tables export + postprocess, then:
uv run python scripts/build_published_dataset.py --job tournament --write-csv
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

Clubmeisterschaft VPS path: [`CLUBMEISTERSCHAFT_AUTO_IMPORT.md`](CLUBMEISTERSCHAFT_AUTO_IMPORT.md).

### E. New GF league weeks (current season)

```powershell
uv run python scripts/run_gf_pipeline.py --mode incremental
uv run python scripts/build_published_dataset.py --job league --write-csv
# Incremental warm (unchanged seasons keep disk cache):
uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8
```

### F. Keep cache up to date (no full rebuild)

```powershell
# After a small data change already published:
uv run python scripts/warm_league_cache.py --database db_real_merged --workers 8

# After a full publish / identity change:
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

### G. Deploy published data to VPS

```powershell
.\deploy\deploy.ps1 -SyncDatabase
# if you warmed caches on the build machine and want them on VPS:
.\deploy\deploy.ps1 -SyncDatabase -SyncCache
```

---

## League merge priority

Low → high (later wins on duplicate keys):

1. Historical extract (`historical_league_results.csv`)
2. Legacy scrape extract (`legacy_scrape_extracted.csv`) — **default on**
3. `--extra-league` (optional)
4. GF pipeline (`pipeline/.../legacy_out/latest.csv`)

Tournaments: GF combined postprocessed ∪ `tournament_manual_postprocessed` (and other manual/PDF outputs folded into that path by import scripts).

---

## Related

| Doc | Role |
|-----|------|
| [`pipeline/fetch.md`](pipeline/fetch.md) | Scrape / Excel / GF intake |
| [`pipeline/validate.md`](pipeline/validate.md) | Audits and publish gates |
| [`pipeline/import.md`](pipeline/import.md) | Tournament + clubmeisterschaft import |
| [`pipeline/publish.md`](pipeline/publish.md) | Orchestrator flags, manifests, cache |
| [`Excel_Extraction.md`](Excel_Extraction.md) | Tool catalog for Excel / scrape CLI |
| [`database/README.md`](../database/README.md) | Paths / mounts |
| [`database/data/README.md`](../database/data/README.md) | Published dir + short build notes |
| [`deploy/README.md`](../deploy/README.md) | Deploy / sync |
