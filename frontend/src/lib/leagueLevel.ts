/** Mirrors ``app/utils/league_utils.get_league_level`` (``league_mapping.csv``). */
const LEAGUE_LEVEL_BY_ID: Record<string, number> = {
  BayL: 3,
  "BayL (D)": 3,
  "LL N1": 4,
  "LL N2": 4,
  "LL N (D)": 4,
  "LL S": 4,
  "LL S (D)": 4,
  "BZOL N1": 5,
  "BZOL N2": 5,
  "BZOL N3": 5,
  "BZOL S1": 5,
  "BZOL S1 (D)": 5,
  "BZOL S2": 5,
  "BZOL S3": 5,
  // Bereichsliga (BL) — predecessor name for the same tier as Bezirksoberliga (BZOL)
  "BL N1": 5,
  "BL N2": 5,
  "BL N3": 5,
  "BL N4": 5,
  "BL S1": 5,
  "BL S2": 5,
  "BL S3": 5,
  "BL S4": 5,
  "BL N1 (D)": 5,
  "BL N2 (D)": 5,
  "BL S1 (D)": 5,
  "BL S2 (D)": 5,
  "BZL N1": 6,
  "BZL N2": 6,
  "BZL N3": 6,
  "BZL N4": 6,
  "BZL S1": 6,
  "BZL S2": 6,
  "BZL S3": 6,
  "KL N1": 7,
  "KL N2": 7,
  "KL N3": 7,
  "KL S1": 7,
  "KL S2": 7,
  "KL S3": 7,
  "KL S4": 7,
  "A N1": 8,
  "A N2": 8,
  "A N3": 8,
  "A N4": 8,
  "A S1": 8,
  "A S2": 8,
  "A S3": 8,
  "A S4": 8,
};

export function getLeagueLevel(league: string): number {
  const key = String(league ?? "").trim();
  return LEAGUE_LEVEL_BY_ID[key] ?? 99;
}

export type LeagueGenderScope = "male" | "female";

/** Short label for all leagues at the same ``level`` (e.g. LL N1 + LL S → ``LL``). */
const LEAGUE_LEVEL_CLUSTER_LABELS: Record<number, string> = {
  3: "BayL",
  4: "LL",
  5: "BZOL / BL",
  6: "BZL",
  7: "KL",
  8: "A",
};

export function getLeagueGenderScope(league: string): LeagueGenderScope {
  const key = String(league ?? "").trim();
  return key.includes("(D)") ? "female" : "male";
}

export function getLeagueClusterKey(league: string): string {
  const key = String(league ?? "").trim();
  const level = getLeagueLevel(key);
  if (level === 99) return `l:unknown:${key}`;
  const gender = getLeagueGenderScope(key);
  return `l:${level}:${gender}`;
}

export function getLeagueClusterLabel(level: number, gender: LeagueGenderScope): string {
  const base = LEAGUE_LEVEL_CLUSTER_LABELS[level];
  if (!base) return gender === "female" ? `Liga ${level} (D)` : `Liga ${level}`;
  return gender === "female" ? `${base} (D)` : base;
}

/** Long label for clustered league tooltips (e.g. ``Landesliga``, ``Bezirksoberliga / Bereichsliga``). */
const LEAGUE_LEVEL_LONG_LABELS: Record<number, string> = {
  3: "Bayernliga",
  4: "Landesliga",
  5: "Bezirksoberliga / Bereichsliga",
  6: "Bezirksliga",
  7: "Kreisliga",
  8: "A-Klasse",
};

export function getLeagueClusterLongLabel(level: number, gender: LeagueGenderScope): string {
  const base = LEAGUE_LEVEL_LONG_LABELS[level];
  if (!base) return gender === "female" ? `Liga ${level} Damen` : `Liga ${level}`;
  return gender === "female" ? `${base} Damen` : base;
}
