import {
  Activity,
  Award,
  Building2,
  CalendarDays,
  CalendarRange,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  PLAYER_HIGHLIGHTS_MIN_GAMES_COMPETITION,
  PLAYER_HIGHLIGHTS_MIN_GAMES_LEAGUE_WEEK,
  PLAYER_HIGHLIGHTS_MIN_GAMES_SEASON,
  playerHighlightsTopN,
  buildPlayerHighlights,
  type PlayerHighlightEntry,
} from "../../../lib/playerHighlights";
import { getPaletteColor } from "../../../lib/color-utils";
import { useTranslations } from "../../../hooks/useTranslations";
import { formatPeriodDetail } from "../../../lib/playerPeriodLabel";
import { useHighestIndividualGames } from "../../../hooks/usePlayer";
import {
  buildIndividualGameEventPath,
  type IndividualGameRecord,
} from "../../../lib/playerCompetitionLinks";
import { formatCompetitionLabel } from "../../../lib/competitionDisplayName";
import { buildUrl } from "../../../lib/api";

import type { PlayerPeriodRow, PlayerSeasonRow } from "../../../hooks/usePlayer";

type Props = {
  scope: "all" | "player";
  seasons: PlayerSeasonRow[];
  periods: PlayerPeriodRow[];
  playerCompetitions: PlayerSeasonRow[];
  playerSeasonTotals: PlayerSeasonRow[];
  selectedPlayerName: string;
  selectedPlayerId?: string;
  season?: string;
  /** Mein Club lens — filters all-player highest-game lists. */
  club?: string | null;
  t: (key: string, fallback?: string) => string;
};

type HighlightCategory = {
  id: string;
  titleKey: string;
  titleFallback: string;
  icon: LucideIcon;
  entries: PlayerHighlightEntry[];
  filterToggle?: {
    active: boolean;
    label: string;
    onToggle: () => void;
  };
};

