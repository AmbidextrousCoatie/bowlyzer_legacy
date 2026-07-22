import { buildUrl } from "./api";
import type { HomeTopicPaletteKey } from "./homePalette";

export type HomeExplainerBlock = {
  id: string;
  eyebrow: string;
  title: string;
  body: string;
  bullets?: string[];
  cta?: { label: string; to: string };
};

export const HOME_HERO = {
  eyebrow: "Bowl-A-Lyzer",
  headline: "Liga- und Turnierergebnisse aus Bayern — tagesaktuell und durchsuchbar.",
  subcopy:
    "Die offiziellen Ergebnisse der Bayerischen Bowling Union — wie früher in der Ergebnisliste, aber jederzeit abrufbar und filterbar.",
  bbuUrl: "https://bowlingbayern.de",
  bbuLabel: "Bayerischen Bowling Union",
  welcomeClub: (club: string) => `Willkommen — ${club}`,
  welcomeClubSub: "Dein Club ist gesetzt. Hier findest du Liga, Turniere und Spieler auf einen Blick.",
} as const;

export const HOME_QUICK_START = {
  eyebrow: "Schnellstart",
  title: "Spieler, Club oder Glossar — direkt loslegen",
  playerSearchCta: "Spieler suchen",
  playerSearchDescription:
    "Spielernamen oder EDV-Nummer finden und zur persönlichen Spieler-Seite springen.",
  clubSearchCta: "Club suchen",
  clubSearchDescription: "Club finden und zur Club-Seite springen.",
  myClubCta: "Mein Club",
  myClubDescription:
    "Deinen Club festlegen — Liga und Turnier werden auf seine Teilnahmen gefiltert.",
  glossaryCta: "Glossar",
  glossaryDescription: "falls einzelne Begriffe unklar sind",
  glossaryButton: "Zum Glossar",
} as const;

export const HOME_LEGACY_BRIDGE = {
  title: "Von der Ergebnisliste zum Live-Archiv",
  body: "Ihr findet hier viele Liga- und Turnier-Ergebnisse aus den letzen 3 Jahrzehnten. Euer Mehrwert: jederzeit abrufbar — nach Spieler, Club, Spieltag und Tunier filterbar.",
} as const;

export const HOME_FOOTER = {
  dataNote: "Datenbasis wächst laufend — Rückmeldungen willkommen.",
  cheers: "Cheers, Chris",
} as const;

export const HOME_HISTORY = {
  eyebrow: "Geschichte",
  title: "Vom Excel-Archiv zum durchsuchbaren Nachschlagewerk",
  timeline: [
    {
      era: "Früher",
      text: "Liga- und Turnierergebnisse erschienen als PDF oder Excel — punktuell, schwer zu durchsuchen.",
    },
    {
      era: "Heute",
      text: "Bowl-A-Lyzer bündelt dieselben BBU-Daten interaktiv: nach Saison, Liga, Spieltag, Club oder Spieler.",
    },
    {
      era: "Archiv",
      text: "Das Archiv reicht zurück bis etwa 2006 und wächst mit jeder Saison.",
    },
  ],
  statsIntro: (games: string, seasons: string, years: string, tournaments: string, players: string) =>
    `Aktuell: ${games} Spiele · ${seasons} Liga-Saisons · ${years} Jahre · ${tournaments} Turniere · ${players} Spieler.`,
} as const;

export const WHY_BOWLYZER = {
  eyebrow: "Hintergrund",
  title: "Warum Bowl-A-Lyzer?",
  intro:
    "Bowl-A-Lyzer ist aus der Praxis des bayerischen Ligabetriebs entstanden: Ergebnislisten waren da, aber schwer auffindbar, vergleichbar und historisch nachvollziehbar.",
  motivation: {
    title: "Motivation",
    paragraphs: [
      "Viele aktive Spieler kennen noch die Excel- oder PDF-Ergebnislisten der BBU — veröffentlicht im Nachgang an den Spieltag, ohne Suche, ohne Filter, ohne Vergleich über Saisons hinweg.",
      "Bowl-A-Lyzer macht dieselben Daten durchsuchbar: nach Spieler, Club, Liga, Spieltag oder Turnier — und ergänzt sie schrittweise um Statistiken, die in Tabellen allein fehlen.",
    ],
  },
  dataSources: {
    title: "Datenquellen",
    paragraphs: [
      "Grundlage sind die offiziellen Ergebnisse der Bayerischen Bowling Union (BBU). Liga- und Turnierdaten werden fortlaufend importiert, bereinigt und mit älteren Archivbeständen zusammengeführt.",
      "Nicht jede historische Saison ist vollständig oder in gleicher Detailtiefe verfügbar — fehlende Spieltage, Formatwechsel oder OCR-Artefakte aus älteren PDF-Quellen können vorkommen. Die Datenbasis wächst laufend.",
    ],
    bbuUrl: "https://bowlingbayern.de",
    bbuLabel: "Bayerischen Bowling Union",
  },
  leagueFormats: {
    title: "Ligaformate & Archiv",
    paragraphs: [
      "Der bayerische Ligabetrieb hat sich über die Jahre verändert: andere Spielklassen, andere Gebietsaufteilungen, teils andere Wertungssysteme. Bowl-A-Lyzer bildet die jeweils gültigen Formate pro Saison ab — historische Tabellen folgen den Regeln ihrer Zeit.",
      "Turnierformate (Qualifikation, Cut, K.-o., Handicap ja/nein) variieren ebenfalls. Details zu einem Turnier findest du am ℹ-Symbol auf der Turnierseite.",
    ],
    bullets: [
      "Ligaarchive ab etwa 2006, ausgebaut mit jedem Import",
      "Turnierarchive reichen bis 2000 zurück, jedoch sind noch nicht alle Ergebnisse eingepflegt",
      "Club- und Spielernamen werden über Saisons hinweg zusammengeführt, wo möglich",
    ],
  },
  behindTheScenes: {
    title: "Hinter den Kulissen",
    paragraphs: [
      "Import, Validierung und Zusammenführung laufen als Datenpipeline — Fehler und Ausreißer werden gesammelt und nachgebessert. Feedback per E-Mail hilft, Lücken zu schließen.",
    ],
  },
} as const;

