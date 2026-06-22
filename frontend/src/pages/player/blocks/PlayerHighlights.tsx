import {
  Activity,
  Award,
  Building2,
  CalendarDays,
  CalendarRange,
  Sparkles,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { PlayerPeriodRow, PlayerSeasonRow } from "../../../hooks/usePlayer";
import {
  buildPlayerHighlights,
  type PlayerHighlightEntry,
  type PlayerHighlightsData,
} from "../../../lib/playerHighlights";
import { getPaletteColor } from "../../../lib/color-utils";
import { useTranslations } from "../../../hooks/useTranslations";
import { formatPeriodDetail } from "../../../lib/playerPeriodLabel";

type Props = {
  seasons: PlayerSeasonRow[];
  periods: PlayerPeriodRow[];
  selectedPlayerName: string;
  t: (key: string, fallback?: string) => string;
};

type HighlightCategory = {
  id: keyof PlayerHighlightsData;
  titleKey: string;
  titleFallback: string;
  icon: LucideIcon;
  entries: PlayerHighlightEntry[];
};

export function PlayerHighlights({ seasons, periods, selectedPlayerName, t }: Props) {
  const databaseParam =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("database")
      : null;

  const { tournamentAbbreviations } = useTranslations();

  const data = buildPlayerHighlights(
    seasons,
    {
      selectedPlayerName,
      database: databaseParam,
      tournamentAbbreviations,
      formatPeriod: (row) => formatPeriodDetail(row, t),
    },
    periods,
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
    },
    {
      id: "bestTournaments",
      titleKey: "ui.player.highlights_best_tournaments",
      titleFallback: "Beste Turniere",
      icon: Trophy,
      entries: data.bestTournaments,
    },
    {
      id: "bestCompetitions",
      titleKey: "ui.player.highlights_best_competitions",
      titleFallback: "Beste Wettbewerbe",
      icon: Sparkles,
      entries: data.bestCompetitions,
    },
    {
      id: "bestDays",
      titleKey: "ui.player.highlights_best_days",
      titleFallback: "Beste Spieltage",
      icon: CalendarDays,
      entries: data.bestDays,
    },
  ];

  const visibleCategories = categories.filter((cat) => cat.entries.length > 0);
  if (visibleCategories.length === 0) return null;

  return (
    <section className="rounded-sm border border-border bg-surface">
      <header className="border-b border-border px-4 py-3 lg:px-5">
        <div className="flex items-start gap-2.5">
          <Award
            className="mt-0.5 h-5 w-5 shrink-0 text-accent"
            strokeWidth={1.75}
            aria-hidden
          />
          <div>
            <h2 className="text-h3">{t("ui.player.highlights_heading", "Spieler-Highlights")}</h2>
            <p className="text-small text-muted mt-1">
              {t(
                "ui.player.highlights_hint",
                "Karriere-Überblick — Clubs, Saisons und Wettbewerbe auf einen Blick.",
              )}
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
        className="mb-3 flex min-w-0 items-start gap-2.5 border-b border-border border-l-4 pb-3 pl-2.5"
        style={{ borderLeftColor: accentColor }}
      >
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-sm border border-border"
          style={{ backgroundColor: `color-mix(in srgb, ${accentColor} 18%, transparent)` }}
        >
          <Icon className="h-4 w-4" style={{ color: accentColor }} strokeWidth={1.75} aria-hidden />
        </span>
        <h3 className="min-w-0 text-body font-semibold leading-snug text-foreground xl:text-h3">
          {t(category.titleKey, category.titleFallback)}
        </h3>
      </div>
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
                <p className="text-label text-muted mt-0.5 truncate" title={entry.detail}>
                  {entry.detail}
                </p>
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
