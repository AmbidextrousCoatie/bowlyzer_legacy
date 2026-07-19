# Pipeline state overview (wrap-up)

> **Superseded for operators:** use [`../DATA_PIPELINE.md`](../DATA_PIPELINE.md) and [`../pipeline/`](../pipeline/).  
> This file remains as an architecture snapshot (status date 2026-06-14). Scrape is **included by default** on publish (`--skip-legacy-scrape` to opt out); `--with-legacy-scrape` is a no-op.

**Purpose:** Single inspection doc — what each data stream is, where it sits in processing, what the last publish recorded, and how downstream artifacts depend on upstream changes.

**Companion docs:**

| Doc | Role |
|-----|------|
| [`DATA_PIPELINE_PLAN.md`](DATA_PIPELINE_PLAN.md) | Target architecture, roadmap, Diagnose UI plan |
| [`BACKEND_REWRITE_RUST.md`](BACKEND_REWRITE_RUST.md) | Deferred follow-up: Postgres + Rust API (after legacy publish) |
| [`database/data/ARTIFACTS.md`](../../database/data/ARTIFACTS.md) | Operator contract (jobs, audits, manifest fields) |
| [`database/data/README.md`](../../database/data/README.md) | Build → warm cache → deploy |
| [`database/data/runs/latest.json`](../../database/data/runs/latest.json) | Machine-readable last publish |

**Status date:** 2026-06-14 (manifest `run_id` `20260614T134924Z`)

---

## 1. Executive summary

| Layer | State today |
|-------|-------------|
| **Intake** | Multiple adapters (Excel, scrape, GF API, GF tables export, club XLSX) — **no unified stage registry file**; state scattered across work-dir logs |
| **Publish** | **Full rebuild** of league + tournament Parquets on each `build_published_dataset.py` run |
| **Manifest** | **Required** — `database/data/runs/latest.json` documents artifacts, inputs, audits, config fingerprints |
| **Incremental ingest** | **GF league only** (`run_gf_pipeline.py --mode incremental` + `state/form_*.json`) |
| **Incremental publish** | **Not yet** — merge always re-reads all league CSVs (~740k rows) |
| **Downstream cache** | **Season-granular** after publish (`revision_index.json` + `warm_league_cache.py` without `--rebuild`) |
| **Traceability** | Manifest → input paths + row counts; **no** “which seasons changed → which API endpoints stale” graph yet |
| **Diagnose UI** | Published data quality (week matrix, oddities); **pipeline ops dashboard** planned (Phase 1 in plan) |

**Your direction (agreed problem):** stop treating the merged league file as one big blob. Partition by **season** (or source×season), reprocess only changed slices, and propagate **impact** to club history, league history, player registry, and warmed caches.

---

## 2. Last publish snapshot

From `runs/latest.json` (`20260614T134924Z`, not forced):

| Job | Published Parquet | Rows | `columns_hash` | App source |
|-----|-------------------|------|----------------|------------|
| `league_merge` | `league_results_merged.parquet` | **741,799** | `e977cb887df8a0c3` | `db_real_merged` |
| `tournament_merge` | `tournaments_postprocessed.parquet` | **4,338** | `4650c0d4cade1081` | `db_tournament_regions_2026_gf` |
| `players_registry` | `players_registry.parquet` | **3,044** | `95b18b9964436471` | identity layer (Spieler) |

**League merge inputs (priority low → high):**

| Prio | Path | Input rows | Unique after per-source dedupe |
|------|------|------------|------------------------------|
| 0 | `{work}/historical_league_results.csv` | 104,841 | 103,994 |
| 1 | `{work}/legacy_scrape/legacy_scrape_extracted.csv` | 630,970 | 630,293 |
| 2 | `database/pipeline/bowling_bayern/legacy_out/latest.csv` | 9,175 | 7,512 |

GF wins on duplicate business keys. Cross-source conflicts on those keys: **0**. Duplicate groups reported: **1,646** (work-dir CSVs).

**Audits:**

