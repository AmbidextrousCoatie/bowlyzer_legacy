import { getPaletteColor } from "./color-utils";
import type { KoBracketMatch, KoBracketPayload } from "../hooks/useTournament";

export function normalizeKoName(name: string): string {
  let raw = String(name ?? "").trim();
  const low = raw.toLowerCase();
  if (low.endsWith("(no show)")) {
    raw = raw.slice(0, low.lastIndexOf("(")).trim();
  }
  return raw
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase();
}

export function isNoShowName(name: string): boolean {
  const n = normalizeKoName(name);
  return !n || n.includes("nicht angetreten") || n === "no show";
}

export function sideKey(side: { name?: string | null }): string {
  return normalizeKoName(side?.name ?? "");
}

export type BracketTiers = {
  qf: KoBracketMatch[];
  sf: KoBracketMatch[];
  final: KoBracketMatch[];
};

const KEY_ORDER = ["QF1", "QF2", "SF1", "SF2", "F"] as const;

export function organizeBracketTiers(matches: KoBracketMatch[]): BracketTiers {
  const byKey = new Map(matches.map((m) => [m.key, m]));
  const ordered = KEY_ORDER.map((k) => byKey.get(k)).filter(Boolean) as KoBracketMatch[];
  const rest = matches.filter((m) => !KEY_ORDER.includes(m.key as (typeof KEY_ORDER)[number]));
  const all = [...ordered, ...rest];

  const qf = all.filter((m) => m.phase === "qf" || /^QF/i.test(m.key));
  const sf = all.filter((m) => m.phase === "sf" || /^SF/i.test(m.key));
  const final = all.filter((m) => m.phase === "final" || m.key === "F");
  return { qf, sf, final };
}

export function bracketLaneColors(bracket: KoBracketPayload) {
  const idxA = bracket.palette_index_a ?? 2;
  const idxB = bracket.palette_index_b ?? 8;
  return {
    a: getPaletteColor(idxA),
    b: getPaletteColor(idxB),
    focus: getPaletteColor(bracket.focus_palette_index ?? idxA),
  };
}

export function matchOnFinalistPath(
  match: KoBracketMatch,
  bracket: KoBracketPayload,
): "a" | "b" | "both" | null {
  const pathA = new Set(bracket.path_keys_a ?? []);
  const pathB = new Set(bracket.path_keys_b ?? []);
  const onA = pathA.has(match.key);
  const onB = pathB.has(match.key);
  if (onA && onB) return "both";
  if (onA) return "a";
  if (onB) return "b";
  return null;
}

export function focusPlayerWonMatch(match: KoBracketMatch, focusKey: string): boolean {
  if (!focusKey || !match.winner) return false;
  const wSide = match.winner === "a" ? match.side_a : match.side_b;
  return sideKey(wSide) === focusKey;
}

export function matchIncludesFocus(match: KoBracketMatch, focusKey: string): boolean {
  if (!focusKey) return false;
  return sideKey(match.side_a) === focusKey || sideKey(match.side_b) === focusKey;
}

export function formatPinGamesLine(pinGames: number[][] | undefined): string | null {
  if (!pinGames?.length) return null;
  const parts = pinGames.map(([a, b]) => `${a}–${b}`);
  return parts.join(" · ");
}

export function formatSeriesScore(
  match: KoBracketMatch,
  scratchMode: boolean,
): string | null {
  if (match.walkover) return null;
  const a = match.side_a?.games_won ?? 0;
  const b = match.side_b?.games_won ?? 0;
  if (scratchMode || match.scratch_series) {
    const ta = match.scratch_total_a ?? 0;
    const tb = match.scratch_total_b ?? 0;
    if (ta === 0 && tb === 0) return null;
    const boldA = match.winner === "a";
    const boldB = match.winner === "b";
    return `${boldA ? `**${ta}**` : ta}:${boldB ? `**${tb}**` : tb}`;
  }
  if (a === 0 && b === 0) return null;
  const boldA = match.winner === "a";
  const boldB = match.winner === "b";
  return `${boldA ? `**${a}**` : a}:${boldB ? `**${b}**` : b}`;
}

/** Parse mini markdown **n** for series display. */
export function renderSeriesParts(text: string): Array<{ bold: boolean; text: string }> {
  const out: Array<{ bold: boolean; text: string }> = [];
  const re = /\*\*(\d+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ bold: false, text: text.slice(last, m.index) });
    out.push({ bold: true, text: m[1] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ bold: false, text: text.slice(last) });
  return out.length ? out : [{ bold: false, text }];
}

export function tierLabel(
  tier: "qf" | "sf" | "final",
  t: (key: string, fallback?: string) => string,
): string {
  if (tier === "qf") return t("ui.tournament.bracket_qf", "Viertelfinale");
  if (tier === "sf") return t("ui.tournament.bracket_sf", "Halbfinale");
  return t("ui.tournament.bracket_final", "Finale");
}
