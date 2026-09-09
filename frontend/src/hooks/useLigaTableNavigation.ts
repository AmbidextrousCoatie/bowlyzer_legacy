import { useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { LeagueTableNavigation } from "../lib/datatable/types";
import type { LigaTableNavKind } from "../lib/leagueNavigation";

/** Liga table cell clicks → URL filters, preserving `database` / `myClub`. */
export function useLigaTableNavigation(
  season: string,
  league: string,
  opts?: {
    week?: string | number | null;
    defaultWeek?: string | number;
    kind?: LigaTableNavKind;
  },
): LeagueTableNavigation {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const onNavigate = useCallback((path: string) => navigate(path), [navigate]);
  const week =
    opts?.week != null && String(opts.week) !== "" ? String(opts.week) : undefined;
  const defaultWeek = opts?.defaultWeek ?? week ?? "";
  const kind = opts?.kind;
  const sourceQuery = searchParams.toString();
  return useMemo(
    () => ({
      season,
      league,
      defaultWeek,
      week,
      sourceQuery,
      onNavigate,
      kind,
    }),
    [season, league, defaultWeek, week, sourceQuery, onNavigate, kind],
  );
}
