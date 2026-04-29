# League API v1 Contract

This document defines a stable backend contract for the new League frontend.

## Goals

- Keep existing data semantics for tables and graphs.
- Normalize parameter names and response envelopes.
- Introduce versioned routes for long-term frontend stability.
- Support fast, mobile-friendly, deep-linkable UX in a modern SPA.

## Versioning and Routing

- Base path: `/api/v1/league`
- Method: `GET` for read-only data endpoints
- Content type: `application/json`
- Encoding: UTF-8

Legacy routes may continue to exist during migration, but the new frontend should consume only `/api/v1/league/*`.

## Global Query Parameters

All endpoints use these canonical names where applicable:

- `league`: string
- `season`: string
- `week`: integer (`>= 1`)
- `team`: string
- `database`: string (optional source selector)
- `lang`: string (`de` or `en`, optional, default server setting)

Rules:

- Reject missing required parameters with `400`.
- Reject invalid types with `400` (for example non-integer `week`).
- Unknown optional parameters are ignored.

## Standard Response Envelopes

All successful responses include:

- `success: true`
- `data: ...`
- `meta: { requestId, generatedAt, version }`

All failures include:

- `success: false`
- `error: { code, message, details? }`
- `meta: { requestId, generatedAt, version }`

### Success Envelope

```json
{
  "success": true,
  "data": {},
  "meta": {
    "requestId": "d6efce42-92cd-4e6a-8c8d-6b5319c8fca2",
    "generatedAt": "2026-04-29T19:45:00Z",
    "version": "v1"
  }
}
```

### Error Envelope

```json
{
  "success": false,
  "error": {
    "code": "MISSING_REQUIRED_PARAM",
    "message": "Missing required parameter: season",
    "details": {
      "parameter": "season"
    }
  },
  "meta": {
    "requestId": "d6efce42-92cd-4e6a-8c8d-6b5319c8fca2",
    "generatedAt": "2026-04-29T19:45:00Z",
    "version": "v1"
  }
}
```

## Canonical Data Schemas

### TableResponse

Use this for all table endpoints (compatible with existing `TableData` semantics).

```json
{
  "title": "League Standings",
  "description": "Final table for selected season",
  "columns": [
    {
      "title": "",
      "columns": [
        { "title": "Team", "field": "team", "sortable": true, "align": "left" },
        { "title": "Points", "field": "points", "sortable": true, "align": "center" }
      ]
    }
  ],
  "rows": [
    { "team": "ABC 1", "points": 42 },
    { "team": "XYZ 1", "points": 39 }
  ],
  "config": {
    "defaultSort": { "field": "points", "dir": "desc" }
  },
  "metadata": {}
}
```

Notes:

- Prefer `rows` (object array) in v1 for frontend ergonomics.
- If backend currently emits positional arrays, provide a compatibility adapter and migrate to object rows.

### ChartResponse

Use this for line/scatter/bar charts.

```json
{
  "chartType": "line",
  "title": "Points Progression",
  "xAxis": {
    "label": "Week",
    "categories": [1, 2, 3, 4]
  },
  "yAxis": {
    "label": "Points"
  },
  "series": [
    {
      "id": "team_abc_1",
      "name": "ABC 1",
      "data": [2, 5, 8, 10]
    }
  ],
  "options": {},
  "metadata": {}
}
```

### ListResponse

Use for dropdown/filter option endpoints.

```json
{
  "items": [
    { "value": "BAYL", "label": "Bayernliga" }
  ]
}
```

### CardsResponse

Use for card tiles and summary blocks.

```json
{
  "cards": [
    {
      "id": "league_leader",
      "title": "League Leader",
      "value": "ABC 1",
      "subtitle": "after week 12"
    }
  ]
}
```

## League v1 Endpoint Set (Phase 1)

These endpoints are enough to launch the new League page with the selected scope.

### Filter/Selector Endpoints

- `GET /api/v1/league/options/leagues`
  - Required: none
  - Optional: `season`, `database`
  - Returns: `ListResponse`

- `GET /api/v1/league/options/seasons`
  - Required: `league`
  - Optional: `team`, `database`
  - Returns: `ListResponse`

- `GET /api/v1/league/options/weeks`
  - Required: `league`, `season`
  - Optional: `database`
  - Returns: `ListResponse`

- `GET /api/v1/league/options/teams`
  - Required: `league`, `season`
  - Optional: `database`
  - Returns: `ListResponse`

### F1: League Overview (league only)

- `GET /api/v1/league/aggregation/averages-history`
  - Required: `league`
  - Returns: `ChartResponse`

- `GET /api/v1/league/aggregation/points-to-win-history`
  - Required: `league`
  - Returns: `ChartResponse`

- `GET /api/v1/league/aggregation/top-team-performances`
  - Required: `league`
  - Returns: `TableResponse`

- `GET /api/v1/league/aggregation/top-individual-performances`
  - Required: `league`
  - Returns: `TableResponse`

- `GET /api/v1/league/aggregation/record-games`
  - Required: `league`
  - Returns: `TableResponse`

