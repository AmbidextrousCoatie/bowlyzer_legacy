# Excel extraction and related import tools

Central reference for scripts that read **Excel workbooks** (`.xls` / `.xlsx`), convert legacy formats, or sit directly downstream of Excel extraction. Related **CSV-only** and **Gravity Forms** tools are listed at the end so you can see the full data path into `database/data/`.

All Python commands assume the **repo root** as the current directory and **`uv run python`** (see `CLAUDE.md`).

---

## Directory layout and environment

| Role | Typical path (Windows) | Override |
|------|----------------------|----------|
| **Historical Excel tree** | `C:\tmp\Sammlung-Ligaergebnisse\` (your machine) | Pass `--folder` / `--file` explicitly |
| **Work / intermediates** | `C:\tmp\bowlyzer\data` | `BOWLYZER_WORK_DATA_DIR` |
| **Published app data** | `database/data/` | `BOWLYZER_DATA_DIR` |

Important work-dir artifacts (from `database/paths.py`):

| File | Purpose |
|------|---------|
| `extract_excel_analysis_log.json` | Analyze/process cache (per-file SHA256, format, eligibility) |
| `historical_league_results.csv` | Default merged output of `extract_excel_data.py` **process** mode |
| `historical_league_results_combos/` | Per league+season combo CSVs (sibling dir of merged file) |
| `legacy_scrape_extracted.csv` | Output after processing scraped `.xls` (see legacy scrape) |

Config used by the main extractor (not CLI flags):

| File | Purpose |
|------|---------|
| `database/config/extract_excel_overrides.csv` | Per-workbook fixes (`force_season`, `force_league`, `exclude_file`, …) |
| `database/config/team_name_normalization.json` | Team name cleanup during extract/merge |
| `database/config/team_number_overrides.csv` | Team number normalization |
| `database/relational_csv/league_mapping.csv` | Display name → canonical league id |

---

## Pipeline overview

```text
Historical Liga Excel (Sammlung-Ligaergebnisse)
        │
        ├─ convert_legacy_xls  (.xls → .xlsx via LibreOffice, optional)
        ├─ analyze             (classify format, cache in analysis log)
        └─ process             → historical_league_results.csv (+ combo dir)
                │
                └─ merge_league_sources.py / build_published_dataset.py
                        → league_results_merged.parquet

Tournament XLSX (openpyxl)
        ├─ import_bayerische_meisterschaft_xlsx.py
        └─ import_clubmeisterschaft_donaubowler_xlsx.py
                → postprocessed CSV → manual / GF combined → player hybrid

Legacy web .xls (HTTP scrape, not local Excel folder)
        scrape_legacy_liga.py → .xls files on disk
        → extract_excel_data.py (convert + process) → legacy_scrape_extracted.csv
                │
                └─ analyze_legacy_scrape_csv.py  (LOW_WEEKS / LOW_TEAMS / HIGH_TEAMS)

Excel analyze log (after extract_excel --mode analyze|process)
        └─ analyze_missing_league_weeks.py → missing weeks per league/season CSVs

Merged league CSV (any source)
        ├─ validate_data.py  (teams per week, match counts, …)
        └─ app: /diagnose/liga-wochen, /diagnose/daten-anomalien
