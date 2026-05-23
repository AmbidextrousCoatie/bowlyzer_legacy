# Bowl-A-Lyzer Design System

The visual language for the React rewrite of the Bowl-A-Lyzer frontend. This
document is the source of truth for tokens; component specs follow once the
tokens are stable.

## Direction

- **Variant**: Stadium — dense-analytics × energetic, restrained chrome with
  energy expressed through type and numerals rather than decoration.
- **Modes**: light + dark, both first-class from day one.
- **Brand**: teal anchored on `rainbowPastel[0]` (`#1B8CA6`) — same hue as chart palette slot 0.
- **Neutrals**: Tailwind `zinc` (true neutral, no warm/cool cast).
- **UI font**: Inter.
- **Numeric font**: JetBrains Mono — used for all scores, averages, ranks,
  deltas, scorelines, and table cells holding numbers.
- **Radius**: 4–6 px (sharp-medium, not pill).
- **Shadows**: flat by default; hairline borders. Ambient elevation reserved
  for raised surfaces (popover, dialog, dropdown menu).
- **Density**: mixed — comfortable chrome (15 px base, 8 px grid), compact
  tables (13 px, 4 px row spacing).

Things that stay untouched from the legacy app: chart series configuration,
Tabulator column definitions, the `ColorUtils` data-vis palettes
(`rainbowPastel`, `harmonic10`). The DS only governs UI chrome and typographic
tokens around them.

## Color tokens

### Brand — primary teal (derived from `rainbowPastel[0]`)

Canonical values live in `frontend/src/lib/design-tokens.ts` and `frontend/src/index.css`.

| Token         | Hex       | Usage                                |
| ------------- | --------- | ------------------------------------ |
| `primary-50`  | `#E9F5F8` | Subtle tint backgrounds              |
| `primary-100` | `#CFEAEF` | Hover tint on selected states (light)|
| `primary-200` | `#A5D6E2` | Soft chips, low-emphasis fills       |
| `primary-300` | `#74BECF` | Disabled accent                      |
| `primary-400` | `#45A5BC` | Accent on dark surfaces              |
| `primary-500` | `#1B8CA6` | **= rainbowPastel[0]**               |
| `primary-600` | `#177A90` | **Default accent** (light mode)      |
| `primary-700` | `#136879` | Hover                                |
| `primary-800` | `#0F5663` | Pressed                              |
| `primary-900` | `#0B444F` | Headline accent on subtle tints      |
| `primary-950` | `#07323A` | Reserved                             |

### Neutrals — zinc

| Token       | Hex       | Usage (light → dark)                          |
| ----------- | --------- | --------------------------------------------- |
| `zinc-50`   | `#FAFAFA` | App background (light)                        |
| `zinc-100`  | `#F4F4F5` | Subtle surface, hover row (light)             |
| `zinc-200`  | `#E4E4E7` | Border (light)                                |
| `zinc-300`  | `#D4D4D8` | Strong border, divider                        |
| `zinc-400`  | `#A1A1AA` | Disabled text, placeholders                   |
| `zinc-500`  | `#71717A` | Muted text (light)                            |
| `zinc-600`  | `#52525B` | Secondary text (light)                        |
| `zinc-700`  | `#3F3F46` | Border (dark)                                 |
| `zinc-800`  | `#27272A` | Subtle surface (dark)                         |
| `zinc-900`  | `#18181B` | Surface (dark) / body text (light)            |
| `zinc-950`  | `#09090B` | App background (dark)                         |

### Status — mapped to `rainbowPastel` slots

| Token       | Hex       | Palette slot | Use                            |
| ----------- | --------- | ------------ | ------------------------------ |
| `success`   | `#8CBF8A` | [2] positive | Gains, wins, deltas+           |
| `warning`   | `#E6C86E` | [3]          | Soft attention                 |
| `danger`    | `#E86E56` | [5] negative | Losses, deltas−, errors        |
| `info`      | `#2CA89A` | [1]          | Neutral notice                 |
| `highlight` | `#A04CBF` | [9]          | Emphasis / cut-line highlight  |

Status colors are used for foreground glyphs/text and thin accents — not for
filled backgrounds, except in toast/banner components.

### Semantic mapping

Build components against semantic tokens, not raw ramps. Only the table below
flips between light and dark.

