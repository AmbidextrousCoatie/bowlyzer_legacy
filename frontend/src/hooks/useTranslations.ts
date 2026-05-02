import { useQuery } from "@tanstack/react-query";
import { fetchJson } from "../lib/api";

type TranslationsPayload = {
  success: boolean;
  current_language?: string;
  translations?: Record<string, string>;
  translations_version?: string;
  message?: string;
};

/**
 * Server-driven i18n. Mirrors the legacy `/league/get_translations` flow:
 * one fetch returns the active language + translation map. We don't touch
 * sessionStorage caching here — TanStack Query handles in-memory caching.
 */
export function useTranslations() {
  const query = useQuery({
    queryKey: ["translations"],
    queryFn: () => fetchJson<TranslationsPayload>("/league/get_translations"),
    staleTime: 60 * 60_000,
    gcTime: 24 * 60 * 60_000,
  });

  const translations = query.data?.translations ?? {};
  const language = query.data?.current_language ?? "de";

  /**
   * Look up a translation key. Returns the fallback if the key is missing or
   * translations haven't loaded yet.
   */
  function t(key: string, fallback?: string): string {
    const value = translations[key];
    if (typeof value === "string" && value.length > 0 && value !== key) {
      return value;
    }
    return fallback ?? key;
  }

  return { t, language, translations, query };
}