```

---

## 1. `extract_excel_data.py` — historical league Excel

**Location:** repo root  
**Input:** Bowling Bayern / regional **Liga** workbooks (team sheets `Erfassung*`, season sheet `Schiedsrichterinfos`, week sheets, `Spielzettel`, etc.)  
**Output:** Semicolon-separated CSV aligned with `bowling_ergebnisse_real.csv` column shape.

### Modes (`--mode`)

| Mode | What it does |
|------|----------------|
| `analyze` | Inspect workbooks; update `extract_excel_analysis_log.json`; optional analysis CSV |
| `process` | Run analyze (with cache), then extract eligible files into merged + per-combo CSVs |
| `normalize_data` | Re-run normalization on existing CSV(s) only (no Excel) |
| `convert_legacy_xls` | Convert `.xls` → `.xlsx` in place (LibreOffice headless); skips if `.xlsx` exists unless `--force_convert_xls` |

Alias: `--normalize_data` sets mode to `normalize_data`.

### Parameters

| Flag | Applies to | Description |
|------|------------|-------------|
| `--mode` | all | `analyze` \| `process` \| `normalize_data` \| `convert_legacy_xls` |
| `--file` | analyze, process, convert | Single workbook path |
| `--folder` | analyze, process, convert | Directory to scan for `*.xls` / `*.xlsx` |
| `-r`, `--recursive` | with `--folder` | Recursive glob |
| `--team-sheet-prefix` | process | Team sheet prefix (default: `Erfassung`) |
| `--season-sheet` | process | Season metadata sheet (default: `Schiedsrichterinfos`) |
| `--output-file` | process, normalize_data | Merged CSV path (default: `historical_league_results.csv` in work dir) |
| `--output-dir` | process | Per league/season combo directory (default: `<output-file stem>_combos` next to merged file) |
| `--weeks` | process | Comma-separated week numbers (default: `1`) |
| `--analysis-output` | analyze, process | Optional CSV listing analyze results |
| `--skip_xls` | analyze, process | Ignore `.xls` (use after conversion to `.xlsx`) |
| `--old-format-sheet-threshold` | analyze, process | Sheet count threshold for “old 1-week” format (default: `15`) |
| `--force_reanalyze` | analyze, process | Ignore analysis cache for this run |
| `--no-parallel-subdirs` | process | Disable parallel workers per top-level folder under `--folder` |
| `--force_convert_xls` | convert_legacy_xls | Overwrite existing same-stem `.xlsx` |
| `--input` | normalize_data | One or more semicolon CSVs to normalize (repeatable) |
| `--normalize_data` | — | Shorthand for `--mode normalize_data` |

Discovery skips paths containing `fehlerhaft` or `logdatei`. If both `.xls` and `.xlsx` exist for the same stem, **process/analyze** prefer `.xlsx`.

### Example commands

```powershell
# Analyze entire historical tree (writes/updates analysis log)
uv run python extract_excel_data.py --mode analyze `
  --folder "C:\tmp\Sammlung-Ligaergebnisse" -r `
  --analysis-output "C:\tmp\bowlyzer\data\excel_analyze_report.csv"

# Convert legacy .xls to .xlsx before processing (LibreOffice must be on PATH)
uv run python extract_excel_data.py --mode convert_legacy_xls `
  --folder "C:\tmp\Sammlung-Ligaergebnisse" -r

# Full extract → historical merged CSV (typical batch)
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python extract_excel_data.py --mode process `
  --folder "C:\tmp\Sammlung-Ligaergebnisse" -r `
  --output-file "C:\tmp\bowlyzer\data\historical_league_results.csv"

# Process one workbook, weeks 1–3
uv run python extract_excel_data.py --mode process `
  --file "C:\tmp\Sammlung-Ligaergebnisse\Liga 2024-25\BYL Männer.xlsx" `
  --weeks 1,2,3

# Re-normalize an existing extract without re-reading Excel
uv run python extract_excel_data.py --mode normalize_data `
  --input "C:\tmp\bowlyzer\data\historical_league_results.csv"
```

After a successful **process** run, merge into published data:

```powershell
uv run python scripts/merge_league_sources.py `
  --inputs "C:\tmp\bowlyzer\data\historical_league_results.csv" `
           "database\pipeline\bowling_bayern\legacy_out\latest.csv" `
  --out "database\data\league_results_merged.csv"
```

