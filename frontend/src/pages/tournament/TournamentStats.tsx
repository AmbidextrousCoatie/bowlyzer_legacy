import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMobileNav } from "../../context/MobileNavContext";
import { pickLatestSeason } from "../../hooks/useLeague";
import {
  usePlayerSectionForTournament,
  useTournamentNames,
  useTournamentPlayers,
  useTournamentRounds,
  useTournamentSeasons,
  useTournamentSection,
} from "../../hooks/useTournament";
import { useTranslations } from "../../hooks/useTranslations";
import { resolveTournamentPlayerName } from "../../lib/tournamentPlayer";
import { BestEfforts } from "./blocks/BestEfforts";
import { KoBracket } from "./blocks/KoBracket";
import { Leaderboard } from "./blocks/Leaderboard";
import { PlayerSection } from "./blocks/PlayerSection";
import { RoundResults } from "./blocks/RoundResults";
import { SummaryCards } from "./blocks/SummaryCards";
import { TournamentFilterBar } from "./TournamentFilterBar";

export function TournamentStats() {
  const { t } = useTranslations();
  const { setCompactPageChrome } = useMobileNav();
  const [searchParams, setSearchParams] = useSearchParams();
  const [heatmapEnabled, setHeatmapEnabled] = useState(false);

  useEffect(() => {
    setCompactPageChrome(true);
    return () => setCompactPageChrome(false);
  }, [setCompactPageChrome]);

  const season = searchParams.get("season") ?? "";
  const tournament = searchParams.get("tournament") ?? "";
  const round = searchParams.get("round") ?? "";
  const player = searchParams.get("player") ?? "";

  const seasonsQuery = useTournamentSeasons();
  const tournamentsQuery = useTournamentNames(season || null);
  const roundsQuery = useTournamentRounds(season || null, tournament || null);
  const playersQuery = useTournamentPlayers(season || null, tournament || null, round || null);

  const roster = playersQuery.data ?? [];
  const resolvedPlayer = useMemo(() => {
    if (!player) return "";
    if (!playersQuery.isSuccess || roster.length === 0) return player;
    return resolveTournamentPlayerName(player, roster) ?? player;
  }, [player, playersQuery.isSuccess, roster]);

  const sectionQuery = useTournamentSection(season || null, tournament || null, round || null);
  const playerSectionQuery = usePlayerSectionForTournament(
    season || null,
    tournament || null,
    resolvedPlayer || null,
  );

  // Backfill defaults: if season missing or invalid, pick latest available season.
  useEffect(() => {
    if (!seasonsQuery.isSuccess) return;
    const list = seasonsQuery.data ?? [];
    if (list.length === 0) return;
    const latest = pickLatestSeason(list);
    if (!latest) return;
    if (season && list.includes(season)) return;
    const next = new URLSearchParams(searchParams);
    next.set("season", latest);
    if (season !== latest) {
      next.delete("tournament");
      next.delete("round");
      next.delete("player");
    }
    setSearchParams(next, { replace: true });
  }, [seasonsQuery.isSuccess, seasonsQuery.data, season, tournament, searchParams, setSearchParams]);

  useEffect(() => {
    if (!tournamentsQuery.isSuccess) return;
    const list = tournamentsQuery.data ?? [];
    if (!tournament && list.length > 0) {
      const next = new URLSearchParams(searchParams);
      next.set("tournament", list[0]);
      setSearchParams(next, { replace: true });
    } else if (tournament && list.length > 0 && !list.includes(tournament)) {
      const next = new URLSearchParams(searchParams);
      next.set("tournament", list[0]);
      next.delete("round");
      setSearchParams(next, { replace: true });
    }
  }, [
    tournamentsQuery.isSuccess,
    tournamentsQuery.data,
    tournament,
    searchParams,
    setSearchParams,
  ]);

  // If round is set but not in the available list, drop it.
  useEffect(() => {
    if (!roundsQuery.isSuccess) return;
    if (!round) return;
    const list = roundsQuery.data ?? [];
    if (!list.some((r) => String(r.round_number) === round)) {
      const next = new URLSearchParams(searchParams);
      next.delete("round");
      setSearchParams(next, { replace: true });
    }
  }, [roundsQuery.isSuccess, roundsQuery.data, round, searchParams, setSearchParams]);

  // Normalize deep-link player names to the roster spelling (do not strip unknown players).
  useEffect(() => {
    if (!playersQuery.isSuccess || !player) return;
    const canonical = resolveTournamentPlayerName(player, playersQuery.data ?? []);
    if (canonical && canonical !== player) {
      const next = new URLSearchParams(searchParams);
      next.set("player", canonical);
      setSearchParams(next, { replace: true });
    }
  }, [playersQuery.isSuccess, playersQuery.data, player, searchParams, setSearchParams]);

  function setParam(key: string, value: string, drop: string[] = []) {
    const next = new URLSearchParams(searchParams);
    if (value === "") next.delete(key);
    else next.set(key, value);
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

  const playerMode = !!resolvedPlayer;

  const showKoBracket = useMemo(() => {
    const data = sectionQuery.data;
    if (!data?.ko_bracket?.matches?.length) return false;
    if (data.is_ko_finale_round) return true;
    if (!round && data.ko_finale_round_number != null) return true;
    return false;
  }, [sectionQuery.data, round]);

  return (
    <div className="mx-auto max-w-[1280px] px-4 pt-8 pb-24 max-lg:landscape:pt-2 lg:px-8 lg:pt-12">
      <header className="mb-6 max-lg:landscape:hidden lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.tournament.title", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("ui.tournament.title", "Turnier")}
          {tournament ? (
            <>
              {" "}
              · <span className="text-muted font-normal">{tournament}</span>
            </>
          ) : null}
        </h1>
      </header>

      <TournamentFilterBar
        pageHeading={buildTournamentPageHeading(tournament, season)}
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
        playerMode={playerMode}
        onSeasonChange={(v) => setParam("season", v, ["tournament", "round", "player"])}
        onTournamentChange={(v) => setParam("tournament", v, ["round", "player"])}
        onRoundChange={(v) => setParam("round", v)}
        onPlayerChange={(v) => setParam("player", v)}
        t={t}
      />

      <div className="mt-6 space-y-12 lg:mt-10">
        {playerMode ? (
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
                fieldProgress={sectionQuery.data?.field_progress}
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
                  {t(
                    "ui.tournament.no_player_data",
                    "Keine Spielerdaten für diese Auswahl.",
                  )}
                </p>
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

function buildTournamentPageHeading(tournament: string, season: string): string {
  if (tournament && season) return `${tournament} · ${season}`;
  if (tournament) return tournament;
  if (season) return season;
  return "";
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
