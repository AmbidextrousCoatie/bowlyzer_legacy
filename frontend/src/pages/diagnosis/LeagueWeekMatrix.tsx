import { useState } from "react";
import { Link } from "react-router-dom";
import { useWeekMatrix, type WeekMatrixCell } from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { weekMatrixCellPath } from "../../lib/diagnosisLinks";

const STATUS_BG: Record<string, string> = {
  ok: "bg-emerald-100 dark:bg-emerald-950/50",
  warn: "bg-amber-100 dark:bg-amber-950/50",
  bad: "bg-orange-100 dark:bg-orange-950/40",
  critical: "bg-rose-100 dark:bg-rose-950/50",
};

function cellClass(cell: WeekMatrixCell | undefined): string {
  const status = cell?.status ?? "";
  return STATUS_BG[status] ?? "";
}

export function LeagueWeekMatrix() {
  const { t } = useTranslations();
  const [expectedWeeks, setExpectedWeeks] = useState(6);
  const query = useWeekMatrix(expectedWeeks);
  const matrix = query.data?.matrix;
  const longNames = query.data?.league_long_names ?? {};

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.week_matrix_title", "Liga-Wochen-Matrix")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.week_matrix_desc",
            "Zeilen sind Ligen, Spalten Saisons. Pro Zelle fehlende Spieltage (erwartet 1…n) oder ✓ wenn vollständig.",
          )}
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-end gap-4 rounded-sm border border-border bg-surface p-4 lg:p-5">
        <label className="flex flex-col gap-1.5">
          <span className="text-label text-muted">
            {t("ui.diagnosis.expected_weeks", "Erwartete Spieltage")}
          </span>
          <input
            type="number"
            min={1}
            max={52}
            value={expectedWeeks}
            onChange={(e) => setExpectedWeeks(Math.max(1, Number(e.target.value) || 6))}
            className="h-9 w-24 rounded-sm border border-border bg-surface-subtle px-2.5 font-mono text-small"
          />
        </label>
      </div>

      {query.isError && (
        <p className="text-small text-danger-fg">
          {query.error instanceof Error ? query.error.message : "Fehler beim Laden"}
        </p>
      )}

      {query.isPending && (
        <p className="text-small text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}

      {matrix && (
        <section className="rounded-sm border border-border bg-surface overflow-hidden">
          <div className="overflow-x-auto p-4 lg:p-5">
            {matrix.rows.length === 0 ? (
              <p className="text-small text-muted">
                {t("ui.diagnosis.no_week_matrix", "Keine Wochen-Matrix-Daten.")}
              </p>
            ) : (
              <table className="w-full min-w-[480px] border-collapse text-small">
                <thead>
                  <tr>
                    <th className="border border-border bg-surface-subtle px-3 py-2 text-left font-semibold">
                      {t("league", "Liga")}
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
                    <tr key={row.league}>
                      <td className="border border-border px-3 py-2 font-semibold whitespace-nowrap">
                        {row.league}
                      </td>
                      {matrix.seasons.map((season) => {
                        const cell = row.seasons[season];
                        const label = cell?.label ?? "";
                        const href = weekMatrixCellPath(season, row.league, cell, longNames);
                        return (
                          <td
                            key={season}
                            className={`border border-border px-3 py-2 ${cellClass(cell)}`}
                          >
                            {label ? (
                              <Link
                                to={href}
                                className="block text-accent hover:text-accent-hover hover:underline"
                                title={`${row.league} · ${season}`}
                              >
                                {label}
                              </Link>
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
