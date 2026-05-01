export const THEME = {
  neutral: {
    slate800: "#1f2937",
    slate900: "#0f172a",
    slate700: "#334155",
    slate600: "#475569",
    slate500: "#64748b",
    gray100: "#f3f4f6",
    gray50: "#f8fafc",
    white: "#ffffff",
    black: "#000000",
    border: "#e5e7eb",
    borderStrong: "#d1d5db",
  },
  brand: {
    blue600: "#2563eb",
    blue700: "#1d4ed8",
    teal700: "#0e7490",
    teal600: "#0891b2",
    cyan800: "#083344",
  },
  state: {
    success: "#16a34a",
    successDark: "#052e16",
    danger: "#dc2626",
    dangerDark: "#450a0a",
    dangerStrong: "#b91c1c",
    purple: "#9333ea",
    orange: "#ea580c",
  },
  fallback: {
    teamDot: "#94a3b8",
  },
} as const;

export const SERIES_COLORS = [
  THEME.brand.blue600,
  THEME.state.success,
  THEME.state.danger,
  THEME.state.purple,
  THEME.state.orange,
  THEME.brand.teal600,
] as const;

export const TEAM_PALETTES = {
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
} as const;

export function rgbaFromHex(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  const full = clean.length === 3 ? clean.split("").map((ch) => ch + ch).join("") : clean;
  const n = Number.parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
