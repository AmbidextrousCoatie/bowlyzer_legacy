export type AppLanguage = "de" | "en";

export const LANGUAGE_STORAGE_KEY = "bowlyzer:lang";

export function readStoredLanguage(): AppLanguage {
  if (typeof window === "undefined") return "de";
  return localStorage.getItem(LANGUAGE_STORAGE_KEY) === "en" ? "en" : "de";
}
