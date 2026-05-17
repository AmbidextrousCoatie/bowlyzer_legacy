# Bowl-A-Lyzer

Bowling league / tournament / player statistics app. Currently a Flask + Jinja
+ Bootstrap monolith; a React rewrite is in progress under `frontend/`.

## Repo layout

- `app/` — Flask backend. Routes (`league`, `team`, `player`, `tournament`,
  `main`), services, models, and the legacy Jinja templates + vanilla JS in
  `app/templates/` and `app/static/`. Source of truth for data access.
- `business_logic/`, `data_access/`, `database/`, `pipeline/` — Python data
  layer feeding the Flask routes. **Do not touch as part of frontend work.**
- `frontend/` — new Vite-Plus + React 19 + TypeScript app. Currently a bare
  scaffold; the visual rewrite lands here.
- `designsystem/` — design tokens and component direction for the rewrite.
  See `designsystem/design-system.md`. **All UI work in `frontend/` must
  conform to it.**
- `tests/` — Python tests for the backend.

## Migration goal

Visual overhaul of the existing Jinja frontend into React. Hard rules:

1. **Do not edit data access** (Python services, route handlers, query logic).
2. **Do not redesign charts or table column logic.** Series configs, Tabulator
   column definitions, formatters, and the `ColorUtils` chart palettes
   (`rainbowPastel`, `harmonic10`) carry over unchanged. Wrap them in thin
   React components.
3. **Drop Bootstrap** and the UX conventions that come with it. Replace with
   the Stadium design system in `designsystem/design-system.md`.
4. UX improvements (filter UX, mobile layout, loading states) are in scope —
   bake them into the design system primitives so every page inherits them.

Strangler-fig cutover: Flask continues to serve JSON; React renders pages one
at a time. Keep deep links (including the `?database=…` query param) working.

## Design system

Stadium variant — refined blue (Tailwind `blue-600`), zinc neutrals, Inter +
JetBrains Mono, mixed density, flat with hairline borders, light + dark from
the start. Full spec in `designsystem/design-system.md`. Tailwind v4 + Radix +
shadcn/ui copied in is the planned stack.

When building any UI in `frontend/`, read `designsystem/design-system.md`
first and use its semantic tokens — never hardcode hex values, never reach
for Bootstrap utility classes.

## Tooling

- **Python**: always via `uv` (`uv run python`, `uv run pytest`). Never call
  `python`/`python3`/`pip` directly. Lint with `ruff`.
- **Frontend**: Vite-Plus via the `vp` CLI (`vp dev`, `vp build`, `vp check`,
  `vp test`, `vp lint`). Do not invoke pnpm/npm/Vite directly. See
  `frontend/AGENTS.md` for the full Vite-Plus contract.
- **Backend dev server**: started outside Claude Code via `start.sh`. Do not
  start it as a background task.
- **Git/GitHub**: `gh` CLI for PRs, issues, checks.

## Architecture conventions

- DDD-leaning Python layout (routes → services → data access). Keep that
  shape when adding endpoints.
- Run all tests before committing.
- For architecture audits, run parallel agents (frontend TS, backend Python,
  test coverage) and consolidate findings.

## German org hierarchy (bowling)

Real-world structure has three tiers; the app only models the bottom two:

| Tier | Example | In Bowl-A-Lyzer |
|------|---------|-----------------|
| **Verein** (association) | BV 68 Regensburg | **Not modeled** — unlikely to be added |
| **Club** | Donaubowler Regensburg | Club selector on `/mannschaft`, club matrix, `get_club_matrix` |
| **Team** / Mannschaft | 1, 2, 3 (trailing number on team name) | Full `team_name` (e.g. `Donaubowler Regensburg 2`), team detail + Liga links |

Team strings are split with `_split_club_and_team_number` / `frontend/src/lib/teamUtils.ts`
(base name + optional number). UI on the Mannschaft page says **Club**, not Verein —
that page is Club → Team(s), not Verein → Club.

## Out of scope (for now)

- Pruning chart libraries (Chart.js + ECharts + a sliver of Highcharts coexist
  — audit only, do not act).
- Replacing Tabulator.
- Moving i18n off the server (`/league/get_translations` keeps working;
  React wraps it in a hook).
- Any backend API changes.
- **Verein**-level views or data (see German org hierarchy above).
