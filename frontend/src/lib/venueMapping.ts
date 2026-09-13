/** Alias → canonical bowling-center names (mirrors database/relational_csv/venue_mapping.csv). */

const VENUE_GROUPS: { canonical: string; aliases: string[] }[] = [
  { canonical: "ABC Augsburg", aliases: ["ABC Bowling Augsburg"] },
  {
    canonical: "Augsburg Blu Bowl",
    aliases: ["Augsburg Blu-Bowl", "Blu Bowl Augsburg", "Blu-Bowl Augsburg", "BluBowl Augsburg"],
  },
  {
    canonical: "Augsburg City Bowling",
    aliases: [
      "Augsburg City-Bowling",
      "City Augsburg",
      "City Bowling",
      "City Bowling Augsburg",
      "City-Augsburg",
      "City-Bowling",
      "City-Bowling Augsburg",
    ],
  },
  { canonical: "Bad-Aibling", aliases: [] },
  { canonical: "Bad-Tölz", aliases: ["Flint-Bowling Bad-Tölz"] },
  {
    canonical: "Bamberg Bowlinghaus",
    aliases: [
      "Bamberg Mainfranken",
      "Bamberg-Bowlinghaus",
      "Bamberg-Mainfranken",
      "Bamberg-Mainfranken Bowling",
      "Bamberger Bowlinghaus",
      "Bowlinghaus Bamberg",
      "Mainfranken Bamberg",
      "Mainfranken Bowling Bamberg",
    ],
  },
  {
    canonical: "Bayreuth Blu Bowl",
    aliases: [
      "Bayreuth BluBowl",
      "Bayreuth Bowling Center",
      "Bayreuth Bowling-Center",
      "Blu Bowl Bayreuth",
      "BluBowl Bayreuth",
    ],
  },
  {
    canonical: "Bindlach OK Bowling",
    aliases: ["Bindlach OK-Bowling", "Bindlach-OK Bowling", "OK Bowling Bindlach"],
  },
  {
    canonical: "Bowling in Tauber",
    aliases: ["Tauberbischofsheim", "Tauberbischofsheim BiT", "Tauberbischofsheim-BiT"],
  },
  { canonical: "Bowlingworld Nürnberg", aliases: ["Nürnberg Bowling World"] },
  {
    canonical: "Brunnthal Max Munich",
    aliases: [
      "Brunnthal",
      "MAX München Brunnthal",
      "Max Munich Brunnthal",
      "Max München Brunnthal",
      "Max-Bowling",
      "Max-Brunnthal",
      "Max Brunnthal",
    ],
  },
  {
    canonical: "Coburg Sportland",
    aliases: [
      "Coburg - Sportland",
      "Dörfles Esbach Sportland",
      "Dörfles Esbach-Sportland",
      "Sportland Coburg",
    ],
  },
  { canonical: "Dachau", aliases: [] },
  {
    canonical: "Dettelbach Extreme Bowlingarena",
    aliases: [
      "Dettelbach Extreme Bowling",
      "Dettelbach Extreme-Bowling",
      "Dettelbach-Extreme Bowling",
      "Exteme Bowling Dettelbach",
      "Extrem Bowling Dettelbach",
      "Extreme Bowling Dettelbach",
      "Extreme Dettelbach",
    ],
  },
  { canonical: "Erlangen Sportland", aliases: ["Erlangen-Sportland", "Sportland Erlangen"] },
  { canonical: "Friedrichshafen Seaside", aliases: ["Friedrichshafen"] },
  {
    canonical: "Fürth Funk Bowling Arena",
    aliases: ["Funk Bowling Arena Fürth", "Fürth Funk Freestyle Bowling"],
  },
  { canonical: "Fürth Lifestyle-Bowling", aliases: ["Fürth-Lifestyle Bowling"] },
  { canonical: "Fürth PX-Bowling", aliases: ["Fürth-PX Bowling"] },
  { canonical: "Garmisch Zugspitzbowling", aliases: ["Garmisch", "Zugspitz-Bowling Garmisch"] },
  { canonical: "Herbrechtingen", aliases: ["Bowling World Herbrechtingen"] },
  { canonical: "Ingolstadt Cosmos Bowling Arena", aliases: ["Ingolstadt"] },
  { canonical: "Kempten Big Bowl", aliases: ["Big-Bowl Kempten", "Kempten"] },
  {
    canonical: "Kitzingen Goldberg",
    aliases: ["Kitzingen Goldberg Bowling", "Kitzingen-Goldberg Bowling"],
  },
  { canonical: "Landshut LA-Bowling", aliases: ["LA-Bowling Landshut", "Landshut"] },
  { canonical: "Lauterach Strike-Center", aliases: ["Lauterach"] },
  { canonical: "Lichtenfels Pegasus Bowling", aliases: ["Lichtenfels-Pegasus Bowling"] },
  { canonical: "Maschy's Bowling Würzburg", aliases: [] },
  {
    canonical: "München Hollywood Super Bowling",
    aliases: [
      "Hollwood München",
      "Hollywood Bowling München",
      "Hollywood München",
      "Hollywood-Bowling München",
      "Hollywood-München",
    ],
  },
  {
    canonical: "München Isar Bowling",
    aliases: [
      "Isar Bowling",
      "Isar Bowling München",
      "Isar München",
      "Isar-Bowling München",
      "Isar-München",
      "München Isar-Bowling",
    ],
  },
  { canonical: "Neu-Ulm", aliases: [] },
  {
    canonical: "Nürnberg BluBowl",
    aliases: ["Blu Bowl Nürnberg", "BluBowl Nürnberg", "Nürnberg Blu Bowl", "Nürnberg Blubowl"],
  },
  {
    canonical: "Nürnberg Brunswick",
    aliases: [
      "Brunswick Nürnberg",
      "Nürnberg Brunswick Bowling",
      "Nürnberg Brunswick-Bowling",
      "Nürnberg-Brunswick Bowling",
    ],
  },
  {
    canonical: "Nürnberg Cosmos",
    aliases: [
      "Cosmos Arena Nürnberg",
      "Nürnberg Cosmos Arena",
      "Nürnberg Cosmos Bowling",
      "Nürnberg-Cosmos Bowling",
    ],
  },
  {
    canonical: "Nürnberg West Bowling",
    aliases: [
      "West Bowl Nürnberg",
      "West Bowling Nürnberg",
      "Westbowl Nürnberg",
      "Westbowling Nürnberg",
      "Nürnberg Westbowl",
      "Nürnberg Westbowling",
      "neu: West Bowl Nürnberg",
    ],
  },
  { canonical: "Olching 5005 Bowling", aliases: ["Olching"] },
  { canonical: "Olympia München", aliases: ["Olympia-Bowling München"] },
  { canonical: "Pfaffenhofen Hollywood Super Bowling", aliases: ["Pfaffenhofen"] },
  { canonical: "Pfarrkirchen", aliases: [] },
  {
    canonical: "Regensburg Super Bowl",
    aliases: [
      "Regensburg SuperBowl",
      "Regensburg Superbowl",
      "Regensburg-Super Bowl",
      "Regensburg-Superbowl",
      "Super Bowl Regensburg",
      "SuperBowl Regensburg",
      "Superbowl Regensburg",
    ],
  },
  { canonical: "Rottendorf Bowling-Center", aliases: ["Rottendorf", "neu: Rottendorf"] },
  {
    canonical: "Schweinfurt Extreme Bowlingarena",
    aliases: [
      "Exteme Bowling Schweinfurt",
      "Extrem Bowling Schweinfurt",
      "Extreme Bowling Schweinfurt",
      "Schweinfurt",
      "Schweinfurt Extreme Bowling",
    ],
  },
  { canonical: "Schweinfurt World of Bowling", aliases: [] },
  { canonical: "Sky Salzburg", aliases: [] },
  { canonical: "Sport-Arena Salzburg", aliases: [] },
  { canonical: "Sport-Oase Salzburg", aliases: ["SOS Salzburg", "Salzburg", "Sport-Oase-Salzburg"] },
  { canonical: "Star Salzburg", aliases: [] },
  {
    canonical: "Unterföhring Dreambowl Palace",
    aliases: [
      "Dream Bowl",
      "Dream Bowl Palace",
      "Dream Bowl Unterföhring",
      "Dream Bowl Unterführing",
      "Dream-Bowl",
      "Dream-Bowl München",
      "Dream-Bowl Palace",
      "Dream-Bowl Palace Ufö.",
      "Dream-Bowl Unterföhring",
      "Dream-Bowl-Palace",
      "DreamBowl",
      "DreamBowl Palace",
      "DreamBowl Palace Unt.fö.",
      "DreamBowl Palace Unterführg",
      "DreamBowl Palace Unterföhring",
      "DreamBowl Palace Unterführing",
      "Dreambowl Palace",
      "Dreambowl Unterführing",
      "Dreambowl Unterföhring",
      "München Dream Bowl",
      "München Dream-Bowl Palace",
      "München-Dream Bowl",
      "Unterführing Dreambowl Palace",
    ],
  },
  {
    canonical: "Würzburg Cosmos Arena",
    aliases: [
      "Cosmos Arena Würzburg",
      "Cosmos Bolwing Würzburg",
      "Cosmos Bowling Würzburg",
      "Würzburg Cosmos",
      "Würzburg Cosmos Bowling",
      "Würzburg Cosmos-Bowling",
      "Würzburg-Cosmos Bowling",
    ],
  },
];