| Audit | Status | Notes |
|-------|--------|-------|
| `female_league_split` | **ok** | Blocks publish if failed |
| `player_id_name` | **deferred** | 10 rows in `{work}/player_id_name_conflicts.csv`; does not block publish |
| `league_standings` | **report** | `{work}/league_standings_validation.csv` — Excel Tabellen vs computed; **week coverage** (same rules as Liga-Wochen) |

**Normalization recorded:**

| Step | Applied in last run? | Fingerprint |
|------|----------------------|-------------|
| Team name rules | yes | (rules in `team_name_normalization.json`) |
| Player ID remap JSON | loaded, not “applied” flag | `eb74c4e2c837` |
| Player name alias JSON | not applied | — |
| Players registry | yes (job ran first) | parquet content hash in merge summary |

---

## 3. Source / stream matrix

Logical **streams:** `league` | `tournament` | `player` (registry).  
Logical **stages** (target vocabulary — see §5): `intake → raw → sanitized → canonical → merged → published → cached`.

| Source ID | Stream | Typical intake | Current stage (approx.) | Incremental? | Work / published path |
|-----------|--------|----------------|-------------------------|--------------|------------------------|
| `legacy_league_excel` | league | `.xls`/`.xlsx` tree | **canonical** → `historical_league_results.csv` | Per-file SHA in `extract_excel_analysis_log.json` | `{work}/` |
| `legacy_league_scrape` | league | HTTP `.xls` | **canonical** → `legacy_scrape_extracted.csv` | Per-season scrape | `{work}/legacy_scrape/` |
| `gf_league` | league | GF REST JSON | **canonical** → `legacy_out/latest.csv` | **Yes** (API `date_updated` cursor) | `database/pipeline/bowling_bayern/` |
| `bowlingbayern_csv` | league | static CSV | optional one-shot | No | `database/input/` |
| `gf_tournament` | tournament | GF tables REST | **canonical** → GF combined postprocessed | Batch export | `database/input/gf_tables_export/` |
| `tournament_xlsx` | tournament | club/regional `.xlsx` | **canonical** → manual postprocessed | Per import | `database/input/`, `database/data/tournament_manual_postprocessed.csv` |
| `players_registry` | player | Aktive workbooks + JSON configs | **published** parquet | `from_scratch` default; optional merge | `database/data/players_registry.parquet` |

Registry file: `database/config/data_sources.json`.

**Path split (known footgun):**

- Published runtime: `database/paths.py` → `BOWLYZER_DATA_DIR` (default `database/data/`)
- GF league stages: `pipeline/paths.py` → `database/pipeline/bowling_bayern/`
- Work intermediates: `BOWLYZER_WORK_DATA_DIR` (default `C:\tmp\bowlyzer\data`)

---

## 4. Processing steps (what happens when)

### 4.1 Orchestrator: `build_published_dataset.py`

```text
[optional] players_registry     ← Aktive Mitglieder (min season 2008-09 default) + configs
[fatal?]   female_league_audit  ← on legacy / extra league inputs only
           league_merge          ← merge_league_sources.merge_sources()
           tournament_merge      ← concat GF + manual
           [optional] player_hybrid        ← deprecated; Spieler uses runtime merge
           player_id_name_audit  ← deferred gate
           league_standings_audit ← Excel Tabelle/TabGes vs computed (report only)
           publish_gate          ← strict unless --force-publish
           manifest              ← runs/latest.json + timestamped copy
```

### 4.2 Inside `league_merge` (per input CSV, then concat)

