import { useMemo } from "react";
import { Trophy } from "lucide-react";
import type { KoBracketFieldPlayer, KoBracketMatch, KoBracketPayload } from "../../../hooks/useTournament";
import {
  formatPinGamesLine,
  isNoShowName,
  isStepladderFormat,
  normalizeKoName,
  organizeBracketTiers,
  renderSeriesParts,
  sideKey,
  tierLabel,
  type BracketTiers,
  type BracketTierId,
} from "../../../lib/koBracket";

type Props = {
  bracket: KoBracketPayload;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

export function KoBracket({ bracket, onPlayerClick, t }: Props) {
  const matches = bracket.matches ?? [];
  if (matches.length === 0) return null;

  const tiers = useMemo(() => organizeBracketTiers(matches), [matches]);
  const focusKey = bracket.focus_player ? normalizeKoName(bracket.focus_player) : "";
  const stepladder = isStepladderFormat(bracket);
  const showInferredNote = tiers.sf.some((m) => m.inferred);

  return (
    <section className="ko-bracket-section" aria-label={t("ui.tournament.ko_bracket_title", "K.-o.-Schema")}>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.tournament.ko_bracket_title", "K.-o.-Schema")}
        </p>
        <h2 className="text-h2">{t("ui.tournament.ko_finale_heading", "Finale")}</h2>
        {stepladder ? (
          <p className="mt-1 text-small text-muted">
            {t(
              "ui.tournament.ko_stepladder_format_note",
              "Eliminierung Spiel-für-Spiel inkl. Handicap → Stepladder 1 Spiel inkl. HDC → Finale Best-of-3 inkl. HDC",
            )}
          </p>
        ) : null}
      </div>

      {showInferredNote ? (
        <p className="mb-4 rounded-sm border border-border bg-surface-subtle px-3 py-2 text-small text-muted">
          {t(
            "ui.tournament.ko_sf2_inferred_note",
            "Halbfinale 2 fehlte im Export und wird als Walkover ergänzt, damit das Schema zur Auslosung passt.",
          )}
        </p>
      ) : null}

      <div
        className="ko-bracket-scroll rounded-sm border border-border bg-surface p-4 md:p-6"
        role="region"
      >
        {stepladder ? (
          <StepladderFlow
            tiers={tiers}
            focusKey={focusKey}
            onPlayerClick={onPlayerClick}
            t={t}
          />
        ) : (
          <TreeGrid tiers={tiers} focusKey={focusKey} onPlayerClick={onPlayerClick} t={t} />
        )}
      </div>
    </section>
  );
}

function TreeGrid({
  tiers,
  focusKey,
  onPlayerClick,
  t,
}: {
  tiers: BracketTiers;
  focusKey: string;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const hasQf = tiers.qf.length > 0;
  const hasSf = tiers.sf.length > 0;

  return (
    <div
      className={
        "ko-bracket-grid " +
        (hasQf ? "ko-bracket-grid--full" : hasSf ? "ko-bracket-grid--sf" : "ko-bracket-grid--final")
      }
    >
      {hasQf ? (
        <TreeColumn tier="qf" matches={tiers.qf} focusKey={focusKey} onPlayerClick={onPlayerClick} t={t} />
      ) : null}
      {hasSf ? (
        <TreeColumn tier="sf" matches={tiers.sf} focusKey={focusKey} onPlayerClick={onPlayerClick} t={t} />
      ) : null}
      {tiers.final.length > 0 ? (
        <TreeColumn
          tier="final"
          matches={tiers.final}
          focusKey={focusKey}
          onPlayerClick={onPlayerClick}
          t={t}
          emphasize
        />
      ) : null}
    </div>
  );
}

function TreeColumn({
  tier,
  matches,
  focusKey,
  emphasize,
  onPlayerClick,
  t,
}: {
  tier: BracketTierId;
  matches: KoBracketMatch[];
  focusKey: string;
  emphasize?: boolean;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <div className="ko-bracket-column flex min-h-[12rem] flex-col">
      <p className="ko-bracket-tier-label text-label uppercase text-subtle mb-3 text-center">
        {tierLabel(tier, t)}
      </p>
      <div className="flex flex-1 flex-col justify-around gap-4">
        {matches.map((match) => (
          <PairMatchCard
            key={match.key}
            match={match}
            focusKey={focusKey}
            emphasize={emphasize}
            onPlayerClick={onPlayerClick}
            t={t}
          />
        ))}
      </div>
    </div>
  );
}

/** Left→right: one elim box (both rounds), then stepladder ascending toward top-right. */
function StepladderFlow({
  tiers,
  focusKey,
  onPlayerClick,
  t,
}: {
  tiers: BracketTiers;
  focusKey: string;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const elimMatches = expandElimRounds(
    [...tiers.elim].sort((a, b) => {
      const ai = Number(String(a.key).replace(/\D/g, "") || 0);
      const bi = Number(String(b.key).replace(/\D/g, "") || 0);
      return ai - bi;
    }),
  );
  const ascent = [...tiers.stepladder, ...tiers.final];

  return (
    <div className="ko-stepladder-flow">
      {elimMatches.length > 0 ? (
        <div className="ko-stepladder-elim" aria-label={t("ui.tournament.bracket_elim", "Eliminierung")}>
          <p className="ko-bracket-tier-label text-label uppercase text-subtle mb-3 w-full text-center">
            {t("ui.tournament.bracket_elim", "Eliminierung")}
          </p>
          <ElimCombinedCard
            rounds={elimMatches}
            focusKey={focusKey}
            onPlayerClick={onPlayerClick}
            t={t}
          />
        </div>
      ) : null}

      <div
        className="ko-stepladder-ascent"
        aria-label={t("ui.tournament.bracket_stepladder", "Stepladder")}
      >
        {ascent.map((match, i) => (
          <div
            key={match.key}
            className="ko-stepladder-step"
            style={{ ["--step" as string]: i }}
          >
            <p className="ko-bracket-tier-label text-label uppercase text-subtle mb-2 text-center">
              {match.phase === "final"
                ? t("ui.tournament.bracket_final", "Finale")
                : match.label || match.key}
            </p>
            <PairMatchCard
              match={match}
              focusKey={focusKey}
              emphasize={match.phase === "final"}
              onPlayerClick={onPlayerClick}
              t={t}
              showHdcScores
            />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Prefer nested ELIM.rounds[]; fall back to top-level ELIM1/ELIM2 matches. */
function expandElimRounds(elimMatches: KoBracketMatch[]): KoBracketMatch[] {
  const out: KoBracketMatch[] = [];
  for (const m of elimMatches) {
    if (m.rounds && m.rounds.length > 0) {
      out.push(
        ...m.rounds.map((r) => ({
          ...r,
          decision_basis: r.decision_basis ?? m.decision_basis,
          side_a: r.side_a ?? { name: "—", id: "", games_won: 0 },
          side_b: r.side_b ?? { name: "—", id: "", games_won: 0 },
        })),
      );
    } else if (!/^ELIM$/i.test(m.key) || (m.field && m.field.length > 0)) {
      out.push(m);
    }
  }
  return out;
}

/** Both elim games in one box; 6. Platz then 5. Platz marked on eliminated players. */
function ElimCombinedCard({
  rounds,
  focusKey,
  onPlayerClick,
  t,
}: {
  rounds: KoBracketMatch[];
  focusKey: string;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const hdc = rounds.some((r) => r.decision_basis === "handicap") || rounds.every((r) => !r.decision_basis);

  return (
    <article
      className="ko-bracket-match ko-bracket-match--field ko-bracket-match--elim-combined rounded-sm border border-border bg-surface-raised shadow-1"
      data-phase="elim"
    >
      <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <span className="font-mono text-caption font-semibold uppercase tracking-wide text-muted">
          {t("ui.tournament.bracket_elim", "Eliminierung")}
        </span>
        <span className="text-caption text-subtle">
          {hdc
            ? t("ui.tournament.incl_hdc_score", "inkl. HDC")
            : t("ui.tournament.single_game_match", "1 Spiel")}
        </span>
      </header>
      {rounds.map((match, idx) => {
        const field = [...(match.field ?? [])].sort((a, b) => (b.total ?? 0) - (a.total ?? 0));
        const roundLabel =
          match.label ||
          `${t("ui.tournament.elim_game_n", "Spiel")} ${idx + 1}`;
        return (
          <div key={match.key} className={idx > 0 ? "border-t border-border" : undefined} data-match-key={match.key}>
            <p className="px-3 pt-2 pb-1 text-caption font-medium uppercase tracking-wide text-subtle">
              {roundLabel}
            </p>
            <div className="divide-y divide-border">
              {field.map((player) => (
                <ElimPlayerRow
                  key={`${match.key}-${player.name}`}
                  player={player}
                  focusKey={focusKey}
                  onPlayerClick={onPlayerClick}
                  t={t}
                />
              ))}
            </div>
          </div>
        );
      })}
    </article>
  );
}

function ElimPlayerRow({
  player,
  focusKey,
  onPlayerClick,
  t,
}: {
  player: KoBracketFieldPlayer;
  focusKey: string;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
}) {
  const name = player.name ?? "—";
  const noShow = isNoShowName(name);
  const isFocus = Boolean(focusKey && normalizeKoName(name) === focusKey);
  const placeSuffix =
    player.eliminated && player.place
      ? ` – ${player.place}. ${t("ui.tournament.place_suffix", "Platz")}`
      : "";

  const inner = (
    <>
      <span
        className={
          "min-w-0 flex-1 truncate " +
          (player.advances ? "font-semibold text-foreground " : "font-medium text-foreground ") +
          (player.eliminated ? "opacity-80 " : "") +
          (isFocus ? "underline decoration-accent/50 " : "")
        }
      >
        {name}
        {placeSuffix ? <span className="text-muted font-normal">{placeSuffix}</span> : null}
      </span>
      <span className="font-mono text-small tabular-nums font-semibold text-foreground">
        {player.total ?? player.games?.[0] ?? "—"}
      </span>
      <OutcomeMark
        kind={player.advances ? "advance" : player.eliminated ? "out" : null}
        advanceLabel={t("ui.tournament.advances", "Weiter")}
        outLabel={t("ui.tournament.eliminated", "Ausgeschieden")}
      />
    </>
  );

  const className =
    "flex items-center gap-2 px-3 py-2 text-small " +
    (player.highlight ? "bg-accent-tint/40 " : "") +
    (onPlayerClick && !noShow ? "cursor-pointer hover:bg-surface-subtle " : "");

  if (onPlayerClick && !noShow) {
    return (
      <button type="button" className={className + "w-full text-left"} onClick={() => onPlayerClick(name)}>
        {inner}
      </button>
    );
  }
  return <div className={className}>{inner}</div>;
}

function PairMatchCard({
  match,
  focusKey,
  emphasize,
  onPlayerClick,
  t,
  showHdcScores = false,
}: {
  match: KoBracketMatch;
  focusKey: string;
  emphasize?: boolean;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
  showHdcScores?: boolean;
}) {
  const pinLine = formatPinGamesLine(match.pin_games);
  const isFinal = match.key === "F" || match.phase === "final";
  const hdc =
    showHdcScores ||
    match.decision_basis === "handicap" ||
    match.series_mode === "single_game" ||
    isFinal;
  const singleGame = match.series_mode === "single_game" || match.phase === "stepladder";
  const seriesLabel = (() => {
    if (match.walkover) return null;
    if (isFinal && !singleGame) {
      const a = match.side_a?.games_won ?? 0;
      const b = match.side_b?.games_won ?? 0;
      if (a === 0 && b === 0) return null;
      const boldA = match.winner === "a";
      const boldB = match.winner === "b";
      return `${boldA ? `**${a}**` : a}:${boldB ? `**${b}**` : b}`;
    }
    return null;
  })();

  return (
    <article
      className={
        "ko-bracket-match rounded-sm border border-border bg-surface-raised shadow-1 " +
        (emphasize ? "ko-bracket-match--final " : "")
      }
      data-phase={match.phase}
      data-match-key={match.key}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <span className="font-mono text-caption font-semibold uppercase tracking-wide text-muted">
          {match.label || match.key}
        </span>
        <span className="flex items-center gap-1.5">
          {hdc ? (
            <span className="text-caption text-subtle">
              {isFinal && !singleGame
                ? t("ui.tournament.bo3_incl_hdc", "Best-of-3 inkl. HDC")
                : t("ui.tournament.incl_hdc_score", "inkl. HDC")}
            </span>
          ) : null}
          {isFinal && match.winner ? (
            <Trophy size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden />
          ) : null}
        </span>
      </header>
      <div className="divide-y divide-border">
        <PairPlayerRow
          side={match.side_a}
          match={match}
          sideId="a"
          focusKey={focusKey}
          pinIndex={0}
          onPlayerClick={onPlayerClick}
          t={t}
        />
        <PairPlayerRow
          side={match.side_b}
          match={match}
          sideId="b"
          focusKey={focusKey}
          pinIndex={1}
          onPlayerClick={onPlayerClick}
          t={t}
        />
      </div>
      <footer className="space-y-0.5 border-t border-border bg-surface-subtle/60 px-3 py-2">
        {pinLine && !match.walkover ? (
          <p className="font-mono text-caption text-muted tabular-nums">{pinLine}</p>
        ) : null}
        {seriesLabel ? (
          <p className="font-mono text-small font-medium tabular-nums text-foreground">
            {renderSeriesParts(seriesLabel).map((part, i) =>
              part.bold ? (
                <strong key={i} className="font-semibold">
                  {part.text}
                </strong>
              ) : (
                <span key={i}>{part.text}</span>
              ),
            )}
          </p>
        ) : null}
        {match.walkover ? (
          <span className="inline-block rounded-xs border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-caption font-medium text-warning">
            {t("ui.tournament.walkover", "Walkover")}
          </span>
        ) : null}
      </footer>
    </article>
  );
}

function PairPlayerRow({
  side,
  match,
  sideId,
  focusKey,
  pinIndex,
  onPlayerClick,
  t,
}: {
  side: KoBracketMatch["side_a"];
  match: KoBracketMatch;
  sideId: "a" | "b";
  focusKey: string;
  pinIndex: 0 | 1;
  onPlayerClick?: (player: string) => void;
  t?: (key: string, fallback?: string) => string;
}) {
  const name = side?.name ?? "—";
  const noShow = isNoShowName(name);
  const won = match.winner === sideId;
  const isFocus = Boolean(focusKey && sideKey({ name }) === focusKey);
  const gameScores =
    match.pin_games?.map((g) => g[pinIndex]).filter((n) => n != null && !Number.isNaN(n)) ?? [];
  const scoreText = gameScores.length ? gameScores.join(" · ") : null;
  const place =
    !won && match.winner
      ? (side?.place ?? match.loser_place)
      : undefined;
  const placeSuffix =
    place
      ? ` – ${place}. ${t?.("ui.tournament.place_suffix", "Platz") ?? "Platz"}`
      : "";

  const inner = (
    <>
      <span
        className={
          "min-w-0 flex-1 truncate " +
          (won ? "font-semibold text-foreground " : "font-medium text-foreground ") +
          (isFocus ? "underline decoration-accent/50 " : "")
        }
      >
        {name}
        {placeSuffix ? <span className="text-muted font-normal">{placeSuffix}</span> : null}
      </span>
      {scoreText ? (
        <span className={"font-mono text-caption tabular-nums " + (won ? "font-semibold" : "text-muted")}>
          {scoreText}
        </span>
      ) : null}
      <OutcomeMark
        kind={match.winner ? (won ? "advance" : "out") : null}
        advanceLabel={t?.("ui.tournament.advances", "Weiter") ?? "Weiter"}
        outLabel={t?.("ui.tournament.eliminated", "Ausgeschieden") ?? "Ausgeschieden"}
      />
    </>
  );

  const className =
    "flex items-center gap-2 px-3 py-2 text-small " +
    (side?.highlight ? "bg-accent-tint/40 " : "") +
    (onPlayerClick && !noShow ? "cursor-pointer hover:bg-surface-subtle " : "");

  if (onPlayerClick && !noShow) {
    return (
      <button type="button" className={className + "w-full text-left"} onClick={() => onPlayerClick(name)}>
        {inner}
      </button>
    );
  }
  return <div className={className}>{inner}</div>;
}

/** Fixed-width ✓ / ✕ so advancing and eliminated rows share the same trailing column. */
function OutcomeMark({
  kind,
  advanceLabel,
  outLabel,
}: {
  kind: "advance" | "out" | null;
  advanceLabel: string;
  outLabel: string;
}) {
  if (kind === "advance") {
    return (
      <span
        className="inline-flex w-3.5 shrink-0 justify-center text-caption font-semibold text-success-fg"
        aria-label={advanceLabel}
      >
        ✓
      </span>
    );
  }
  if (kind === "out") {
    return (
      <span
        className="inline-flex w-3.5 shrink-0 justify-center text-caption font-semibold text-danger-fg"
        aria-label={outLabel}
      >
        ✕
      </span>
    );
  }
  return <span className="inline-flex w-3.5 shrink-0" aria-hidden />;
}
