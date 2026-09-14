import type { HomeTopicPaletteKey } from "./homePalette";

export const EINSTIEG_DEMO_DATABASE = "db_real_merged";

export type EinstiegBeat = {
  path: string;
  params: Record<string, string>;
  caption: string;
};

export type EinstiegStory = {
  id: string;
  persona: string;
  job: string;
  topicKey: HomeTopicPaletteKey;
  beats: readonly EinstiegBeat[];
};

export const EINSTIEG_PAGE = {
  eyebrow: "Einstieg",
  title: "Typische Einstiege",
  intro:
    "Kurze Wege durch echte Seiten — keine parallel gebaute Demo. Du kannst jederzeit abbiegen, Filter ändern oder den nächsten Schritt gehen.",
  hint: "Die Beispiele sind festgehalten (Saison, Club, Spieler). Denselben Weg für dich findest du über Suche und Mein Club.",
  startCta: "Diesen Weg gehen",
  beatsLabel: (count: number) => (count === 1 ? "1 Schritt" : `${count} Schritte`),
} as const;

const EMAX_CLUB = "BC EMAX Unterföhring";
const EMAX_TEAM_1 = "BC EMAX Unterföhring 1";
const BM_FRAUEN = "Bayerische Meisterschaft - Frauen Einzel";
/** Podium-archive group name (Männer Einzel across seasons). */
const BM_EINZEL = "Bayerische Meisterschaft Einzel";
const NBM_MAENNER = "Nordbayrische Meisterschaft Einzel";
/** Career close for the Verbandstag rundgang (Club-300 honor roll). */
const VERBAND_CAREER_PLAYER = "Fliegner, Torsten";
const VERBAND_CAREER_PLAYER_ID = "7418";

