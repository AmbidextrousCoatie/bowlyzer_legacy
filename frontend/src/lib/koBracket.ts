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

export type BracketTierId = "elim" | "stepladder" | "qf" | "sf" | "final";

export type BracketTiers = {
  elim: KoBracketMatch[];
  stepladder: KoBracketMatch[];
  qf: KoBracketMatch[];
  sf: KoBracketMatch[];
  final: KoBracketMatch[];
};

const TREE_KEY_ORDER = ["QF1", "QF2", "SF1", "SF2", "F"] as const;
const STEPLADDER_KEY_ORDER = ["ELIM1", "ELIM2", "ELIM", "SL1", "SL2", "F"] as const;

export function organizeBracketTiers(matches: KoBracketMatch[]): BracketTiers {
  const byKey = new Map(matches.map((m) => [m.key, m]));
  const treeOrdered = TREE_KEY_ORDER.map((k) => byKey.get(k)).filter(Boolean) as KoBracketMatch[];
  const stepOrdered = STEPLADDER_KEY_ORDER.map((k) => byKey.get(k)).filter(Boolean) as KoBracketMatch[];
  const known = new Set([...TREE_KEY_ORDER, ...STEPLADDER_KEY_ORDER]);
  const rest = matches.filter((m) => !known.has(m.key as (typeof TREE_KEY_ORDER)[number]));
  const all = [...stepOrdered, ...treeOrdered, ...rest];
  // Dedupe by key while preserving order
  const seen = new Set<string>();
  const unique: KoBracketMatch[] = [];
  for (const m of all) {
    if (seen.has(m.key)) continue;
    seen.add(m.key);
    unique.push(m);
  }

  const elim = unique.filter((m) => m.phase === "elim" || m.kind === "field" || /^ELIM/i.test(m.key));
  const stepladder = unique.filter(
    (m) => m.phase === "stepladder" || /^SL\d+/i.test(m.key),
  );
  const qf = unique.filter((m) => m.phase === "qf" || /^QF/i.test(m.key));
  const sf = unique.filter((m) => m.phase === "sf" || /^SF/i.test(m.key));
  const final = unique.filter((m) => m.phase === "final" || m.key === "F");
  return { elim, stepladder, qf, sf, final };
}

export function isStepladderFormat(bracket: KoBracketPayload): boolean {
  if (bracket.ko_bracket_format === "seeded_elim_stepladder") return true;
  const matches = bracket.matches ?? [];
  return matches.some(
    (m) => m.phase === "elim" || m.phase === "stepladder" || m.kind === "field" || /^SL\d+/i.test(m.key),
  );
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
  if (!focusKey) return false;
  if (match.kind === "field") {
    const adv = normalizeKoName(match.advancer ?? "");
    if (adv && adv === focusKey) return true;
    return (match.field ?? []).some(
      (p) => p.advances && normalizeKoName(p.name ?? "") === focusKey,
    );
  }
  if (!match.winner) return false;
  const wSide = match.winner === "a" ? match.side_a : match.side_b;
  return sideKey(wSide) === focusKey;
}

export function matchIncludesFocus(match: KoBracketMatch, focusKey: string): boolean {
  if (!focusKey) return false;
  if (match.kind === "field") {
    return (match.field ?? []).some((p) => normalizeKoName(p.name ?? "") === focusKey);
  }
  return sideKey(match.side_a) === focusKey || sideKey(match.side_b) === focusKey;
}

export function formatPinGamesLine(pinGames: number[][] | undefined): string | null {
  if (!pinGames?.length) return null;
  const parts = pinGames.map(([a, b]) => `${a}–${b}`);
  return parts.join(" · ");
}

export function formatFieldGamesLine(games: number[] | undefined): string | null {
  if (!games?.length) return null;
  return games.join(" · ");
}

export function formatSeriesScore(
  match: KoBracketMatch,
  scratchMode: boolean,
): string | null {
  if (match.walkover) return null;
  const a = match.side_a?.games_won ?? 0;
  const b = match.side_b?.games_won ?? 0;
  const useScratch =
    scratchMode ||
    match.scratch_series ||
    match.series_mode === "scratch_total_2g" ||
    match.series_mode === "scratch_total";
  if (useScratch) {
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
  tier: BracketTierId,
  t: (key: string, fallback?: string) => string,
): string {
  if (tier === "elim") return t("ui.tournament.bracket_elim", "Eliminierung");
  if (tier === "stepladder") return t("ui.tournament.bracket_stepladder", "Stepladder");
  if (tier === "qf") return t("ui.tournament.bracket_qf", "Viertelfinale");
  if (tier === "sf") return t("ui.tournament.bracket_sf", "Halbfinale");
  return t("ui.tournament.bracket_final", "Finale");
}
