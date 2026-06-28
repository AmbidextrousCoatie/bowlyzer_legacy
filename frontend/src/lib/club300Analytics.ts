import type { EChartsOption } from "echarts";
import type { IndividualGameRecord } from "../hooks/usePlayer";
import { compareSeasonString } from "./playerClubHistory";
import {
  buildIndividualGameEventPath,
  type CompetitionLinkContext,
} from "./playerCompetitionLinks";
import { formatCompetitionLabel } from "./competitionDisplayName";
import { getLeagueLevel } from "./leagueLevel";
import { TEAM_COLOR_PALETTES } from "./color-utils";
import type { RowMetaEntry, TableData } from "./datatable/types";

export const CLUB300_LEVEL_LABELS: Record<number, string> = {
  0: "Turnier",
  3: "Bayernliga",
  4: "Landesliga",
  5: "BZOL / BL",
  6: "Bezirksliga",
  7: "Kreisliga",
  8: "A-Klasse",
  99: "Sonstige",
};

/** Y-axis order: strongest leagues at the top. */
export const CLUB300_LEVEL_ORDER = [3, 4, 5, 6, 7, 8, 0, 99] as const;

export type Club300BubblePoint = {
  season: string;
  seasonIndex: number;
  level: number;
  levelIndex: number;
  levelLabel: string;
  count: number;
};

export type Club300PlayerTier = {
  count: number;
  players: Array<{ name: string; playerId?: string | null }>;
  playersAhead: number;
};

function gameLeagueLevel(game: IndividualGameRecord): number {
  if (game.is_tournament) return 0;
  const comp = String(game.competition ?? "").trim();
  return getLeagueLevel(comp);
}

export function buildClub300BubblePoints(games: IndividualGameRecord[]): {
  seasons: string[];
  levelOrder: number[];
  points: Club300BubblePoint[];
} {
  const bucket = new Map<string, number>();
  const seasonsSet = new Set<string>();
  const levelsPresent = new Set<number>();

  for (const game of games) {
    const season = String(game.season ?? "").trim() || "—";
    const level = gameLeagueLevel(game);
    seasonsSet.add(season);
    levelsPresent.add(level);
    const key = `${season}\0${level}`;
    bucket.set(key, (bucket.get(key) ?? 0) + 1);
  }

  const seasons = [...seasonsSet].sort(compareSeasonString);
  const levelOrder: number[] = CLUB300_LEVEL_ORDER.filter((level) => levelsPresent.has(level));
  if (levelOrder.length === 0) levelOrder.push(...CLUB300_LEVEL_ORDER);

  const points: Club300BubblePoint[] = [];
  for (const [key, count] of bucket) {
    const [season, levelStr] = key.split("\0");
    const level = Number(levelStr);
    const levelIndex = levelOrder.indexOf(level);
    points.push({
      season,
      seasonIndex: seasons.indexOf(season),
      level,
      levelIndex: levelIndex >= 0 ? levelIndex : levelOrder.length - 1,
      levelLabel: CLUB300_LEVEL_LABELS[level] ?? `Liga ${level}`,
      count,
    });
  }

  return { seasons, levelOrder, points };
}

export function buildClub300PlayerTiers(games: IndividualGameRecord[]): Club300PlayerTier[] {
  const byPlayer = new Map<string, { name: string; id?: string | null; count: number }>();

  for (const game of games) {
    const name = String(game.player_name ?? "").trim();
    if (!name) continue;
    const key = String(game.player_id ?? "").trim() || name;
    const prev = byPlayer.get(key) ?? { name, id: game.player_id, count: 0 };
    prev.count += 1;
    byPlayer.set(key, prev);
  }

  const tierMap = new Map<number, Club300PlayerTier["players"]>();
  for (const { name, id, count } of byPlayer.values()) {
    const list = tierMap.get(count) ?? [];
    list.push({ name, playerId: id });
    tierMap.set(count, list);
  }

  const tiers = [...tierMap.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([count, players]) => ({
      count,
      players: players.sort((a, b) => a.name.localeCompare(b.name, "de")),
      playersAhead: 0,
    }));

  let ahead = 0;
  for (const tier of tiers) {
    tier.playersAhead = ahead;
    ahead += tier.players.length;
  }

  return tiers;
}

