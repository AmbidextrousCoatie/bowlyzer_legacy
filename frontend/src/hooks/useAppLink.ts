import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { linkForPath } from "../lib/navigationQuery";

/** Build in-app links that preserve ``myClub`` and other global query params. */
export function useAppLink() {
  const [searchParams] = useSearchParams();
  return useCallback(
    (targetPath: string, params: Record<string, string | number | undefined | null> = {}) =>
      linkForPath(targetPath, searchParams, params),
    [searchParams],
  );
}
