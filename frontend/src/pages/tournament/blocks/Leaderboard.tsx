import { useEffect, useMemo, useRef, useState } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import { localizeTableData } from "../../../lib/datatable/localizeTableData";
import type { TableData } from "../../../lib/datatable/types";
import {
  leaderboardSupportsNetSort,
  resortLeaderboardByNetMetric,
  type LeaderboardNetSortMode,
} from "../../../lib/tournament/resortLeaderboard";
import { tournamentLeaderboardTableOptions } from "../tournamentTableOptions";

type Props = {
  data: TableData;
  stageLabel?: string | null;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function Leaderboard({ data, stageLabel, onPlayerClick, t }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [netSortMode, setNetSortMode] = useState<LeaderboardNetSortMode>("average");
  const showNetSortToggle = useMemo(() => leaderboardSupportsNetSort(data), [data]);

  const sortedData = useMemo(
    () => (showNetSortToggle ? resortLeaderboardByNetMetric(data, netSortMode) : data),
    [data, netSortMode, showNetSortToggle],
  );

  const localizedData = useMemo(
    () => localizeTableData(sortedData, t),
    [sortedData, t],
  );
  const tableOptions = useMemo(
    () => ({
      ...tournamentLeaderboardTableOptions,
      tournamentCutRowStyling:
        data.metadata?.kind !== "ko_placements" && data.metadata?.suppress_cut_styling !== true,
    }),
    [data.metadata],
  );

  useEffect(() => {
    if (!onPlayerClick) return;
    const root = containerRef.current;
    if (!root) return;
    const handler = (event: MouseEvent) => {
      const target = (event.target as HTMLElement | null) ?? null;
      const cell = target?.closest(".tabulator-cell");
      if (!cell) return;
      const field = cell.getAttribute("tabulator-field")?.toLowerCase();
      if (field !== "player") return;
      const name = (cell.textContent ?? "").trim();
      if (name) onPlayerClick(name);
    };
    root.addEventListener("click", handler);
    return () => root.removeEventListener("click", handler);
  }, [onPlayerClick]);

  const sortButtonClass = (selected: boolean) =>
    "h-9 rounded-sm border px-3 text-small font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
    (selected
      ? "border-accent bg-accent text-accent-foreground hover:bg-accent-hover"
      : "border-border bg-surface text-foreground hover:border-border-strong");

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          {stageLabel ? (
            <>
              <p className="text-label uppercase text-muted mb-1.5">
                {t("ui.tournament.leaderboard", "Gesamtwertung")}
              </p>
              <h2 className="text-h2">
                {t("ui.tournament.leaderboard_after", "nach")}{" "}
                <span className="font-semibold">{stageLabel}</span>
              </h2>
            </>
          ) : (
            <h2 className="text-h2">{t("ui.tournament.leaderboard", "Gesamtwertung")}</h2>
          )}
        </div>
        {showNetSortToggle ? (
          <div
            className="flex flex-wrap items-center gap-2"
            role="group"
            aria-label={t("ui.tournament.lb_sort_mode", "Sortierung")}
          >
            <span className="text-small font-medium text-muted">
              {t("ui.tournament.lb_sort_mode", "Sortierung")}
            </span>
            <button
              type="button"
              onClick={() => setNetSortMode("total")}
              aria-pressed={netSortMode === "total"}
              className={sortButtonClass(netSortMode === "total")}
            >
              {t("ui.tournament.lb_sort_total", "Gesamtpins")}
            </button>
            <button
              type="button"
              onClick={() => setNetSortMode("average")}
              aria-pressed={netSortMode === "average"}
              className={sortButtonClass(netSortMode === "average")}
            >
              {t("ui.tournament.lb_sort_average", "Schnitt")}
            </button>
          </div>
        ) : null}
      </div>
      <div ref={containerRef}>
        <DataTable data={localizedData} options={tableOptions} />
      </div>
    </section>
  );
}
