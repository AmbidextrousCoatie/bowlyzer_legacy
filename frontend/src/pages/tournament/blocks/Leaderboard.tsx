import { useEffect, useRef } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { TableData } from "../../../lib/datatable/types";

type Props = {
  data: TableData;
  stageLabel?: string | null;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function Leaderboard({ data, stageLabel, onPlayerClick, t }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

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
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.tournament.leaderboard", "Rangliste")}
        </p>
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-h2">{t("ui.tournament.leaderboard", "Rangliste")}</h2>
          {stageLabel ? <p className="text-small text-muted">{stageLabel}</p> : null}
        </div>
      </div>
      <div ref={containerRef}>
        <DataTable
          data={data}
          options={{
            disablePositionCircle: false,
            enableSpecialRowStyling: true,
            tooltips: true,
            disableTeamColorUpdate: true,
          }}
        />
      </div>
    </section>
  );
}
