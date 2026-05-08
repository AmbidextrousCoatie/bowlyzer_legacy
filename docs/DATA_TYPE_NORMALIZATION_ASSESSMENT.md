# Data Type Normalization Assessment

## Context

Recent changes introduced two competing needs:

1. Stability and responsiveness for large mixed CSV sources (`db_real_merged`, player hybrid sources)
2. Correct numeric/boolean behavior in league and player computations

To suppress pandas mixed-type inference warnings and reduce parsing variability, CSV loading was switched to string-first parsing (`dtype=str`, `low_memory=False`). This solved warning noise and some latency spikes, but exposed downstream assumptions where code expected numeric/bool columns to already be typed.

## Observed Runtime Effects

### Confirmed error class (current)

From terminal logs (example):

- `Error getting standings for league KL N2: agg function failed [how->mean,dtype->object]`
- `could not convert string to float: '0.00.00.01.00.00...'`

This indicates aggregate paths are still operating on object/string columns (not normalized numeric columns) in some league standings logic.

### Other previously observed effects

- Player lifetime rank/mean code paths failed on string `Score` values until explicit coercion was added.
- Filter behavior changed when comparing bool/int filter values against string-loaded columns.

These are expected side effects of string-first loading when normalization is not centralized.

## Root Technical Issue

Type conversion and validation are currently fragmented:

- some conversion in adapters
- some conversion in service methods
- some implicit assumptions (e.g. groupby mean on already-numeric columns)

As data sources broaden (historical + GF + merged + hybrid), this increases risk of:

- silent mismatches
- endpoint-specific regressions
- repeated conversion overhead

## Recommended Work Package

### Goal

Implement **schema-aware normalization at load boundaries** so all downstream services operate on stable dtypes.

### Scope

1. Define canonical dtype profile for core columns:
   - numeric: `Score`, `Points`, `Week`, `Round Number`, `Match Number`
   - bool-like: `Input Data`, `Computed Data`
   - string identifiers/text: `League`, `Team`, `Player`, `Player ID`, etc.
2. Add one shared normalization utility (single source of truth).
3. Apply it in:
   - `DataManager` load path
   - `DataAdapterPandas` load path
4. Remove/trim ad hoc conversions in service methods.
5. Add diagnostics (invalid-coercion counts per column).
6. Regression-test key endpoints:
   - league season standings and league averages
   - player search / seasons / lifetime stats
   - tournament routes with fallback behavior

## Effort Estimate

- Phase 1: schema inventory + instrumentation: **0.5-1 day**
- Phase 2: normalization utility + loader integration: **1-2 days**
- Phase 3: service cleanup and fixes: **1-2 days**
- Phase 4: endpoint regression and perf validation: **1 day**

Total: **~3.5 to 6 days** (depending on breadth of regression cases).

## Side Effects / Risks

- Filter result changes where string-equality previously masked type issues.
- Rows with invalid numerics become explicit `NaN` and may be excluded from aggregates.
- Legacy assumptions in older routes may break until migrated.

## Performance Expectations

- Load-time: slight increase from explicit normalization.
- Request-time: expected decrease from eliminating repeated per-endpoint coercion.
- Net: better tail latency and fewer runtime type exceptions on aggregate endpoints.

## Immediate Mitigation While Full Package Is Pending

1. Keep string-first CSV ingest for stability.
2. Ensure all aggregate-heavy paths explicitly coerce numerics before groupby/mean/sum.
3. Keep filter layer type-aware (bool/int/string comparisons).
4. Track all new type errors as migration targets for normalization centralization.

## Acceptance Criteria for Full Migration

- No pandas dtype warnings in server logs for active merged/hybrid sources.
- No `dtype->object` aggregate errors in league/player endpoints.
- Consistent API outputs across:
  - `db_real_pipeline_gf`
  - `db_real_historical_league`
  - `db_real_merged`
  - player hybrid source
- Measurable improvement in player search responsiveness and league standings endpoint latency.