export const EINSTIEG_STORIES: readonly EinstiegStory[] = [
  {
    id: "verband",
    persona: "Verbandstag: von den Excels zur dynamischen Auswertung",
    job: "Kurzer Pitch für Clubvertreter: Was steckt alles in 20 Jahren Liga & Meisterschaften?",
    topicKey: "verband",
    beats: [
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "intro",
        },
        caption:
          "Rahmen: neue Datenerfassung im Verband — Bowl-A-Lyzer als gemeinsame Darstellung.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "q-300",
        },
        caption: "Frage stellen: 300er-Rekorde und das letzte perfekte Spiel.",
      },
      {
        path: "/club-300",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption: "Antwort: Club 300 — alle erfassten 300er.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "q-team-games",
        },
        caption: "Frage stellen: höchstes Mannschaftsspiel.",
      },
      {
        path: "/club",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption: "Antwort: Club-Rankings — Höchstes Mannschaftsspiel und weitere Bestenlisten.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "13/14",
          league: "LL S",
          week: "7",
          team: "Schanzer-Strikers Ingolstadt 1",
          round: "5",
        },
        caption: "Und hier das Ergebnis im Detail.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "q-bm",
        },
        caption: "Frage stellen: Dominanz bei der Bayerischen Meisterschaft.",
      },
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          tournament: BM_EINZEL,
        },
        caption:
          "Antwort: Podium-Archiv der Bayerischen Meisterschaft Einzel über die erfassten Jahre.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "excel-liga",
        },
        caption: "Bekanntes Artefakt: Ligatabelle im Excel-Ligaprogramm (Screenshot).",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
        },
        caption: "Dieselbe Ligastory live: Bayernliga 25/26 — Tabelle und Saisonübersicht.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "excel-turnier",
        },
        caption: "Bekanntes Artefakt: Turnierergebnisblatt aus dem Meisterschafts-Excel.",
      },
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          tournament: BM_FRAUEN,
        },
        caption: "BM Frauen 25/26 in der Turnieransicht — Rangliste und Runden statt Workbook.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "career",
        },
        caption: "Alle Ergebnisse eines Spielers auf einen Blick.",
      },
      {
        path: "/spieler",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          player_name: VERBAND_CAREER_PLAYER,
          player_id: VERBAND_CAREER_PLAYER_ID,
          season: "all",
        },
        caption:
          "Abschluss: Karriereseite eines Spielers — Clubs, Wettbewerbe, Trend.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "10/11",
          league: "LL S",
          team: "Bajuwaren München 1",
          week: "1",
        },
        caption:
          "Und schließlich schauen wir uns das Spiel an, in dem Torsten seinen 300er geworfen hat.",
      },
      {
        path: "/",
        params: {
          database: EINSTIEG_DEMO_DATABASE
        },
        caption:
          "Was alles schon da ist, und euer Startpunkt.",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "final_remarks",
        },
        caption: "Was ist heute schon da?",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "final_remarks_2",
        },
        caption: "Was ist noch geplant?",
      },
      {
        path: "/praesentation",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          slide: "q-mitmachen",
        },
        caption: "Frage stellen: Fehlende Daten",
      },
    ],
  },
  {
    id: "spieler",
    persona: "Ich will meine Zahlen verstehen",
    job: "Clubs, Turniere, beste Platzierungen und höchste Scores.",
    topicKey: "player",
    beats: [
      {
        path: "/spieler",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          player_name: "Birkner, Steffen",
          player_id: "25082",
          season: "all",
        },
        caption:
          "Karriere von Steffen Birkner über alle Saisons: Clubs, Wettbewerbe, Highlights und Trend.",
      },
      {
        path: "/spieler",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          player_name: "Birkner, Steffen",
          player_id: "25082",
          season: "25/26",
        },
        caption:
          "Dieselbe Spielerseite auf Saison 25/26 gefiltert — nur die Ergebnisse der aktuellen Saison.",
      },
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          player: "Birkner, Steffen",
          season: "25/26",
          tournament: NBM_MAENNER,
          round: "3",
        },
        caption: "Wie hat Steffen in einem Turnier abgeschnitten?",
      },
    ],
  },
  {
    id: "club",
    persona: "Ich interessiere mich für meinen Club",
    job: "Die besten Ergebnisse der Mitglieder, dann Fokus auf die Ligamannschaften des Clubs.",
    topicKey: "club",
    beats: [
      {
        path: "/spieler",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          myClub: EMAX_CLUB,
        },
        caption: "Die besten Ergebnisse der Club-Mitglieder über den Verlauf des Club-Bestehens.",
      },
      {
        path: "/club",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          club: EMAX_CLUB,
        },
        caption:
          "Club-Übersicht von BC EMAX Unterföhring: alle Mannschaften, Platzierungsverlauf und die Saison×Liga-Matrix.",
      },
      {
        path: "/club",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          club: EMAX_CLUB,
          season: "25/26",
        },
        caption:
          "Saison 25/26 in der Club-Übersicht: Matrix und aktueller Ligastand nur für diese Saison.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          myClub: EMAX_CLUB,
          season: "17/18",
        },
        caption:
          "Mein Club auf Liga: nur die Spielklassen, in denen BC EMAX Unterföhring 17/18 vertreten war — Spielplan und Tabellen für genau diese Ligen.",
      },
      {
        path: "/club",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          myClub: EMAX_CLUB,
          club: EMAX_CLUB,
          team: EMAX_TEAM_1,
          season: "25/26",
        },
        caption:
          "Mannschaft 1 in Saison 25/26: Platzierungsverlauf, besondere Spiele und Leistung gegen den Liga-Schnitt.",
      },
    ],
  },
  {
    id: "tabelle",
    persona: "Ich möchte allgemeines über die Ligen erfahren.",
    job: "Historisches und aktueller Statistiken, wie etwas das Aufstiegsrennen innerhalb einer Spielklasse.",
    topicKey: "league",
    beats: [
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "all",
          league: "LL N1",
        },
        caption:
          "Historie der Landesliga Nord 1: Schnittverlauf, beste Team- und Einzel-Ergebnisse.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
        },
        caption:
          "Saison 25/26 ohne Liga-Filter: alle Spielklassen nebeneinander — alle Ligen und alle Spielorte - der Überblick für Sportwart und Ligaausschuss.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
        },
        caption:
          "Bayernliga 25/26: Tabelle, Spielplan, Punkteverlauf und Einzel-Schnitte einer Spielklasse.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "19/20",
          level: "5",
        },
        caption:
          "Der Stand im Aufstiegsrennen zur Landesliga im Jahr 2020. Alle BZOLs auf einen Blick",
      },
    ],
  },
  {
    id: "spieltag",
    persona: "Ich will einen Liga-Spieltag verstehen.",
    job: "Saison → Liga → Spieltag → Mannschaft → Spiel.",
    topicKey: "league",
    beats: [
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
        },
        caption: "Zuerst die Saison: 25/26, noch ohne Liga — alle Tabellen dieser Saison.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
        },
        caption: "Liga dazu: Bayernliga — Saisonübersicht dieser Spielklasse.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
          week: "2",
        },
        caption:
          "Spieltag 2: Tabelle, Besondere Leistungen, Team gegen Team — die Ergebnisliste dieses Wochenendes.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
          week: "2",
          team: "BK München 3",
        },
        caption: "Mannschaft BK München 3 an diesem Spieltag — der Spielbericht der Mannschaft.",
      },
      {
        path: "/liga",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          league: "BayL",
          week: "2",
          team: "BK München 3",
          round: "1",
        },
        caption: "Spiel 1: ein einzelnes Spiel der Mannschaft an diesem Spieltag.",
      },
    ],
  },
  {
    id: "meisterschaft",
    persona: "Ich will eine Meisterschaft verstehen",
    job: "Vom Turnier-Archiv in eine Meisterschaft, Runde für Runde.",
    topicKey: "tournament",
    beats: [
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption:
          "Alle Turniere, alle Saisons — das Podium-Archiv, bevor eine Meisterschaft gewählt ist.",
      },
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          tournament: BM_FRAUEN,
        },
        caption:
          "Bayerische Meisterschaft Frauen 25/26: Gesamtwertung, Runden und Format (ℹ am Seitenkopf).",
      },
      {
        path: "/turnier",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
          season: "25/26",
          tournament: BM_FRAUEN,
          round: "3",
        },
        caption: "Dieselbe Meisterschaft, Runde 3 — das Finale, in dem der Titel entschieden wird.",
      },
    ],
  },
  {
    id: "hall-of-fame",
    persona: "Hall of Fame",
    job: "Die besten Ergebnisse von Einzelspielern, Clubs und alle erfassten perfekten 300er Spiele.",
    topicKey: "club300",
    beats: [
      {
        path: "/spieler",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption: "Die besten Ergebnisse von Einzelspielern über alle erfassten Wettbewerbe hinweg.",
      },
      {
        path: "/club",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption: "Die erfolgreichsten Clubs über alle erfassten Wettbewerbe hinweg.",
      },
      {
        path: "/club-300",
        params: {
          database: EINSTIEG_DEMO_DATABASE,
        },
        caption: "Club 300: Alle erfassten perfekten Spiele.",
      },
    ],
  },
] as const satisfies readonly EinstiegStory[];

export function findEinstiegStory(id: string | null | undefined): EinstiegStory | null {
  if (!id) return null;
  return EINSTIEG_STORIES.find((story) => story.id === id) ?? null;
}
