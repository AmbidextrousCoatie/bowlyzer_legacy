import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useClubMatrix } from "./useLeague";
import {
  MY_CLUB_QUERY_KEY,
  participationFromClubMatrix,
  type ClubLeagueParticipation,
} from "../lib/myClub";
import { normalizeUnicodeLabel } from "../lib/teamUtils";

export type MyClubState = {
  /** Raw URL value (may be empty). */
  myClub: string;
  /** True when a non-empty myClub is set. */
  active: boolean;
  /** Canonical club label from matrix when resolved. */
  resolvedClub: string;
  setMyClub: (club: string | null) => void;
  clearMyClub: () => void;
  /** League participation for filtering Liga; null while loading / inactive. */
  participation: ClubLeagueParticipation | null;
  participationLoading: boolean;
};

export function useMyClub(): MyClubState {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = (searchParams.get(MY_CLUB_QUERY_KEY) ?? "").trim();
  const active = raw.length > 0;

  const matrixQuery = useClubMatrix(active ? raw : null, false, { enabled: active });

  const resolvedClub = useMemo(() => {
    if (!active) return "";
    const fromApi = (
      matrixQuery.data?.selected_club ||
      matrixQuery.data?.matrix?.club ||
      ""
    ).trim();
    if (fromApi && normalizeUnicodeLabel(fromApi) === normalizeUnicodeLabel(raw)) {
      return fromApi;
    }
    return raw;
  }, [active, matrixQuery.data, raw]);

  const participation = useMemo(() => {
    if (!active || !matrixQuery.isSuccess) return null;
    return participationFromClubMatrix(matrixQuery.data);
  }, [active, matrixQuery.isSuccess, matrixQuery.data]);

  const setMyClub = useCallback(
    (club: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const value = (club ?? "").trim();
          if (!value) next.delete(MY_CLUB_QUERY_KEY);
          else next.set(MY_CLUB_QUERY_KEY, value);
          return next;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  const clearMyClub = useCallback(() => setMyClub(null), [setMyClub]);

  return {
    myClub: raw,
    active,
    resolvedClub,
    setMyClub,
    clearMyClub,
    participation,
    participationLoading: active && matrixQuery.isPending,
  };
}
