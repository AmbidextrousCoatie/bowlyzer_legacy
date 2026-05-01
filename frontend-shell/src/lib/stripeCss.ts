/** Mirrors legacy `tables.html` + `color-utils.generateStripeCss` / `injectStripeCss`. */
import { THEME } from "./theme";

const THEME_PRIMARY = THEME.brand.teal700;

export const DEFAULT_STRIPE_PALETTE = [THEME.neutral.white, THEME_PRIMARY];

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace(/^#/, "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((ch) => ch + ch)
      .join("");
  }
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toRgba(color: string, alpha: number): string {
  if (color.startsWith("#")) {
    const [r, g, b] = hexToRgb(color);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return color;
}

export type StripeCssOptions = {
  palette?: string[];
  headerAlpha?: number;
  cellAlpha?: number;
};

/** CSS rules targeting `.bowlyzer-tabulator` so they match injected Tabulator markup. */
export function generateTabulatorStripeCss(
  scopeClass: string,
  groupCount: number,
  options: StripeCssOptions = {},
): string {
  const palette = options.palette ?? DEFAULT_STRIPE_PALETTE;
  const headerAlpha =
    typeof options.headerAlpha === "number" ? options.headerAlpha : 0.2;
  const cellAlpha = typeof options.cellAlpha === "number" ? options.cellAlpha : 0.1;

  let css = "";
  for (let i = 0; i < groupCount; i++) {
    const color = palette[i % palette.length];
    const headerBg = toRgba(color, headerAlpha);
    const cellBg = toRgba(color, cellAlpha);
    const sel = `.${scopeClass}`;
    css += `${sel} .tabulator-cell.col-group-${i}:not(.tabulator-frozen) { background-color: ${cellBg} !important; }\n`;
    css += `${sel} .tabulator-col.col-group-${i}:not(.tabulator-frozen) { background-color: ${headerBg} !important; }\n`;
    css += `${sel} .tabulator-col-group.col-group-${i}:not(.tabulator-frozen) { background-color: ${headerBg} !important; }\n`;
  }
  return css;
}

/**
 * Writes scoped stripe rules under `.{stripeScopeClass}`. Attach that class only to one table wrapper.
 */
export function injectStripeCss(stripeScopeClass: string, groupCount: number, options: StripeCssOptions): () => void {
  const styleId = `bowlyzer-stripes-css-${stripeScopeClass.replace(/[^\w-]/g, "")}`;
  let styleEl = document.getElementById(styleId) as HTMLStyleElement | null;
  if (!styleEl) {
    styleEl = document.createElement("style");
    styleEl.id = styleId;
    document.head.appendChild(styleEl);
  }
  styleEl.textContent = generateTabulatorStripeCss(stripeScopeClass, groupCount, options);
  return () => {
    styleEl?.remove();
  };
}
