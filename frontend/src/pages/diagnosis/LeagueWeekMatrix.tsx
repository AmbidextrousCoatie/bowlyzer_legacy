import { Link } from "react-router-dom";
import { useWeekMatrix, type WeekMatrixCell } from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { DiagnosisToolbar } from "../../components/DiagnosisToolbar";
import { weekMatrixCellPath } from "../../lib/diagnosisLinks";

const STATUS_BG: Record<string, string> = {
  ok: "bg-emerald-100 dark:bg-emerald-950/50",
  warn: "bg-amber-100 dark:bg-amber-950/50",
  bad: "bg-orange-100 dark:bg-orange-950/40",
  critical: "bg-rose-100 dark:bg-rose-950/50",
};

/** Sticky header + league column; scrollport is flush (no inner padding) so cells never bleed into gutters. */
const STICKY_CORNER_TH =
  "sticky top-0 left-0 z-30 border border-border bg-surface-subtle px-3 py-2 text-left font-semibold shadow-[inset_-1px_0_0_var(--color-border),inset_0_-1px_0_var(--color-border)]";
const STICKY_HEAD_TH =
  "sticky top-0 z-20 border border-border bg-surface-subtle px-3 py-2 text-left font-semibold whitespace-nowrap shadow-[inset_0_-1px_0_var(--color-border)]";
const STICKY_ROW_TD =
  "sticky left-0 z-10 border border-border bg-surface px-3 py-2 font-semibold whitespace-nowrap shadow-[inset_-1px_0_0_var(--color-border)]";
const DATA_TD = "relative z-0 border border-border px-3 py-2";

function cellClass(cell: WeekMatrixCell | undefined): string {
  const status = cell?.status ?? "";
  return STATUS_BG[status] ?? "";
}

function cellTitle(cell: WeekMatrixCell | undefined, league: string, season: string): string {
  if (!cell) return `${league} · ${season}`;
  const expected = cell.expected_weeks;
  const teams = cell.team_count;
  const parts = [`${league} · ${season}`];
  if (expected != null) parts.push(`${expected} Spieltage erwartet`);
  if (teams != null && teams > 0) parts.push(`${teams} Teams`);
  if (cell.missing_weeks?.length) {
    parts.push(`fehlend: ${cell.missing_weeks.join(", ")}`);
  }
  return parts.join(" · ");
}

export function LeagueWeekMatrix() {
  const { t } = useTranslations();
  const query = useWeekMatrix();
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
            "Zeilen sind Ligen, Spalten Saisons. Pro Zelle fehlende Spieltage oder ✓ wenn vollständig. Erwartete Spieltage: Bayernliga immer 6, sonst Anzahl Teams in der Liga (historisch oft mehr als 6).",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
        <p className="text-small text-muted max-w-[72ch]">
          {t(
            "ui.diagnosis.week_matrix_rule_hint",
            "Corona-Saisons ohne Spielbetrieb (z. B. 20/21, 21/22) erscheinen nicht als fehlende Wochen, solange für die Liga/Saison keine Daten erwartet werden.",
          )}
        </p>
      </DiagnosisToolbar>

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
          {matrix.rows.length === 0 ? (
            <p className="p-4 text-small text-muted lg:p-5">
              {t("ui.diagnosis.no_week_matrix", "Keine Wochen-Matrix-Daten.")}
            </p>
          ) : (
            <div className="isolate max-h-[min(70vh,720px)] overflow-auto bg-surface">
              <table className="w-full min-w-[480px] border-separate border-spacing-0 text-small">
                <thead className="bg-surface-subtle">
                  <tr>
                    <th className={STICKY_CORNER_TH}>{t("league", "Liga")}</th>
                    {matrix.seasons.map((season) => (
                      <th key={season} className={STICKY_HEAD_TH}>
                        {season}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.rows.map((row) => (
                    <tr key={row.league}>
                      <td className={STICKY_ROW_TD}>{row.league}</td>
                      {matrix.seasons.map((season) => {
                        const cell = row.seasons[season];
                        const label = cell?.label ?? "";
                        const linkLeague = cell?.league_id ?? row.league;
                        const href = weekMatrixCellPath(season, linkLeague, cell, longNames);
                        return (
                          <td
                            key={season}
                            className={`${DATA_TD} ${cellClass(cell) || "bg-surface"}`}
                          >
                            {label ? (
                              <Link
                                to={href}
                                className="block text-accent hover:text-accent-hover hover:underline"
                                title={cellTitle(cell, linkLeague, season)}
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
            </div>
          )}
        </section>
      )}
    </div>
  );
}
