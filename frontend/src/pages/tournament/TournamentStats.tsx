import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMobileNav } from "../../context/MobileNavContext";
import { useMyClub } from "../../hooks/useMyClub";
import {
  usePlayerSectionForTournament,
  usePlayerTournamentResults,
  useTournamentNames,
  useTournamentPlayers,
  useTournamentPodiums,
  useTournamentRounds,
  useTournamentSeasons,
  useTournamentSection,
} from "../../hooks/useTournament";
import { useTranslations } from "../../hooks/useTranslations";
import { TopicPageHeader } from "../../components/TopicPageHeader";
import { seasonForUrlQuery } from "../../lib/api";
import { normalizeUnicodeLabel } from "../../lib/teamUtils";
import { resolveTournamentPlayerName } from "../../lib/tournamentPlayer";
import { BestEfforts } from "./blocks/BestEfforts";
import { KoBracket } from "./blocks/KoBracket";
import { Leaderboard } from "./blocks/Leaderboard";
import { PlayerSection } from "./blocks/PlayerSection";
import { RoundResults } from "./blocks/RoundResults";
import { SummaryCards } from "./blocks/SummaryCards";
import { TournamentFilterBar } from "./TournamentFilterBar";
import { TournamentPlayerOverview } from "./blocks/TournamentPlayerOverview";
import { TournamentPodiumOverview } from "./blocks/TournamentPodiumOverview";

