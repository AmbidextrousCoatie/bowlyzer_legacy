import { createContext, useCallback, useContext, useMemo, useState } from "react";

type MobileNavContextValue = {
  mobileOpen: boolean;
  openMobileNav: () => void;
  closeMobileNav: () => void;
  /** Liga page merges menu + filters in landscape; hide the global mobile top bar. */
  leagueCompactChrome: boolean;
  setLeagueCompactChrome: (active: boolean) => void;
};

const MobileNavContext = createContext<MobileNavContextValue | null>(null);

export function MobileNavProvider({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [leagueCompactChrome, setLeagueCompactChrome] = useState(false);

  const openMobileNav = useCallback(() => setMobileOpen(true), []);
  const closeMobileNav = useCallback(() => setMobileOpen(false), []);

  const value = useMemo(
    () => ({
      mobileOpen,
      openMobileNav,
      closeMobileNav,
      leagueCompactChrome,
      setLeagueCompactChrome,
    }),
    [mobileOpen, openMobileNav, closeMobileNav, leagueCompactChrome],
  );

  return <MobileNavContext.Provider value={value}>{children}</MobileNavContext.Provider>;
}

export function useMobileNav(): MobileNavContextValue {
  const ctx = useContext(MobileNavContext);
  if (!ctx) {
    throw new Error("useMobileNav must be used within MobileNavProvider");
  }
  return ctx;
}
