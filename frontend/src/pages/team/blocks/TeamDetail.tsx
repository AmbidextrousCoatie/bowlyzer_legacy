import { Link } from "react-router-dom";
import { CollapsibleSection } from "../../../components/CollapsibleSection";
import {
  useClutchAnalysis,
  useConsistencyMetrics,
  useLeagueComparison,
  useSpecialMatches,
  useTeamHistory,
} from "../../../hooks/useTeam";
import { buildTeamNavPath } from "../../../lib/teamNavigation";
import { ClutchAnalysisSection } from "./ClutchAnalysisSection";
import { ConsistencySection } from "./ConsistencySection";
import { LeagueComparisonSection } from "./LeagueComparisonSection";
import { SpecialMatchesSection } from "./SpecialMatchesSection";
import { TeamHistoryChart } from "./TeamHistoryChart";
import { useState } from "react";

type Props = {
  club: string;
  teamName: string;
  season: string;
  seasons: string[];
  onSeasonChange: (season: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function TeamDetail({
  club,
  teamName,
  season,
  seasons,
  onSeasonChange,
  t,
}: Props) {
  const [clutchThreshold, setClutchThreshold] = useState(10);

  const historyQuery = useTeamHistory(teamName);
  const leagueCmpQuery = useLeagueComparison(teamName);
  const clutchQuery = useClutchAnalysis(teamName, season, clutchThreshold);
  const consistencyQuery = useConsistencyMetrics(teamName, season);
  const specialQuery = useSpecialMatches(teamName, season);

  return (
    <div className="space-y-8">
      <nav className="text-small text-muted">
        <Link to={buildTeamNavPath({ club })} className="hover:text-accent">
          {club}
        </Link>
        <span className="mx-2">/</span>
        <span className="text-foreground">{teamName}</span>
      </nav>

      {seasons.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <SeasonChip
            label={t("ui.team.all_seasons", "Alle Saisons")}
            active={season === "all"}
            onClick={() => onSeasonChange("all")}
          />
          {seasons.map((s) => (
            <SeasonChip
              key={s}
              label={s}
              active={season === s}
              onClick={() => onSeasonChange(s)}
            />
          ))}
        </div>
      )}

      <CollapsibleSection
        eyebrow={t("ui.team_history.eyebrow", "Verlauf")}
        title={t("ui.team_history.title", "Platzierungsverlauf")}
        defaultOpen
      >
        {historyQuery.isPending && <LoadingHint t={t} />}
        {historyQuery.isError && <ErrorHint error={historyQuery.error} t={t} />}
        {historyQuery.isSuccess && (
          <TeamHistoryChart teamName={teamName} history={historyQuery.data} t={t} />
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title={t("ui.special.title", "Besondere Momente")}
        defaultOpen
      >
        {specialQuery.isPending && <LoadingHint t={t} />}
        {specialQuery.isError && <ErrorHint error={specialQuery.error} t={t} />}
        {specialQuery.isSuccess && (
          <SpecialMatchesSection teamName={teamName} data={specialQuery.data} t={t} />
        )}
      </CollapsibleSection>

      <CollapsibleSection
        eyebrow={t("ui.league_comparison.eyebrow", "Liga")}
        title={t("ui.league_comparison.title", "Leistung vs. Liga-Durchschnitt")}
        defaultOpen
      >
        {leagueCmpQuery.isPending && <LoadingHint t={t} />}
        {leagueCmpQuery.isError && <ErrorHint error={leagueCmpQuery.error} t={t} />}
        {leagueCmpQuery.isSuccess && (
          <LeagueComparisonSection data={leagueCmpQuery.data} t={t} />
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title={t("ui.clutch.title", "Clutch Performance")}
        defaultOpen={false}
      >
        {clutchQuery.isPending && <LoadingHint t={t} />}
        {clutchQuery.isError && <ErrorHint error={clutchQuery.error} t={t} />}
        {clutchQuery.isSuccess && (
          <ClutchAnalysisSection
            data={clutchQuery.data}
            threshold={clutchThreshold}
            onThresholdChange={setClutchThreshold}
            t={t}
          />
        )}
      </CollapsibleSection>

      <CollapsibleSection
        title={t("ui.consistency.title", "Konstanz")}
        defaultOpen={false}
      >
        {consistencyQuery.isPending && <LoadingHint t={t} />}
        {consistencyQuery.isError && <ErrorHint error={consistencyQuery.error} t={t} />}
        {consistencyQuery.isSuccess && (
          <ConsistencySection data={consistencyQuery.data} t={t} />
        )}
      </CollapsibleSection>

    </div>
  );
}

function SeasonChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-sm border px-2.5 py-1 text-small transition-colors ${
        active
          ? "border-accent bg-accent/10 text-accent font-medium"
          : "border-border bg-surface-subtle text-muted hover:border-accent/50"
      }`}
    >
      {label}
    </button>
  );
}

function LoadingHint({ t }: { t: (k: string, f?: string) => string }) {
  return (
    <p className="p-4 text-small text-muted">{t("loading", "Laden…")}</p>
  );
}

function ErrorHint({
  error,
  t,
}: {
  error: unknown;
  t: (k: string, f?: string) => string;
}) {
  return (
    <p className="p-4 text-small text-danger-fg">
      {error instanceof Error ? error.message : t("error_generic", "Fehler beim Laden")}
    </p>
  );
}
