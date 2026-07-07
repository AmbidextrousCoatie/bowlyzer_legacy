import { Fragment } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { usePipelineStatus } from "../../hooks/usePipelineStatus";
import { useTranslations } from "../../hooks/useTranslations";
import { querySuffixForPath } from "../../lib/navigationQuery";

const STATUS_ROW: Record<string, string> = {
  ok: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  forced: "text-amber-700 dark:text-amber-400",
  deferred: "text-amber-700 dark:text-amber-400",
  blocked: "text-rose-700 dark:text-rose-400",
  missing: "text-rose-700 dark:text-rose-400",
  absent: "text-muted",
  skipped: "text-muted",
};

const BUILD_COMMAND = "uv run python scripts/build_published_dataset.py";

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMtime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatRows(count: number | null | undefined): string {
  if (count == null) return "—";
  return count.toLocaleString();
}

export function DataPipeline() {
  const { t } = useTranslations();
  const [searchParams] = useSearchParams();
  const query = usePipelineStatus();
  const data = query.data;

  const requiredOk = data?.published_artifacts.filter((a) => a.required && a.exists).length ?? 0;
  const requiredTotal = data?.published_artifacts.filter((a) => a.required).length ?? 0;
  const manifest = data?.manifest_summary;
  const auditOverall = manifest?.audit_overall ?? "ok";
  const exposePaths = data?.expose_operator_paths ?? false;

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.pipeline_title", "Datenpipeline")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.pipeline_desc",
            exposePaths
              ? "Veröffentlichte Datensätze, App-Quellen und Build-Pfade. Ergänzt die Inhaltsdiagnose (Liga-Übersicht, Anomalien) um den operativen Überblick."
              : "Veröffentlichte Datensätze, Publish-Manifest und Audit-Status. Ergänzt die Inhaltsdiagnose (Liga-Übersicht, Anomalien) um den operativen Überblick.",
          )}
        </p>
      </header>

      {query.isLoading && (
        <p className="text-body text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600">
          {t("ui.diagnosis.pipeline_error", "Pipeline-Status konnte nicht geladen werden.")}
        </p>
      )}

      {data && (
        <>
          {manifest?.present && auditOverall !== "ok" && (
            <section
              className={`mb-6 rounded-sm border px-4 py-3 text-body ${
                auditOverall === "forced" || auditOverall === "deferred"
                  ? "border-amber-500/40 bg-amber-500/10"
                  : "border-rose-500/40 bg-rose-500/10"
              }`}
            >
              {auditOverall === "forced" ? (
                <p>
                  {t(
                    "ui.diagnosis.pipeline_forced_publish",
                    "Letzter Lauf mit --force-publish veröffentlicht trotz Audit-Warnungen.",
                  )}{" "}
                  {(manifest.blocking_audit_ids ?? []).join(", ") || "—"}
                </p>
              ) : auditOverall === "deferred" ? (
                <p>
                  {t(
                    "ui.diagnosis.pipeline_audit_deferred",
                    "Player-ID/Name-Konflikte sind erfasst, blockieren Publish aber nicht (Auflösung mit players_registry, Phase 2b).",
                  )}{" "}
                  {(manifest.deferred_audit_ids ?? []).join(", ")}
                </p>
              ) : (
                <p>
                  {t(
                    "ui.diagnosis.pipeline_audit_blocked",
                    "Manifest meldet blockierende Audits — Parquet sollte nicht veröffentlicht sein.",
                  )}{" "}
                  {(manifest.blocking_audit_ids ?? []).join(", ")}
                </p>
              )}
            </section>
          )}

          <section className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              {
                label: t("ui.diagnosis.pipeline_kpi_required", "Pflicht-Artefakte"),
                value: `${requiredOk}/${requiredTotal}`,
              },
              {
                label: t("ui.diagnosis.pipeline_kpi_published", "Veröffentlicht"),
                value: String(data.published_artifacts.filter((a) => a.exists).length),
              },
              {
                label: t("ui.diagnosis.pipeline_kpi_manifest", "Publish-Manifest"),
                value: manifest?.present
                  ? manifest.run_id ?? t("ui.common.yes", "ja")
                  : t("ui.common.no", "nein"),
              },
              {
                label: t("ui.diagnosis.pipeline_kpi_audit", "Audit-Status"),
                value: manifest?.present ? auditOverall : "—",
              },
              {
                label: t("ui.diagnosis.pipeline_kpi_build", "Letzter Build"),
                value: formatMtime(manifest?.published_at ?? data.last_publish_mtime_utc),
              },
            ].map((tile) => (
              <div
                key={tile.label}
                className="rounded-sm border border-border bg-surface px-4 py-3"
              >
                <p className="text-label uppercase text-muted">{tile.label}</p>
                <p className="text-h3 mt-1 tabular-nums">{tile.value}</p>
              </div>
            ))}
          </section>

          {manifest?.present && (
            <section className="mb-8 rounded-sm border border-border bg-surface overflow-x-auto">
              <div className="px-4 pt-4 pb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-h3">
                  {t("ui.diagnosis.pipeline_manifest", "Letzter Publish-Lauf")}
                </h2>
                <p className="text-caption text-muted font-mono">
                  runs/latest.json
                  {manifest.forced ? " · forced" : ""}
                </p>
              </div>
              <dl className="grid gap-2 px-4 pb-3 sm:grid-cols-[10rem_1fr] text-caption border-b border-border">
                <dt className="text-muted">Run</dt>
                <dd className="font-mono">{manifest.run_id ?? "—"}</dd>
                <dt className="text-muted">Jobs</dt>
                <dd>{(manifest.jobs_run ?? []).join(", ") || "—"}</dd>
                <dt className="text-muted">Schema</dt>
                <dd>v{manifest.data_schema_version ?? "?"}</dd>
                <dt className="text-muted">Veröffentlicht</dt>
                <dd>{formatMtime(manifest.published_at)}</dd>
              </dl>
              <table className="w-full text-body text-left">
                <thead>
                  <tr className="border-t border-border text-label uppercase text-muted">
                    <th className="px-4 py-2 font-medium">Job</th>
                    <th className="px-4 py-2 font-medium">Stream</th>
                    <th className="px-4 py-2 font-medium">Zeilen</th>
                    <th className="px-4 py-2 font-medium">Inputs</th>
                    <th className="px-4 py-2 font-medium">Columns hash</th>
                  </tr>
                </thead>
                <tbody>
                  {(manifest.artifacts ?? []).map((row) => (
                    <tr
                      key={`${row.job}-${row.source_id}`}
                      className="border-t border-border"
                    >
                      <td className="px-4 py-2 font-mono text-caption">{row.job ?? "—"}</td>
                      <td className="px-4 py-2">
                        {row.stream ?? "—"}
                        {row.deprecated ? (
                          <span className="block text-caption text-muted">deprecated</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-2 tabular-nums">{formatRows(row.row_count)}</td>
                      <td className="px-4 py-2 tabular-nums">{row.input_source_count ?? "—"}</td>
                      <td className="px-4 py-2 font-mono text-caption">{row.columns_hash ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {manifest.audits && (
                <dl className="grid gap-2 px-4 py-3 border-t border-border sm:grid-cols-[10rem_1fr] text-caption">
                  {Object.entries(manifest.audits).map(([key, audit]) => (
                    <Fragment key={key}>
                      <dt className="text-muted">Audit {key}</dt>
                      <dd className={STATUS_ROW[audit.status ?? ""] ?? ""}>
                        {audit.status ?? "—"}
                        {audit.detail_rows != null ? ` · ${audit.detail_rows} Zeilen` : ""}
                      </dd>
                    </Fragment>
                  ))}
                </dl>
              )}
            </section>
          )}

          <section className="mb-8 rounded-sm border border-border bg-surface overflow-x-auto">
            <h2 className="text-h3 px-4 pt-4 pb-2">
              {t("ui.diagnosis.pipeline_artifacts", "Veröffentlichte Artefakte")}
            </h2>
            <table className="w-full text-body text-left">
              <thead>
                <tr className="border-t border-border text-label uppercase text-muted">
                  <th className="px-4 py-2 font-medium">Dataset</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Zeilen</th>
                  <th className="px-4 py-2 font-medium">Größe</th>
                  <th className="px-4 py-2 font-medium">Geändert</th>
                </tr>
              </thead>
              <tbody>
                {data.published_artifacts.map((row) => (
                  <tr key={row.id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <span className="font-medium">{row.label}</span>
                      {row.source_id && (
                        <span className="block text-caption text-muted">{row.source_id}</span>
                      )}
                    </td>
                    <td className={`px-4 py-2 capitalize ${STATUS_ROW[row.status] ?? ""}`}>
                      {row.status}
                    </td>
                    <td className="px-4 py-2 tabular-nums">{formatRows(row.row_count)}</td>
                    <td className="px-4 py-2 tabular-nums">{formatBytes(row.size_bytes)}</td>
                    <td className="px-4 py-2 text-caption text-muted whitespace-nowrap">
                      {formatMtime(row.mtime_utc)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="mb-8 rounded-sm border border-border bg-surface overflow-x-auto">
            <h2 className="text-h3 px-4 pt-4 pb-2">
              {t("ui.diagnosis.pipeline_sources", "Registrierte App-Quellen")}
            </h2>
            <table className="w-full text-body text-left">
              <thead>
                <tr className="border-t border-border text-label uppercase text-muted">
                  <th className="px-4 py-2 font-medium">Quelle</th>
                  <th className="px-4 py-2 font-medium">Aktiv</th>
                  {exposePaths && (
                    <th className="px-4 py-2 font-medium">Datei</th>
                  )}
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.app_sources.map((row) => (
                  <tr key={row.source_id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <span className="font-medium">{row.display_name}</span>
                      <span className="block text-caption text-muted">{row.source_id}</span>
                      {!exposePaths && row.filename && (
                        <span className="block text-caption text-muted font-mono">{row.filename}</span>
                      )}
                    </td>
                    <td className="px-4 py-2">{row.is_enabled ? "ja" : "nein"}</td>
                    {exposePaths && (
                      <td className="px-4 py-2 text-caption text-muted max-w-[28rem] truncate">
                        {row.load_path || row.logical_path}
                      </td>
                    )}
                    <td className={`px-4 py-2 capitalize ${STATUS_ROW[row.status] ?? ""}`}>
                      {row.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-sm border border-border bg-surface px-4 py-4 text-body">
            <h2 className="text-h3 mb-3">
              {exposePaths
                ? t("ui.diagnosis.pipeline_paths", "Pfade & Audits")
                : t("ui.diagnosis.pipeline_operator", "Betrieb")}
            </h2>
            <dl className="grid gap-2 sm:grid-cols-[10rem_1fr] text-caption">
              {exposePaths && (
                <>
                  <dt className="text-muted">Published</dt>
                  <dd className="font-mono break-all">{data.paths.published_data_dir}</dd>
                  <dt className="text-muted">Work</dt>
                  <dd className="font-mono break-all">
                    {data.paths.work_data_dir}
                    {!data.paths.work_dir_readable && (
                      <span className="text-muted"> (nicht lesbar)</span>
                    )}
                  </dd>
                </>
              )}
              <dt className="text-muted">ID/Name-Audit</dt>
              <dd>
                {data.audits.player_id_name_conflicts?.exists
                  ? `${data.audits.player_id_name_conflicts.detail_rows ?? "?"} Zeilen`
                  : "—"}
              </dd>
              <dt className="text-muted">Turnier-Validierung</dt>
              <dd>
                {data.audits.tournament_data_quality?.exists ? (
                  <>
                    {data.audits.tournament_data_quality.detail_rows ?? "?"} Zeilen ·{" "}
                    <Link
                      to={`/diagnose/validierung${querySuffixForPath("/diagnose/validierung", searchParams)}`}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {t("ui.diagnosis.standings_validation_open", "Details")}
                    </Link>
                  </>
                ) : (
                  <>
                    — ·{" "}
                    <Link
                      to={`/diagnose/validierung${querySuffixForPath("/diagnose/validierung", searchParams)}`}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {t("ui.diagnosis.standings_validation_open", "Details")}
                    </Link>
                  </>
                )}
              </dd>
              <dt className="text-muted">Turnier-Übersicht</dt>
              <dd>
                <Link
                  to={`/diagnose/turnier-uebersicht${querySuffixForPath("/diagnose/turnier-uebersicht", searchParams)}`}
                  className="text-primary underline-offset-2 hover:underline"
                >
                  {t("ui.diagnosis.tournament_coverage_open", "Matrix")}
                </Link>
              </dd>
              <dt className="text-muted">Liga-Validierung</dt>
              <dd>
                {data.audits.league_standings_validation?.exists ? (
                  <>
                    {data.audits.league_standings_validation.detail_rows ?? "?"} Zeilen ·{" "}
                    <Link
                      to={`/diagnose/validierung${querySuffixForPath("/diagnose/validierung", searchParams)}`}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {t("ui.diagnosis.standings_validation_open", "Details")}
                    </Link>
                  </>
                ) : (
                  <>
                    — ·{" "}
                    <Link
                      to={`/diagnose/validierung${querySuffixForPath("/diagnose/validierung", searchParams)}`}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {t("ui.diagnosis.standings_validation_open", "Details")}
                    </Link>
                  </>
                )}
              </dd>
              {exposePaths && (
                <>
                  <dt className="text-muted">Manifest</dt>
                  <dd className="font-mono break-all">{data.paths.latest_manifest ?? "—"}</dd>
                </>
              )}
              {exposePaths && (
                <>
                  <dt className="text-muted">{t("ui.diagnosis.pipeline_build_cmd", "Build")}</dt>
                  <dd>
                    <code className="block font-mono text-caption bg-surface-subtle rounded-sm px-2 py-1 break-all">
                      {BUILD_COMMAND}
                    </code>
                    <code className="block font-mono text-caption text-muted mt-1 break-all">
                      {BUILD_COMMAND} --force-publish
                    </code>
                  </dd>
                </>
              )}
            </dl>
            {exposePaths && (
              <p className="text-caption text-muted mt-4 max-w-[72ch]">
                {t(
                  "ui.diagnosis.pipeline_runbook",
                  "Vollständiger Plan und Build-Befehle: docs/planning/DATA_PIPELINE_PLAN.md und database/data/README.md im Repository.",
                )}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
