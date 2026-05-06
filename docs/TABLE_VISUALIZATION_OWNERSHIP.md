# Table visualization ownership (agreed decisions vs. shipped state)

**Last reviewed:** 2026-05-06  
**Context:** Follow-up from the “less distractful tables” discussion: split **semantic intent** (backend / payload) from **visual policy** (frontend / Stadium skin). Detailed narrative lives in [.specstory/history/2026-05-05_06-10-28Z-table-design-and-responsibilities-analysis.md](../.specstory/history/2026-05-05_06-10-28Z-table-design-and-responsibilities-analysis.md).

This file is the **checkpoint**: what we decided, and whether the repo reflects it yet.

---

## Summary table

| Topic | Intended owner | Default / rule | Implemented? | Notes (where to look) |
| --- | --- | --- | --- | --- |
| **Row / cell grid lines (“chrome”)** | Frontend only — no backend fields | **Off** by default for generic tables | **Partial** | React `.ds-tabulator` still draws a hairline **between every body row** (`.tabulator-row + .tabulator-row`). That contradicts “grid off”; needs a deliberate DS toggle when we prioritize this. Legacy Tabulator Bootstrap paths unchanged. [`frontend/src/lib/datatable/datatable.css`](../frontend/src/lib/datatable/datatable.css) |
| **Semantic row separators** (e.g. summary vs. players when row layout shifts) | **Both:** backend marks intent; frontend renders look | Backend: `separator_before` and/or `rowType`; frontend: separator styling, never row-index hacks | **Partial** | Backend emits `separator_before` (+ `rowType`) for league tables touched in services. Legacy `tables.html` applies `.tab-row-separator-before` + CSS. React `createDataTable` toggles the same class and strips conflicting inline `borderTop`, but **`datatable.css` has no `.tab-row-separator-before` rule**, so emphasis may be weak vs legacy. [`app/services/league_service.py`](../app/services/league_service.py), [`app/templates/components/tables.html`](../app/templates/components/tables.html), [`frontend/src/lib/datatable/createDataTable.ts`](../frontend/src/lib/datatable/createDataTable.ts) |
| **Table zebra `striped` (`config.striped`)** | Frontend-only policy; backend should stop being source of truth | Default **off** globally in DS | **Not done** | Legacy Bootstrap builder still respects `config.striped`. React path does not use Bootstrap, but legacy Jinja Tabulator styling still zebra-stripes even rows globally. Payloads may still ship `striped`. |
| **`stripedColGroups` / column-group striping** | Discussed under “striping”; still often treated as semantic “compare groups” | Keep as backend **hint** until we explicitly migrate | **Yes (unchanged)** | Both legacy Tabulator JS and React read `tableConfig.stripedColGroups === true`. Services still set it where tables need alternating group shading. [`createDataTable.ts`](../frontend/src/lib/datatable/createDataTable.ts), [`tables.html`](../app/templates/components/tables.html) |
| **`hover` row highlight** | Frontend only | Prefer **on** for pointer devices; DS tokens | **Yes (React)** | `.ds-tabulator .tabulator-row:hover` uses DS surface token. Not driven by backend `config.hover`. [`datatable.css`](../frontend/src/lib/datatable/datatable.css) |
| **`compact` density** | Agreed: frontend-owned; backend field ideally ignored later | Default **compact on** at DS layer | **Not done** | React Tabulator still keys layout off **`data.config.compact`** (`fitData` vs `fitColumns`, padding). Need to invert to “frontend default compact, optional loosen” without breaking backend payloads. [`createDataTable.ts`](../frontend/src/lib/datatable/createDataTable.ts) |
| **Sticky header** | Frontend-only (behavior + CSS) when body scrolls | **On** when table body scrolls (DS) | **Unclear / minimal** | No explicit sticky-header implementation in React datatable code; scrolling is on `.tabulator-tableholder`. Tabulator may or may not give “sticky captions” parity with legacy Bootstrap `stickyHeader`. Follow-up item. |
| **Sticky / frozen columns** | Backend semantic (`frozen`), frontend renders | Frozen columns remain a backend hint | **Yes** | `frozen` on groups/columns; React applies frozen cell/header styles + inset shadow. [`datatable.css`](../frontend/src/lib/datatable/datatable.css) |
| **`width`** | Shared | Backend **hint**; frontend min/max + `widthGrow` / density | **Yes (historical)** | Column `width` + compact layout adjustments in `createDataTable`. |
| **`highlighted` column groups** | Backend intent, frontend tokens | Palette from DS / `--highlight-*` CSS vars where used | **Yes** | `tab-group-highlighted` / `tab-col-highlighted` in React CSS; backend sets `highlighted` on groups. |
| **Heatmaps** | Keep domain-sensitive computation; avoid per-page hardcoded scales where possible | “As-is” for now with possible future tightening (scale in payload, colors from DS) | **Not refactored** | Tournament/league flows still rely on established patterns; no new cross-cutting contract landed in this track. |
| **Single shared table policy (“no page-level DOM hacks”)** | Frontend architecture goal | All tables go through one policy layer (`DataTable` / shared legacy renderer) | **Aspiration** | Legacy tournament pages still have extra passes; React should converge on `createDataTable` options over time. |
| **`row_metadata` / `cell_metadata` contract** | Backend supplies structure; frontend applies | Document keys in Python + TS types | **Partial** | `TableData` docstring lists `separator_before`, `styling`, `rowType`. TS `RowMetaEntry` includes `separator_before`, `rowType`. Not every consumer maps `kind` yet; **`rowType` is the canonical server field.** [`app/models/table_data.py`](../app/models/table_data.py), [`frontend/src/lib/datatable/types.ts`](../frontend/src/lib/datatable/types.ts) |

---

## Short narrative (current architecture)

1. **Backend** should continue to ship **meaning** (“this row starts a summary block”, “this group is highlighted”, widths as hints, default sort).
2. **Frontend** should own **how that looks**: density, grids, hover, separator *drawing*, scrollbar chrome, frozen presentation.
3. **Practical gap:** React DS theme still behaves like “light grid everywhere” (`border-top` per row), while polish items from the conversation (grid off by default, compact defaulted in frontend regardless of payload, sticky header story, explicit separator styling in CSS) remain **finish work**.

---

## Next implementation checkpoints (when resuming)

- [ ] Add explicit **`horizontalLines` / `verticalLines` (or equivalent)** to `DataTableOptions` defaulting **off**, and remove implicit per-row borders in `.ds-tabulator` when off.
- [ ] Add **`tab-row-separator-before`** rules to [`datatable.css`](../frontend/src/lib/datatable/datatable.css) (and verify token strength vs semantic border).
- [ ] Shift **`compact`** to a frontend default with optional payload override documented as transitional.
- [ ] Audit backend payloads for **`striped`** / **`hover`** / **`stickyHeader`** and mark deprecated vs still consumed by legacy Bootstrap tables.
- [ ] Decide whether **`stripedColGroups`** stays backend-only indefinitely or gains a frontend override (decision intentionally deferred vs “row striped”).

When this list is mostly checked, replace “Partial / Not done” in the table above with ✅ and narrow the narrative.
