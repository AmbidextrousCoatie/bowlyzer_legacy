/**
 * Port of app/static/js/theme/color-utils.js. Preserves the data-vis palettes
 * (rainbowPastel / harmonic10), heatmap math, and team/player color mapping.
 * Drops the legacy THEME_COLORS dict and applyThemeColors() — DS tokens own
 * UI chrome now.
 */

export type PaletteName = "harmonic10" | "rainbowPastel";
export type HeatmapPaletteId = 1 | 2 | 3 | 4 | 5 | 6 | "default";

export const TEAM_COLOR_PALETTES: Record<PaletteName, readonly string[]> = {
  harmonic10: [
    "#1F77B4",
    "#FF7F0E",
    "#2CA02C",
    "#D62728",
    "#9467BD",
    "#8C564B",
    "#E377C2",
    "#7F7F7F",
    "#BCBD22",
    "#17BECF",
  ],
  rainbowPastel: [
    "#1B8CA6",
    "#2CA89A",
    "#8CBF8A",
    "#E6C86E",
    "#F7A86E",
    "#E86E56",
    "#D95A6A",
    "#C94C8A",
    "#A04CBF",
    "#D6A4E6",
  ],
};

export const SEMANTIC_COLOR_MAPPINGS: Record<
  PaletteName,
  { positive: number; negative: number; highlight: number }
> = {
  harmonic10: { positive: 2, negative: 3, highlight: 9 },
  rainbowPastel: { positive: 2, negative: 5, highlight: 9 },
};

type HeatmapStops = { start: string; end: string; mid: string };

export const HEATMAP_PALETTES: Record<HeatmapPaletteId, HeatmapStops> = {
  1: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[8],
    end: TEAM_COLOR_PALETTES.rainbowPastel[0],
    mid: "#B5B5B5",
  },
  2: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[5],
    end: TEAM_COLOR_PALETTES.rainbowPastel[1],
    mid: "#C0C0C0",
  },
  3: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[7],
    end: TEAM_COLOR_PALETTES.rainbowPastel[2],
    mid: "#C2C2C2",
  },
  4: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[3],
    end: TEAM_COLOR_PALETTES.rainbowPastel[0],
    mid: "#C8C8C8",
  },
  5: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[7],
    end: TEAM_COLOR_PALETTES.rainbowPastel[0],
    mid: "#B5B5B5",
  },
  6: {
    start: TEAM_COLOR_PALETTES.rainbowPastel[6],
    end: TEAM_COLOR_PALETTES.rainbowPastel[0],
    mid: "#C8C8C8",
  },
  default: { start: "#dddddd", end: "#1b8da7", mid: "#B5B5B5" },
};

export const DEFAULT_STRIPE_PALETTE: readonly string[] = ["#ffffff", "#1B8CA6"];

let currentPaletteName: PaletteName = "rainbowPastel";
let currentPalette: readonly string[] = TEAM_COLOR_PALETTES[currentPaletteName];
let currentHeatmapPaletteId: HeatmapPaletteId = 6;

const teamColorMap: Record<string, string> = {};
const playerColorMap: Record<string, string> = {};

export function getCurrentPaletteName(): PaletteName {
  return currentPaletteName;
}

export function getCurrentPalette(): readonly string[] {
  return [...currentPalette];
}

export function setPalette(name: PaletteName): boolean {
  if (TEAM_COLOR_PALETTES[name]) {
    currentPaletteName = name;
    currentPalette = TEAM_COLOR_PALETTES[name];
    return true;
  }
  return false;
}

export function getCurrentHeatmapPalette(): HeatmapStops {
  return HEATMAP_PALETTES[currentHeatmapPaletteId] ?? HEATMAP_PALETTES[1];
}

export function setHeatmapPalette(id: HeatmapPaletteId): boolean {
  if (HEATMAP_PALETTES[id]) {
    currentHeatmapPaletteId = id;
    return true;
  }
  return false;
}

export function getAvailableHeatmapPalettes(): HeatmapPaletteId[] {
  return Object.keys(HEATMAP_PALETTES) as HeatmapPaletteId[];
}

export function getCurrentHeatmapPaletteId(): HeatmapPaletteId {
  return currentHeatmapPaletteId;
}

