import { buildTournamentUrl, buildUrl } from "./api";

const DB = "db_real_merged";

export type HomeExampleLink = {
  label: string;
  to: string;
};

/** Curated deep links for the landing page (paths match React routes). */
export const HOME_EXAMPLE_LINKS: HomeExampleLink[] = [
  {
    label: "22/23 — Abschlusstabellen aller Ligen",
    to: buildUrl("/liga", { season: "22/23", database: DB }),
  },
  {
    label: "25/26 — Bayernliga - aktuelle Saisonübersicht",
    to: buildUrl("/liga", { season: "25/26", league: "BayL", database: DB }),
  },
  {
    label: "22/23 — Bezirksoberliga Süd 1 - Spieltag 3",
    to: buildUrl("/liga", { season: "22/23", league: "BZOL S1", week: "3", database: DB }),
  },
  {
    label: "25/26 — Bayernliga - Spieltag 2 - BK München 2",
    to: buildUrl("/liga", {
      season: "25/26",
      league: "BayL",
      week: "2",
      team: "BK München 3",
      database: DB,
    }),
  },
  {
    label: "25/26 — Nordbayerische Meisterschaft - Gesamt",
    to: buildTournamentUrl("/turnier", {
      season: "25/26",
      tournament: "Nordbayerische Meisterschaft",
    }),
  },
  {
    label: "25/26 — Bayerische Meisterschaft - Frauen - Finale",
    to: buildTournamentUrl("/turnier", {
      season: "25/26",
      tournament: "Bayerische Meisterschaft - Frauen Einzel",
      round: "3",
    }),
  },
  {
    label: "25/26 — Südbayerische Meisterschaft - Spieler - Alexander Koller",
    to: buildTournamentUrl("/turnier", {
      season: "25/26",
      tournament: "Südbayerische Meisterschaft",
      player: "Alexander Koller",
    }),
  },
  {
    label: "Clubübersicht — BC EMAX Unterföhring",
    to: buildUrl("/club", { club: "BC EMAX Unterföhring", database: DB }),
  },
  {
    label: "Spielerprofil — Steffen Birkner",
    to: buildUrl("/spieler", {
      club: "BC EMAX Unterföhring",
      database: DB,
      player_name: "Birkner, Steffen",
      player_id: "25082",
    }),
  },
];
