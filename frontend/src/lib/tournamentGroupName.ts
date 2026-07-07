/**
 * Tournament event label normalization (mirrors app/utils/tournament_utils.py).
 * Groups year-suffixed legacy names and GF wording variants into one category.
 */

const YEAR_SUFFIX_RE = /\s+20\d{2}\s*$/;

/** Stripped label → canonical group name. */
const GROUP_CANONICAL_ALIASES: Record<string, string> = {
  "Bayerische Meisterschaft - Männer Einzel": "Bayerische Meisterschaft Einzel",
  "Bayerische Meisterschaft Männer Einzel": "Bayerische Meisterschaft Einzel",
  "Bayerische Meisterschaft - Frauen Einzel": "Bayerische Meisterschaft Einzel Damen",
  "Bayerische Meisterschaft - Damen Einzel": "Bayerische Meisterschaft Einzel Damen",
  "Bayerische Meisterschaft Damen Einzel": "Bayerische Meisterschaft Einzel Damen",
  "Südbayerische Meisterschaft": "Südbayerische Meisterschaft Einzel",
  "Südbayerische Meisterschaft Männer Einzel": "Südbayerische Meisterschaft Einzel",
  "Südbayerische Meisterschaft - Männer Einzel": "Südbayerische Meisterschaft Einzel",
  "Südbayerische Meisterschaft Damen Einzel": "Südbayerische Meisterschaft Einzel Damen",
  "Südbayerische Meisterschaft - Damen Einzel": "Südbayerische Meisterschaft Einzel Damen",
  "Südbayerische Meisterschaft - Frauen Einzel": "Südbayerische Meisterschaft Einzel Damen",
  "Nordbayerische Meisterschaft": "Nordbayrische Meisterschaft Einzel",
  "Nordbayrische Meisterschaft": "Nordbayrische Meisterschaft Einzel",
  "Nordbayerische Meisterschaft Männer Einzel": "Nordbayrische Meisterschaft Einzel",
  "Nordbayerische Meisterschaft - Männer Einzel": "Nordbayrische Meisterschaft Einzel",
  "Nordbayerische Meisterschaft Damen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
  "Nordbayerische Meisterschaft - Damen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
  "Nordbayerische Meisterschaft - Frauen Einzel": "Nordbayrische Meisterschaft Einzel Damen",
};

/** Canonical group name → chart abbreviation (from tournament_mapping.csv). */
const TOURNAMENT_GROUP_ABBREVIATIONS: Record<string, string> = {
  "Bayerische Meisterschaft Einzel": "BM M",
  "Bayerische Meisterschaft Einzel Damen": "BM D",
  "Bayerische Meisterschaft Männer Doppel": "BM M D",
  "Bayerische Meisterschaft Damen Doppel": "BM D D",
  "Nordbayrische Meisterschaft Einzel": "NBM M",
  "Nordbayrische Meisterschaft Einzel Damen": "NBM D",
  "Nordbayerische Meisterschaft Männer Doppel": "NBM M D",
  "Südbayerische Meisterschaft Einzel": "SBM M",
  "Südbayerische Meisterschaft Einzel Damen": "SBM D",
  "Südbayerische Meisterschaft Männer Doppel": "SBM M D",
};

/** Mirrors rows in database/relational_csv/tournament_mapping.csv */
const TOURNAMENT_MAPPING_ROWS: Array<{ longName: string; aliases: string[] }> = [
  {
    longName: "Nordbayerische Meisterschaft",
    aliases: [
      "Nordbayerische Meisterschaft Männer Einzel",
      "Nordbayerische Meisterschaft - Männer Einzel",
    ],
  },
  {
    longName: "Nordbayerische Meisterschaft Damen Einzel",
    aliases: [
      "Nordbayerische Meisterschaft - Damen Einzel",
      "Nordbayerische Meisterschaft - Frauen Einzel",
    ],
  },
  {
    longName: "Nordbayerische Meisterschaft Männer Doppel",
    aliases: ["Nordbayerische Meisterschaft - Männer Doppel"],
  },
  {
    longName: "Südbayerische Meisterschaft",
    aliases: [
      "Südbayerische Meisterschaft Männer Einzel",
      "Südbayerische Meisterschaft - Männer Einzel",
    ],
  },
  {
    longName: "Südbayerische Meisterschaft Damen Einzel",
    aliases: [
      "Südbayerische Meisterschaft - Damen Einzel",
      "Südbayerische Meisterschaft - Frauen Einzel",
    ],
  },
  {
    longName: "Südbayerische Meisterschaft Männer Doppel",
    aliases: ["Südbayerische Meisterschaft - Männer Doppel"],
  },
  {
    longName: "Bayerische Meisterschaft - Männer Einzel",
    aliases: ["Bayerische Meisterschaft Männer Einzel"],
  },
  {
    longName: "Bayerische Meisterschaft - Frauen Einzel",
    aliases: [
      "Bayerische Meisterschaft Damen Einzel",
      "Bayerische Meisterschaft - Damen Einzel",
    ],
  },
  {
    longName: "Bayerische Meisterschaft Männer Doppel",
    aliases: ["Bayerische Meisterschaft - Männer Doppel"],
  },
  {
    longName: "Bayerische Meisterschaft Damen Doppel",
    aliases: [
      "Bayerische Meisterschaft - Damen Doppel",
      "Bayerische Meisterschaft - Frauen Doppel",
    ],
  },
];

function buildGroupAliasLookup(): Record<string, string> {
  const lookup: Record<string, string> = { ...GROUP_CANONICAL_ALIASES };
  for (const row of TOURNAMENT_MAPPING_ROWS) {
    const canonical = GROUP_CANONICAL_ALIASES[row.longName] ?? row.longName;
    lookup[row.longName] = canonical;
    for (const alias of row.aliases) {
      lookup[alias] = canonical;
    }
  }
  return lookup;
}

const GROUP_ALIAS_LOOKUP = buildGroupAliasLookup();

export function normalizeTournamentGroupName(eventName: string): string {
  const text = String(eventName ?? "").trim();
  if (!text) return "";
  const stripped = text.replace(YEAR_SUFFIX_RE, "").trim();
  return GROUP_ALIAS_LOOKUP[stripped] ?? stripped;
}

export function tournamentClusterKey(eventName: string): string {
  return `t:${normalizeTournamentGroupName(eventName)}`;
}

export function tournamentGroupAbbreviation(groupName: string): string | undefined {
  const group = normalizeTournamentGroupName(groupName);
  return TOURNAMENT_GROUP_ABBREVIATIONS[group];
}
