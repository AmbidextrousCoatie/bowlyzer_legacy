import { Database } from "lucide-react";
import { useDatabaseSelection } from "../hooks/useDatabase";
import { useTranslations } from "../hooks/useTranslations";

type DatabaseSelectorProps = {
  className?: string;
  variant?: "toolbar" | "sidebar";
  collapsed?: boolean;
};

export function DatabaseSelector({
  className = "",
  variant = "toolbar",
  collapsed = false,
}: DatabaseSelectorProps) {
  const { t } = useTranslations();
  const { currentId, currentDisplayName, sourceIds, sources, setDatabase, isLoading, isError, error } =
    useDatabaseSelection();

  if (isError) {
    const message = error instanceof Error ? error.message : "Fehler";
    return (
      <p className={`text-small text-danger-fg ${className}`}>
        {t("ui.database.load_error", "Datenquelle konnte nicht geladen werden")}: {message}
      </p>
    );
  }

  if (variant === "sidebar" && collapsed) {
    return (
      <div
        className={`grid h-9 w-full place-items-center rounded-sm text-muted ${className}`}
        title={`${t("ui.database.label", "Datenquelle")}: ${currentDisplayName}`}
      >
        <Database size={16} strokeWidth={1.75} aria-hidden />
      </div>
    );
  }

  const isSidebar = variant === "sidebar";

  return (
    <label
      className={
        (isSidebar
          ? "flex w-full flex-col gap-1 px-2"
          : "flex min-w-[min(100%,320px)] flex-1 flex-col gap-1.5") +
        ` ${className}`
      }
    >
      <span
        className={
          isSidebar
            ? "text-label uppercase text-subtle"
            : "flex items-center gap-1.5 text-label text-muted"
        }
      >
        {!isSidebar && <Database size={14} strokeWidth={1.75} aria-hidden />}
        {t("ui.database.label", "Datenquelle")}
      </span>
      <select
        className={
          isSidebar
            ? "h-9 w-full rounded-sm border border-border bg-surface-subtle px-2 text-small text-foreground disabled:opacity-60"
            : "h-9 rounded-sm border border-border bg-surface-subtle px-2.5 text-small text-foreground disabled:opacity-60"
        }
        value={currentId}
        disabled={isLoading || sourceIds.length === 0}
        onChange={(e) => void setDatabase(e.target.value)}
        title={sources[currentId]?.description}
        aria-label={t("ui.database.label", "Datenquelle")}
      >
        {sourceIds.length === 0 ? (
          <option value="">{t("ui.database.none", "Keine Quelle verfügbar")}</option>
        ) : (
          sourceIds.map((id) => (
            <option key={id} value={id}>
              {sources[id]?.display_name ?? id}
            </option>
          ))
        )}
      </select>
    </label>
  );
}
