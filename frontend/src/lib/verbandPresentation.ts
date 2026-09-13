/**
 * Slide content for the Verbandstag presentation journey (`story=verband`).
 * Deep-linked via `/praesentation?slide=…` — same story/beat mechanic as Einstieg.
 *
 * Replace files under `public/presentation/` when real Excel screenshots arrive.
 */

export const PRESENTATION_PATH = "/praesentation";
export const PRESENTATION_SLIDE_QUERY_KEY = "slide";

export type VerbandSlideId =
  | "intro"
  | "q-300"
  | "q-team-games"
  | "q-bm"
  | "excel-liga"
  | "excel-turnier"
  | "career"
  | "final_remarks"
  | "final_remarks_2";

export type VerbandSlideLayout = "talk" | "question" | "artifact";

export type VerbandSlide = {
  id: VerbandSlideId;
  layout: VerbandSlideLayout;
  eyebrow: string;
  /** Page title (talk/artifact) or short label above the question. */
  title: string;
  /** Central question — rendered at display size when `layout === "question"`. */
  question?: string;
  /** Short lead under the title / question. */
  lead?: string;
  /** Body paragraphs (talking points). */
  paragraphs: readonly string[];
  /** Optional screenshot / placeholder image (public URL). */
  imageSrc?: string;
  imageAlt?: string;
  imageCaption?: string;
};

export const VERBAND_SLIDES: Record<VerbandSlideId, VerbandSlide> = {
  intro: {
    id: "intro",
    layout: "talk",
    eyebrow: "Verbandstag",
    title: "Das Gegenstück zur neuen Datenerfassung",
    lead: "Die BBU stellt ja gerade die Ergebniserfassung auf digital um. Der Bowl-A-Lyzer zeigt, was alles aus den Daten gewonnen werden kann.",
    paragraphs: [
      "Kleiner Rundgang durch historische Bestleistungen und die Infos die wichtig sind für Liga & Meisterschaften."
    ],
  },
  "q-300": {
    id: "q-300",
    layout: "question",
    eyebrow: "Quiz I",
    title: "300er",
    question: "Wer hat die meisten 300er — und wer warf den letzten?",
    lead: "Die Antworten darauf gibt's im Club 300.",
    paragraphs: [],
  },
  "q-team-games": {
    id: "q-team-games",
    layout: "question",
    eyebrow: "Quiz II",
    title: "Mannschaftsspiele",
    question: "Was war das höchste Mannschaftsspiel aller Zeiten?",
    lead: "Finden wirs raus im Allzeit-Club-Ranking.",
    paragraphs: [],
  },
  "q-bm": {
    id: "q-bm",
    layout: "question",
    eyebrow: "Quiz III",
    title: "Meisterschaften",
    question: "Wer dominierte die Bayerische Meisterschaft über die Jahre?",
    lead: "Ist bestimmt kein Geheimnis, aber das Podiums-Archiv verschafft uns Gewissheit.",
    paragraphs: [],
  },
  "excel-liga": {
    id: "excel-liga",
    layout: "artifact",
    eyebrow: "Ligabetrieb",
    title: "Ligatabelle im Ligaprogramm",
    lead: "So kennen viele die Liga heute: Der Excel-Export in dem alle Infos stecken, die sich aber mühsam erarbeitet werden müssen.",
    paragraphs: [
      "Dieselbe Story jetzt live — filterbar nach Saison, Spielklasse, Liga und Mannschaft.",
    ],
    imageSrc: "/presentation/slide_league.png",
    imageAlt: "Excel-Screenshot Ligatabelle",
    imageCaption: "Die diversen Informationen aus den Excel-Exporten.",
  },
  "excel-turnier": {
    id: "excel-turnier",
    layout: "artifact",
    eyebrow: "Turniere",
    title: "Turnierergebnis als Excelexport",
    lead: "Nach den Meisterschaften erlaubt der Blick in die Ergebnis-Excel einen Überblick über das Turnier.",
    paragraphs: [
      "Die Tunierseite erlaubt detaillierte Einblicke, sowohl ins Turnier als auch in die Leistung Einzelner.",
    ],
    imageSrc: "/presentation/slide_tournament.png",
    imageAlt: "Excel-Screenshot Turnierergebnisse",
    imageCaption: "Turnierergebnisse aus mehreren Jahren.",
  },
  "career": {
    id: "career",
    layout: "question",
    eyebrow: "Quiz III",
    title: "Alle Ergebnisse eines Spielers auf einen Blick",
    question: "Was hat Torsten denn für Erfolge vorzuweisen?",
    lead: "Schauen wir uns mal seine Karriere-Seite an.",
    paragraphs: [],
  },
  final_remarks: {
    id: "final_remarks",
    layout: "talk",
    eyebrow: "Abschluss",
    title: "Was ist heute schon da?",
    lead: "Alles basiert auf einzeln erfassten Spielen. Saison, Spieler, Liga, Turnier Club ... das sind alles nur Filter, welche die Daten Stück für Stück aussieben.",
    paragraphs: [
      "- Liga-Archiv bis zurück ins Jahr 2008, jedes einzelne Spiel erfasst basierend auf den Spielzetteln.",
      "- Turnier-Archiv bis zurück ins Jahr 2005, SBM / NBM, BM Frauen & Männer bis auf wenige Ausnahmen.",
      "- Club-300: Jeder 300er einzeln aufgeführt.",
      "- Allzeit Statistiken für Clubs und Einzelspieler",
      "- Prototyp für Anbindung an digital erfasste Ergebnisse steht."
    ],
  },
  final_remarks_2: {
    id: "final_remarks_2",
    layout: "talk",
    eyebrow: "Abschluss",
    title: "Was ist noch geplant?",
    lead: "Historische Lücken schließen und Ausbau.",
    paragraphs: [
      "- Doppel-Meisterschaften und Senioren-Trios bis ins Jahr 2005 ergänzen.",
      "- Club-Pokal einbauen (Datenlage schwierig).",
      "- Anbindung an den neuen digitalen Live-Betrieb ohne Umweg über Excel.",
    ],
  },
} as const;

export function findVerbandSlide(id: string | null | undefined): VerbandSlide | null {
  if (!id) return null;
  return Object.prototype.hasOwnProperty.call(VERBAND_SLIDES, id)
    ? VERBAND_SLIDES[id as VerbandSlideId]
    : null;
}

export const VERBAND_PRESENTATION_PAGE = {
  missingTitle: "Folie nicht gefunden",
  missingBody: "Unbekannte Präsentationsfolie. Zurück zum Einstieg oder den Rundgang neu starten.",
} as const;
