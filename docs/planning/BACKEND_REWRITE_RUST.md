# Backend rewrite — Rust API + relational DB (planning)

**Status:** Deferred — start after a solid amount of legacy tournament/league data is published into the current pipeline.  
**Companion docs:** [`DATA_PIPELINE_PLAN.md`](DATA_PIPELINE_PLAN.md), [`PIPELINE_STATE_OVERVIEW.md`](PIPELINE_STATE_OVERVIEW.md), [`FRONTEND_REFACTORING_PLAN.md`](../FRONTEND_REFACTORING_PLAN.md), [`architecture_analysis.md`](../architecture_analysis.md)  
**Scope:** Follow-up project to replace the Flask + Parquet/CSV serving layer with a structured backend (proper DB, repositories, strict boundaries). Optional language shift to Rust for the API tier.

---

## Prerequisite

Do **not** start the rewrite until:

1. Legacy sources (regional PDFs, GF exports, club Excel, etc.) are imported and published through the unified pipeline.
2. Published artifacts and manifests are trustworthy enough to treat as the migration source of truth.
3. The React frontend covers the main user journeys (strangler-fig cutover far enough that API contracts are stable).

The rewrite should migrate **known-good data**, not chase moving import targets at the same time.

---

## Goals

1. **Postgres (or similar) as source of truth** — normalized schema for players, clubs, teams, seasons, games, tournaments, standings.
2. **Strict architecture** — thin HTTP handlers → services (domain rules) → repositories (SQL only).
3. **Fast, stable REST/JSON API** — same shapes the React app already consumes; version where needed.
4. **Read-optimized serving** — precomputed aggregates / materialized views for heavy pages (league matrix, player career, tournament podiums).
5. **Learning Rust on a real project** — viable if the API layer is the primary Rust surface.

## Non-goals (initial phase)

- Rewriting every import adapter in Rust on day one.
- Replacing Tabulator, chart configs, or frontend table logic.
- Bidirectional sync to GF / Google Sheets.
- Big-bang cutover — strangler-fig alongside Flask until parity is proven.

---

## Current state (as-is)

| Layer | Today |
|-------|--------|
| HTTP | Flask blueprints (`app/routes/`) |
| Domain | `app/services/` (large, some pandas at request time) |
| Data | Parquet + CSV via adapters (`data_access/`, `database/data/`) |
| Cache | Disk JSON caches (`app/cache/`) |
| Imports | Python scripts + `database/tournament_import/`, GF pipeline |
| Frontend | React rewrite in progress; deep links + `?database=` |

Pain points that motivate the rewrite:

- Event names and schemas vary by era (normalization happens in multiple places).
- Heavy pages depend on warmup scripts and disk caches.
- Business logic, I/O, and presentation concerns are intertwined in services.
- No relational constraints (player ID drift, duplicate event labels).

---

## Is Rust a good fit?

**Yes, for the API + domain + persistence layer** — especially read-heavy endpoints (standings, aggregates, podiums, player history).

| Strength | Why it matters here |
|----------|---------------------|
| Performance | Lower latency and memory than Flask + pandas on a small VPS |
| Concurrency | Async I/O to Postgres/Redis without GIL limits |
| Correctness | Explicit types help model seasons, rounds, KO brackets, handicaps |
| Long-running service | Single static binary, predictable ops |

**Harder in Rust (keep in Python initially):**

- Ad-hoc ETL: Excel/PDF parsing, scrapers, one-off data fixes
- Exploratory data work (pandas ergonomics)
- Re-implementing every legacy import adapter

**Pragmatic split:**

```text
Rust API service                    Python (or Rust batch CLIs later)
     │                                        │
     ├─ REST / auth / caching                 ├─ imports (XLSX, PDF, scrape)
     ├─ domain services                       ├─ validate + publish → Postgres
     ├─ repositories (sqlx → Postgres)        └─ manifest / audit reports
     └─ read models / materialized views
```

---

## Target architecture

```text
React (Vite)  →  Rust API (Axum)
                      │
                      ├─ handlers        (HTTP, query params, JSON)
                      ├─ services        (KO rules, handicap, standings logic)
                      ├─ repositories    (SQL only, no business rules)
                      └─ read models     (denormalized tables / MVs for hot paths)

Import jobs (Python)  →  Postgres  ←  optional parquet archive for audit
```

### Suggested Rust stack

| Concern | Options |
|---------|---------|
| HTTP | **Axum** (preferred), Actix Web |
| Async runtime | **Tokio** |
| Database | **Postgres** + **sqlx** (compile-time checked SQL) or Diesel |
| Migrations | sqlx migrate, refinery |
| Serialization | **serde** + JSON |
| Config | figment, envy |
| Caching | Redis or in-process + TTL (mirror current league cache keys) |
| Observability | tracing, metrics |

### Alternatives (if Rust feels too heavy)

