# Published Parquet artifacts

Operator contract for `database/data/` (synced to VPS). Machine-readable twin: `runs/latest.json` after each `build_published_dataset.py` run.

**Day-to-day commands:** [`../../docs/DATA_PIPELINE.md`](../../docs/DATA_PIPELINE.md).

## Jobs

| Job | Parquet | App source | Stream |
|-----|---------|------------|--------|
| `players_registry` (auto) | `players_registry.parquet` | — | player identity |
| `league_merge` | `league_results_merged.parquet` | `db_real_merged` | league (+ rebuild `clubs_registry`, extend `affiliation_index`) |
| `tournament_merge` | `tournaments_postprocessed.parquet` | `db_tournament_regions_2026_gf` | tournament |

Also published: `affiliation_index`, `clubs_registry`, `vereine_registry`.

**Spieler** does not use a third Parquet: `db_player_merged_hybrid` loads league + tournament at runtime.

## Players registry (`players_registry.parquet`)

| Column | Meaning |
|--------|---------|
| `player_id` | Canonical EDV id |
| `player_id_legacy` | Pre-06/07 EDVs (pipe-separated) |
| `player_id_pass` | Pass-Nr bridge |
| `canonical_name` | Preferred display label |
| `aliases` | Pipe-separated alternates |
| `source` | `dbu_id`, … |

**Registry updates:** run via `build_published_dataset` (default) or `scripts/build_players_registry.py`. Club aliases: `database/relational_csv/club_mapping.csv`.

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
| Club | from Team at publish | resolved via `clubs_registry` / `club_mapping` |
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
uv run python scripts/build_published_dataset.py --write-csv
uv run python scripts/build_published_dataset.py --job league,tournament --write-csv
# scrape included by default; opt out: --skip-legacy-scrape
uv run python scripts/rebuild_league_caches.py --all-published --workers 8
```

Override emergencies: `--force-publish`. Legacy single-file hybrid: `--with-player-hybrid` (deprecated).

Registry: `database/config/data_sources.json`. Operator guide: [`docs/DATA_PIPELINE.md`](../../docs/DATA_PIPELINE.md).
