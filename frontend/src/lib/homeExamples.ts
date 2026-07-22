import { buildTournamentUrl } from "./api";
import { linkForPath } from "./navigationQuery";

const DB = "db_real_merged";

export type HomeExampleLink = {
  label: string;
  to: string;
};

/** Curated deep links for the landing page (paths match React routes). */
export function buildHomeExampleLinks(source: URLSearchParams): HomeExampleLink[] {
  const link = (path: string, params: Record<string, string> = {}) =>
    linkForPath(path, source, params);

  return [
    {
      label: "Saison 22/23 — alle Ligatabellen auf einen Blick",
      to: link("/liga", { season: "22/23", database: DB }),
    },
    {
      label: "Aktuelle Bayernliga — Saisonübersicht",
      to: link("/liga", { season: "25/26", league: "BayL", database: DB }),
    },
    {
      label: "Bezirksoberliga Süd 1 — Spieltag 3 (22/23)",
      to: link("/liga", { season: "22/23", league: "BZOL S1", week: "3", database: DB }),
    },
    {
      label: "Bayernliga — Spieltag 2, Mannschaft BK München",
      to: link("/liga", {
        season: "25/26",
        league: "BayL",
        week: "2",
        team: "BK München 3",
        database: DB,
      }),
    },
    {
      label: "Nordbayerische Meisterschaft — Gesamtergebnis",
      to: linkForPath(
        buildTournamentUrl("/turnier", {
          season: "25/26",
          tournament: "Nordbayerische Meisterschaft",
        }),
        source,
      ),
    },
    {
      label: "Bayerische Meisterschaft Frauen — Finale",
      to: linkForPath(
        buildTournamentUrl("/turnier", {
          season: "25/26",
          tournament: "Bayerische Meisterschaft - Frauen Einzel",
          round: "3",
        }),
        source,
      ),
    },
    {
      label: "Südbayerische Meisterschaft — Spielerprofil Alexander Koller",
      to: linkForPath(
        buildTournamentUrl("/turnier", {
          season: "25/26",
          tournament: "Südbayerische Meisterschaft",
          player: "Alexander Koller",
        }),
        source,
      ),
    },
    {
      label: "Club BC EMAX Unterföhring — Übersicht",
      to: link("/club", { club: "BC EMAX Unterföhring", database: DB }),
    },
    {
      label: "Spielerprofil Steffen Birkner",
      to: link("/spieler", {
        club: "BC EMAX Unterföhring",
        database: DB,
        player_name: "Birkner, Steffen",
        player_id: "25082",
      }),
    },
  ];
}
