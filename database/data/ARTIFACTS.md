# Published Parquet artifacts

Operator contract for `database/data/` (synced to VPS). Machine-readable twin: `runs/latest.json` after each `build_published_dataset.py` run.

## Jobs

| Job | Parquet | App source | Stream |
|-----|---------|------------|--------|
| `league_merge` | `league_results_merged.parquet` | `db_real_merged` | league |
| `tournament_merge` | `tournaments_postprocessed.parquet` | `db_tournament_regions_2026_gf` | tournament |
| `players_registry` | `players_registry.parquet` | — | player identity |

**Spieler** does not use a third Parquet: `db_player_merged_hybrid` loads league + tournament at runtime (`merge_file_paths`).

## Players registry (`players_registry.parquet`)

| Column | Meaning |
|--------|---------|
| `player_id` | EDV id |
| `canonical_name` | Preferred display label |
| `aliases` | Pipe-separated valid alternates (marriage names, spelling variants) |
| `source` | `dbu_id`, `same_person_alias`, … |

**Name resolution at publish:** exact match → format reassembly → close typo (same given name). No majority/autoresolve name rules. Unresolved → `player_id_name_conflicts.csv`. ID remaps still use JSON until registry handles ids.

**Registry updates:** `uv run python scripts/build_players_registry.py` merges JSON into the published Parquet (aliases accumulate; canonical only from trusted sources). League publish does **not** rebuild the registry. `--from-scratch` is for deliberate full rebuilds only.

## Schema v2 core (both Parquets)

| Column | League | Tournament |
|--------|--------|------------|
| Event Type | `league` | `tournament` |
| Event | league id (`BayL`, …) | tournament title |
| Season | yes | yes |
| Date | yes | yes |
| Player / Player ID | yes | yes |
| Score | yes | yes |
| Location | yes | yes |
| Club | from Team at publish | from sheet |
| Input Data | yes | `True` on publish |
| Computed Data | yes | `False` on publish |

Stream-specific columns (Week, Opponent, Round Name, handicap, …) stay on one Parquet only; union at runtime is fine.

## Manifest (`runs/latest.json`)

Written by default on successful publish. Fields:

- `run_id`, `published_at`, `data_schema_version`
- `artifacts[]` — row counts, `columns_hash`, `input_sources[]`
- `audits` — status per audit (`ok`, `deferred`, `warn`, `skipped`)
- `deferred_audit_ids` — conflicts tracked but not blocking (see below)
- `forced` / `blocking_audit_ids` — when `--force-publish` overrides a blocking audit

## Audits

| Audit | Blocks publish? | Notes |
|-------|-----------------|-------|
| Female league split | **Yes** (pre-merge) | `--skip-female-league-audit` to override |
| Player ID / name | **No** (deferred) | Report in work dir; registry absorbs known fixes; flip `blocks_publish` after audit import |

Strict publish blocks only on audits that are not deferred. Player conflicts are listed in the manifest with `status: deferred` and `deferred_until: players_registry`.

## Build commands

```powershell
uv run python scripts/build_published_dataset.py
uv run python scripts/build_published_dataset.py --job league
uv run python scripts/build_published_dataset.py --job tournament
uv run python scripts/build_published_dataset.py --with-legacy-scrape
```

Override emergencies: `--force-publish`. Legacy single-file hybrid: `--with-player-hybrid` (deprecated).

Registry: `database/config/data_sources.json`. Full plan: `docs/planning/DATA_PIPELINE_PLAN.md`.
