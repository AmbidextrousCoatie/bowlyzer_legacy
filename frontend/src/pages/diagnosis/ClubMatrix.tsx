import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ClubMultiSearch } from "../../components/ClubMultiSearch";
import { DiagnosisToolbar } from "../../components/DiagnosisToolbar";
import type { ClubMatrixPayload } from "../../hooks/useLeague";
import { useClubMatrices, useClubMatrix } from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { formatMatrixCellItem, normalizeClubMatrixCell } from "../../lib/clubMatrixCell";
import { leagueDiagnosisPath } from "../../lib/diagnosisLinks";

function teamLabel(teamNumber: string): string {
  if (teamNumber === "base") return "Basis";
  return teamNumber;
}

export function ClubMatrix() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();
  const onlyUnnumbered = searchParams.get("only_unnumbered") === "1";

  const selectedClubs = useMemo(
    () => [...new Set(searchParams.getAll("club").map((c) => c.trim()).filter(Boolean))],
    [searchParams],
  );

  const listQuery = useClubMatrix(null, onlyUnnumbered);
  const matrixQueries = useClubMatrices(selectedClubs, onlyUnnumbered);

  const availableClubs = listQuery.data?.clubs ?? [];

  function setSelectedClubs(clubs: string[]) {
    const next = new URLSearchParams(searchParams);
    next.delete("club");
    for (const c of clubs) {
      if (c.trim()) next.append("club", c.trim());
    }
    setSearchParams(next, { replace: false });
  }

  useEffect(() => {
    if (!listQuery.isSuccess || selectedClubs.length === 0) return;
    const valid = listQuery.data?.clubs ?? [];
    if (valid.length === 0) return;
    const filtered = selectedClubs.filter((c) => valid.includes(c));
    if (filtered.length === selectedClubs.length) return;
    const next = new URLSearchParams(searchParams);
    next.delete("club");
    for (const c of filtered) next.append("club", c);
    setSearchParams(next, { replace: true });
  }, [listQuery.isSuccess, listQuery.data, selectedClubs, searchParams, setSearchParams]);

  const longNames =
    matrixQueries.find((q) => q.data?.league_long_names)?.data?.league_long_names ?? {};

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">{t("ui.diagnosis.club_matrix_title", "Club-Matrix")}</h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.club_matrix_desc",
            "Mannschaften eines Vereins und ihre Liga-Zuordnung je Saison. Mehrere Vereine parallel auswählbar.",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
        <label className="flex min-w-[min(100%,360px)] flex-1 flex-col gap-1.5">
          <span className="text-label text-muted">{t("ui.player.club", "Verein")}</span>
          <ClubMultiSearch
            selected={selectedClubs}
            clubs={availableClubs}
            isLoading={listQuery.isPending}
            placeholder={t("ui.diagnosis.club_matrix_search_placeholder", "Verein suchen…")}
            ariaLabel={t("ui.diagnosis.club_matrix_clubs_aria", "Vereine auswählen")}
            removeChipAriaLabel={(club) =>
              t("ui.diagnosis.club_matrix_remove_chip", `${club} entfernen`)
            }
            onChange={setSelectedClubs}
          />
        </label>
        <label className="flex items-center gap-2 pb-1 text-small text-foreground">
          <input
            type="checkbox"
            className="h-4 w-4 rounded-xs border-border accent-accent"
            checked={onlyUnnumbered}
            onChange={(e) => {
              const next = new URLSearchParams(searchParams);
              if (e.target.checked) next.set("only_unnumbered", "1");
              else next.delete("only_unnumbered");
              setSearchParams(next, { replace: false });
            }}
          />
          {t(
            "ui.diagnosis.only_unnumbered",
            "Nur Vereine mit unnummeriertem Team",
          )}
        </label>
      </DiagnosisToolbar>

      {listQuery.isError && (
        <p className="mt-4 text-small text-danger-fg">
          {listQuery.error instanceof Error ? listQuery.error.message : "Fehler beim Laden"}
        </p>
      )}

      <div className="mt-6 space-y-8">
        {selectedClubs.map((club, index) => (
          <ClubMatrixSection
            key={club}
            club={club}
            query={matrixQueries[index]!}
            longNames={longNames}
            t={t}
          />
        ))}
      </div>
    </div>
  );
}

type SectionProps = {
  club: string;
  query: UseQueryResult<ClubMatrixPayload>;
  longNames: Record<string, string>;
  t: (key: string, fallback?: string) => string;
};

function ClubMatrixSection({ club, query, longNames, t }: SectionProps) {
  const matrix = query.data?.matrix;

  if (query.isPending) {
    return (
      <section className="rounded-sm border border-border bg-surface">
        <header className="border-b border-border px-4 py-3 lg:px-5">
          <h2 className="text-h3 text-muted">
            {club} — {t("status.loading", "Laden…")}
          </h2>
        </header>
        <div className="p-4 lg:p-5">
          <div className="h-32 animate-pulse rounded-xs bg-surface-subtle" />
        </div>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="rounded-sm border border-border border-danger-fg/30 bg-surface p-4 text-small text-danger-fg lg:p-5">
        {club}:{" "}
        {query.error instanceof Error ? query.error.message : t("error_generic", "Fehler")}
      </section>
    );
  }

  if (!matrix) return null;

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <h2 className="text-h3">
          {club} — {t("ui.diagnosis.team_x_season", "Mannschaft × Saison")}
        </h2>
      </header>
      <div className="overflow-x-auto p-4 lg:p-5">
        {matrix.rows.length === 0 ? (
          <p className="text-small text-muted">
            {t("ui.diagnosis.no_matrix_data", "Keine Matrix-Daten für diesen Verein.")}
          </p>
        ) : (
          <table className="w-full min-w-[480px] border-collapse text-small">
            <thead>
              <tr>
                <th className="border border-border bg-surface-subtle px-3 py-2 text-left font-semibold">
                  {t("team", "Mannschaft")}
                </th>
                {matrix.seasons.map((season) => (
                  <th
                    key={season}
                    className="border border-border bg-surface-subtle px-3 py-2 text-left font-semibold whitespace-nowrap"
                  >
                    {season}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.rows.map((row) => (
                <tr key={row.team_number}>
                  <td className="border border-border px-3 py-2 font-semibold">
                    {teamLabel(row.team_number)}
                  </td>
                  {matrix.seasons.map((season) => {
                    const { items } = normalizeClubMatrixCell(row.seasons[season]);
                    return (
                      <td key={season} className="border border-border px-3 py-2 align-top">
                        {items.length > 0 ? (
                          <div className="flex flex-col gap-0.5">
                            {items.map((item) => (
                              <Link
                                key={item.league}
                                to={leagueDiagnosisPath(season, item.league, longNames)}
                                className="text-accent hover:text-accent-hover hover:underline"
                              >
                                {formatMatrixCellItem(item)}
                              </Link>
                            ))}
                          </div>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
