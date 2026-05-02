import { useState } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import {
  type TeamDetailsView,
  useIndividualAverages,
  useTeamWeekDetails,
} from "../../../hooks/useLeague";
import { useTranslations } from "../../../hooks/useTranslations";

type Props = {
  season: string;
  league: string;
  week: string;
  team: string;
};

const VIEWS: Array<{ id: TeamDetailsView; labelKey: string; labelFallback: string }> = [
  { id: "classic", labelKey: "view_classic", labelFallback: "Klassisch" },
  { id: "individual", labelKey: "view_individual", labelFallback: "Einzeln" },
  { id: "headToHead", labelKey: "view_head_to_head", labelFallback: "Head-to-Head" },
];

/** Visible when season + league + week + team are set (no round). */
export function TeamDetails({ season, league, week, team }: Props) {
  const { t } = useTranslations();
  const [view, setView] = useState<TeamDetailsView>("classic");
  const detail = useTeamWeekDetails(season, league, week, team, view);
  const individual = useIndividualAverages(season, league, week, team);

  return (
    <div className="space-y-12">
      <section>
        <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <p className="text-label uppercase text-muted mb-1.5">
              {team} · {t("week", "Spieltag")} {week}
            </p>
            <h2 className="text-h2">{t("score_sheet_for_team", "Spielprotokoll")}</h2>
          </div>
          <SegmentedControl
            value={view}
            onChange={setView}
            options={VIEWS.map((v) => ({
              value: v.id,
              label: t(v.labelKey, v.labelFallback),
            }))}
          />
        </div>
        <DataTableQuery
          query={detail}
          options={{
            disablePositionCircle: true,
            enableSpecialRowStyling: true,
            tooltips: true,
          }}
        />
      </section>

      <section>
        <div className="mb-4">
          <p className="text-label uppercase text-muted mb-1.5">
            {t("individual_averages", "Einzelschnitte")}
          </p>
          <h2 className="text-h2">{t("team_individual_averages", "Spieler des Teams")}</h2>
        </div>
        <DataTableQuery
          query={individual}
          options={{
            disablePositionCircle: true,
            enableSpecialRowStyling: true,
            tooltips: true,
          }}
        />
      </section>
    </div>
  );
}

function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
}) {
  return (
    <div role="group" className="inline-flex rounded-sm border border-border bg-surface p-[3px]">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={
            "rounded-xs px-3 py-1 text-caption font-medium transition-colors " +
            (value === opt.value
              ? "bg-accent text-accent-foreground"
              : "text-muted hover:text-foreground")
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function DataTableQuery({
  query,
  options,
}: {
  query: {
    data: import("../../../lib/datatable/types").TableData | undefined;
    isPending: boolean;
    isError: boolean;
    error: Error | null;
  };
  options: import("../../../lib/datatable/types").DataTableOptions;
}) {
  if (query.isPending) {
    return <div className="h-48 rounded-sm border border-border bg-surface-subtle" />;
  }
  if (query.isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {query.error?.message ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!query.data || !query.data.columns || !query.data.data) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return <DataTable data={query.data} options={options} />;
}