Or use the all-in-one publisher (includes GF pipeline paths by default):

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --with-player-hybrid
```

### Analyze output (per-workbook oddities)

**Process** mode always re-runs analyze first. Use `--analysis-output` to save a semicolon CSV with columns such as `file`, `league`, `season`, `available_weeks`, `number_of_teams`, `eligible_for_processing`, `issues`, `data_format`. That is the input to `analyze_missing_league_weeks.py` (via the JSON log, not this CSV directly).

---

## 1b. Data quality and oddity discovery (not Excel parsers)

These scripts **do not read Excel**. They scan **extracted CSVs**, the **analysis log**, or **merged league data** for structural problems (too few weeks, too many teams, missing teams, etc.).

### `scripts/analyze_legacy_scrape_csv.py`

Summarizes **weeks and team counts per league×season** on a legacy-scrape extract (default: `legacy_scrape_extracted.csv` under the legacy scrape dir / work dir).

| Flag | Default | Description |
|------|---------|-------------|
| `--csv` | auto-resolve scrape CSV | Input semicolon CSV |
| `--export` | — | Optional summary CSV path |
| `--high-teams-threshold` | `10` | If team count exceeds this, print every team name |

**Flags in `note` column:**

| Note | Meaning |
|------|---------|
| `LOW_WEEKS` | Fewer than 6 distinct weeks |
| `LOW_TEAMS` | Fewer than 5 teams |
| `HIGH_TEAMS` | More than `--high-teams-threshold` teams (often duplicate team names before normalization) |

```powershell
uv run python scripts/analyze_legacy_scrape_csv.py
uv run python scripts/analyze_legacy_scrape_csv.py --csv "C:\tmp\bowlyzer\data\legacy_scrape_extracted.csv" --high-teams-threshold 12
uv run python scripts/analyze_legacy_scrape_csv.py --export database/data/legacy_scrape/legacy_scrape_summary.csv
```

Run **after** `extract_excel_data.py --mode process` on scraped `.xls` (or on `historical_league_results.csv` with `--csv`).

### `scripts/analyze_missing_league_weeks.py`

Reads **`extract_excel_analysis_log.json`** (same cache as analyze/process), groups by league+season, compares **available weeks** from workbooks vs **expected** week count (max `number_of_weeks` hint per group, else 6). Writes CSV tables to the work dir.

| Flag | Default | Description |
|------|---------|-------------|
| `--log` | `extract_excel_analysis_log.json` (work dir) | Analysis log JSON |
| `--outdir` | `BOWLYZER_WORK_DATA_DIR` | Output directory |

**Outputs:**

- `available_weeks_by_league_season.csv`
- `missing_weeks_by_league_season.csv`
- `available_weeks_matrix.csv`, `missing_weeks_matrix.csv`
- `league_weeks_combined_matrix.csv`

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
# Run after extract_excel analyze or process (populates the log)
uv run python scripts/analyze_missing_league_weeks.py
uv run python scripts/analyze_missing_league_weeks.py --log "C:\tmp\bowlyzer\data\extract_excel_analysis_log.json"
```

### `data_access/validate_data.py`

Validates a **flat league CSV** against **`database/relational_csv/`** definitions (expected teams per week, match/round structure, points sums).

| Flag | Description |
|------|-------------|
| `--source` | `real` \| `reconstructed` \| `test_with_errors` (default: `real`) |
| `--file` | Custom CSV path (overrides `--source`) |
| `--disable-all-teams` | Skip “all teams present per week” |
| `--disable-match-points` | Skip match points sum |
| `--disable-round-points` | Skip round match count vs `number_of_teams/2` |
| `--disable-week-points` | Skip week opponent count vs `number_of_teams - 1` |
| `--disable-player-team` | Skip player–team association |
| `--disable-one-player-per-position` | Skip duplicate players per position |

**Issue types (examples):** `missing_teams`, `round_match_count_mismatch`, `week_opponent_count_mismatch`, `match_points_sum_mismatch`, `player_not_associated_with_team`, `multiple_players_same_position`.

```powershell
uv run python data_access/validate_data.py --file database/data/league_results_merged.csv
uv run python data_access/validate_data.py --source test_with_errors
```

See also `database/data/TEST_ERRORS_SUMMARY.md` for the intentional error fixture.

### `scripts/audit_female_league_split.py`

Detects **male/female league collapse** (e.g. `BayL` with 21 teams and no `BayL (D)`). Covers all pairs from `league_mapping.csv`: `BayL`, `LL N1`/`LL N (D)`, `LL S`, `BL N1`/`BL N2`, `BL S1`/`BL S2`, `BZOL S1`, etc.

| Flag | Default | Description |
|------|---------|-------------|
| positional `csv` | required | Semicolon league CSV or Parquet path (Parquet: use merged export CSV for now) |
| `--high-teams-threshold` | `12` | Flag when male league exceeds this and female id is absent |

```powershell
uv run python scripts/audit_female_league_split.py "C:\tmp\bowlyzer\data\legacy_scrape\legacy_scrape_extracted.csv"
uv run python scripts/build_published_dataset.py --with-legacy-scrape   # fails if legacy scrape collapses Damen
```

Use **`legacy_scrape_extracted.csv`** (correct split), not **`legacy_scrap_extracxted.csv`** (typo copy — Damen rows folded into male ids).

---

Ad-hoc script (no argparse): checks **team totals** and **opponent pairing** in `bowling_ergebnisse_real.csv`. Useful for debugging specific reconstruction bugs, not a full league scan.