export function PlayerHighlights({
  scope,
  seasons,
  periods,
  playerCompetitions,
  playerSeasonTotals,
  selectedPlayerName,
  selectedPlayerId = "",
  season = "all",
  club = null,
  t,
}: Props) {
  const databaseParam =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;

  const { tournamentAbbreviations } = useTranslations();
  const topN = playerHighlightsTopN(scope);

  const [minGamesAvgSeason, setMinGamesAvgSeason] = useState(true);
  const [minGamesBestComp, setMinGamesBestComp] = useState(true);
  const [minGamesLeagueWeeks, setMinGamesLeagueWeeks] = useState(true);

  const highlightInput = useMemo(
    () => ({
      scope,
      seasons,
      periods,
      playerCompetitions,
      playerSeasonTotals,
    }),
    [scope, seasons, periods, playerCompetitions, playerSeasonTotals],
  );

  const baseHighlightOptions = useMemo(
    () => ({
      selectedPlayerName,
      database: databaseParam,
      tournamentAbbreviations,
      formatPeriod: (row: PlayerPeriodRow) => formatPeriodDetail(row, t),
    }),
    [selectedPlayerName, databaseParam, tournamentAbbreviations, t],
  );

  const data = useMemo(
    () =>
      buildPlayerHighlights(highlightInput, {
        ...baseHighlightOptions,
        minGamesAvgBySeason: minGamesAvgSeason ? PLAYER_HIGHLIGHTS_MIN_GAMES_SEASON : undefined,
        minGamesBestCompetitions: minGamesBestComp
          ? PLAYER_HIGHLIGHTS_MIN_GAMES_COMPETITION
          : undefined,
        minGamesBestDays: minGamesLeagueWeeks ? PLAYER_HIGHLIGHTS_MIN_GAMES_LEAGUE_WEEK : undefined,
        leagueWeeksOnlyBestDays: minGamesLeagueWeeks,
      }),
    [
      highlightInput,
      baseHighlightOptions,
      minGamesAvgSeason,
      minGamesBestComp,
      minGamesLeagueWeeks,
    ],
  );

  const dataUnfiltered = useMemo(
    () => buildPlayerHighlights(highlightInput, baseHighlightOptions),
    [highlightInput, baseHighlightOptions],
  );

  const highestGamesQuery = useHighestIndividualGames(topN, {
    playerName: scope === "player" ? selectedPlayerName : "",
    playerId: scope === "player" ? selectedPlayerId : "",
    season,
    club: scope === "all" ? club : null,
  });

  const highestIndividualGames = buildHighestIndividualGameEntries(
    highestGamesQuery.data ?? [],
    topN,
    {
      scope,
      selectedPlayerName,
      database: databaseParam,
      tournamentAbbreviations,
    },
  );

  const categories: HighlightCategory[] = [
    {
      id: "clubAffiliation",
      titleKey: "ui.player.highlights_club_affiliation",
      titleFallback: "Clubzugehörigkeit",
      icon: Building2,
      entries: data.clubAffiliation,
    },
    {
      id: "gamesByClub",
      titleKey: "ui.player.highlights_games_by_club",
      titleFallback: "Spiele nach Club",
      icon: Activity,
      entries: data.gamesByClub,
    },
    {
      id: "avgByClub",
      titleKey: "ui.player.highlights_avg_by_club",
      titleFallback: "Schnitt nach Club",
      icon: TrendingUp,
      entries: data.avgByClub,
    },
    {
      id: "avgBySeason",
      titleKey: "ui.player.highlights_avg_by_season",
      titleFallback: "Schnitt nach Saison",
      icon: CalendarRange,
      entries: data.avgBySeason,
      filterToggle: {
        active: minGamesAvgSeason,
        label: t(
          "ui.player.highlights_min_games_season",
          `min. ${PLAYER_HIGHLIGHTS_MIN_GAMES_SEASON} Spiele`,
        ),
        onToggle: () => setMinGamesAvgSeason((v) => !v),
      },
    },
    {
      id: "highestIndividualGames",
      titleKey: "ui.player.highlights_highest_games",
      titleFallback: "Höchste Einzelspiele",
      icon: Target,
      entries: highestIndividualGames,
    },
    ...(scope === "player"
      ? [
          {
            id: "bestTournaments",
            titleKey: "ui.player.highlights_best_tournaments",
            titleFallback: "Beste Turniere",
            icon: Trophy,
            entries: data.bestTournaments,
          } satisfies HighlightCategory,
        ]
      : []),
    {
      id: "bestCompetitions",
      titleKey: "ui.player.highlights_best_competitions",
      titleFallback: "Beste Wettbewerbe",
      icon: Sparkles,
      entries: data.bestCompetitions,
      filterToggle: {
        active: minGamesBestComp,
        label: t(
          "ui.player.highlights_min_games_competition",
          `min. ${PLAYER_HIGHLIGHTS_MIN_GAMES_COMPETITION} Spiele`,
        ),
        onToggle: () => setMinGamesBestComp((v) => !v),
      },
    },
    {
      id: "bestDays",
      titleKey: "ui.player.highlights_best_days",
      titleFallback: "Beste Spieltage",
      icon: CalendarDays,
      entries: data.bestDays,
      filterToggle: {
        active: minGamesLeagueWeeks,
        label: t(
          "ui.player.highlights_min_games_league_week",
          `Liga · min. ${PLAYER_HIGHLIGHTS_MIN_GAMES_LEAGUE_WEEK} Spiele`,
        ),
        onToggle: () => setMinGamesLeagueWeeks((v) => !v),
      },
    },
  ];

  const unfilteredById: Record<string, PlayerHighlightEntry[]> = {
    avgBySeason: dataUnfiltered.avgBySeason,
    bestCompetitions: dataUnfiltered.bestCompetitions,
    bestDays: dataUnfiltered.bestDays,
  };

  const visibleCategories = categories.filter(
    (cat) =>
      cat.entries.length > 0 ||
      (cat.filterToggle != null && (unfilteredById[cat.id]?.length ?? 0) > 0),
  );
  if (visibleCategories.length === 0) return null;

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <div className="flex items-start gap-2.5">
          <Award className="mt-0.5 h-5 w-5 shrink-0 text-accent" strokeWidth={1.75} aria-hidden />
          <div>
            <h2 className="text-h3">
              {scope === "all"
                ? t("ui.player.highlights_heading_all", "Highlights — alle Spieler")
                : t("ui.player.highlights_heading", "Spieler-Highlights")}
            </h2>
            <p className="text-small text-muted mt-1">
              {scope === "all"
                ? t(
                    "ui.player.highlights_hint_all",
                    "Top-10 je Kategorie über alle Einzelleistungen in der Datenquelle.",
                  )
                : t("ui.player.highlights_hint", "Karriere-Überblick — Top-5 je Kategorie.")}
            </p>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-3 lg:p-5">
        {visibleCategories.map((category, categoryIdx) => (
          <HighlightCategoryBlock
            key={category.id}
            category={category}
            categoryIdx={categoryIdx}
            t={t}
          />
        ))}
      </div>
    </section>
  );
}

