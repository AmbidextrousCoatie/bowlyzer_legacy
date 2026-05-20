import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useDataOddities, type DataOddityType } from "../../hooks/useLeague";
import { useTranslations } from "../../hooks/useTranslations";
import { DiagnosisToolbar } from "../../components/DiagnosisToolbar";
import { oddityLigaPath } from "../../lib/diagnosisLinks";

const ALL_TYPES: DataOddityType[] = ["unnumbered_team", "low_score", "incomplete_row"];

const TYPE_LABEL: Record<DataOddityType, string> = {
  unnumbered_team: "Mannschaft ohne Nummer",
  low_score: "Ergebnis < 1",
  incomplete_row: "Spieltag / Ergebnis fehlt",
};

const SEVERITY_ROW: Record<string, string> = {
  warn: "border-l-4 border-l-amber-400",
  bad: "border-l-4 border-l-orange-500",
  critical: "border-l-4 border-l-rose-500",
};

export function DataOddities() {
  const { t } = useTranslations();
  const [enabledTypes, setEnabledTypes] = useState<Set<DataOddityType>>(
    () => new Set(ALL_TYPES),
  );
  const types = useMemo(() => Array.from(enabledTypes), [enabledTypes]);
  const query = useDataOddities(types);
  const longNames = query.data?.league_long_names ?? {};
  const oddities = query.data?.oddities ?? [];

  function toggleType(type: DataOddityType) {
    setEnabledTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        if (next.size <= 1) return prev;
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.oddities_title", "Daten-Anomalien")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.oddities_desc",
            "Auffälligkeiten in den Ligadaten mit Sprung zur betroffenen Stelle in der Liga-Ansicht.",
          )}
        </p>
      </header>

      <DiagnosisToolbar>
        <fieldset className="flex flex-wrap items-end gap-4">
          <legend className="sr-only">{t("ui.diagnosis.oddity_types", "Kategorien")}</legend>
          {ALL_TYPES.map((type) => (
            <label key={type} className="flex items-center gap-2 text-small cursor-pointer">
              <input
                type="checkbox"
                checked={enabledTypes.has(type)}
                onChange={() => toggleType(type)}
                className="size-4 rounded-sm border-border"
              />
              <span>{TYPE_LABEL[type]}</span>
              {query.data?.summary.by_type?.[type] != null && (
                <span className="font-mono text-muted">({query.data.summary.by_type[type]})</span>
              )}
            </label>
          ))}
        </fieldset>
      </DiagnosisToolbar>

      {query.isError && (
        <p className="text-small text-danger-fg">
          {query.error instanceof Error ? query.error.message : "Fehler beim Laden"}
        </p>
      )}

      {query.isPending && (
        <p className="text-small text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}

      {query.isSuccess && (
        <section className="rounded-sm border border-border bg-surface overflow-hidden">
          <div className="border-b border-border px-4 py-3 lg:px-5 flex flex-wrap gap-3 text-small text-muted">
            <span>
              {query.data.summary.total}{" "}
              {t("ui.diagnosis.oddities_entries", "Einträge")}
            </span>
            {query.data.truncated && (
              <span className="text-amber-700 dark:text-amber-400">
                {t("ui.diagnosis.oddities_truncated", "Liste gekürzt")} (Limit{" "}
                {query.data.limit})
              </span>
            )}
          </div>

          {oddities.length === 0 ? (
            <p className="px-4 py-8 text-small text-muted lg:px-5">
              {t("ui.diagnosis.no_oddities", "Keine Anomalien für die gewählten Kategorien.")}
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {oddities.map((item) => {
                const href = oddityLigaPath(item, longNames);
                return (
                  <li
                    key={item.id}
                    className={`px-4 py-3 lg:px-5 ${SEVERITY_ROW[item.severity] ?? ""}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-label text-muted">{TYPE_LABEL[item.type]}</p>
                        <p className="text-body mt-0.5">{item.message}</p>
                      </div>
                      {href ? (
                        <Link
                          to={href}
                          className="shrink-0 text-small text-accent hover:text-accent-hover hover:underline whitespace-nowrap"
                        >
                          {t("ui.diagnosis.open_in_liga", "In Liga öffnen →")}
                        </Link>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
