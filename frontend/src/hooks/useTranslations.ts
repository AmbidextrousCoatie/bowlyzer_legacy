import { useQuery } from "@tanstack/react-query";

import { useLanguage } from "../context/LanguageContext";

import { buildUrl, fetchJson } from "../lib/api";
import { formatCompetitionLabel } from "../lib/competitionDisplayName";

type TranslationsPayload = {
  success: boolean;
  current_language?: string;
  translations?: Record<string, string>;
  translations_version?: string;
  tournament_abbreviations?: Record<string, string>;
  message?: string;
};

/**
 * Server-driven i18n via ``/league/get_translations?language=…``.
 * Language preference is also stored in a cookie by ``/league/set_language``.
 */
export function useTranslations() {
  const { language, setLanguage, toggleLanguage } = useLanguage();

  const query = useQuery({
    queryKey: ["translations", language] as const,
    queryFn: () =>
      fetchJson<TranslationsPayload>(buildUrl("/league/get_translations", { language })),
    staleTime: 60 * 60_000,
    gcTime: 24 * 60 * 60_000,
  });

  const translations = query.data?.translations ?? {};
  const tournamentAbbreviations = query.data?.tournament_abbreviations ?? {};

  function t(key: string, fallback?: string): string {
    const value = translations[key];
    if (typeof value === "string" && value.length > 0 && value !== key) {
      return value;
    }
    return fallback ?? key;
  }

  function formatCompetition(
    name: string,
    options?: { isTournament?: boolean },
  ): string {
    return formatCompetitionLabel(name, {
      isTournament: options?.isTournament,
      tournamentAbbreviations,
    });
  }

  return {
    t,
    language,
    translations,
    tournamentAbbreviations,
    formatCompetition,
    query,
    setLanguage,
    toggleLanguage,
  };
}