| Order | Step | Config / module | Output / side effect |
|-------|------|-----------------|----------------------|
| 1 | Load CSV | — | DataFrame per source |
| 2 | **Team name normalization** | `team_name_normalization.json` | Canonical team strings |
| 3 | **Team number normalization** | `team_number_overrides.csv` | Trailing team digits |
| 4 | **Player ID remap** | `player_id_name_normalization.json` (`id_only`) | Stable EDV IDs |
| 5 | **Player name resolution** | `players_registry.parquet` | Names aligned to registry |
| 6 | Per-source dedupe | business keys | `input_unique_dims` stats |
| 7 | Concat + priority merge | GF last | Single league frame |
| 8 | Global dedupe + conflict report | — | `{work}/league_results_merged_duplicates*.csv` |
| 9 | **Schema v2** | `apply_league_competition_schema_v2` | `Event`, `Event Type=league`, `Club` |
| 10 | **Publish Parquet** | `parquet_sidecar.publish_dataframe` | `league_results_merged.parquet` |
| 11 | **Dtype normalization** | `dtype_normalization` | On read + write |

### 4.3 Separate cadence jobs (not in every publish)

| Script | When | Produces |
|--------|------|----------|
| `extract_excel_data.py` | Historical refresh | `historical_league_results.csv`, analysis log |
| `scrape_legacy_liga.py` | Legacy seasons | `legacy_scrape_extracted.csv` |
| `run_gf_pipeline.py` | Weekly / incremental | `legacy_out/latest.csv` |
| `export_gf_tables.py` | Tournament batch | `gf_tables_export/*` |
| `import_*_xlsx.py` | Club events | `tournament_manual_postprocessed.csv` |
| `build_players_registry.py` | Identity refresh | `players_registry.parquet` |
| `audit_player_id_names.py` | QA | `player_id_name_conflicts.csv` |
| `audit_league_standings.py` | QA | `league_standings_validation.csv` |
| `warm_league_cache_shard.py` | After deploy | `.cache/league/entries/*.json` |

### 4.4 Post-publish (runtime, not data build)

| Mechanism | Granularity | File |
|-----------|-------------|------|
| League API disk cache | Per endpoint × query × **season/league revision** | `.cache/league/{db}/entries/` |
| Revision index | Per-season / per-league content hash | `.cache/league/{db}/revision_index.json` |
| Shared pandas store | Process-local DF | mtime of Parquet |

---

## 5. Unified stage ladder (target vs today)

```text
intake → raw → sanitized → canonical → merged → published → cached
```

| Stage | Meaning | Example today |
|-------|---------|---------------|
| **intake** | Bytes as received | GF `incoming/`, Excel tree, scraped `.xls` |
| **raw** | Parsed rows + metadata | GF `staging/`, extract per-combo CSVs |
| **sanitized** | Clean strings, drop garbage | GF `sanitized/`, extract normalizers |
| **canonical** | Legacy flat `Columns` schema | `historical_league_results.csv`, `latest.csv`, scrape extract |
| **merged** | Multi-source dedupe | **In-memory only** — single `league_results_merged` |
| **published** | Parquet under `database/data/` | + `runs/latest.json` |
| **cached** | API JSON | `.cache/league/` |

**Gap:** There is no `stages/{source_id}/` tree or JSON registry listing “source X is at canonical, fingerprint Y, last run Z”. The manifest only captures **publish-time** inputs, not per-source stage history.

---

## 6. Fingerprints & traceability (today)

### 6.1 What we record

| Fingerprint | Where | Used for |
|-------------|-------|----------|
| Input file path + row counts | `manifest.artifacts[].input_sources` | “What went into this publish?” |
| `columns_hash` | manifest per artifact | Schema drift detection |
| Config SHA (12 hex) | `normalization.*_fingerprint` | Player ID JSON changes |
| Excel file SHA256 | `extract_excel_analysis_log.json` | Skip unchanged workbooks |
| GF form cursor | `pipeline/.../state/form_{id}.json` | Incremental API fetch |
| League cache revision | `revision_index.json` seasons/leagues/clubs | Skip warming unchanged seasons |
| Parquet mtime/size | `compute_data_revision()` fallback | Whole-file cache bust |

### 6.2 What we do **not** record yet

- Per-source, per-season content hash at **canonical** stage (before merge)
- Diff between publish N and N−1 (“seasons added/changed/removed”)
- Dependency graph: “GF `25/26` changed → invalidate club matrix for clubs X, league history for league Y”
- Lineage from a **single match row** back to intake file (row-level provenance)