export function TournamentStats() {
  const { t } = useTranslations();
  const { setCompactPageChrome } = useMobileNav();
  const [searchParams, setSearchParams] = useSearchParams();
  const [heatmapEnabled, setHeatmapEnabled] = useState(false);
  const { active: myClubActive, resolvedClub } = useMyClub();
  const clubFilter = myClubActive ? resolvedClub || null : null;

  useEffect(() => {
    setCompactPageChrome(true);
    return () => setCompactPageChrome(false);
  }, [setCompactPageChrome]);

  const season = searchParams.get("season") ?? "";
  const tournament = searchParams.get("tournament") ?? "";
  const round = searchParams.get("round") ?? "";
  const player = searchParams.get("player") ?? "";

  const hasSeason = !!season;
  const hasTournament = !!tournament;
  const showEventDetail = hasSeason && hasTournament;
  const showPlayerDetail = showEventDetail && !!player;
  const showPlayerOverview = !!player && !showEventDetail;
  const showPodiumOverview = !player && !showEventDetail;

  const seasonsQuery = useTournamentSeasons(tournament || undefined, clubFilter);
  const tournamentsQuery = useTournamentNames(season || null, clubFilter);
  const roundsQuery = useTournamentRounds(season || null, tournament || null);
  const playersQuery = useTournamentPlayers(season || null, tournament || null, round || null);
  const podiumsQuery = useTournamentPodiums(season || null, tournament || null, clubFilter);
  const playerResultsQuery = usePlayerTournamentResults(
    player || null,
    season || null,
    tournament || null,
  );

  const roster = playersQuery.data ?? [];
  const resolvedPlayer = useMemo(() => {
    if (!player) return "";
    if (!playersQuery.isSuccess || roster.length === 0) return player;
    return resolveTournamentPlayerName(player, roster) ?? player;
  }, [player, playersQuery.isSuccess, roster]);

  const sectionQuery = useTournamentSection(
    showEventDetail && !showPlayerDetail ? season : null,
    showEventDetail && !showPlayerDetail ? tournament : null,
    round || null,
  );
  const playerSectionQuery = usePlayerSectionForTournament(
    showPlayerDetail ? season : null,
    showPlayerDetail ? tournament : null,
    showPlayerDetail ? resolvedPlayer || null : null,
  );

  // Clear season/tournament when Mein Club excludes the current selection.
  useEffect(() => {
    if (!myClubActive || !clubFilter) return;
    if (!seasonsQuery.isSuccess || !tournamentsQuery.isSuccess) return;
    const seasons = seasonsQuery.data ?? [];
    const tournaments = tournamentsQuery.data ?? [];
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (
      season &&
      seasons.length > 0 &&
      !seasons.some((s) => normalizeUnicodeLabel(s) === normalizeUnicodeLabel(season))
    ) {
      next.delete("season");
      next.delete("tournament");
      next.delete("round");
      next.delete("player");
      changed = true;
    } else if (
      tournament &&
      tournaments.length > 0 &&
      !tournaments.some((tn) => normalizeUnicodeLabel(tn) === normalizeUnicodeLabel(tournament))
    ) {
      next.delete("tournament");
      next.delete("round");
      next.delete("player");
      changed = true;
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [
    myClubActive,
    clubFilter,
    seasonsQuery.isSuccess,
    seasonsQuery.data,
    tournamentsQuery.isSuccess,
    tournamentsQuery.data,
    season,
    tournament,
    searchParams,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!roundsQuery.isSuccess || !showEventDetail) return;
    if (!round) return;
    const list = roundsQuery.data ?? [];
    if (!list.some((r) => String(r.round_number) === round)) {
      const next = new URLSearchParams(searchParams);
      next.delete("round");
      setSearchParams(next, { replace: true });
    }
  }, [
    roundsQuery.isSuccess,
    roundsQuery.data,
    round,
    searchParams,
    setSearchParams,
    showEventDetail,
  ]);
  useEffect(() => {
    if (!playersQuery.isSuccess || !player || !showEventDetail) return;
    const canonical = resolveTournamentPlayerName(player, playersQuery.data ?? []);
    if (canonical && canonical !== player) {
      const next = new URLSearchParams(searchParams);
      next.set("player", canonical);
      setSearchParams(next, { replace: true });
    }
  }, [
    playersQuery.isSuccess,
    playersQuery.data,
    player,
    searchParams,
    setSearchParams,
    showEventDetail,
  ]);

  function setParam(key: string, value: string, drop: string[] = []) {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else next.set(key, key === "season" ? seasonForUrlQuery(value) : value);
    drop.forEach((k) => next.delete(k));
    setSearchParams(next, { replace: false });
  }

  function selectPlayer(name: string) {
    setParam("player", name);
  }

  function clearPlayer() {
    setParam("player", "");
  }

  const stageLabel = useMemo(() => {
    if (!round) return null;
    const list = roundsQuery.data ?? sectionQuery.data?.rounds ?? [];
    const found = list.find((r) => String(r.round_number) === round);
    if (found?.round_name) return found.round_name;
    return `${t("ui.tournament.round", "Runde")} ${round}`;
  }, [round, roundsQuery.data, sectionQuery.data?.rounds, t]);

  const overviewStageLabel = useMemo(() => {
    if (!round) return t("ui.tournament.overall_standings", "Gesamtstand");
    return stageLabel ?? `${t("ui.tournament.round", "Runde")} ${round}`;
  }, [round, stageLabel, t]);

  const showKoBracket = useMemo(() => {
    const data = sectionQuery.data;
    if (!data?.ko_bracket?.matches?.length) return false;
    if (data.is_ko_finale_round) return true;
    if (!round && data.ko_finale_round_number != null) return true;
    return false;
  }, [sectionQuery.data, round]);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 max-lg:landscape:pt-2 lg:px-8 lg:pt-12">
      <TopicPageHeader
        topic="tournament"
        eyebrow={t("ui.tournament.title", "Bowl-A-Lyzer")}
        hideOnLandscape
        title={
          <>
            {t("ui.tournament.title", "Turnier")}
            {tournament ? (
              <>
                {" "}
                · <span className="text-muted font-normal">{tournament}</span>
              </>
            ) : null}
          </>
        }
        description={t(
          "ui.tournament.page_desc",
          "Meisterschaftsergebnisse nach Saison und Turnier — Format-Details über das ℹ-Symbol.",
        )}
      />

      <TournamentFilterBar
        pageHeading={buildTournamentPageHeading(tournament, season, resolvedPlayer)}
        season={season}
        seasons={seasonsQuery.data ?? []}
        seasonsLoading={seasonsQuery.isPending}
        tournament={tournament}
        tournaments={tournamentsQuery.data ?? []}
        tournamentsLoading={tournamentsQuery.isPending}
        round={round}
        rounds={roundsQuery.data ?? []}
        roundsLoading={roundsQuery.isPending}
        player={resolvedPlayer}
        players={roster}
        playersLoading={playersQuery.isPending}
        playerMode={showPlayerDetail}
        showEventDetail={showEventDetail}
        onSeasonChange={(v) => setParam("season", v, ["round", "player"])}
        onTournamentChange={(v) => setParam("tournament", v, ["round", "player"])}
        onRoundChange={(v) => setParam("round", v)}
        onPlayerChange={(v) => setParam("player", v)}
        t={t}
      />

      <div className="mt-6 space-y-12 lg:mt-10">
        {showPlayerOverview ? (
          <>
            {playerResultsQuery.isPending && <LoadingSection t={t} />}
            {playerResultsQuery.isError && (
              <ErrorSection
                message={
                  playerResultsQuery.error instanceof Error
                    ? playerResultsQuery.error.message
                    : t("error_generic", "Fehler beim Laden")
                }
              />
            )}
            {playerResultsQuery.isSuccess && (
              <TournamentPlayerOverview
                rows={playerResultsQuery.data ?? []}
                player={resolvedPlayer}
                season={season}
                tournament={tournament}
                t={t}
              />
            )}
          </>
        ) : showPlayerDetail ? (
          <>
            {playerSectionQuery.isPending && <LoadingSection t={t} />}
            {playerSectionQuery.isError && (
              <ErrorSection
                message={
                  playerSectionQuery.error instanceof Error
                    ? playerSectionQuery.error.message
                    : t("error_generic", "Fehler beim Laden")
                }
              />
            )}
            {playerSectionQuery.isSuccess && playerSectionQuery.data && (
              <PlayerSection
                data={playerSectionQuery.data}
                fieldProgress={playerSectionQuery.data.field_progress}
                heatmapEnabled={heatmapEnabled}
                onToggleHeatmap={() => setHeatmapEnabled((v) => !v)}
                onBack={clearPlayer}
                onPlayerClick={selectPlayer}
                t={t}
              />
            )}
            {playerSectionQuery.isSuccess &&
              !playerSectionQuery.isFetching &&
              resolvedPlayer &&
              !playerSectionQuery.data && (
                <p className="text-small text-muted">
                  {t("ui.tournament.no_player_data", "Keine Spielerdaten für diese Auswahl.")}
                </p>
              )}
          </>
        ) : showPodiumOverview ? (
          <>
            {podiumsQuery.isPending && <LoadingSection t={t} />}
            {podiumsQuery.isError && (
              <ErrorSection
                message={
                  podiumsQuery.error instanceof Error
                    ? podiumsQuery.error.message
                    : t("error_generic", "Fehler beim Laden")
                }
              />
            )}
            {podiumsQuery.isSuccess && (
              <TournamentPodiumOverview
                podiums={podiumsQuery.data?.podiums ?? []}
                season={season}
                tournament={tournament}
                t={t}
              />
            )}
          </>
        ) : (
          <>
            {sectionQuery.isPending && <LoadingSection t={t} />}
            {sectionQuery.isError && (
              <ErrorSection
                message={
                  sectionQuery.error instanceof Error
                    ? sectionQuery.error.message
                    : t("error_generic", "Fehler beim Laden")
                }
              />
            )}
            {sectionQuery.isSuccess && sectionQuery.data && (
              <>
                <SummaryCards
                  cards={sectionQuery.data.cards ?? []}
                  overviewStageLabel={overviewStageLabel}
                  onPlayerClick={selectPlayer}
                  t={t}
                />
                <BestEfforts bestEfforts={sectionQuery.data.best_efforts} t={t} />
                {showKoBracket && sectionQuery.data.ko_bracket ? (
                  <KoBracket
                    bracket={sectionQuery.data.ko_bracket}
                    onPlayerClick={selectPlayer}
                    t={t}
                  />
                ) : null}
                <Leaderboard
                  data={sectionQuery.data.leaderboard}
                  stageLabel={stageLabel}
                  onPlayerClick={selectPlayer}
                  t={t}
                />
                {round && sectionQuery.data.round_results ? (
                  <RoundResults
                    data={sectionQuery.data.round_results}
                    heatmapEnabled={heatmapEnabled}
                    onToggleHeatmap={() => setHeatmapEnabled((v) => !v)}
                    stageLabel={stageLabel}
                    onPlayerClick={selectPlayer}
                    t={t}
                  />
                ) : null}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function buildTournamentPageHeading(tournament: string, season: string, player: string): string {
  const parts: string[] = [];
  if (player) parts.push(player);
  if (tournament) parts.push(tournament);
  if (season) parts.push(season);
  return parts.join(" · ");
}

function LoadingSection({ t }: { t: (key: string, fallback?: string) => string }) {
  return (
    <section aria-label={t("status.loading", "Lade Daten…")}>
      <div className="h-3 w-24 rounded-xs bg-surface-subtle" />
      <div className="mt-2 h-6 w-64 rounded-xs bg-surface-subtle" />
      <div className="mt-4 h-64 rounded-sm border border-border bg-surface-subtle" />
    </section>
  );
}

function ErrorSection({ message }: { message: string }) {
  return (
    <section className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
      {message}
    </section>
  );
}