### F2: Season Overview (league + season)

- `GET /api/v1/league/season/standings`
  - Required: `league`, `season`
  - Returns: `TableResponse`

- `GET /api/v1/league/season/timetable`
  - Required: `league`, `season`
  - Returns: `ListResponse` or domain-specific schedule object inside `data`

- `GET /api/v1/league/season/individual-averages`
  - Required: `league`, `season`
  - Optional: `week`, `team`
  - Returns: `TableResponse`

- `GET /api/v1/league/season/team-points`
  - Required: `league`, `season`
  - Returns: `ChartResponse`

- `GET /api/v1/league/season/team-positions`
  - Required: `league`, `season`
  - Returns: `ChartResponse`

- `GET /api/v1/league/season/team-averages`
  - Required: `league`, `season`
  - Returns: `ChartResponse`

### F3: Match Day (league + season + week)

- `GET /api/v1/league/matchday/standings`
  - Required: `league`, `season`, `week`
  - Returns: `TableResponse`

- `GET /api/v1/league/matchday/honor-scores`
  - Required: `league`, `season`, `week`
  - Returns: cards/list domain object

### F4: Team Week Details (league + season + week + team)

- `GET /api/v1/league/team-week/classic`
  - Required: `league`, `season`, `week`, `team`
  - Returns: `TableResponse`

- `GET /api/v1/league/team-week/individual-scores`
  - Required: `league`, `season`, `week`, `team`
  - Returns: `TableResponse`

- `GET /api/v1/league/team-week/head-to-head`
  - Required: `league`, `season`, `week`, `team`
  - Optional: `viewMode` (`own_team` default)
  - Returns: `TableResponse`

### Optional Advanced Blocks

- `GET /api/v1/league/season/team-vs-team`
  - Required: `league`, `season`
  - Optional: `week`
  - Returns: `TableResponse` with heatmap metadata in `metadata`

## TypeScript Interfaces (Frontend)

```ts
export type ApiVersion = "v1";

export interface ResponseMeta {
  requestId: string;
  generatedAt: string;
  version: ApiVersion;
}

export interface ApiError {
  code:
    | "MISSING_REQUIRED_PARAM"
    | "INVALID_PARAM"
    | "NOT_FOUND"
    | "INTERNAL_ERROR"
    | "UNAUTHORIZED"
    | "FORBIDDEN";
  message: string;
  details?: Record<string, unknown>;
}

export interface ApiSuccess<T> {
  success: true;
  data: T;
  meta: ResponseMeta;
}

export interface ApiFailure {
  success: false;
  error: ApiError;
  meta: ResponseMeta;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiFailure;

export interface TableColumn {
  title: string;
  field: string;
  sortable?: boolean;
  filterable?: boolean;
  width?: string;
  align?: "left" | "center" | "right";
  format?: string;
  decimalPlaces?: number;
  tooltip?: string;
}

export interface TableColumnGroup {
  title: string;
  columns: TableColumn[];
  frozen?: "left" | "right";
  highlighted?: boolean;
}

export interface TableConfig {
  defaultSort?: { field: string; dir: "asc" | "desc" };
  [key: string]: unknown;
}

export interface TableDataV1 {
  title?: string;
  description?: string;
  columns: TableColumnGroup[];
  rows: Array<Record<string, unknown>>;
  config?: TableConfig;
  metadata?: Record<string, unknown>;
}

export type ChartType = "line" | "bar" | "scatter" | "area";

export interface ChartSeries {
  id: string;
  name: string;
  data: Array<number | null>;
  color?: string;
  meta?: Record<string, unknown>;
}

export interface ChartDataV1 {
  chartType: ChartType;
  title?: string;
  xAxis: { label?: string; categories: Array<string | number> };
  yAxis?: { label?: string };
  series: ChartSeries[];
  options?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface OptionItem {
  value: string;
  label: string;
  meta?: Record<string, unknown>;
}

export interface ListDataV1 {
  items: OptionItem[];
}
```

## HTTP Status Rules

- `200`: successful read
- `400`: missing or invalid query params
- `404`: requested entity does not exist for given filters
- `500`: unexpected server failure

Do not return `200` for error payloads.

## Caching and Performance Rules

- Emit `ETag` and `Cache-Control` for selector endpoints (`options/*`).
- Support gzip/brotli via nginx.
- Keep payload keys stable; add new fields backward-compatibly.
- Add optional `?includeMeta=false` later if payload trimming is needed.

## Migration Plan (Legacy -> v1)

1. Add v1 routes as thin adapters over current services.
2. Normalize parameter names and validation in adapters.
3. Wrap legacy payloads into standard success/error envelopes.
4. Add contract tests for each endpoint:
   - required params
   - invalid param types
   - happy path schema validation
   - not-found behavior
5. Point new frontend only to `/api/v1/league/*`.
6. Deprecate legacy routes after frontend cutover and soak period.

## Non-Goals for Phase 1

- No breaking changes to business logic or database schema.
- No removal of existing legacy endpoints during initial rollout.
- No requirement to rewrite team/player/tournament pages yet.
