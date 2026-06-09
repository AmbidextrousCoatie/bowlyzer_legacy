import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  LANGUAGE_STORAGE_KEY,
  readStoredLanguage,
  type AppLanguage,
} from "../lib/language";
import { postJson } from "../lib/api";

export type { AppLanguage };

type LanguageContextValue = {
  language: AppLanguage;
  setLanguage: (next: AppLanguage) => Promise<void>;
  toggleLanguage: () => Promise<void>;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

async function syncServerLanguage(language: AppLanguage): Promise<void> {
  await postJson("/league/set_language", { language });
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [language, setLanguageState] = useState<AppLanguage>(readStoredLanguage);
  const skipInvalidateRef = useRef(true);

  useEffect(() => {
    void syncServerLanguage(readStoredLanguage()).catch((error) => {
      console.error("[language] initial sync failed", error);
    });
  }, []);

  const setLanguage = useCallback(async (next: AppLanguage) => {
    if (next !== "de" && next !== "en") return;
    const previous = readStoredLanguage();

    setLanguageState(next);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, next);

    try {
      await syncServerLanguage(next);
    } catch (error) {
      setLanguageState(previous);
      localStorage.setItem(LANGUAGE_STORAGE_KEY, previous);
      console.error("[language] set_language failed", error);
      throw error;
    }
  }, []);

  const toggleLanguage = useCallback(async () => {
    await setLanguage(language === "de" ? "en" : "de");
  }, [language, setLanguage]);

  useEffect(() => {
    if (skipInvalidateRef.current) {
      skipInvalidateRef.current = false;
      return;
    }
    void queryClient.invalidateQueries();
  }, [language, queryClient]);

  const value = useMemo(
    () => ({ language, setLanguage, toggleLanguage }),
    [language, setLanguage, toggleLanguage],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return ctx;
}
