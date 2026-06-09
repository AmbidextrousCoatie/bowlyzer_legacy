import { usePipelineStatus } from "../../hooks/usePipelineStatus";
import { useTranslations } from "../../hooks/useTranslations";

const STATUS_ROW: Record<string, string> = {
  ok: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  missing: "text-rose-700 dark:text-rose-400",
  absent: "text-muted",
};

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
  const query = usePipelineStatus();
  const data = query.data;

  const requiredOk = data?.published_artifacts.filter((a) => a.required && a.exists).length ?? 0;
  const requiredTotal = data?.published_artifacts.filter((a) => a.required).length ?? 0;

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
            "Veröffentlichte Datensätze, App-Quellen und Build-Pfade. Ergänzt die Inhaltsdiagnose (Liga-Wochen, Anomalien) um den operativen Überblick.",
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
          <section className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
                label: t("ui.diagnosis.pipeline_kpi_sources", "App-Quellen"),
                value: String(data.app_sources.filter((s) => s.is_enabled && s.exists).length),
              },
              {
                label: t("ui.diagnosis.pipeline_kpi_build", "Letzter Build"),
                value: formatMtime(data.last_publish_mtime_utc),
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
                  <th className="px-4 py-2 font-medium">Datei</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.app_sources.map((row) => (
                  <tr key={row.source_id} className="border-t border-border">
                    <td className="px-4 py-2">
                      <span className="font-medium">{row.display_name}</span>
                      <span className="block text-caption text-muted">{row.source_id}</span>
                    </td>
                    <td className="px-4 py-2">{row.is_enabled ? "ja" : "nein"}</td>
                    <td className="px-4 py-2 text-caption text-muted max-w-[28rem] truncate">
                      {row.load_path || row.logical_path}
                    </td>
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
              {t("ui.diagnosis.pipeline_paths", "Pfade & Audits")}
            </h2>
            <dl className="grid gap-2 sm:grid-cols-[10rem_1fr] text-caption">
              <dt className="text-muted">Published</dt>
              <dd className="font-mono break-all">{data.paths.published_data_dir}</dd>
              <dt className="text-muted">Work</dt>
              <dd className="font-mono break-all">
                {data.paths.work_data_dir}
                {!data.paths.work_dir_readable && (
                  <span className="text-muted"> (nicht lesbar)</span>
                )}
              </dd>
              <dt className="text-muted">ID/Name-Audit</dt>
              <dd>
                {data.audits.player_id_name_conflicts?.exists
                  ? `${data.audits.player_id_name_conflicts.detail_rows ?? "?"} Zeilen — ${data.audits.player_id_name_conflicts.path}`
                  : "—"}
              </dd>
            </dl>
            <p className="text-caption text-muted mt-4 max-w-[72ch]">
              {t(
                "ui.diagnosis.pipeline_runbook",
                "Vollständiger Plan und Build-Befehle: docs/planning/DATA_PIPELINE_PLAN.md und database/data/README.md im Repository.",
              )}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
