import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { ClubSearch } from "../../../components/ClubSearch";import {
  useClubNameValidation,
  useSaveClubNameMappings,
  type ClubNameValidationRow,
} from "../../../hooks/useClubNameValidation";
import { useTranslations } from "../../../hooks/useTranslations";
import { querySuffixForPath } from "../../../lib/navigationQuery";

const PLACEHOLDER_VALUE = "";

function initialSelection(row: ClubNameValidationRow): string {
  return row.default_canonical?.trim() || PLACEHOLDER_VALUE;
}

export function ClubNameValidation() {
  const { t } = useTranslations();
  const [searchParams] = useSearchParams();
  const query = useClubNameValidation();
  const saveMutation = useSaveClubNameMappings();
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const rows = query.data?.rows ?? [];
  const canonicalNames = query.data?.canonical_names ?? [];

  useEffect(() => {
    if (!rows.length) return;
    setSelections((prev) => {
      const next = { ...prev };
      for (const row of rows) {
        if (!(row.club_label in next)) {
          next[row.club_label] = initialSelection(row);
        }
      }
      return next;
    });
  }, [rows]);

  const resolvedCount = useMemo(
    () => Object.values(selections).filter((value) => value.trim()).length,
    [selections],
  );

  const hubSuffix = querySuffixForPath("/diagnose/validierung", searchParams);

  function updateSelection(clubLabel: string, canonicalName: string) {
    setSelections((prev) => ({ ...prev, [clubLabel]: canonicalName }));
    setSaveMessage(null);
    setSaveError(null);
  }

  async function handleSave() {
    setSaveMessage(null);
    setSaveError(null);
    const mappings = Object.entries(selections)
      .filter(([, canonical]) => canonical.trim())
      .map(([unresolved_label, canonical_name]) => ({ unresolved_label, canonical_name }));
    if (mappings.length === 0) {
      setSaveError(
        t(
          "ui.diagnosis.club_mapping_save_empty",
          "Keine Zuordnungen ausgewählt. Bitte mindestens einen Verein wählen.",
        ),
      );
      return;
    }
    try {
      const result = await saveMutation.mutateAsync(mappings);
      setSaveMessage(
        `${result.row_count} ${t("ui.diagnosis.club_mapping_save_ok", "Zuordnung(en) gespeichert.")}`,
      );
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    }
  }

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
          <span>{t("ui.diagnosis.club_mapping_title", "Vereinszuordnung")}</span>
        </p>
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1">
          {t("ui.diagnosis.club_mapping_title", "Vereinszuordnung")}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.diagnosis.club_mapping_desc",
            "Unaufgelöste Turnier-Vereinsnamen den kanonischen Vereinen aus der Liga-Registry zuordnen. Gespeicherte Zuordnungen landen in club_name_mapping_resolved.csv für spätere Normalisierung.",
          )}
        </p>
      </header>

      {query.isLoading && (
        <p className="text-body text-muted">{t("ui.common.loading", "Laden…")}</p>
      )}
      {query.isError && (
        <p className="text-body text-rose-600">
          {t("ui.diagnosis.standings_validation_error", "Validierung konnte nicht geladen werden.")}
        </p>
      )}

      {query.data && (
        <>
          {query.data.source === "absent" && (
            <section className="mt-6 rounded-sm border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-body">
              {t(
                "ui.diagnosis.club_mapping_absent",
                "Kein Vereins-Audit gefunden. Auf dem Build-Rechner: uv run python scripts/audit_club_names.py --registry",
              )}
            </section>
          )}

          <section className="mt-6 grid gap-3 grid-cols-2 sm:grid-cols-4">
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted">
                {t("ui.diagnosis.club_mapping_kpi_unresolved", "Unaufgelöst")}
              </p>
              <p className="text-h3 mt-1 tabular-nums">{query.data.summary.unresolved}</p>
            </div>
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted">
                {t("ui.diagnosis.club_mapping_kpi_proposal", "Mit Vorschlag")}
              </p>
              <p className="text-h3 mt-1 tabular-nums text-amber-700 dark:text-amber-400">
                {query.data.summary.with_proposal}
              </p>
            </div>
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted">
                {t("ui.diagnosis.club_mapping_kpi_registry", "Registry")}
              </p>
              <p className="text-h3 mt-1 tabular-nums">{canonicalNames.length}</p>
            </div>
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted">
                {t("ui.diagnosis.club_mapping_kpi_saved", "Gespeichert")}
              </p>
              <p className="text-h3 mt-1 tabular-nums">{query.data.saved_mapping.row_count}</p>
            </div>
          </section>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saveMutation.isPending || resolvedCount === 0}
              className="rounded-sm border border-primary bg-primary px-4 py-2 text-body text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending
                ? t("ui.common.saving", "Speichern…")
                : t("ui.diagnosis.club_mapping_save", "Speichern")}
            </button>
            <p className="text-caption text-muted">
              {resolvedCount} / {rows.length}{" "}
              {t("ui.diagnosis.club_mapping_selected", "ausgewählt")}
            </p>
            {saveMessage && <p className="text-body text-emerald-700 dark:text-emerald-400">{saveMessage}</p>}
            {saveError && <p className="text-body text-rose-600">{saveError}</p>}
          </div>

          <section className="mt-8 rounded-sm border border-border bg-surface overflow-x-auto w-full">
            <div className="px-4 pt-4 pb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-h3">
                {t("ui.diagnosis.club_mapping_table", "Unaufgelöste Vereinsnamen")}
              </h2>
              <p className="text-caption text-muted">
                {rows.length} {t("ui.diagnosis.standings_rows", "Zeilen")}
                {query.data.report_mtime_utc
                  ? ` · Report ${new Date(query.data.report_mtime_utc).toLocaleString()}`
                  : null}
              </p>
            </div>
            <table className="w-full text-body text-left">
              <thead>
                <tr className="border-t border-border text-label uppercase text-muted">
                  <th className="px-4 py-2 font-medium min-w-[14rem]">
                    {t("ui.diagnosis.club_mapping_col_label", "Turnier-Verein")}
                  </th>
                  <th className="px-4 py-2 font-medium">Zeilen</th>
                  <th className="px-4 py-2 font-medium min-w-[10rem]">
                    {t("ui.diagnosis.club_mapping_col_proposal", "Vorschlag")}
                  </th>
                  <th className="px-4 py-2 font-medium min-w-[18rem]">
                    {t("ui.diagnosis.club_mapping_col_registry", "Registry-Verein")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const selected = selections[row.club_label] ?? initialSelection(row);
                  const hasProposal = Boolean(row.proposed_canonical?.trim());
                  return (
                    <tr key={row.club_label} className="border-t border-border align-top">
                      <td className="px-4 py-2 font-medium">{row.club_label}</td>
                      <td className="px-4 py-2 tabular-nums">{row.row_count}</td>
                      <td className="px-4 py-2 text-caption">
                        {hasProposal ? (
                          <span title={row.proposed_rule}>{row.proposed_canonical}</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <ClubSearch
                          value={selected}
                          clubs={canonicalNames}
                          isLoading={query.isLoading}
                          placeholder={t("ui.diagnosis.club_mapping_select", "Team wählen")}
                          ariaLabel={t("ui.diagnosis.club_mapping_col_registry", "Registry-Verein")}
                          clearAriaLabel={t("ui.team.clear_club", "Auswahl löschen")}
                          containerClassName="relative w-full min-w-[16rem] max-w-none"
                          onSelect={(club) => updateSelection(row.club_label, club ?? "")}
                        />
                      </td>                    </tr>
                  );
                })}
              </tbody>
            </table>
            {rows.length === 0 && (
              <p className="px-4 py-6 text-body text-muted">
                {t(
                  "ui.diagnosis.club_mapping_empty",
                  "Keine unaufgelösten Vereinsnamen — alle Turnier-Labels passen zur Registry.",
                )}
              </p>
            )}
          </section>

          {query.data.saved_mapping.present && (
            <p className="mt-4 text-caption text-muted font-mono break-all">
              {t("ui.diagnosis.club_mapping_file", "Datei")}: club_name_mapping_resolved.csv
              {query.data.saved_mapping.mtime_utc
                ? ` · ${new Date(query.data.saved_mapping.mtime_utc).toLocaleString()}`
                : null}
            </p>
          )}
        </>
      )}
    </div>
  );
}