| Semantic              | Light                  | Dark                   |
| --------------------- | ---------------------- | ---------------------- |
| `bg`                  | `zinc-50`              | `zinc-950`             |
| `surface`             | `#FFFFFF`              | `zinc-900`             |
| `surface-subtle`      | `zinc-100`             | `zinc-800`             |
| `surface-raised`      | `#FFFFFF`              | `zinc-800`             |
| `border`              | `zinc-200`             | `zinc-800`             |
| `border-strong`       | `zinc-300`             | `zinc-700`             |
| `fg`                  | `zinc-900`             | `zinc-50`              |
| `fg-muted`            | `zinc-500`             | `zinc-400`             |
| `fg-subtle`           | `zinc-400`             | `zinc-500`             |
| `accent`              | `primary-600`          | `rainbowPastel[1]`     |
| `accent-hover`        | `primary-700`          | `primary-400`          |
| `accent-fg`           | `#FFFFFF`              | `#FFFFFF`              |
| `accent-tint`         | `primary-50`           | `rgba(27,140,166,.14)` |
| `focus-ring`          | `primary-500`          | `primary-300`          |
| `success-fg`          | `#5A9E58` (light)      | `rainbowPastel[2]`     |
| `danger-fg`           | `#C45A42` (light)      | `#F09580`              |

## Typography

### Families

```
--font-sans: 'Inter', -apple-system, system-ui, 'Segoe UI', sans-serif;
--font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
```

Inter is loaded with weights `400, 500, 600, 700, 800`. JetBrains Mono with
`400, 500, 600, 700`.

### Feature settings

```
font-feature-settings: 'cv11', 'ss01', 'tnum';
```

`tnum` (tabular numerals) is **on by default** for the entire app — this is
the most important typographic decision in a stats UI.

### Scale

| Role         | Size | Weight | Tracking | Line-height | Font  |
| ------------ | ---- | ------ | -------- | ----------- | ----- |
| Display      | 56   | 800    | -0.03em  | 1.0         | sans  |
| H1           | 36   | 700    | -0.02em  | 1.1         | sans  |
| H2           | 24   | 700    | -0.015em | 1.2         | sans  |
| H3           | 18   | 600    | -0.01em  | 1.3         | sans  |
| Body         | 15   | 400    | 0        | 1.55        | sans  |
| Small        | 13   | 400    | 0        | 1.5         | sans  |
| Caption      | 12   | 500    | 0        | 1.4         | sans  |
| Label (caps) | 11   | 600    | 0.1em    | 1.2         | sans  |
| Stat XL      | 36   | 600    | -0.02em  | 1.0         | mono  |
| Stat L       | 28   | 600    | -0.01em  | 1.0         | mono  |
| Stat M       | 20   | 500    | -0.005em | 1.1         | mono  |
| Code / cell  | 13   | 500    | 0        | 1.4         | mono  |

Labels are uppercase, used over stat cards and section eyebrows.

### Mono usage rules

Use the mono font for: scores, averages, ranks, win/loss records, deltas,
scorelines, percentages in stat cards, all numeric table cells. Keep
labels and team names in Inter.

## Spacing

8 px grid for chrome, 4 px sub-grid for compact tables.

| Token   | Value | Use                                  |
| ------- | ----- | ------------------------------------ |
| `xs`    | 4px   | Compact table row padding, icon gap  |
| `sm`    | 8px   | Default gap                          |
| `md`    | 12px  | Card inner padding (compact)         |
| `lg`    | 16px  | Card inner padding (default)         |
| `xl`    | 24px  | Section gaps, card outer padding     |
| `2xl`   | 32px  | Page padding (desktop)               |
| `3xl`   | 48px  | Section separation                   |
| `4xl`   | 64px  | Major section separation             |

## Radius

| Token        | Value | Use                                  |
| ------------ | ----- | ------------------------------------ |
| `radius-xs`  | 3px   | Inner pills, tag chips               |
| `radius-sm`  | 4px   | Inputs, buttons, segmented controls  |
| `radius-md`  | 6px   | Cards, popovers                      |
| `radius-lg`  | 8px   | Dialog, raised surfaces              |
| `radius-full`| 999px | Avatars, status dots                 |

No `radius-full` on buttons — keep them rectangular.

## Elevation / shadow

Default state is **flat**: surfaces sit on the page with a 1 px border and
nothing else. Shadows enter only when a surface lifts above the page plane.