const PLACEHOLDERS = new Set(["", "unknown", "none", "nan", "tbd", "n/a", "na", "-", "—"]);

function venueIdentityKey(raw: string): string {
  const text = raw.normalize("NFC").trim().replace(/^neu:\s*/i, "").trim();
  return text.toLowerCase();
}

function venueCompactKey(raw: string): string {
  return venueIdentityKey(raw)
    .replace(/[-–—./,]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildLookup(): Map<string, string> {
  const exact = new Map<string, string>();
  const compact = new Map<string, string>();
  const collisions = new Set<string>();
  for (const group of VENUE_GROUPS) {
    for (const label of [group.canonical, ...group.aliases]) {
      const text = label.trim();
      if (!text || PLACEHOLDERS.has(venueIdentityKey(text))) continue;
      exact.set(venueIdentityKey(text), group.canonical);
      const compactKey = venueCompactKey(text);
      const existing = compact.get(compactKey);
      if (existing && existing !== group.canonical) collisions.add(compactKey);
      else if (!existing) compact.set(compactKey, group.canonical);
    }
  }
  for (const key of collisions) compact.delete(key);
  const out = new Map(compact);
  for (const [key, value] of exact) out.set(key, value);
  return out;
}

const LOOKUP = buildLookup();

export function canonicalizeVenueLabel(raw: string): string {
  const text = raw.normalize("NFC").trim();
  if (!text) return "";
  if (PLACEHOLDERS.has(venueIdentityKey(text))) return text;
  return LOOKUP.get(venueIdentityKey(text)) ?? LOOKUP.get(venueCompactKey(text)) ?? text;
}
