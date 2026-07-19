# Pipeline: validate

See also [`../DATA_PIPELINE.md`](../DATA_PIPELINE.md).

Publish runs several audits by default (override with `--skip-*-audit` / `--force-publish`).

## Offline / CLI

| Check | Command |
|-------|---------|
| Female league split (scrape / extras) | `uv run python scripts/audit_female_league_split.py` |
| League standings vs Excel | `uv run python scripts/audit_league_standings.py` |
| Player ID ↔ name conflicts | `uv run python scripts/audit_player_id_names.py` |
| Tournament player/club quality | `uv run python scripts/audit_tournament_data_quality.py` |
| Unmapped tournament clubs | `uv run python scripts/audit_club_names.py` |
| Tournament affiliation gaps | `uv run python scripts/audit_tournament_club_gaps.py --out tmp/tournament_affiliation_gaps.csv` |
| PDF import coverage | `uv run python scripts/audit_nbm_imports.py` (and sbm/bm variants) |

## Diagnose UI

| Page | Purpose |
|------|---------|
| `/diagnose/validierung` | Hub |
| `/diagnose/validierung/liga` | Standings |
| `/diagnose/validierung/turniere` | Tournament quality |
| `/diagnose/validierung/clubs` | Unallocated tournament Club → canonical Club (`club_mapping.csv`) |
| `/diagnose/liga-wochen` | Week coverage matrix |
| `/diagnose/datenpipeline` | Artifact / path status |

## Club mapping review loop

1. Open `/diagnose/validierung/clubs`
2. Map labels → canonical Club → save (writes `club_mapping.csv` + updates `clubs_registry`)
3. Republish + rebuild caches ([`../DATA_PIPELINE.md`](../DATA_PIPELINE.md) § Correct publish commands)
