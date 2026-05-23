/**
 * UI chrome tokens aligned with TEAM_COLOR_PALETTES.rainbowPastel (ColorUtils).
 * Chart series colors still come from color-utils.ts unchanged.
 */

import { SEMANTIC_COLOR_MAPPINGS, TEAM_COLOR_PALETTES } from "./color-utils";

/** Brand anchor — rainbowPastel[0], stripe default, league column tint. */
export const BRAND_PRIMARY = TEAM_COLOR_PALETTES.rainbowPastel[0];

/** Primary ramp derived from BRAND_PRIMARY (teal); keep in sync with index.css @theme. */
export const PRIMARY_RAMP = [
  { token: "primary-50", hex: "#E9F5F8" },
  { token: "primary-100", hex: "#CFEAEF" },
  { token: "primary-200", hex: "#A5D6E2" },
  { token: "primary-300", hex: "#74BECF" },
  { token: "primary-400", hex: "#45A5BC" },
  { token: "primary-500", hex: "#1B8CA6" },
  { token: "primary-600", hex: "#177A90" },
  { token: "primary-700", hex: "#136879" },
  { token: "primary-800", hex: "#0F5663" },
  { token: "primary-900", hex: "#0B444F" },
  { token: "primary-950", hex: "#07323A" },
] as const;

/** Status colors mapped to rainbowPastel semantic slots (see SEMANTIC_COLOR_MAPPINGS). */
export const STATUS_COLORS = {
  success: TEAM_COLOR_PALETTES.rainbowPastel[SEMANTIC_COLOR_MAPPINGS.rainbowPastel.positive],
  warning: TEAM_COLOR_PALETTES.rainbowPastel[3],
  danger: TEAM_COLOR_PALETTES.rainbowPastel[SEMANTIC_COLOR_MAPPINGS.rainbowPastel.negative],
  info: TEAM_COLOR_PALETTES.rainbowPastel[1],
  highlight: TEAM_COLOR_PALETTES.rainbowPastel[SEMANTIC_COLOR_MAPPINGS.rainbowPastel.highlight],
} as const;

export const PALETTE_SHOWCASE = [
  {
    name: "rainbowPastel" as const,
    description: "Default charts, tables, team colors (ColorUtils)",
    colors: TEAM_COLOR_PALETTES.rainbowPastel,
    semantics: SEMANTIC_COLOR_MAPPINGS.rainbowPastel,
  },
  {
    name: "harmonic10" as const,
    description: "Alternate Matplotlib-style series palette",
    colors: TEAM_COLOR_PALETTES.harmonic10,
    semantics: SEMANTIC_COLOR_MAPPINGS.harmonic10,
  },
];