| Token       | Value                                                        | Use                          |
| ----------- | ------------------------------------------------------------ | ---------------------------- |
| `shadow-0`  | none                                                         | Cards, page surfaces         |
| `shadow-1`  | `0 1px 2px rgba(9,9,11,0.06), 0 1px 1px rgba(9,9,11,0.04)`   | Hovered card                 |
| `shadow-2`  | `0 4px 12px rgba(9,9,11,0.08), 0 1px 2px rgba(9,9,11,0.04)`  | Popover, dropdown menu       |
| `shadow-3`  | `0 16px 32px rgba(9,9,11,0.12), 0 4px 8px rgba(9,9,11,0.06)` | Dialog, command palette      |

In dark mode shadows become near-imperceptible; rely on `border-strong`
instead for separation.

## Borders

- Default border: 1 px solid `border` semantic.
- Strong border (table headers, separators between dense regions): 1 px solid
  `border-strong`.
- Focus ring: 2 px solid `focus-ring`, 2 px offset on dark surfaces, 0 px
  offset on solid colored backgrounds.
- Selected state on segmented controls: filled `accent` background, no border.

## Motion

- Default duration: 120 ms.
- Hover/press transitions: `border-color`, `background-color`, `transform`.
- Easing: `cubic-bezier(0.4, 0, 0.2, 1)` (Tailwind default).
- Disable for `prefers-reduced-motion`.

Avoid choreography. Snap-to-target beats animated reveals in a stats UI.

## Iconography

- Library: Lucide.
- Default size: 16 px in dense rows, 18 px in chrome, 20 px in headers.
- Stroke width: 1.75 px.
- Color follows surrounding text by default (`currentColor`).

## Data visualization

The chart palettes (`rainbowPastel`, `harmonic10`) are owned by
`frontend/src/lib/color-utils.ts` (port of legacy ColorUtils) and **must not
be redefined for series colors**. UI chrome (accent, status) is aligned to
`rainbowPastel` indices; the DS also documents:

- `chart.bg` — chart canvas background (= `surface` semantic).
- `chart.gridline` — `border` semantic, opacity 0.6.
- `chart.axis` — `fg-muted` semantic.
- `chart.crosshair` — `accent`, opacity 0.5.

Series colors come from `ColorUtils.getCurrentPalette()` unchanged.

## Component direction (high level — full specs land later)

- **Buttons**: rectangular with 4 px radius. Variants: `primary` (filled
  accent), `secondary` (border + transparent), `ghost` (text-only with
  hover tint), `danger`. Sizes: `sm` (28 px), `md` (32 px), `lg` (40 px).
- **Segmented control**: replaces `btn-group` for ≤ 4 mutually exclusive
  options (e.g. Game/Spiel selector).
- **Combobox**: replaces button groups for high-cardinality filters (teams,
  seasons with many entries). Built on Radix Popover + listbox.
- **Section** (layout primitive): the major content unit per page. Eyebrow
  label + H2 + content body, separated from neighbours by `space-y-12`. No
  card border, no background — sections live directly on `background`. This
  is what every block on Liga / Spieler / Turnier renders into.
- **Card** (KPI tile only): 1 px border, no shadow, 16 px padding. Used for
  small KPI tiles inside a section (e.g. tournament summary cards, lifetime
  averages, player section tiles), never as a wrapper around a whole block.
  Variants: default (`border-border bg-surface`), winner-accent
  (`border-accent bg-accent-tint`).
- **Stat card**: small uppercase label, large mono number, optional delta in
  status color. Implemented as a Card with `text-stat-md` numeral.
- **Table** (Tabulator-themed): 13 px body, 11 px caps header, 4 px vertical
  cell padding, hairline row separators, hover row tint = `surface-subtle`.
- **Page header**: H1 + optional eyebrow label, 32 px bottom margin to the
  filter rail.
- **Filter rail**: sticky to the top of the scroll container with backdrop
  blur and a hairline bottom border. Inline label above each control.

## Tooling notes

- Tailwind v4 with `@theme` directive driving the tokens above.
- `next-themes`-style class-based dark mode (`<html data-theme="dark">`).
- Icons: `lucide-react`.
- Behavior primitives: Radix UI.
- Component layer: shadcn/ui copied into the repo, retuned to these tokens.