### 6.3 Downstream impact map (conceptual)

When **league merge** changes, these are affected:

| Downstream | Depends on | Invalidation today |
|------------|------------|-------------------|
| Liga standings / week tables | `league_results_merged` | Full publish → revision index rebuild; granular cache warm |
| Club matrix / club history | team×season cells from league rows | Same |
| League aggregation (all seasons) | all league rows for a league id | Same |
| Spieler search / lifetime | league + tournament (+ registry) | Runtime merge; registry separate job |
| Tournament UI | `tournaments_postprocessed` | Separate stream; tournament cache warm |
| `players_registry` | Aktive + configs | Separate job; can desync from league names |

**Only the API cache layer is season-aware today.** The **data build** is not.

---

## 7. Problem statement: big blob vs seasonal slices

### Current behavior

1. Append 500 rows to GF current season in `latest.csv`.
2. `build_published_dataset.py` re-reads **~740k** historical rows, re-normalizes all, re-merges, rewrites full Parquet.
3. Manifest gets new `run_id` but no “only `25/26` changed” section.
4. `warm_league_cache.py` **can** skip unchanged seasons — **if** revision index matches new Parquet content.

### Target behavior (aligned with your ask)

```text
                    ┌─────────────────────────────────────┐
                    │  Source registry (per source×season) │
                    │  stage, fingerprint, last_run, errs  │
                    └─────────────────┬───────────────────┘
                                      │
     intake ──► canonical slices      │     merged view
     (per season parquet/csv) ◄─────┘     (lazy or materialized)
              │                                    │
              └──── changed seasons only ──────────┘
                                      │
                              published manifest
                              + impact: {seasons, leagues, clubs}
                                      │
                              cache warm (targeted shards)
```

**Design principles:**

1. **Canonical storage by season** (or source×season) under work dir — not one 700k-row CSV for merge input.
2. **Merge reads slices** — only re-merge seasons whose canonical fingerprint changed (plus dependency rules, e.g. registry change → all seasons with affected player IDs).
3. **Manifest records deltas** — `changed_seasons: ["25-26"]`, `input_fingerprints: { "gf_league/25-26": "abc…" }`.
4. **Impact projection** — table mapping artifact → dimensions:
   - `club_matrix` → clubs × seasons
   - `get_league_history` → league × season
   - `get_season_league_standings` → season
5. **Traceability** — each published row carries optional `source_id`, `source_run_id`, `format_era` (schema v2 partial today).

**Smallest next step (suggested):**

1. Add `scripts/build_season_index.py` — scan published Parquet, emit `{season: row_count, fingerprint}` JSON beside manifest.
2. Extend manifest with `season_index` for league artifact.
3. Diagnose API: expose manifest + season index + config fingerprints (`pipeline_status_service` already partial).
4. Prototype merge: `merge_league_sources` accepts `--only-seasons 25-26` for dev iteration.

Full season-partitioned canonical store is Phase 2 in [`DATA_PIPELINE_PLAN.md`](DATA_PIPELINE_PLAN.md) §2.3–2.5.

---

## 8. Operator quick reference

```powershell
# Paths
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"

# Dry-run publish plan
uv run python scripts/build_published_dataset.py --dry-run

# Standard publish (registry + league + tournament)
uv run python scripts/build_players_registry.py --aktive-min-season 2008-09
uv run python scripts/build_published_dataset.py --write-csv
# see docs/DATA_PIPELINE.md (scrape included by default)

# GF league only (separate cadence)
uv run python scripts/run_gf_pipeline.py --mode incremental

# Inspect last manifest
Get-Content database/data/runs/latest.json | ConvertFrom-Json | Select run_id, jobs_run, @{n='league_rows';e={$_.artifacts[0].row_count}}

# Pipeline status (Diagnose backend)
uv run python -c "from app.services.pipeline_status_service import get_pipeline_status; import json; print(json.dumps(get_pipeline_status(), indent=2)[:4000])"

# Cache warm after publish
uv run python scripts/warm_league_cache_shard.py --database db_real_merged --rebuild --warm-clubs --max-parallel 8
```