export function hexToRgb(hex: string): [number, number, number] {
  if (!hex) return [255, 255, 255];
  let clean = hex.replace("#", "");
  if (clean.length === 3) {
    clean = clean
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const n = parseInt(clean, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function toRgba(color: string, alpha = 1): string {
  if (!color) return `rgba(255,255,255,${alpha})`;
  if (color.startsWith("rgb")) {
    return color.replace(")", `, ${alpha})`).replace("rgb", "rgba");
  }
  const [r, g, b] = hexToRgb(color);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function getGradientColors(count: number, start = "#ffffff", end = "#2196F3"): string[] {
  if (!count || count <= 1) return [start];
  const startRgb = hexToRgb(start);
  const endRgb = hexToRgb(end);
  return Array.from({ length: count }, (_, index) => {
    if (index === 0) return start;
    if (index === count - 1) return end;
    const f = index / (count - 1);
    const r = Math.round(startRgb[0] + (endRgb[0] - startRgb[0]) * f);
    const g = Math.round(startRgb[1] + (endRgb[1] - startRgb[1]) * f);
    const b = Math.round(startRgb[2] + (endRgb[2] - startRgb[2]) * f);
    return `rgb(${r}, ${g}, ${b})`;
  });
}

export function getStripeColors(
  groupIndex: number,
  options: {
    enabled?: boolean;
    palette?: readonly string[];
    headerAlpha?: number;
    cellAlpha?: number;
  } = {},
): { headerBg: string; cellBg: string } | null {
  if (options.enabled === false) return null;
  const palette = options.palette ?? DEFAULT_STRIPE_PALETTE;
  const color = palette[groupIndex % palette.length];
  const headerAlpha = options.headerAlpha ?? 0.55;
  const cellAlpha = options.cellAlpha ?? 0.25;
  return {
    headerBg: toRgba(color, headerAlpha),
    cellBg: toRgba(color, cellAlpha),
  };
}

type LooseColumn = {
  cssClass?: string;
  headerClass?: string;
  columns?: LooseColumn[];
};

export function assignGroupStripeCss(groups: LooseColumn[]): void {
  groups.forEach((group, index) => {
    group.cssClass = ((group.cssClass ?? "") + " col-group-" + index).trim();
    if (group.columns) assignLeafColumnCss(group.columns, index);
  });
}

function assignLeafColumnCss(columns: LooseColumn[], groupIndex: number): void {
  columns.forEach((col) => {
    if (col.columns) {
      assignLeafColumnCss(col.columns, groupIndex);
    } else {
      col.cssClass = ((col.cssClass ?? "") + " col-group-" + groupIndex).trim();
      col.headerClass = ((col.headerClass ?? "") + " col-group-" + groupIndex).trim();
    }
  });
}

const STRIPE_SCOPE = ".ds-tabulator.is-striped-column-groups";

export function generateStripeCss(
  groupCount: number,
  options: {
    palette?: readonly string[];
    headerAlpha?: number;
    cellAlpha?: number;
  } = {},
): string {
  const palette = options.palette ?? DEFAULT_STRIPE_PALETTE;
  const headerAlpha = options.headerAlpha ?? 0.55;
  const cellAlpha = options.cellAlpha ?? 0.25;
  let css = "";
  for (let i = 0; i < groupCount; i++) {
    const color = palette[i % palette.length];
    const headerBg = toRgba(color, headerAlpha);
    const cellBg = toRgba(color, cellAlpha);
    css += `${STRIPE_SCOPE} .tabulator-cell.col-group-${i}:not(.tabulator-frozen) { background-color: ${cellBg} !important; }\n`;
    css += `${STRIPE_SCOPE} .tabulator-col.col-group-${i}:not(.tabulator-frozen) { background-color: ${headerBg} !important; }\n`;
    css += `${STRIPE_SCOPE} .tabulator-col-group.col-group-${i}:not(.tabulator-frozen) { background-color: ${headerBg} !important; }\n`;
  }
  return css;
}

export function injectStripeCss(
  groupCount: number,
  options: {
    palette?: readonly string[];
    headerAlpha?: number;
    cellAlpha?: number;
  } = {},
): void {
  if (typeof document === "undefined") return;
  const styleId = "tabulator-stripe-styles";
  let styleEl = document.getElementById(styleId) as HTMLStyleElement | null;
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = styleId;
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = generateStripeCss(groupCount, options);
}

function rgbToHsl(r: number, g: number, b: number): { h: number; s: number; l: number } {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;
  if (d !== 0) {
    s = d / (1 - Math.abs(2 * l - 1));
    switch (max) {
      case r:
        h = ((g - b) / d) % 6;
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      case b:
        h = (r - g) / d + 4;
        break;
    }
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s, l };
}

function hslToRgbString(h: number, s: number, l: number): string {
  h = h / 360;
  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number): number => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  return `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
}

export function getHeatMapColor(
  value: number,
  minVal: number,
  maxVal: number,
  options: {
    startColor?: string;
    endColor?: string;
    midColor?: string;
    curveStrength?: number;
  } = {},
): string {
  const stops = getCurrentHeatmapPalette();
  const startHex = options.startColor ?? stops.start;
  const endHex = options.endColor ?? stops.end;
  const midHex = options.midColor ?? stops.mid;
  const k = options.curveStrength ?? 2;
  let t = Math.min(Math.max((value - minVal) / (maxVal - minVal), 0), 1);
  const nonlinear = (Math.atan(k * (t - 0.5)) / Math.atan(k * 0.5) + 1) / 2;
  t = nonlinear;
  const start = rgbToHsl(...hexToRgb(startHex));
  const end = rgbToHsl(...hexToRgb(endHex));
  const mid = rgbToHsl(...hexToRgb(midHex));
  mid.s = 0;
  let h: number, s: number, l: number;
  if (t < 0.5) {
    const u = t / 0.5;
    h = start.h;
    s = start.s * (1 - u);
    l = start.l + (mid.l - start.l) * u;
  } else {
    const u = (t - 0.5) / 0.5;
    h = end.h;
    s = mid.s + (end.s - mid.s) * u;
    l = mid.l + (end.l - mid.l) * u;
  }
  return hslToRgbString(h, s, l);
}

export function getPaletteColor(index: number): string {
  if (!currentPalette.length) return "#888";
  return currentPalette[Math.abs(index) % currentPalette.length];
}

const TEAM_COLOR_KEY_SEP = "::";

/** Storage key: scoped by league when multiple leagues share team names (e.g. men's / women's). */
export function teamColorMapKey(teamName: string, league?: string | null): string {
  const name = String(teamName ?? "").trim();
  if (!name) return "";
  if (league) return `${league}${TEAM_COLOR_KEY_SEP}${name}`;
  return name;
}

export function clearLeagueTeamColors(league: string): void {
  const prefix = `${league}${TEAM_COLOR_KEY_SEP}`;
  for (const key of Object.keys(teamColorMap)) {
    if (key.startsWith(prefix)) delete teamColorMap[key];
  }
}

export function updateTeamColorMap(currentTeams: string[] = [], league?: string | null): void {
  if (!Array.isArray(currentTeams)) return;
  if (league) {
    clearLeagueTeamColors(league);
  } else {
    Object.keys(teamColorMap).forEach((key) => {
      if (!key.includes(TEAM_COLOR_KEY_SEP) && !currentTeams.includes(key)) {
        delete teamColorMap[key];
      }
    });
  }
  let paletteIdx = 0;
  currentTeams.forEach((team) => {
    const key = teamColorMapKey(team, league);
    if (key && !teamColorMap[key]) {
      teamColorMap[key] = getPaletteColor(paletteIdx++);
    }
  });
}

/** Stable palette slot from team name (when map not seeded yet). */
function paletteIndexForTeamName(teamName: string): number {
  let hash = 0;
  for (let i = 0; i < teamName.length; i++) {
    hash = teamName.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash);
}

export function isTeamVsTeamComparisonTable(data: { title?: string }): boolean {
  const title = data.title ?? "";
  return (
    title.includes("Team vs Team Comparison") || title.includes("Team vs Team Vergleichsmatrix")
  );
}

type TablePayloadLike = {
  columns?: Array<{ columns?: Array<{ field?: string }> }>;
  data?: Array<Record<string, unknown> | unknown[]>;
};

/** Column index of the team name in a TableData row (flatten order). */
export function tableTeamColumnIndex(tablePayload: TablePayloadLike): number {
  const groups = tablePayload.columns;
  if (!Array.isArray(groups)) return 1;
  let idx = 0;
  for (const group of groups) {
    if (!group?.columns) continue;
    for (const col of group.columns) {
      const field = col.field;
      if (field === "team" || field === "team_name") return idx;
      idx++;
    }
  }
  return 1;
}

/** Unique team names in table row order (first occurrence wins). */
export function extractTeamNamesFromTablePayload(tablePayload: TablePayloadLike): string[] {
  if (!tablePayload.data?.length) return [];
  const teamIdx = tableTeamColumnIndex(tablePayload);
  const teams: string[] = [];
  const seen = new Set<string>();
  for (const row of tablePayload.data) {
    let raw: unknown;
    if (Array.isArray(row)) {
      raw = teamIdx >= 0 && teamIdx < row.length ? row[teamIdx] : null;
    } else {
      const r = row as Record<string, unknown>;
      raw = r.team ?? r.team_name ?? null;
    }
    if (raw === null || raw === undefined) continue;
    const name = String(raw).trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    teams.push(name);
  }
  return teams;
}

/**
 * Assign palette colors by team name without removing existing entries.
 * New teams get the next free palette index (alphabetically sorted for stability).
 */
export function ensureTeamColors(teamNames: string[], league?: string | null): void {
  const sorted = [...new Set(teamNames.map((t) => t.trim()).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" }),
  );
  sorted.forEach((team, idx) => {
    const key = teamColorMapKey(team, league);
    if (key && !teamColorMap[key]) {
      teamColorMap[key] = getPaletteColor(idx);
    }
  });
}

/**
 * Reassign colors in league-standings row order (position 1 → palette[0], …).
 * Matches legacy `seedTeamColorsFromLeagueTablePayload` for chart/table alignment.
 */
export function seedTeamColorsFromTablePayload(
  tablePayload: TablePayloadLike,
  league?: string | null,
): void {
  const teams = extractTeamNamesFromTablePayload(tablePayload);
  if (!teams.length) return;
  if (league) {
    clearLeagueTeamColors(league);
  } else {
    teams.forEach((t) => {
      delete teamColorMap[teamColorMapKey(t, null)];
    });
  }
  let paletteIdx = 0;
  teams.forEach((t) => {
    const key = teamColorMapKey(t, league);
    if (key) teamColorMap[key] = getPaletteColor(paletteIdx++);
  });
}

export type GetTeamColorOptions = {
  league?: string | null;
  fallbackIndex?: number;
};

export function getTeamColor(
  teamName: string,
  optionsOrFallback: number | GetTeamColorOptions = 0,
): string {
  const options: GetTeamColorOptions =
    typeof optionsOrFallback === "number"
      ? { fallbackIndex: optionsOrFallback }
      : { fallbackIndex: 0, ...optionsOrFallback };

  const name = teamName?.trim() ?? "";
  const league = options.league;
  const key = teamColorMapKey(name, league);
  if (key && teamColorMap[key]) return teamColorMap[key];
  if (!league && name && teamColorMap[name]) return teamColorMap[name];
  if (name && playerColorMap[name]) return playerColorMap[name];
  if (name) return getPaletteColor(paletteIndexForTeamName(name));
  return getPaletteColor(options.fallbackIndex ?? 0);
}

export function setTeamColor(teamName: string, color: string, league?: string | null): void {
  const key = teamColorMapKey(teamName, league);
  if (key) teamColorMap[key] = color;
}

export function clearTeamColor(teamName: string, league?: string | null): void {
  const key = teamColorMapKey(teamName, league);
  if (key) delete teamColorMap[key];
}

export function getTeamColorMap(): Record<string, string> {
  return teamColorMap;
}

export function updatePlayerColorMap(currentPlayers: string[] = []): void {
  if (!Array.isArray(currentPlayers)) return;
  Object.keys(playerColorMap).forEach((player) => {
    if (!currentPlayers.includes(player)) delete playerColorMap[player];
  });
  let paletteIdx = 0;
  currentPlayers.forEach((player) => {
    if (!playerColorMap[player]) {
      playerColorMap[player] = getPaletteColor(paletteIdx++);
    }
  });
}

export function getPlayerColor(playerName: string, fallbackIndex = 0): string {
  if (playerName && playerColorMap[playerName]) return playerColorMap[playerName];
  if (playerName) {
    let hash = 0;
    for (let i = 0; i < playerName.length; i++) {
      hash = playerName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % currentPalette.length;
    return getPaletteColor(index);
  }
  return getPaletteColor(fallbackIndex);
}

export function getPlayerColorMap(): Record<string, string> {
  return playerColorMap;
}

export function getSemanticColor(semanticName: "positive" | "negative" | "highlight"): string {
  const mapping = SEMANTIC_COLOR_MAPPINGS[currentPaletteName];
  if (mapping && mapping[semanticName] !== undefined) {
    return getPaletteColor(mapping[semanticName]);
  }
  const fallbacks: Record<string, string> = {
    positive: "#2CA02C",
    negative: "#D62728",
    highlight: "#ffd700",
  };
  return fallbacks[semanticName] ?? "#888";
}