```powershell
uv run python data_access/check_input_data_issues.py
```

### In the running app (React diagnosis)

| UI route | API | What it checks |
|----------|-----|----------------|
| `/diagnose/liga-wochen` | `GET /league/get_week_matrix` | Missing matchdays per league×season (BayL → 6 weeks; other leagues → team count) |
| `/diagnose/daten-anomalien` | `GET /league/get_data_oddities` | Row-level issues: unnumbered team names, scores &lt; 1, incomplete rows |

These use **merged published data**, not the Sammlung Excel tree. They complement the CLI scripts above after deploy.

---

## 2. `database/input/import_bayerische_meisterschaft_xlsx.py`

**Input:** One or more `.xlsx` in a directory (sheets `Optionen`, `Vorrunde`, `Zwischenlauf`; optional KO sheet with `--include-ko-finale`).  
**Output:**

- Batch: `database/data/tournament_bayerische_meisterschaft_2026_postprocessed.csv` (default)
- Merged into: `database/input/gf_tables_export/gf_tournaments_2026__combined_postprocessed.csv`
- Rebuilds: `database/data/player_stats_merged_plus_tournaments.csv`

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--xlsx-dir` | yes | — | Folder of `*.xlsx` workbooks |
| `--output` | no | `database/data/tournament_bayerische_meisterschaft_2026_postprocessed.csv` | Batch postprocessed CSV |
| `--include-ko-finale` | no | off | Parse KO-Finale bracket as round 3 |

**Input directory convention:** `database/input/bayerische_meisterschaft_xlsx/`

```powershell
# Put workbooks in database\input\bayerische_meisterschaft_xlsx\
uv run python database/input/import_bayerische_meisterschaft_xlsx.py `
  --xlsx-dir database/input/bayerische_meisterschaft_xlsx `
  --include-ko-finale

# Wrapper (same args)
.\scripts\reimport_bayerische_meisterschaft.ps1
```

---

## 3. `database/input/import_clubmeisterschaft_donaubowler_xlsx.py`

**Input:** Clubmeisterschaft Donaubowler layout (openpyxl, `data_only=True`): name col B, six 6-column set blocks, handicap refs cols AO/AP.  
**Not** Clubpokal (separate format).

**Output:**

- `database/data/tournament_clubmeisterschaft_donaubowler_2026_postprocessed.csv`
- Merged into `database/data/tournament_manual_postprocessed.csv`
- Strips this event from GF combined CSV if present; rebuilds player hybrid

| Flag | Default | Description |
|------|---------|-------------|
| `--xlsx` | first `*.xlsx` in `--input-dir` | Single workbook |
| `--input-dir` | `database/input/clubmeisterschaft_donaubowler` | Inbox directory |
| `--output` | `database/data/tournament_clubmeisterschaft_donaubowler_2026_postprocessed.csv` | Batch snapshot |
| `--league-csv` | `database/data/league_results_merged.csv` | Player ID lookup |
| `--season` | from `--year` | e.g. `25/26` |
| `--year` | `2026` | Calendar year for default season label |
| `--date` | `2026-05-15` | ISO date on rows |
| `--location` | `""` | Venue string |
| `--sheet` | first sheet | Worksheet name |
| `--first-data-row` | `2` | First Excel row with player data |

```powershell
uv run python database/input/import_clubmeisterschaft_donaubowler_xlsx.py `
  --xlsx "database/input/clubmeisterschaft_donaubowler\Clubmeisterschaft.xlsx" `
  --date 2026-05-15 --year 2026 --location "Dream Bowl"