export type HomeEntityStep = {
  label: string;
  description: string;
  to: string;
  paletteKey: HomeTopicPaletteKey;
};

export type HomeEntityGroup = {
  id: string;
  eyebrow: string;
  title: string;
  steps: HomeEntityStep[];
};

export const HOME_ENTITY_MAP = {
  groups: [
    {
      id: "stats",
      eyebrow: "Akteure & Rekorde",
      title: "Spieler, Clubs und besondere Leistungen",
      steps: [
        {
          label: "Spieler",
          description: "Karriereseite für Einzelspieler mit Ergebnissen, Statistiken und Rekorden",
          to: "/spieler",
          paletteKey: "player",
        },
        {
          label: "Club",
          description: "Club-Historie mit Ergebnissen, Statistiken und Rekorden",
          to: "/club",
          paletteKey: "club",
        },
        {
          label: "Club 300",
          description: "Alle erfassten perfekten 300er Spiele — die höchste Einzelleistung im Bowling",
          to: "/club-300",
          paletteKey: "club300",
        },
      ] satisfies HomeEntityStep[],
    },
    {
      id: "events",
      eyebrow: "Wettbewerbe & Ergebnisse",
      title: "Liga, Turniere und Pokal — Saison für Saison",
      steps: [
        {
          label: "Liga",
          description: "Über mehrere Spieltage ausgetragener Wettbewerb mit Auf- und Abstieg in verschiedene Spielklassen",
          to: "/liga",
          paletteKey: "league",
        },
        {
          label: "Turniere",
          description: "Meisterschaften, Einzel, Doppel, Mixed und Trio Wettbewerbe",
          to: "/turnier",
          paletteKey: "tournament",
        },
        {
          label: "Clubpokal",
          description: "Verteilt ausgetragener K.-o.-Wettbewerb für Clubmannschaften mit abschließendem Turnier",
          to: "/clubpokal",
          paletteKey: "clubpokal",
        },
      ] satisfies HomeEntityStep[],
    },
  ] satisfies HomeEntityGroup[],
  footnote: "",
} as const;

export const CLUBPOKAL_PLACEHOLDER = {
  title: "Clubpokal",
  headline: "Demnächst verfügbar",
  body: "Die Clubpokal-Ansicht mit Runden, Paarungen und Ergebnissen ist in Arbeit.",
} as const;

export const HOME_EXPLAINERS: HomeExplainerBlock[] = [
  {
    id: "league",
    eyebrow: "Liga",
    title: "Ligaspiel in 60 Sekunden",
    body: "In der Saison treten Mannschaften wöchentlich in ihrer Liga gegeneinander an. Die Tabelle zeigt Platzierungen und Punkte.",
    bullets: [
      "Saison wählen (z. B. 25/26)",
      "Liga wählen (z. B. Bayernliga)",
      "Spieltag öffnen für Einzelergebnisse",
      "Tabelle = Abschlusstabelle nach jedem Spieltag",
    ],
    cta: { label: "Zur Liga-Übersicht", to: buildUrl("/liga", { season: "latest" }) },
  },
  {
    id: "tournament",
    eyebrow: "Turnier",
    title: "Turniere in 60 Sekunden",
    body: "Meisterschaften laufen oft über mehrere Runden — Qualifikation, K.-o.-Phase, Finale. Die Gesamtwertung fasst alle Runden zusammen.",
    bullets: [
      "Saison und Turnier wählen",
      "Runde für Runden-Ergebnisse",
      "Gesamtstand für die Meisterschaftswertung",
      "ℹ-Symbol erklärt Turnierformat und Handicap-Regeln",
    ],
    cta: { label: "Zu den Turnieren", to: "/turnier" },
  },
];