---

## 9. Related code entry points

| Concern | Module |
|---------|--------|
| Paths | `database/paths.py`, `pipeline/paths.py` |
| Publish orchestration | `scripts/build_published_dataset.py` |
| League merge | `scripts/merge_league_sources.py` |
| Manifest | `data_access/publish_manifest.py` |
| Publish gate | `data_access/publish_gate.py` |
| Parquet I/O | `data_access/parquet_sidecar.py`, `data_access/dtype_normalization.py` |
| Players registry | `data_access/players_registry.py` |
| Diagnose status | `app/services/pipeline_status_service.py` |
| Cache revision | `app/cache/league_data_revision.py` |
| Source config | `database/config/data_sources.json` |

---

## 10. Locked decisions (2026-06-03)

| # | Topic | Decision |
|---|-------|----------|
| 1 | **Season partition key** | **Hyphen-normalized** everywhere in pipeline storage, paths, manifests, and slice filenames: `25-26`. Slash form (`25/26`) is **presentation only** (UI labels, legacy Parquet column values until migrated). |
| 2 | **Source × era guardrails** | **Plausibility checks** at ingest/merge: each source is only allowed in defined season ranges and format eras (pre-2022, post-2022, GF-live). Violations → audit row, block or warn per policy. |
| 3 | **Downstream invalidation** | **Impact-only reprocessing** — when a slice changes, re-evaluate only downstream documents/endpoints whose dependency dimensions intersect the change (not full blob rebuild). |
| 4 | **Tournament slices** | **Season partitions when schema is stable enough**; defer event-level slices unless volume forces it. Yearly format drift is a risk — generalize tournament canonical schema first; monitor slice count growth. |
| 5 | **Diagnose pipeline UI** | **Two tiers:** executive summary on top (KPIs, blockers, last delta), **grid** below (source × stage × season depth, drill-down). Extends current `/diagnose/datenpipeline`, not a separate app. |

Track implementation in [`DATA_PIPELINE_PLAN.md`](DATA_PIPELINE_PLAN.md) §2.4–2.5, §3, §5.

---

## 11. Season key convention

### Storage vs presentation

| Layer | Format | Example |
|-------|--------|---------|
| Work-dir slices, manifest, registry JSON | `YY-YY` (hyphen) | `25-26` |
| URL query (wire) | hyphen preferred | `?season=25-26` |
| UI display | slash (German convention) | `25/26` |
| Published Parquet `Season` column (today) | slash | migrate read-path to accept both; write-path emits hyphen in new partitions |

**Canonical function (target):** `normalize_season_key(raw) -> "25-26"` in `data_access/` (pipeline) — distinct from `app.utils.season_query.normalize_season_query_value` which maps to slash for **runtime data lookups** against legacy column values.

**Migration:** Phase 3 introduces hyphen keys on disk first; app i18n/formatters render slash. Optional later: normalize `Season` column on publish.

---

## 12. Source × era guardrails

Each source adapter declares **allowed season ranges** and **format era**. Merge and publish validate that rows in a slice match expectations.

| Source / adapter | Format era | Allowed seasons (inclusive) | Notes |
|------------------|------------|----------------------------|-------|
| `legacy_league_excel` | `pre2022` | through `21-22` | Pre-GF workbook layout |
| `legacy_league_excel` | `post2022` | `22-23` onward (if present in tree) | Newer sheet shape |
| `legacy_league_scrape` | `pre2022` | through `21-22` | Scraped `.xls` archive |
| `gf_league` | `post2022` (GF-live) | `22-23` onward (configurable cutoff) | Must not appear in pre-2022 seasons |
| `bowlingbayern_csv` | per file | explicit in manifest | One-shot imports |
| `tournament_xlsx` / `gf_tournament` | tournament schema v1 | all | Season guard + event-type plausibility |

**Guardrail actions:**