```

### VPS auto-import (wrapper, not Excel parser itself)

`scripts/clubmeisterschaft_auto_import.sh` — rclone sync from Dropbox, stable-file wait, hash skip, `docker run` importer, restart app.

| Option / env | Meaning |
|--------------|---------|
| `--dry-run` | Sync only; report import, no write/restart |
| `--sync-only` | rclone only |
| `--skip-restart` | Import without `docker compose restart` |
| `--force` | Import even if SHA256 unchanged |
| `CLUBMEISTERSCHAFT_RCLONE_SRC` | rclone remote path |
| `IMPORT_DATE`, `IMPORT_YEAR`, `IMPORT_SEASON` | Passed to importer |

See `docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md`.

```bash
./scripts/clubmeisterschaft_auto_import.sh --dry-run
CLUBMEISTERSCHAFT_RCLONE_SRC="dropbox:Clubmeisterschaft 2026" ./scripts/clubmeisterschaft_auto_import.sh
```

---

## 4. Legacy `.xls` download (feeds the extractor)

### `scripts/scrape_legacy_liga.py`

Downloads historical **`LB_*.xls`** from bowlingbayern.de into the legacy scrape tree (under work dir / `database/input/legacy_scrape/`). Does **not** parse Excel itself.

| Flag | Description |
|------|-------------|
| `--season` | Required, e.g. `2018-19` |
| `--dry-run` | List URLs only |
| `--interval` | Seconds between downloads (default from script) |

```powershell
uv run python scripts/scrape_legacy_liga.py --season 2018-19 --dry-run
uv run python scripts/scrape_legacy_liga.py --season 2018-19
```

Typical follow-up: `convert_legacy_xls` + `process` on the scrape folder, then merge with `--with-legacy-scrape` in `build_published_dataset.py`.

---

## 5. Tournament CSV chain (usually after GF export, not Excel)

These do **not** read Excel; they transform semicolon CSVs produced by GF export or test generators.

### `database/input/postprocess_tournament_results.py`

Adds cumulative score, stage rank, cut line, overall cumulative.

| Flag | Description |
|------|-------------|
| `--input` | Clean per-game CSV |
| `--output` | Postprocessed CSV |
| `--cut` | Repeatable `ROUND:CUT_TO`, e.g. `--cut 1:8 --cut 2:4` |

```powershell
uv run python database/input/postprocess_tournament_results.py `
  --input database/data/tournament_nordbayerische_2026_clean.csv `
  --output database/data/tournament_nordbayerische_2026_postprocessed.csv `
  --cut 1:8 --cut 2:4
```

### `database/input/generate_tournament_clean_results.py`

Synthetic **clean** tournament rows from a league/player CSV (testing / demos).

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | required | Output clean CSV |
| `--player-source` | `bowling_ergebnisse_real_from_bowlingbayern.csv` | Player pool |
| `--season` | `2026` | |
| `--event-name` | `Nordbayerische Meisterschaft` | |
| `--event-type` | `tournament` | |
| `--location` | Dream Bowl… | |
| `--field-size` | `10` | Player count |
| `--seed` | `nordbayerische-2026` | Deterministic selection |
| `--stage` | built-in 3×6 | `ROUND\|NAME\|DATE\|GAMES` (repeatable) |

```powershell
uv run python database/input/generate_tournament_clean_results.py `
  --output database/data/tournament_nordbayerische_2026_clean.csv `
  --field-size 10 --seed demo-2026
```

### `database/input/generate_geek_tournament_data.py`

No CLI — runs `main()` and writes geek/mythic/clash synthetic tournament CSVs under `database/data/`.

```powershell
uv run python database/input/generate_geek_tournament_data.py
```

### `scripts/transform_gf_tournament_to_canonical.py`

GF table export CSV → canonical per-game + stage meta (used in GF table pipeline).

| Flag | Description |
|------|-------------|
| `--source-csv` | GF export CSV |
| `--field-map-csv` | Field map from `export_gf_tables.py` |
| `--output-csv` | Canonical output |
| `--stage-meta-csv` | Stage metadata output |
| `--season` | e.g. `2026` |
| `--event-name` | Canonical event name |
| `--event-type` | default `tournament` |
| `--handicap` | default `0` |
| `--player-lookup-csv` | optional ID/club lookup |
| `--stage` | Repeatable `stage_id\|name\|cut\|eval\|date\|location\|game_start\|game_end` |

---

## 6. CSV-only league import (not Excel)

### `database/input/convert_bowlingbayern_to_legacy.py`

Reads **Bowling Bayern CSV exports** from `database/input/` (`liga_*_ergebnisse-*.csv`), writes `database/data/bowling_ergebnisse_real_from_bowlingbayern.csv`. No arguments.

```powershell
uv run python database/input/convert_bowlingbayern_to_legacy.py
```

---

## 7. GF / WordPress tools (adjacent; not Excel)

Documented here because tournament **XLSX** imports merge with GF outputs.

### `scripts/export_gf_tables.py`