export function club300BubbleChartOption(
  seasons: string[],
  levelOrder: number[],
  points: Club300BubblePoint[],
): EChartsOption | null {
  if (!points.length || !seasons.length || !levelOrder.length) return null;

  const levelLabels = levelOrder.map((level) => CLUB300_LEVEL_LABELS[level] ?? String(level));
  const maxCount = Math.max(1, ...points.map((p) => p.count));
  const palette = TEAM_COLOR_PALETTES.rainbowPastel;

  const scatterData = points.map((point) => ({
    value: [point.seasonIndex, point.levelIndex, point.count] as [number, number, number],
    itemStyle: {
      color: palette[point.levelIndex % palette.length],
      opacity: 0.82,
    },
  }));

  return {
    tooltip: {
      trigger: "item",
      formatter: (raw) => {
        const params = raw as { data?: { value?: number[] } };
        const value = params.data?.value;
        if (!value) return "";
        const season = seasons[value[0]] ?? "";
        const levelLabel = levelLabels[value[1]] ?? "";
        return `${levelLabel}<br/>${season}<br/><strong>${value[2]}× 300</strong>`;
      },
    },
    grid: {
      top: 28,
      right: 20,
      bottom: 40,
      left: 12,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: seasons,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { type: "dashed", opacity: 0.25 } },
    },
    yAxis: {
      type: "category",
      data: levelLabels,
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { type: "dashed", opacity: 0.25 } },
    },
    series: [
      {
        type: "scatter",
        data: scatterData,
        symbolSize: (val: number | number[]) => {
          const count = Array.isArray(val) ? (val[2] ?? 1) : 1;
          return (14 + (count / maxCount) * 52) * 0.5;
        },
        emphasis: { scale: 1.08 },
      },
    ],
    animation: false,
  };
}

export function buildClub300TableData(
  games: IndividualGameRecord[],
  ctx: CompetitionLinkContext & {
    tournamentAbbreviations?: Record<string, string>;
    t: (key: string, fallback?: string) => string;
  },
): { tableData: TableData; eventPaths: Array<string | null> } {
  const eventPaths = games.map((game) => buildIndividualGameEventPath(game, ctx));

  const rows = games.map((game, index) => {
    const player = String(game.player_name ?? "").trim() || "—";
    const fullName = String(game.competition ?? "—");
    const isTournament = !!game.is_tournament;
    const compLabel = isTournament
      ? formatCompetitionLabel(fullName, {
          isTournament: true,
          tournamentAbbreviations: ctx.tournamentAbbreviations,
        })
      : fullName;
    const dateLabel = String(game.date ?? "").trim() || "—";
    const season = String(game.season ?? "").trim() || "—";
    const level = gameLeagueLevel(game);
    const levelLabel = CLUB300_LEVEL_LABELS[level] ?? String(level);

    return {
      player,
      competition: compLabel,
      season,
      level: levelLabel,
      date: dateLabel,
      __rowIndex: index,
    };
  });

  const rowMetadata: RowMetaEntry[] = eventPaths.map((path) => (path ? { eventNav: true } : null));

  return {
    eventPaths,
    tableData: {
      columns: [
        {
          title: "",
          columns: [
            { title: ctx.t("ui.player.player", "Spieler"), field: "player", align: "left" },
            {
              title: ctx.t("ui.player.event", "Wettbewerb"),
              field: "competition",
              align: "left",
            },
            { title: ctx.t("ui.player.season", "Saison"), field: "season", align: "left" },
            {
              title: ctx.t("ui.club300.league_level", "Ligaebene"),
              field: "level",
              align: "left",
            },
            { title: ctx.t("ui.player.date", "Datum"), field: "date", align: "right" },
          ],
        },
      ],
      data: rows,
      row_metadata: rowMetadata,
      default_sort: { field: "date", dir: "desc" },
      config: { stripedColGroups: true },
    },
  };
}