| Severity | When | Action |
|----------|------|--------|
| **error** | GF rows in `15-16`, or pre2022 adapter tagged `post2022` season | Block slice publish; log to `audit/source_era_violations.csv` |
| **warn** | Excel post2022 row in season `20-21` | Allow with manifest flag `era_mismatch: true` |
| **info** | Historical source contributes to current season while GF also present | Expected — merge priority resolves (GF wins) |

Config target: `database/config/source_era_bounds.json` (new) referenced from `data_sources.json`.

---

## 13. Downstream impact-only reprocessing

When canonical slice `S` changes (fingerprint delta), compute **impact set** `I(S)` and touch only those downstream artifacts.

### Dependency dimensions

| Downstream artifact / cache | Dimensions | Invalidated when… |
|----------------------------|------------|-------------------|
| `league_results_merged` season partition | `season` | That season's canonical slice changed |
| `revision_index.json` season entry | `season` | Published rows for season changed |
| `get_season_league_standings` cache | `season`, `league` | Season changed, or league appears in changed slice |
| `get_club_matrix` / club history | `club`, `season` | Any team row for club×season changed |
| `get_league_history` | `league` | Any season for league changed |
| League aggregation (cross-season) | `league` | Any season for league changed |
| `players_registry` apply | `player_id` | Registry job changed → **only seasons containing those IDs** |
| Tournament published slice | `season` | Tournament canonical slice for season changed |
| Spieler runtime merge | `player_id`, streams | Union of league + tournament impacts |

### Algorithm (sketch)

```text
1. diff manifest.season_index vs previous → changed_seasons C
2. for each season s in C: resolve leagues L(s), clubs K(s), player_ids P(s)
3. merge: rewrite partition parquet for s only; stitch into published view
4. revision_index: bump only s (and affected league/club keys)
5. warm_league_cache: --seasons C --leagues union(L) instead of --rebuild
6. manifest.impact = { changed_seasons, leagues, clubs, player_ids, cache_endpoints }
```

**Registry blast radius (locked):** re-resolve player names **only in seasons where affected `player_id` appears**, not all historical seasons.

---

## 14. Tournament season slices

**Direction:** use **season-level** partitions (same key convention `25-26`) once the tournament canonical schema absorbs yearly layout differences.

**Rationale:**

- Event-level slices (`season × event_name`) multiply quickly (many regional/club events per year).
- Season slices stay bounded (~1 file per year per stream).
- Risk: a new year's Excel layout may need adapter branch — handle via `tournament_format_era` tag (mirror league pre/post 2022), not finer slices by default.

**Escalation path:** if a single season exceeds a row/size threshold (e.g. 50k rows or N events), optional sub-partition by `event_id` under `stages/tournament_xlsx/25-26/{event_id}/` — opt-in, not default.

**Guardrail:** tournament rows must carry normalized `season_key`; reject orphan events without resolvable season.

---

## 15. Diagnose UI — executive view + grid

Extends Phase 1 page [`frontend/src/pages/diagnosis/DataPipeline.tsx`](../../frontend/src/pages/diagnosis/DataPipeline.tsx).

### Tier 1 — Executive (above the fold)

| Tile / row | Content |
|------------|---------|
| Publish health | Last `run_id`, audit overall, forced? |
| Delta summary | `changed_seasons` since previous run (when manifest diff exists) |
| Blockers | Audits that block publish; era violations; missing required artifacts |
| Stream KPIs | League / tournament / registry row counts + staleness |
| Actions | Copy runbook commands; link to ARTIFACTS.md |

### Tier 2 — Grid (drill-down)

Matrix: **rows** = source ids (`gf_league`, `legacy_league_excel`, …); **columns** = stages (`intake` … `cached`) or collapsed stage groups.

Cell states: `empty` | `stale` | `ok` | `warn` | `error` | `blocked`.

**Season depth:** expand row → sub-grid **source × season** (`25-26`, `24-25`, …) with fingerprint, row count, last run, era tag, guardrail status.

Optional filter: stream (`league` | `tournament` | `player`), season range, show-only-changed.

### API extensions (Phase 2c)

