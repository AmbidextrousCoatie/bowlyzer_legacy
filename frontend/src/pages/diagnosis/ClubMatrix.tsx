import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useClubMatrix } from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { formatMatrixCellItem, normalizeClubMatrixCell } from "../../lib/clubMatrixCell";
import { DiagnosisToolbar } from "../../components/DiagnosisToolbar";
import { leagueDiagnosisPath } from "../../lib/diagnosisLinks";

function teamLabel(teamNumber: string): string {
  if (teamNumber === "base") return "Basis";
  return teamNumber;
}

export function ClubMatrix() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();
  const club = searchParams.get("club") ?? "";
  const onlyUnnumbered = searchParams.get("only_unnumbered") === "1";

  const query = useClubMatrix(club || null, onlyUnnumbered);

  useEffect(() => {
    if (!query.isSuccess || !club) return;
    const clubs = query.data?.clubs ?? [];
    if (clubs.length > 0 && !clubs.includes(club)) {
      const next = new URLSearchParams(searchParams);
      next.delete("club");
      setSearchParams(next, { replace: true });
    }
  }, [query.isSuccess, query.data, club, searchParams, setSearchParams]);

  const matrix = query.data?.matrix;
  const longNames = query.data?.league_long_names ?? {};

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
            "Mannschaften eines Vereins und ihre Liga-Zuordnung je Saison.",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
          <label className="flex min-w-[min(100%,280px)] flex-1 flex-col gap-1.5">
            <span className="text-label text-muted">{t("ui.player.club", "Verein")}</span>
            <select
              className="h-9 rounded-sm border border-border bg-surface-subtle px-2.5 text-small text-foreground"
              value={club}
              disabled={query.isPending}
              onChange={(e) => {
                const next = new URLSearchParams(searchParams);
                const v = e.target.value;
                if (v) next.set("club", v);
                else next.delete("club");
                setSearchParams(next, { replace: false });
              }}
            >
              <option value="">{t("ui.diagnosis.select_club", "Verein wählen…")}</option>
              {(query.data?.clubs ?? []).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
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

      {query.isError && (
        <p className="mt-4 text-small text-danger-fg">
          {query.error instanceof Error ? query.error.message : "Fehler beim Laden"}
        </p>
      )}

      {club && matrix && (
        <section className="mt-6 rounded-sm border border-border bg-surface">
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
      )}
    </div>
  );
}