Pulls Gravity Forms tables (default IDs 124/125) to `database/input/gf_tables_export/`, builds canonical + postprocessed artifacts.

| Flag | Default | Description |
|------|---------|-------------|
| `--tables` | 124/125 | `ID:label` comma list |
| `--output-dir` | `database/input/gf_tables_export` | |
| `--stage-definitions-json` | `gf_tournament_stage_definitions.json` | |
| `--table-tournament-map-json` | `gf_table_tournament_map.json` | |
| `--league-source-csv` | pipeline legacy_out latest | |
| `--site`, `--ck`, `--cs` | env `GF_*` | WordPress GF API |
| `--page-size` | `200` | |
| `--insecure` | off | Skip TLS verify |

```powershell
$env:GF_SITE_BASE_URL = "https://bowlingbayern.de"
$env:GF_CONSUMER_KEY = "..."
$env:GF_CONSUMER_SECRET = "..."
uv run python scripts/export_gf_tables.py --tables "124:sbm,125:nbm"
```

### `scripts/run_gf_pipeline.py`

Incremental/full GF ingest for league forms (not tournament Excel).

| Flag | Description |
|------|-------------|
| `--mode` | `incremental` (default) or `full` |
| `--forms` | Comma-separated form IDs |
| `--site`, `--ck`, `--cs` | Credentials |
| `--field-ids` | Optional field subset |
| `--entries-sort` | `id` or `date_updated` |
| `--page-size` | default `100` |
| `--insecure` | |
| `--skip-legacy` | Skip legacy CSV merge step |

---

## 8. Merge / publish wrappers

### `scripts/merge_league_sources.py`

Merges multiple league CSVs (applies same team normalization as `extract_excel_data` unless `--no-normalize-team-names`).

| Flag | Description |
|------|-------------|
| `--inputs` | Ordered CSV list (last wins on duplicate keys) |
| `--out` | default `database/data/league_results_merged.csv` |
| `--keys` | Dedupe columns (default: league, season, week, round number, match number, team, position, player) |
| `--sep` | default `;` |
| `--duplicates-out`, `--duplicates-non-exact-out` | Optional reports (work dir) |
| `--write-csv` | Also write CSV (default: Parquet only) |
| `--no-normalize-team-names` | |

### `scripts/build_published_dataset.py`

Builds published **Parquet** (and optional CSV): merges historical + GF league + tournaments; optional `--with-legacy-scrape`, `--extra-league`, `--with-player-hybrid`.

```powershell
$env:BOWLYZER_WORK_DATA_DIR = "C:\tmp\bowlyzer\data"
uv run python scripts/build_published_dataset.py --dry-run
uv run python scripts/build_published_dataset.py --with-player-hybrid --with-legacy-scrape
uv run python scripts/build_published_dataset.py --extra-league "C:\tmp\bowlyzer\data\historical_league_results.csv"
```

---

## Quick reference: which tool for what?

| Source | Tool |
|--------|------|
| Liga Excel archive (Sammlung) | `extract_excel_data.py` |
| Legacy web `.xls` | `scrape_legacy_liga.py` → `extract_excel_data.py` |
| Too few weeks / too many teams (scrape CSV) | `scripts/analyze_legacy_scrape_csv.py` |
| Missing weeks (Excel analyze log) | `scripts/analyze_missing_league_weeks.py` |
| Schema / team-week validation (flat CSV) | `data_access/validate_data.py` |
| Bayerische Meisterschaft `.xlsx` | `import_bayerische_meisterschaft_xlsx.py` |
| Clubmeisterschaft Donaubowler `.xlsx` | `import_clubmeisterschaft_donaubowler_xlsx.py` (+ VPS shell script) |
| Bowling Bayern CSV file export | `convert_bowlingbayern_to_legacy.py` |
| GF tournament tables (API) | `export_gf_tables.py` + postprocess chain |
| Publish for app / VPS | `build_published_dataset.py` + `deploy.ps1 -SyncDatabase` |
| Oddities in live merged data | App: `/diagnose/liga-wochen`, `/diagnose/daten-anomalien` |

---

## Related docs

- `database/README.md` — VPS vs build machine paths  
- `database/data/README.md` — Parquet publish and deploy sync  
- `docs/CLUBMEISTERSCHAFT_AUTO_IMPORT.md` — Dropbox → VPS import  
- `DEPLOY.md` — deployment and `-SyncDatabase`
