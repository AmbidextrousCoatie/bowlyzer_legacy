import { Link, useSearchParams } from "react-router-dom";
import { useMemo } from "react";
import { DiagnosisToolbar } from "../../components/DiagnosisToolbar";
import { useAvailableSeasons } from "../../hooks/useLeague";
import { useLeagueStandingsValidation, VALIDATION_ERROR_CATEGORIES } from "../../hooks/useLeagueStandingsValidation";
import { useTranslations } from "../../hooks/useTranslations";
import { seasonForUrlQuery } from "../../lib/api";
import { querySuffixForPath } from "../../lib/navigationQuery";

const STATUS_CLASS: Record<string, string> = {
  perfect: "text-emerald-700 dark:text-emerald-400",
  corrected: "text-emerald-700 dark:text-emerald-400",
  green: "text-emerald-700 dark:text-emerald-400",
  yellow: "text-amber-700 dark:text-amber-400",
  red: "text-rose-700 dark:text-rose-400",
  skipped: "text-muted",
};

const GREEN_STATUSES = new Set(["perfect", "corrected", "green"]);

const WEEK_STATUS_CLASS: Record<string, string> = {
  ok: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  bad: "text-orange-700 dark:text-orange-400",
  critical: "text-rose-700 dark:text-rose-400",
};

function findingKind(line: string): "team" | "pos" | "pts" | "pts-total" | "pts-week" | "pins" | "corrected" {
  if (line.startsWith("corrected: ")) return "corrected";
  if (line.startsWith("pts-week: ")) return "pts-week";
  if (line.startsWith("pts-total: ")) return "pts-total";
  if (line.startsWith("pos: ")) return "pos";
  if (line.startsWith("pts: ")) return "pts";
  if (line.startsWith("pins: ")) return "pins";
  return "team";
}

const FINDING_CLASS: Record<string, string> = {
  team: "text-foreground",
  corrected: "text-emerald-800 dark:text-emerald-300 font-medium",
  "pts-week": "text-violet-800 dark:text-violet-300 font-mono text-[0.8125rem]",
  pos: "text-amber-800 dark:text-amber-300",
  pts: "text-orange-800 dark:text-orange-300",
  "pts-total": "text-orange-900 dark:text-orange-200 font-medium",
  pins: "text-rose-800 dark:text-rose-300",
};

const STATUS_FILTER_KEYS = ["perfect", "corrected", "yellow", "red", "skipped", "week_incomplete"] as const;
type StatusFilterKey = (typeof STATUS_FILTER_KEYS)[number];

const STATUS_FILTER_LABEL: Record<StatusFilterKey, string> = {
  perfect: "Perfekt",
  corrected: "Korrigiert",
  yellow: "Gelb",
  red: "Rot",
  skipped: "Übersprungen",
  week_incomplete: "Wochen lückenhaft",
};

const CATEGORY_LABEL: Record<string, string> = {
  perfect: "Perfekt",
  corrected: "Korrigiert",
  teams: "Teams",
  positions: "Platz",
  points: "Punkte/Team",
  pins: "Pins",
  weeks: "Wochen",
  weekly_points: "Punkte/Woche",
  total_points_ref: "Punkte-Summe Excel",
  total_points_comp: "Punkte-Summe Merge",
  points_excel_total: "Excel-Gesamtpunkte",
  skipped: "Übersprungen",
};

function formatTotalPoints(row: {
  total_points_reference?: number;
  total_points_computed?: number;
  total_points_expected?: number;
  reference_total_points_ok?: boolean;
  computed_total_points_ok?: boolean;
}): string {
  const ref = row.total_points_reference;
  const comp = row.total_points_computed;
  const exp = row.total_points_expected;
  if (ref == null && comp == null) return "—";
  const parts = [`${ref ?? "—"}/${comp ?? "—"}`];
  if (exp != null && exp > 0) parts.push(`exp ${exp}`);
  if (row.reference_total_points_ok === false || row.computed_total_points_ok === false) {
    parts.push("!");
  }
  return parts.join(" · ");
}