export const HOME_SECTIONS = {
  statsEyebrow: "Umfang",
  stats: "Daten im Überblick",
  preview: "Aktuelle Tabelle",
  previewHint: "Auszug aus der Bayernliga — wie in der gewohnten Ergebnisliste.",
  club300: "Club 300",
  club300Teaser: "Perfekte 300er — die höchste Einzelleistung im Bowling.",
  examples: "Direkt zu Beispiel-Ansichten",
  latestEvents: "Letzte Events",
  latestEventsAnchor: "latest-events",
} as const;

export const GLOSSARY_ENTRIES = [
  {
    term: "Scratch Ergebnis",
    definition: "Das erzielte Ergebnis ohne Handicap — die tatsächlich erspielten Pins.",
  },
  {
    term: "Hcp / Handicap",
    definition:
      "Maßnahme zur Erhöhung der Chancengleichheit - in manchen Wettbewerben erhalten Spieler basierend auf vorhergehenden Leistungen individuell errechnete Bonus-Pins. Diese werden zu jedem Scratch Ergebnis hinzuaddiert und sorgen dafür, dass schwächere Spieler in einem Vergleich bestehen können.",
  },
  {
    term: "Netto Ergebnis",
    definition: "Wert mit Handicap — für faire Vergleiche zwischen Spielern unterschiedlicher Stärke.",
  },
  {
    term: "Club",
    definition:
      "Ein Club ist eine organisatorische Einheit, die einem Verein zugeordnet wird. Jeder Club kann mehrere Mannschaften in unterschieldichen Wettbewerben stellen.",
  },
  {
    term: "Spieler",
    definition: "Ein Spieler muss zwingend einem Verein angehören und für manche Wettbewerbe auch einem Club. Ein Spieler kann zu jedem Zeitpunkt für einen Verein und Club aktiv sein. Wettbwerbe auf Vereinsebene sind z.B. die Landesmeisterschaften und der Ligabetrieb wird von Clkubmitgliedern bestritten. Darüber hinaus kann eine Spieler auch individuell an offen Turnieren teilnehmen.",
  },
  {
    term: "Team / Mannschaft",
    definition:
      "Team innerhalb eines Clubs — erkennbar an der Nummer am Namen (z. B. „… Regensburg 2“). Je nach Wettbewerbsbestiummungen kann ein Spieler für mehrere Teams des selben Clubs innerhalb einer Saison antreten.",
  },
  {
    term: "Saison",
    definition: "Das Sportjahr geht von Juli bis Juni (z. B. 25/26).",
  },
  {
    term: "Wettbewerbe",
    definition:
      "Ein Wettbewerb ist eine Reihe von Spielen, die in einer bestimmten Zeitspanne stattfinden. Er kann sich hierbei um eine Liga, ein Turnier oder ein Pokalwettbewerb handeln.",
  },
  {
    term: "Liga",
    definition: "Eine Liga besteht aus mehreren Teams die je nach Spielklasse aus unterschiedlich größen Gebieten stammen. Über ein Sportjahr hinweg werden über mehrere Spieltage verteilt die Platzierungen ausgespielt, wobei es am Saisonende ein Auf- und Abstiegs-System gibt.",
  },
  {
    term: "Spieltag",
    definition:
      "Ein Spieltag in der Liga — alle Mannschaften einer Liga reisen zu einer gastgebenden Mannschaft. Dort spielt jede Mannschaft ein direktes duell gegen jeden Gegner aus und erhält so ihre Wertungspunkte; Nach jedem Spieltag wird die Tabelle aktualisiert.",
  },
  {
    term: "Pokal",
    definition: "Der Clubpokal ist ein K.O. Format, bei dem über den Zeitraum mehrerer Monaten in der Regel 5 Pokalrunden ausgetragen werden. Das Los bestimmt über Spiel-Paarungen und Heimrecht. Der Pokalsieger wird in einem abschließenden Turnier ermittelt, in dem in der Regel die verbleibenden 10 Teams aus Nord- und Südbereich gegeneinander antreten.",
  },
  {
    term: "Turnier",
    definition:
      "Ein Turnier ist ein Wettbewerb, der über mehrere Runden hinweg ausgetragen wird. Im Verlauf des Turnieres wird das Teilnehmerfeld in der Regel durch eine Cut-Regelung sukzessive verkleinert. In manchen Turniere wird noch eine Finalrunde unter gänderten Bedingungen, z.B. Stepladder oder Elimination ausgespielt.",
  },
  {
    term: "Cutline",
    definition: "Runden-Grenze in einem Turnier — wer darüber liegt, qualifiziert sich für die nächste Runde. So werden über den Verlauf des Turniers die besten Spieler ermittelt.",
  },
] as const;
