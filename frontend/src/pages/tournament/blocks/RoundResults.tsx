import { useEffect, useRef } from "react";
import { DataTable } from "../../../lib/datatable/DataTable";
import { getHeatMapColor } from "../../../lib/color-utils";
import type { TableData } from "../../../lib/datatable/types";
import { tournamentResultsTableOptions } from "../tournamentTableOptions";

type HeatmapRange = {
  min?: number;
  max?: number;
  high_band_min?: number;
  high_band_max?: number;
  perfect_score?: number;
};

type Props = {
  data: TableData;
  heatmapEnabled: boolean;
  onToggleHeatmap: () => void;
  stageLabel?: string | null;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

const DEFAULT_RANGE: Required<HeatmapRange> = {
  min: 130,
  max: 270,
  high_band_min: 271,
  high_band_max: 299,
  perfect_score: 300,
};

export function RoundResults({
  data,
  heatmapEnabled,
  onToggleHeatmap,
  stageLabel,
  onPlayerClick,
  t,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const range = (data.metadata as { heatmap_ranges?: { game_score?: HeatmapRange } } | undefined)
    ?.heatmap_ranges?.game_score;

  // Tabulator's internal mount happens async; tail multiple frames so we paint
  // heatmap colors after cells exist.
  useEffect(() => {
    let cancelled = false;
    const apply = () => {
      if (cancelled) return;
      const root = containerRef.current;
      if (!root) return;
      const cells = root.querySelectorAll<HTMLElement>(".tabulator-cell[tabulator-field^='game_']");
      if (cells.length === 0) {
        // Tabulator might not have built yet — keep trying up to ~5s.
        return false;
      }
      paintHeatmap(cells, heatmapEnabled, range);
      return true;
    };
    let attempts = 0;
    const tick = () => {
      if (cancelled) return;
      const ok = apply();
      attempts += 1;
      if (!ok && attempts < 40) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return () => {
      cancelled = true;
    };
  }, [data, heatmapEnabled, range]);

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
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p className="text-label uppercase text-muted mb-1.5">
              {t("ui.tournament.round_results", "Rundenergebnisse")}
            </p>
            {stageLabel ? (
              <h2 className="text-h2 font-semibold">{stageLabel}</h2>
            ) : (
              <h2 className="text-h2">{t("ui.tournament.round_results", "Rundenergebnisse")}</h2>
            )}
          </div>
          <button
            type="button"
            onClick={onToggleHeatmap}
            aria-pressed={heatmapEnabled}
            className={
              "h-9 rounded-sm border px-3 text-small font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (heatmapEnabled
                ? "border-accent bg-accent text-accent-foreground hover:bg-accent-hover"
                : "border-border bg-surface text-foreground hover:border-border-strong")
            }
          >
            {t("ui.tournament.heatmap", "Heatmap")} ·{" "}
            {heatmapEnabled ? t("ui.common.on", "An") : t("ui.common.off", "Aus")}
          </button>
        </div>
      </div>
      <div ref={containerRef}>
        <DataTable data={data} options={tournamentResultsTableOptions} />
      </div>
    </section>
  );
}

function paintHeatmap(
  cells: NodeListOf<HTMLElement>,
  enabled: boolean,
  range: HeatmapRange | undefined,
): void {
  const r = { ...DEFAULT_RANGE, ...range };
  cells.forEach((cell) => {
    cell.style.removeProperty("background-color");
    cell.style.removeProperty("font-weight");
    cell.style.removeProperty("color");
    cell.style.removeProperty("box-shadow");
    if (!enabled) return;
    const text = (cell.textContent ?? "").trim();
    if (!text) return;
    const value = parseFloat(text);
    if (!Number.isFinite(value)) return;

    if (value === r.perfect_score) {
      cell.style.setProperty("background-color", "#ffc107", "important");
      cell.style.setProperty("font-weight", "800", "important");
      cell.style.setProperty("color", "#111827", "important");
      cell.style.setProperty("box-shadow", "inset 0 0 0 2px #b77900", "important");
      return;
    }
    if (value >= r.high_band_min && value <= r.high_band_max) {
      cell.style.setProperty("background-color", "#ffe7a3", "important");
      cell.style.setProperty("font-weight", "600", "important");
      cell.style.setProperty("color", "#1f2933", "important");
      return;
    }
    const color = getHeatMapColor(value, r.min, r.max);
    cell.style.setProperty("background-color", color, "important");
    cell.style.setProperty("color", "#1f2933", "important");
  });
}