function formatFindings(row: {
  findings?: string[];
  missing_in_computed?: string[];
  missing_in_reference?: string[];
  position_mismatches?: string[];
  points_mismatches?: string[];
  pins_mismatches?: string[];
}): string[] {
  if (row.findings?.length) return row.findings;
  const lines: string[] = [];
  for (const team of row.missing_in_computed ?? []) lines.push(team);
  for (const team of row.missing_in_reference ?? []) lines.push(team);
  for (const line of row.position_mismatches ?? []) lines.push(`pos: ${line}`);
  for (const line of row.points_mismatches ?? []) lines.push(`pts: ${line}`);
  for (const line of row.pins_mismatches ?? []) lines.push(`pins: ${line}`);
  return lines;
}

function formatWeeks(row: {
  available_weeks?: number[];
  expected_weeks?: number;
  missing_matchdays?: number[];
}): string {
  const available = row.available_weeks?.length ?? 0;
  const expected = row.expected_weeks ?? 0;
  if (!expected) return "—";
  const base = `${available}/${expected}`;
  if (row.missing_matchdays?.length) {
    return `${base} (−${row.missing_matchdays.join(",")})`;
  }
  return base;
}

function hasCompleteWeeks(row: {
  expected_weeks?: number;
  available_weeks?: number[];
  missing_matchdays?: number[];
  week_coverage_status?: string;
}): boolean {
  const expected = row.expected_weeks ?? 0;
  if (expected <= 0) return false;
  if ((row.missing_matchdays?.length ?? 0) > 0) return false;
  if (row.week_coverage_status === "ok") return true;
  return (row.available_weeks?.length ?? 0) >= expected;
}

const PROCESSING_STEP_LABEL: Record<string, string> = {
  team_name_normalization: "Namen",
  team_name_regex: "Namen",
  team_number: "Nr.",
};

function formatTeamMismatchPipeline(row: {
  team_mismatches_raw?: number;
  team_mismatches_after_team_name?: number;
  team_mismatches_final?: number;
  team_resolution_step?: string;
  status_raw?: string;
  status?: string;
}): string | null {
  const raw = row.team_mismatches_raw;
  const afterName = row.team_mismatches_after_team_name;
  const final = row.team_mismatches_final;
  if (raw == null && afterName == null && final == null) {
    return null;
  }
  const parts = [raw ?? 0, afterName ?? raw ?? 0, final ?? afterName ?? raw ?? 0];
  const unique = parts.every((v) => v === parts[0]);
  const chain = unique ? String(parts[0]) : parts.join("→");
  const step = row.team_resolution_step?.trim();
  const stepLabel = step ? PROCESSING_STEP_LABEL[step] ?? step : "";
  const statusHint =
    row.status_raw && row.status_raw !== row.status
      ? ` · Status ${row.status_raw}→${row.status}`
      : "";
  if (!step && parts[0] === 0) {
    return null;
  }
  return stepLabel
    ? `${chain} (${stepLabel})${statusHint}`
    : `${chain}${statusHint}`;
}

