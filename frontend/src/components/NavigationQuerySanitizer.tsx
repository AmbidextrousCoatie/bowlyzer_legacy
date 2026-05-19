import { useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { searchParamsForPath } from "../lib/navigationQuery";

/** Drop page-scoped query keys when the route changes (not on component unmount). */
export function NavigationQuerySanitizer() {
  const { pathname } = useLocation();
  const [, setSearchParams] = useSearchParams();

  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = searchParamsForPath(pathname, prev);
        return next.toString() === prev.toString() ? prev : next;
      },
      { replace: true },
    );
  }, [pathname, setSearchParams]);

  return null;
}