| Endpoint | Adds |
|----------|------|
| `GET /pipeline/status` | `season_index`, `manifest_diff`, `impact_summary` |
| `GET /pipeline/sources` | per-source×season stage + fingerprints from work registry |
| `GET /pipeline/guardrails` | era violation report from last validate pass |

Wire format uses **hyphen season keys**; frontend formatter maps to `25/26` for display.

---

## 16. Validation & normalization progress (2026-06)

**Baseline (operator note):** ~**62% green** league×season comparisons in standings validation. Priority for closing gaps: **24/25–25/26** seasons first (GF / recent pipeline), then legacy Excel seasons.

### Standings validation semantics (implemented)

Three totals per league×season:

| Label | Meaning | Pass / signal |
|-------|---------|----------------|
| **ref** | Excel Tabellen / TabGes aggregate | — |
| **schema** (`total_points_expected`) | Pure scoring budget (league size × weeks × placement). **No** no-show reduction. | `ref ≠ schema` → **yellow** (Excel oddity; may heal) |
| **computed** | Merge totals from scratch + placement bonuses | Must match **ref** when data is coherent → `ref ≠ computed` → **red** |

Weekly pool lines (`pts-week`) use **schema** for expected weekly budget; primary merge issue is **comp-ref**. No-show weeks annotate **ref-schema** gap + team name; they no longer green-wash a **comp-ref** mismatch.

**Healing:** `ref` below schema explained by documented no-shows, merge matches Excel ref → **corrected** (not green while computed still diverges).

**Operator:** `uv run python scripts/audit_league_standings.py [--season …] [--league …]` → `{work}/league_standings_validation.csv` + Diagnose UI.

### Normalization (team names)

- Rules in `database/config/team_name_normalization.json`; applied in `normalize_data` / merge (`normalize_extracted_dataframe`).
- Typical run: `uv run python extract_excel_data.py --mode normalize_data --input "{work}/legacy_scrape/legacy_scrape_extracted.csv"`.
- Last normalize pass example: ~250k Team/Opponent cells, 162 distinct strings (legacy scrape).

**Note:** `normalize_data` on legacy scrape **does not** rebuild `league_results_merged`; run `build_published_dataset.py` (or `--job league`) to publish.

### Extraction fixes (pre-2022 placement bonuses)

- **Phantom bye** (5 real teams, 6 Spielzettel blocks incl. `"0"`): placement scale **N = 5**, not 6 (`_pre_2022_placement_team_count` uses Spielzettel block count vs metadata).
- **No-show** (real team absent): placement scale stays **league size N** (e.g. 8-team league → 8..2 for active teams, 0 for absent). Fixed case: absent team has **no** Spielzettel block (A N2 W5 pattern).
- Tests: `tests/test_pre_2022_placement_bonuses.py`.

**Pending until re-extract + merge:** legacy cases still red where merge CSV predates fix (e.g. BL S1 (D) 10/11, A N2 10/11 W5) — merge awards 7-team scale instead of 8.

### Known footguns (accepted for now)

| Issue | Symptom | Mitigation |
|-------|---------|------------|
| **Parquet sidecar stale** | Audit shows `computed=0` / “no computed standings” for old seasons while CSV has data | `resolve_load_path` prefers `.parquet`; rebuild from full CSV or delete stale sidecar before audit |
| **normalize ≠ publish** | Team names fixed in work dir but merged file unchanged | Run `build_published_dataset.py` after normalize |
| **Pre-2022 weekly ref** | `pts-week` missing `ref` before Tabellen weekly parse | `collect_pre_2022_reference_weekly_team_points` + week schema |

### Deferred / next validation work

- Re-extract + merge for pre-2022 placement bonus alignment on affected seasons.
- W4 unexplained Excel ref+1 (BL S1 10/11) — yellow, not merge.
- Parquet/CSV sync policy in publish gate (optional).
- **Not in scope now:** further validation tuning until 24–26 season gaps are reduced.

### Feature work

Resume product/feature tasks after 24–26 data-quality pass (per operator plan).

