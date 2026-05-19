import { useEffect, useMemo, useRef } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { TableData } from "../../../lib/datatable/types";
import { tournamentLeaderboardTableOptions } from "../tournamentTableOptions";

type Props = {
  data: TableData;
  stageLabel?: string | null;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function Leaderboard({ data, stageLabel, onPlayerClick, t }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
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

  return (
    <section>
      <div className="mb-4">
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
      <div ref={containerRef}>
        <DataTable data={data} options={tableOptions} />
      </div>
    </section>
  );
}
