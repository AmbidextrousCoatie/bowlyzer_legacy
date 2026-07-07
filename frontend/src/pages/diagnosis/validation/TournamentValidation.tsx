import { Link, useSearchParams } from "react-router-dom";
import { useMemo } from "react";
import { DiagnosisToolbar } from "../../../components/DiagnosisToolbar";
import { useAvailableSeasons } from "../../../hooks/useLeague";
import { useLeagueStandingsValidation } from "../../../hooks/useLeagueStandingsValidation";
import { useTranslations } from "../../../hooks/useTranslations";
import { seasonForUrlQuery } from "../../../lib/api";
import { querySuffixForPath } from "../../../lib/navigationQuery";
import { STATUS_CLASS, TOURNAMENT_STATUS_KEYS } from "./validationUi";

const TOURNAMENT_STATUS_FILTER_KEYS = ["green", "yellow", "red"] as const;
type TournamentStatusKey = (typeof TOURNAMENT_STATUS_FILTER_KEYS)[number];

const STATUS_LABEL: Record<TournamentStatusKey, string> = {
  green: "Grün",
  yellow: "Gelb",
  red: "Rot",
};

export function TournamentValidation() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();
  const seasonFilter = searchParams.get("season") ?? "";
  const nonGreenOnly = searchParams.get("non_green") === "1";
  const statusFilter = useMemo(() => {
    const raw = searchParams.get("statuses") ?? "";
    return new Set(
      raw
        .split(",")
        .map((item) => item.trim())
        .filter((item): item is TournamentStatusKey =>
          TOURNAMENT_STATUS_FILTER_KEYS.includes(item as TournamentStatusKey),
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
  const data = query.data?.tournament_quality;
  const summary = data?.summary;

  const visibleRows = useMemo(() => {
    let rows = data?.rows ?? [];
    if (nonGreenOnly) rows = rows.filter((row) => row.status !== "green");
    if (statusFilter.size > 0) {
      rows = rows.filter((row) => statusFilter.has(row.status as TournamentStatusKey));
    }
    return rows;
  }, [data?.rows, nonGreenOnly, statusFilter]);

  function toggleStatusFilter(status: TournamentStatusKey) {
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

  function updateSearchParam(key: string, value: string | null) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  }

  const hubSuffix = querySuffixForPath("/diagnose/validierung", searchParams);

  return (
    <div className="w-full min-w-0 px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-small text-muted mb-2">
          <Link
            to={`/diagnose/validierung${hubSuffix}`}
            className="text-primary underline-offset-2 hover:underline"
          >
            {t("ui.diagnosis.validation_hub_title", "Validierung")}
          </Link>
          <span className="mx-1.5">/</span>
          <span>{t("ui.tournament.tournament", "Turnier")}</span>
        </p>
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.tournament_validation_title", "Turnier-Validierung")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.tournament_validation_desc",
            "Datenqualität je Turnier nach Normalisierung von Spieler-ID, Name und Verein. Grün = keine Auffälligkeiten; Gelb = fehlende IDs/Vereine; Rot = ID-/Namenskonflikte.",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
        <label className="flex flex-col gap-1 text-caption">
          <span className="text-muted uppercase text-label">{t("season", "Saison")}</span>
          <select
            className="rounded-sm border border-border bg-background px-3 py-2 text-body min-w-[10rem]"
            value={seasonFilter}
            disabled={seasonsQuery.isPending}
            onChange={(event) => {
              const value = event.target.value;
              updateSearchParam("season", value ? seasonForUrlQuery(value) : null);
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
      </DiagnosisToolbar>

      {query.isLoading && (
        <p className="text-body text-muted mt-6">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600 mt-6">
          {t("ui.diagnosis.standings_validation_error", "Validierung konnte nicht geladen werden.")}
        </p>
      )}

      {data && (
        <>
          {data.source === "absent" && (
            <section className="mt-6 rounded-sm border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-body">
              {t(
                "ui.diagnosis.tournament_validation_absent",
                "Kein Turnier-Report gefunden. Auf dem Build-Rechner: uv run python scripts/audit_tournament_data_quality.py",
              )}
            </section>
          )}

          <section className="mt-6 grid gap-3 grid-cols-2 sm:grid-cols-4">
            {TOURNAMENT_STATUS_KEYS.map((key) => {
              const active = statusFilter.has(key);
              const count = summary?.[key] ?? 0;
              const disabled = count === 0 && !active;
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
                    {t(`ui.diagnosis.tournament_kpi_${key}`, STATUS_LABEL[key])}
                  </p>
                  <p className={`text-h3 mt-1 tabular-nums ${STATUS_CLASS[key] ?? ""}`}>{count}</p>
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
                {t("ui.diagnosis.tournament_quality_table", "Turnier-Datenqualität")}
              </h2>
              <p className="text-caption text-muted">
                {visibleRows.length}
                {(nonGreenOnly || statusFilter.size > 0) && data.row_count !== visibleRows.length
                  ? ` / ${data.row_count}`
                  : ""}{" "}
                {t("ui.diagnosis.standings_rows", "Zeilen")}
                {data.report_mtime_utc
                  ? ` · Report ${new Date(data.report_mtime_utc).toLocaleString()}`
                  : null}
              </p>
            </div>
            <table className="w-full text-body text-left">
              <thead>
                <tr className="border-t border-border text-label uppercase text-muted">
                  <th className="px-4 py-2 font-medium">Saison</th>
                  <th className="px-4 py-2 font-medium">Turnier</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Zeilen</th>
                  <th className="px-4 py-2 font-medium">Spieler</th>
                  <th className="px-4 py-2 font-medium">ID fehlt</th>
                  <th className="px-4 py-2 font-medium">Verein fehlt</th>
                  <th className="px-4 py-2 font-medium">Verein unbek.</th>
                  <th className="px-4 py-2 font-medium">ID-Konfl.</th>
                  <th className="px-4 py-2 font-medium">Name-Konfl.</th>
                  <th className="px-4 py-2 font-medium min-w-[10rem]">Befunde</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr
                    key={`${row.season}-${row.event_name}`}
                    className="border-t border-border align-top"
                  >
                    <td className="px-4 py-2 whitespace-nowrap">{row.season}</td>
                    <td className="px-4 py-2 font-medium min-w-[12rem]">
                      <span title={row.event_name}>{row.tournament_group || row.event_name}</span>
                    </td>
                    <td className={`px-4 py-2 capitalize ${STATUS_CLASS[row.status] ?? ""}`}>
                      {row.status}
                    </td>
                    <td className="px-4 py-2 tabular-nums">{row.row_count ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.player_count ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.missing_player_id ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.missing_club ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.club_unknown ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.same_name_different_ids ?? 0}</td>
                    <td className="px-4 py-2 tabular-nums">{row.same_id_different_names ?? 0}</td>
                    <td className="px-4 py-2 text-caption">
                      {(row.findings?.length ?? 0) > 0 ? (
                        <ul className="space-y-1">
                          {row.findings!.map((line) => (
                            <li key={line} className="font-mono text-[0.8125rem]">
                              {line}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visibleRows.length === 0 && (
              <p className="px-4 py-6 text-body text-muted">
                {t(
                  "ui.diagnosis.tournament_quality_empty",
                  "Keine Turnier-Zeilen für den Filter.",
                )}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