function buildHighestIndividualGameEntries(
  games: IndividualGameRecord[],
  topN: number,
  options: {
    scope: "all" | "player";
    selectedPlayerName: string;
    database: string | null;
    tournamentAbbreviations?: Record<string, string>;
  },
): PlayerHighlightEntry[] {
  return games.slice(0, topN).map((game, idx) => {
    const player = String(game.player_name ?? "").trim() || options.selectedPlayerName || "—";
    const fullName = String(game.competition ?? "—");
    const isTournament = !!game.is_tournament;
    const compLabel = isTournament
      ? formatCompetitionLabel(fullName, {
          isTournament: true,
          tournamentAbbreviations: options.tournamentAbbreviations,
        })
      : fullName;
    const competitionHref =
      buildIndividualGameEventPath(game, {
        selectedPlayerName: player,
        database: options.database,
      }) ?? undefined;

    if (options.scope === "player") {
      const detailParts = [game.season, game.date]
        .map((p) => String(p ?? "").trim())
        .filter(Boolean);
      return {
        id: `highest-game-${fullName}-${game.date}-${idx}`,
        label: compLabel,
        title: fullName,
        value: game.score != null ? String(game.score) : "—",
        detail: detailParts.join(" · ") || undefined,
        href: competitionHref,
      };
    }

    const detailParts = [compLabel, game.season, game.date]
      .map((p) => String(p ?? "").trim())
      .filter(Boolean);
    return {
      id: `highest-game-${player}-${game.date}-${idx}`,
      label: player,
      title: fullName,
      value: game.score != null ? String(game.score) : "—",
      detail: detailParts.join(" · ") || undefined,
      href: playerPageHref(player, game.player_id),
      detailHref: competitionHref,
    };
  });
}

function playerPageHref(name: string, id?: string | null): string {
  const params: Record<string, string> = { player_name: name };
  if (id) params.player_id = String(id);
  return buildUrl("/spieler", params);
}

function HighlightCategoryBlock({
  category,
  categoryIdx,
  t,
}: {
  category: HighlightCategory;
  categoryIdx: number;
  t: (key: string, fallback?: string) => string;
}) {
  const Icon = category.icon;
  const accentColor = getPaletteColor(categoryIdx % 10);

  return (
    <div className="flex min-w-0 flex-col rounded-sm border border-border bg-surface px-3 py-4 sm:px-4">
      <div
        className="mb-3 flex min-w-0 flex-col gap-2 border-b border-border border-l-4 pb-3 pl-2.5 sm:flex-row sm:items-start sm:justify-between"
        style={{ borderLeftColor: accentColor }}
      >
        <div className="flex min-w-0 items-start gap-2.5">
          <span
            className="grid h-8 w-8 shrink-0 place-items-center rounded-sm border border-border"
            style={{ backgroundColor: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}
          >
            <Icon
              className="h-4 w-4"
              style={{ color: accentColor }}
              strokeWidth={1.75}
              aria-hidden
            />
          </span>
          <h3 className="min-w-0 text-body font-semibold leading-snug text-foreground xl:text-h3">
            {t(category.titleKey, category.titleFallback)}
          </h3>
        </div>
        {category.filterToggle ? (
          <button
            type="button"
            onClick={category.filterToggle.onToggle}
            aria-pressed={category.filterToggle.active}
            className={
              "h-8 shrink-0 self-start rounded-sm border px-2.5 text-label font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (category.filterToggle.active
                ? "border-accent bg-accent-tint text-accent"
                : "border-border bg-surface-subtle text-muted hover:border-border-strong hover:text-foreground")
            }
          >
            {category.filterToggle.label}
          </button>
        ) : null}
      </div>
      {category.entries.length === 0 ? (
        <p className="border-t border-border py-3 text-small text-muted">
          {t("ui.player.highlights_filter_empty", "Keine Einträge mit aktuellem Filter.")}
        </p>
      ) : (
        <ul className="border-t border-border">
          {category.entries.map((entry, idx) => (
            <li
              key={entry.id}
              className={
                "flex items-center gap-2.5 border-b border-border py-2.5 text-small sm:gap-3 " +
                (idx === 0 ? "bg-accent-tint/40" : "")
              }
            >
              <RankBadge rank={idx + 1} />
              <div className="min-w-0 flex-1">
                {entry.href ? (
                  <Link
                    to={entry.href}
                    className="block truncate font-medium text-foreground hover:text-accent hover:underline"
                    title={entry.title ?? entry.label}
                  >
                    {entry.label}
                  </Link>
                ) : (
                  <p
                    className="truncate font-medium text-foreground"
                    title={entry.title ?? entry.label}
                  >
                    {entry.label}
                  </p>
                )}
                {entry.detail ? (
                  entry.detailHref ? (
                    <Link
                      to={entry.detailHref}
                      className="text-label text-muted mt-0.5 block truncate hover:text-accent hover:underline"
                      title={entry.detail}
                    >
                      {entry.detail}
                    </Link>
                  ) : (
                    <p className="text-label text-muted mt-0.5 truncate" title={entry.detail}>
                      {entry.detail}
                    </p>
                  )
                ) : null}
              </div>
              <span
                className="shrink-0 font-mono text-small font-semibold tabular-nums text-foreground sm:text-base"
                title={entry.value}
              >
                {entry.value}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RankBadge({ rank }: { rank: number }) {
  const color = getPaletteColor(rank - 1);

  return (
    <span
      className="inline-flex h-6 min-w-[1.75rem] shrink-0 items-center justify-center rounded-r-full pl-1.5 pr-2 font-mono text-[11px] font-semibold tabular-nums leading-none text-white"
      style={{
        backgroundColor: color,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 70%, black 30%)`,
      }}
      aria-hidden
    >
      {rank}
    </span>
  );
}