export function LeagueStandingsValidation() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();
  const seasonFilter = searchParams.get("season") ?? "";
  const nonGreenOnly = searchParams.get("non_green") === "1";
  const completeWeeksOnly = searchParams.get("weeks_complete") === "1";
  const categoryFilter = useMemo(() => {
    const raw = searchParams.get("categories") ?? "";
    return new Set(
      raw
        .split(",")
        .map((item) => item.trim())
        .filter((item) => VALIDATION_ERROR_CATEGORIES.includes(item as never)),
    );
  }, [searchParams]);
  const statusFilter = useMemo(() => {
    const raw = searchParams.get("statuses") ?? "";
    return new Set(
      raw
        .split(",")
        .map((item) => item.trim())
        .filter((item): item is StatusFilterKey =>
          STATUS_FILTER_KEYS.includes(item as StatusFilterKey),
        ),
    );
  }, [searchParams]);
  const seasonsQuery = useAvailableSeasons();
  const seasonOptions = useMemo(() => {
    const seasons = [...(seasonsQuery.data ?? [])];
    seasons.sort((a, b) => String(b).localeCompare(String(a)));
    return seasons;
  }, [seasonsQuery.data]);
  const query = useLeagueStandingsValidation({
    season: seasonFilter.trim() || null,
  });
  const data = query.data;
  const summary = data?.summary;
  const visibleRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (nonGreenOnly) rows = rows.filter((row) => !GREEN_STATUSES.has(row.status));
    if (completeWeeksOnly) rows = rows.filter((row) => hasCompleteWeeks(row));
    if (statusFilter.size > 0) {
      rows = rows.filter((row) => {
        if (statusFilter.has("week_incomplete")) {
          if ((row.missing_matchdays?.length ?? 0) > 0) return true;
        }
        return statusFilter.has(row.status as StatusFilterKey);
      });
    }
    if (categoryFilter.size > 0) {
      rows = rows.filter((row) =>
        (row.error_categories ?? []).some((cat) => categoryFilter.has(cat)),
      );
    }
    return rows;
  }, [data?.rows, nonGreenOnly, completeWeeksOnly, categoryFilter, statusFilter]);

  function toggleStatusFilter(status: StatusFilterKey) {
    const next = new URLSearchParams(searchParams);
    const current = new Set(
      (next.get("statuses") ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    );
    if (current.has(status)) current.delete(status);
    else current.add(status);
    const value = Array.from(current).join(",");
    if (value) next.set("statuses", value);
    else next.delete("statuses");
    setSearchParams(next, { replace: true });
  }

  function toggleCategory(category: string) {
    const next = new URLSearchParams(searchParams);
    const current = new Set(
      (next.get("categories") ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    );
    if (current.has(category)) current.delete(category);
    else current.add(category);
    const value = Array.from(current).join(",");
    if (value) next.set("categories", value);
    else next.delete("categories");
    setSearchParams(next, { replace: true });
  }

  function updateSearchParam(key: string, value: string | null) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="w-full min-w-0 px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.standings_validation_title", "Liga-Saison-Validierung")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.standings_validation_desc",
            "Excel-Tabellenstand (TabGes/Tabelle) gegen berechnete Merge-Daten. Perfekt = vollständige Übereinstimmung; Korrigiert = 1-Punkt-Excel-Abweichung, Merge akzeptiert; Gelb/Rot = weitere Abweichungen; Übersprungen = keine Excel-Referenz.",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
        <label className="flex flex-col gap-1 text-caption">
          <span className="text-muted uppercase text-label">
            {t("season", "Saison")}
          </span>
          <select
            className="rounded-sm border border-border bg-background px-3 py-2 text-body min-w-[10rem]"
            value={seasonFilter}
            disabled={seasonsQuery.isPending}
            onChange={(event) => {
              const value = event.target.value;
              updateSearchParam(
                "season",
                value ? seasonForUrlQuery(value) : null,
              );
            }}
          >
            <option value="">{t("ui.diagnosis.standings_all_seasons", "Alle Saisons")}</option>
            {seasonOptions.map((season) => (
              <option key={season} value={season}>
                {season}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-body self-end pb-2 cursor-pointer">
          <input
            type="checkbox"
            className="size-4 rounded-sm border border-border"
            checked={nonGreenOnly}
            onChange={(event) =>
              updateSearchParam("non_green", event.target.checked ? "1" : null)
            }
          />
          <span>{t("ui.diagnosis.standings_non_green", "Nur nicht grün")}</span>
        </label>
        <label className="flex items-center gap-2 text-body self-end pb-2 cursor-pointer">
          <input
            type="checkbox"
            className="size-4 rounded-sm border border-border"
            checked={completeWeeksOnly}
            onChange={(event) =>
              updateSearchParam("weeks_complete", event.target.checked ? "1" : null)
            }
          />
          <span>
            {t("ui.diagnosis.standings_complete_weeks", "Nur vollständige Ligen")}
          </span>
        </label>
        <p className="text-small text-muted max-w-[48ch] self-end pb-2">
          <Link
            to={`/diagnose/liga-wochen${querySuffixForPath("/diagnose/liga-wochen", searchParams)}`}
            className="text-primary underline-offset-2 hover:underline"
          >
            {t("ui.diagnosis.week_matrix_title", "Liga-Wochen-Matrix")}
          </Link>
          {" · "}
          <Link
            to={`/diagnose/datenpipeline${querySuffixForPath("/diagnose/datenpipeline", searchParams)}`}
            className="text-primary underline-offset-2 hover:underline"
          >
            {t("ui.diagnosis.pipeline_title", "Datenpipeline")}
          </Link>
        </p>
      </DiagnosisToolbar>

      <div className="mt-4 flex flex-wrap gap-2">
        {VALIDATION_ERROR_CATEGORIES.map((category) => {
          const active = categoryFilter.has(category);
          return (
            <button
              key={category}
              type="button"
              onClick={() => toggleCategory(category)}
              className={`rounded-sm border px-2.5 py-1 text-caption ${
                active
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-surface text-muted hover:text-foreground"
              }`}
            >
              {CATEGORY_LABEL[category] ?? category}
            </button>
          );
        })}
      </div>

      {query.isLoading && (
        <p className="text-body text-muted mt-6">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600 mt-6">
          {t(
            "ui.diagnosis.standings_validation_error",
            "Validierung konnte nicht geladen werden.",
          )}
        </p>
      )}

      {data && (
        <>
          {data.source === "absent" && (
            <section className="mt-6 rounded-sm border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-body">
              {t(
                "ui.diagnosis.standings_validation_absent",
                "Kein Report gefunden. Auf dem Build-Rechner: uv run python scripts/audit_league_standings.py",
              )}
            </section>
          )}

          <section className="mt-6 grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-7">
            {STATUS_FILTER_KEYS.map((key) => {
              const active = statusFilter.has(key);
              const count =
                key === "week_incomplete"
                  ? summary?.week_incomplete ?? 0
                  : summary?.[key as keyof typeof summary] ?? 0;
              const disabled = key !== "week_incomplete" && count === 0 && !active;
              return (
                <button
                  key={key}
                  type="button"
                  disabled={disabled}
                  onClick={() => toggleStatusFilter(key)}
                  className={`rounded-sm border px-4 py-3 text-left transition-colors ${
                    active
                      ? "border-primary bg-primary/10"
                      : "border-border bg-surface hover:border-primary/40"
                  } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
                >
                  <p className="text-label uppercase text-muted">
                    {t(`ui.diagnosis.standings_kpi_${key}`, STATUS_FILTER_LABEL[key])}
                  </p>
                  <p
                    className={`text-h3 mt-1 tabular-nums ${
                      STATUS_CLASS[key === "week_incomplete" ? "yellow" : key] ?? ""
                    }`}
                  >
                    {count}
                  </p>
                </button>
              );
            })}
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted">
                {t("ui.diagnosis.standings_kpi_source", "Quelle")}
              </p>
              <p className="text-h3 mt-1 tabular-nums capitalize">{data.source}</p>
            </div>
          </section>

          <section className="mt-8 rounded-sm border border-border bg-surface overflow-x-auto w-full">
            <div className="px-4 pt-4 pb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-h3">
                {t("ui.diagnosis.standings_validation_table", "Ergebnisse")}
              </h2>
              <p className="text-caption text-muted">
                {visibleRows.length}
                {(nonGreenOnly || completeWeeksOnly) && data.row_count !== visibleRows.length
                  ? ` / ${data.row_count}`
                  : ""}{" "}
                {t("ui.diagnosis.standings_rows", "Zeilen")}
                {nonGreenOnly ? ` (${t("ui.diagnosis.standings_non_green", "Nur nicht grün")})` : ""}
                {completeWeeksOnly
                  ? ` (${t("ui.diagnosis.standings_complete_weeks", "Nur vollständige Ligen")})`
                  : ""}
                {statusFilter.size > 0 ? ` · Status ${statusFilter.size}` : ""}
                {categoryFilter.size > 0 ? ` · Kategorie ${categoryFilter.size}` : ""}
                {data.report_mtime_utc
                  ? ` · Report ${new Date(data.report_mtime_utc).toLocaleString()}`
                  : null}
              </p>
            </div>
            <table className="w-full text-body text-left">
              <thead>
                <tr className="border-t border-border text-label uppercase text-muted">
                  <th className="px-4 py-2 font-medium">Saison</th>
                  <th className="px-4 py-2 font-medium">Liga</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Wochen</th>
                  <th className="px-4 py-2 font-medium">Wochen-Status</th>
                  <th className="px-4 py-2 font-medium">Excel</th>
                  <th className="px-4 py-2 font-medium">Teams</th>
                  <th className="px-4 py-2 font-medium">Pkt-Summe</th>
                  <th className="px-4 py-2 font-medium">Team-Δ</th>
                  <th className="px-4 py-2 font-medium min-w-[5rem]">Abweichungen</th>
                  <th className="px-4 py-2 font-medium min-w-[12rem]">Notizen</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr
                    key={`${row.season}-${row.league}`}
                    className="border-t border-border align-top"
                  >
                    <td className="px-4 py-2 whitespace-nowrap">{row.season}</td>
                    <td className="px-4 py-2 font-medium whitespace-nowrap">{row.league}</td>
                    <td
                      className={`px-4 py-2 capitalize ${STATUS_CLASS[row.status] ?? ""}`}
                    >
                      {row.status}
                    </td>
                    <td className="px-4 py-2 tabular-nums whitespace-nowrap">
                      {formatWeeks(row)}
                    </td>
                    <td
                      className={`px-4 py-2 capitalize ${
                        WEEK_STATUS_CLASS[row.week_coverage_status ?? ""] ?? "text-muted"
                      }`}
                    >
                      {row.week_coverage_status || "—"}
                    </td>
                    <td className="px-4 py-2 text-caption text-muted whitespace-nowrap">
                      {row.reference_sheet
                        ? `${row.reference_sheet}${row.reference_week ? ` · W${row.reference_week}` : ""}`
                        : "—"}
                    </td>
                    <td className="px-4 py-2 tabular-nums whitespace-nowrap">
                      {row.reference_team_count ?? 0}/{row.computed_team_count ?? 0}
                    </td>
                    <td
                      className="px-4 py-2 text-caption tabular-nums whitespace-nowrap"
                      title="ref/computed · expected season total"
                    >
                      {formatTotalPoints(row)}
                    </td>
                    <td
                      className="px-4 py-2 text-caption text-muted whitespace-nowrap"
                      title="Team-Mismatches: raw → Namen-Normalisierung → Team-Nr. (wie Merge)"
                    >
                      {formatTeamMismatchPipeline(row) ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-caption">
                      {(() => {
                        const findings = formatFindings(row);
                        if (!findings.length) {
                          return <span className="text-muted">—</span>;
                        }
                        return (
                          <ul className="space-y-1">
                            {findings.map((line) => {
                              const kind = findingKind(line);
                              return (
                                <li
                                  key={line}
                                  className={`font-mono text-[0.8125rem] leading-snug ${FINDING_CLASS[kind]}`}
                                >
                                  {kind === "team" ? `Team: ${line}` : line}
                                </li>
                              );
                            })}
                          </ul>
                        );
                      })()}
                    </td>
                    <td className="px-4 py-2 text-caption text-muted">
                      {row.notes || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visibleRows.length === 0 && (
              <p className="px-4 py-6 text-body text-muted">
                {t("ui.diagnosis.standings_validation_empty", "Keine Zeilen für den Filter.")}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
