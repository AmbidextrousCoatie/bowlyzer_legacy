import { HOME_SECTIONS } from "../../lib/homeContent";
import { HomeSection } from "./HomeSection";

type HomeStatsOverviewProps = {
  games: string;
  leagueSeasons: string;
  years: string;
  tournaments: string;
  players: string;
  loading?: boolean;
  error?: boolean;
};

export function HomeStatsOverview({
  games,
  leagueSeasons,
  years,
  tournaments,
  players,
  loading,
  error,
}: HomeStatsOverviewProps) {
  return (
    <HomeSection
      eyebrow={HOME_SECTIONS.statsEyebrow}
      title={HOME_SECTIONS.stats}
      titleId="home-stats-title"
    >
      {error ? (
        <p className="text-small text-danger-fg mb-4">Statistiken konnten nicht geladen werden.</p>
      ) : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Spiele" value={games} loading={loading} />
        <StatCard label="Liga-Saisons" value={leagueSeasons} loading={loading} />
        <StatCard label="Jahre" value={years} loading={loading} />
        <StatCard label="Turniere" value={tournaments} loading={loading} />
        <StatCard label="Spieler" value={players} loading={loading} />
      </div>
    </HomeSection>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string;
  loading?: boolean;
}) {
  return (
    <div className="rounded-sm border border-border bg-surface px-4 py-3">
      <p className="text-label uppercase text-muted mb-1">{label}</p>
      <p className="font-mono text-h2 tabular-nums text-foreground">
        {loading ? (
          <span className="inline-block h-7 w-16 animate-pulse rounded-xs bg-surface-subtle" />
        ) : (
          value
        )}
      </p>
    </div>
  );
}
