/**
 * Persona quiz answers that drive landing-page CTA order and copy tone.
 * Primary: curious outsider. Co-primary: 50+ bowlers used to PDF/Excel results.
 */
export const HOME_PERSONA_DECISIONS = {
  /** After Spieltag: club picker + latest results before name search. */
  ctaOrder: ["myClub", "latestResults", "playerSearch"] as const,
  /** Spouse journey: league table / club over player search. */
  spouseEntry: "leagueOrClub" as const,
  /** Print/PDF export deferred; deep links suffice for v1. */
  printExport: "phase2" as const,
  /** Softer than corporate “ersetzt” wording. */
  legacyBridgeTone: "familiar" as const,
  /** Table snippet over chart for home preview. */
  previewStyle: "standingsTable" as const,
  /** Explainer copy ships DE-first; EN keys stubbed via fallbacks. */
  i18n: "deFirst" as const,
  /** Mention Verein/Kegelbahn as real-world context only. */
  entityMapFootnote: true,
  /** History claims data back to ~2006 with growing archive framing. */
  historyClaim: "since2006Growing" as const,
  /** Per-page dismissible hints plus linked glossary. */
  helpModel: "perPagePlusGlossary" as const,
  dismissibleBanners: true,
} as const;
