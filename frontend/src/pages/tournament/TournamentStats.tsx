import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  type TournamentRound,
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
import { Leaderboard } from "./blocks/Leaderboard";
import { PlayerSection } from "./blocks/PlayerSection";
import { RoundResults } from "./blocks/RoundResults";
import { SummaryCards } from "./blocks/SummaryCards";

export function TournamentStats() {
  const { t } = useTranslations();
  const [searchParams, setSearchParams] = useSearchParams();
  const [heatmapEnabled, setHeatmapEnabled] = useState(false);

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

  // Backfill defaults: if season missing, pick first available; if tournament
  // missing for the chosen season, pick first.
  useEffect(() => {
    if (!seasonsQuery.isSuccess) return;
    const list = seasonsQuery.data ?? [];
    if (!season && list.length > 0) {
      const next = new URLSearchParams(searchParams);
      next.set("season", list[0]);
      setSearchParams(next, { replace: true });
    }
  }, [seasonsQuery.isSuccess, seasonsQuery.data, season, searchParams, setSearchParams]);

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
    const list = sectionQuery.data?.rounds ?? [];
    const found = list.find((r) => String(r.round_number) === round);
    if (found?.round_name) return found.round_name;
    return `${t("ui.tournament.round", "Runde")} ${round}`;
  }, [round, sectionQuery.data, t]);

  const playerMode = !!resolvedPlayer;

  return (
    <div className="mx-auto max-w-[1280px] px-8 pt-12 pb-24">
      <header className="mb-8">
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

      <FilterRail
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

      <div className="mt-10 space-y-12">
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
                  onPlayerClick={selectPlayer}
                  t={t}
                />
                <BestEfforts bestEfforts={sectionQuery.data.best_efforts} t={t} />
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

type FilterRailProps = {
  season: string;
  seasons: string[];
  seasonsLoading: boolean;
  tournament: string;
  tournaments: string[];
  tournamentsLoading: boolean;
  round: string;
  rounds: TournamentRound[];
  roundsLoading: boolean;
  player: string;
  players: string[];
  playersLoading: boolean;
  playerMode: boolean;
  onSeasonChange: (v: string) => void;
  onTournamentChange: (v: string) => void;
  onRoundChange: (v: string) => void;
  onPlayerChange: (v: string) => void;
  t: (key: string, fallback?: string) => string;
};

function FilterRail(props: FilterRailProps) {
  const { t } = props;
  return (
    <div className="sticky top-0 z-10 -mx-8 border-b border-border bg-background/85 px-8 py-3 backdrop-blur">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <FilterField label={t("ui.tournament.season", "Saison")}>
          <SelectControl
            value={props.season}
            disabled={props.seasonsLoading}
            ariaLabel={t("ui.tournament.season", "Saison")}
            onChange={props.onSeasonChange}
          >
            <option value="">—</option>
            {props.seasons.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        <FilterField label={t("ui.tournament.tournament", "Turnier")}>
          <SelectControl
            value={props.tournament}
            disabled={props.tournamentsLoading}
            ariaLabel={t("ui.tournament.tournament", "Turnier")}
            onChange={props.onTournamentChange}
          >
            <option value="">—</option>
            {props.tournaments.map((tn) => (
              <option key={tn} value={tn}>
                {tn}
              </option>
            ))}
          </SelectControl>
        </FilterField>

        {!props.playerMode && (
          <FilterField label={t("ui.tournament.round", "Runde")}>
            <SelectControl
              value={props.round}
              disabled={props.roundsLoading}
              ariaLabel={t("ui.tournament.round", "Runde")}
              onChange={props.onRoundChange}
            >
              <option value="">{t("ui.tournament.all_latest", "Gesamt")}</option>
              {props.rounds.map((r) => (
                <option
                  key={String(r.round_number)}
                  value={String(r.round_number)}
                  title={r.round_name ? String(r.round_name) : undefined}
                >
                  {r.round_number}
                </option>
              ))}
            </SelectControl>
          </FilterField>
        )}

        <FilterField label={t("ui.tournament.player", "Spieler")}>
          <SelectControl
            value={props.player}
            disabled={props.playersLoading}
            ariaLabel={t("ui.tournament.player", "Spieler")}
            onChange={props.onPlayerChange}
          >
            <option value="">—</option>
            {props.players.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </SelectControl>
        </FilterField>
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-label uppercase text-muted">{label}</span>
      {children}
    </label>
  );
}

function SelectControl({
  value,
  onChange,
  disabled,
  ariaLabel,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 min-w-[160px] rounded-sm border border-border bg-surface px-2.5 text-small text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
    >
      {children}
    </select>
  );
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