- **Python FastAPI + SQLAlchemy + Postgres** — faster delivery, reuse some service logic; less “learn Rust” value.
- **Go + chi/echo + sqlc** — simpler than Rust, still fast; weaker type modeling for complex domain.

Rust is recommended **if** the main motivation includes learning Rust and you accept a steeper first few months on the API crate.

---

## Data model direction (sketch)

Normalize around entities the app already implies:

- `season`, `club`, `team`, `player`, `player_identity` (registry / aliases)
- `competition` (league vs tournament), `event` (specific season instance)
- `game` / `round` / `match` (tournament KO as graph or placement table)
- `standing` / `aggregate` (precomputed per event, per player career slice)

**Read models** (materialized or refreshed on publish):

- League matrix, team history series, player highlights, tournament podiums
- Cache keys similar to today’s `league_response_cache` endpoint revisions

Import pipeline publishes **into** Postgres (and optionally keeps Parquet as an immutable snapshot per manifest run).

---

## Migration strategy (strangler fig)

1. **Freeze API contracts** — document JSON shapes per endpoint the React app uses.
2. **Schema + seed** — migrate published Parquet/CSV into Postgres via one-off loaders (Python is fine).
3. **Vertical slice in Rust** — e.g. `GET /tournament/podiums` + `GET /tournament/get_available_tournaments` behind a feature flag or path prefix.
4. **Expand endpoint by endpoint** — league → team → player; keep Flask for unmigrated routes.
5. **Retire disk JSON caches** when read models + DB indexes cover latency.
6. **Decommission Flask** when parity tests pass and VPS runs the Rust binary only.

Nginx can route `/api/v2/*` to Rust while legacy `/tournament/*` stays on Flask during transition.

---

## Phased roadmap (draft)

| Phase | Focus | Exit criteria |
|-------|--------|----------------|
| **0 — Data** | Finish legacy publish per `DATA_PIPELINE_PLAN.md` | Manifests cover target seasons; audits pass |
| **1 — Schema** | ERD, migrations, seed from published artifacts | Postgres populated; row counts match manifest |
| **2 — Slice** | Rust Axum + sqlx; 2–3 tournament endpoints | React can hit v2 podiums with same JSON |
| **3 — Core read** | League standings, player aggregates, team views | Parity tests vs Flask for golden fixtures |
| **4 — Imports** | Publish job writes Postgres (Python OK) | Single orchestrator updates DB + optional Parquet |
| **5 — Cutover** | VPS deploy Rust service; drop Flask | Cache warmup scripts replaced by MV refresh |

---

## Design principles (carry forward)

1. **Precompute on publish, not on request** — avoid loading full dataframes per HTTP call.
2. **Canonical event names in DB** — display grouping (e.g. strip year suffix) is a view/label layer, not scattered string hacks.
3. **Repositories own SQL; services own rules** — no SQL in handlers.
4. **Stable `database` / tenant concept** — if multi-tenant or multi-corpus remains, make it explicit in schema and routing.
5. **Manifest-driven migrations** — each publish run documents what landed in DB.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Rewrite scope explosion | Rust for API only; Python ETL until imports stabilize |
| Rust learning curve | Start with one vertical slice; pair with sqlx book / Axum examples |
| Domain logic re-bugs | Golden JSON fixtures from current Flask responses |
| VPS 1 GB RAM | Rust helps; still use connection pooling and avoid loading full tables |
| Two backends in flight | Strangler routing + shared Postgres; short overlap period |

---

## Open questions (decide at kickoff)

1. **Postgres hosting** — same VPS, managed DB, or container sidecar?
2. **Auth** — public read-only vs future login (affects crate layout early).
3. **Multi-corpus** — single DB with corpus_id vs separate databases per `?database=`.
4. **Real-time** — is websocket/live updates needed, or REST + cache invalidation enough?
5. **When to port imports to Rust** — never, selectively (PDF hot paths), or full parity?

---

## First spike (when ready)

Suggested 1–2 week spike after Phase 0:

1. Create `bowlyzer-api/` crate (Axum + sqlx + Postgres).
2. Tables: `tournament_event`, `tournament_result`, `player` (minimal).
3. Implement `GET /v2/tournament/podiums` matching current payload shape.
4. Loader script: `tournaments_postprocessed.parquet` → Postgres.
5. One integration test comparing Flask vs Rust JSON for the same season.

If the spike feels good, proceed to Phase 3; if not, reassess FastAPI on the same schema (schema work is not wasted).

---

## References

- Current tournament normalization: `app/utils/tournament_utils.py` (`normalize_tournament_group_name`)
- Cache revision pattern: `app/cache/league_response_cache.py`
- React API hooks: `frontend/src/hooks/useTournament.ts`, `usePlayer.ts`
- Deploy constraints: [`deploy/README.md`](../../deploy/README.md), [`VPS_DISK_AND_USER.md`](../VPS_DISK_AND_USER.md)
