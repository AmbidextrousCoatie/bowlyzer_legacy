import { useMemo, type CSSProperties } from "react";
import { Trophy } from "lucide-react";
import type { KoBracketMatch, KoBracketPayload } from "../../../hooks/useTournament";
import {
  bracketLaneColors,
  focusPlayerWonMatch,
  formatPinGamesLine,
  formatSeriesScore,
  isNoShowName,
  matchIncludesFocus,
  matchOnFinalistPath,
  normalizeKoName,
  organizeBracketTiers,
  renderSeriesParts,
  sideKey,
  tierLabel,
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
  const colors = useMemo(() => bracketLaneColors(bracket), [bracket]);
  const focusKey = bracket.focus_player ? normalizeKoName(bracket.focus_player) : "";
  const scratchMode =
    bracket.ko_finale_series === "scratch_total_2g" ||
    matches.some((m) => m.scratch_series || m.scratch_final);

  const hasQf = tiers.qf.length > 0;
  const hasSf = tiers.sf.length > 0;
  const showInferredNote = tiers.sf.some((m) => m.inferred);

  return (
    <section className="ko-bracket-section" aria-label={t("ui.tournament.ko_bracket_title", "K.-o.-Schema")}>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.tournament.ko_bracket_title", "K.-o.-Schema")}
        </p>
        <h2 className="text-h2">{t("ui.tournament.ko_finale_heading", "Finale")}</h2>
        {!focusKey && bracket.finalist_a && bracket.finalist_b ? (
          <p className="mt-1 text-small text-muted">
            <span style={{ color: colors.a }} className="font-medium">
              {bracket.finalist_a}
            </span>
            {" · "}
            <span style={{ color: colors.b }} className="font-medium">
              {bracket.finalist_b}
            </span>
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
        <div
          className={
            "ko-bracket-grid " +
            (hasQf ? "ko-bracket-grid--full" : hasSf ? "ko-bracket-grid--sf" : "ko-bracket-grid--final")
          }
        >
          {hasQf ? (
            <BracketColumn
              tier="qf"
              matches={tiers.qf}
              bracket={bracket}
              colors={colors}
              focusKey={focusKey}
              scratchMode={scratchMode}
              onPlayerClick={onPlayerClick}
              t={t}
            />
          ) : null}
          {hasQf && hasSf ? <BracketWires variant="qf-sf" /> : null}
          {hasSf ? (
            <BracketColumn
              tier="sf"
              matches={tiers.sf}
              bracket={bracket}
              colors={colors}
              focusKey={focusKey}
              scratchMode={scratchMode}
              onPlayerClick={onPlayerClick}
              t={t}
            />
          ) : null}
          {(hasQf || hasSf) && tiers.final.length > 0 ? <BracketWires variant="sf-f" /> : null}
          {tiers.final.length > 0 ? (
            <BracketColumn
              tier="final"
              matches={tiers.final}
              bracket={bracket}
              colors={colors}
              focusKey={focusKey}
              scratchMode={scratchMode}
              onPlayerClick={onPlayerClick}
              t={t}
              emphasize
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}

type ColumnProps = {
  tier: "qf" | "sf" | "final";
  matches: KoBracketMatch[];
  bracket: KoBracketPayload;
  colors: ReturnType<typeof bracketLaneColors>;
  focusKey: string;
  scratchMode: boolean;
  emphasize?: boolean;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

function BracketColumn({
  tier,
  matches,
  bracket,
  colors,
  focusKey,
  scratchMode,
  emphasize,
  onPlayerClick,
  t,
}: ColumnProps) {
  return (
    <div className="ko-bracket-column flex min-h-[12rem] flex-col">
      <p className="ko-bracket-tier-label text-label uppercase text-subtle mb-3 text-center">
        {tierLabel(tier, t)}
      </p>
      <div className="flex flex-1 flex-col justify-around gap-4">
        {matches.map((match) => (
          <MatchCard
            key={match.key}
            match={match}
            bracket={bracket}
            colors={colors}
            focusKey={focusKey}
            scratchMode={scratchMode}
            emphasize={emphasize}
            onPlayerClick={onPlayerClick}
            t={t}
          />
        ))}
      </div>
    </div>
  );
}

type MatchCardProps = {
  match: NonNullable<KoBracketPayload["matches"]>[number];
  bracket: KoBracketPayload;
  colors: ReturnType<typeof bracketLaneColors>;
  focusKey: string;
  scratchMode: boolean;
  emphasize?: boolean;
  onPlayerClick?: (player: string) => void;
  t: (key: string, fallback?: string) => string;
};

function MatchCard({
  match,
  bracket,
  colors,
  focusKey,
  scratchMode,
  emphasize,
  onPlayerClick,
  t,
}: MatchCardProps) {
  const pathLane = matchOnFinalistPath(match, bracket);
  const borderStyle = resolveMatchBorder(match, colors, focusKey, pathLane);
  const pinLine = formatPinGamesLine(match.pin_games);
  const seriesRaw = formatSeriesScore(match, scratchMode);
  const isFinal = match.key === "F" || match.phase === "final";

  return (
    <article
      className={
        "ko-bracket-match rounded-sm border bg-surface-raised shadow-1 transition-colors " +
        (emphasize ? "ko-bracket-match--final " : "")
      }
      style={borderStyle}
      data-phase={match.phase}
      data-match-key={match.key}
    >
      <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <span className="font-mono text-caption font-semibold uppercase tracking-wide text-muted">
          {match.label || match.key}
        </span>
        {isFinal && match.winner ? (
          <Trophy size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden />
        ) : null}
      </header>
      <div className="divide-y divide-border">
        <PlayerRow
          side={match.side_a}
          match={match}
          sideId="a"
          colors={colors}
          focusKey={focusKey}
          pathLane={pathLane}
          isFinal={isFinal}
          onPlayerClick={onPlayerClick}
        />
        <PlayerRow
          side={match.side_b}
          match={match}
          sideId="b"
          colors={colors}
          focusKey={focusKey}
          pathLane={pathLane}
          isFinal={isFinal}
          onPlayerClick={onPlayerClick}
        />
      </div>
      <footer className="space-y-0.5 border-t border-border bg-surface-subtle/60 px-3 py-2">
        {pinLine && !match.walkover ? (
          <p className="font-mono text-caption text-muted tabular-nums">{pinLine}</p>
        ) : null}
        {seriesRaw ? (
          <p className="font-mono text-small font-medium tabular-nums text-foreground">
            {renderSeriesParts(seriesRaw).map((part, i) =>
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
        {match.scratch_series && !match.walkover ? (
          <p className="text-caption text-subtle">
            {match.scratch_final
              ? t("ui.tournament.scratch_total_title", "Scratch-Gesamt (2 Spiele)")
              : t("ui.tournament.scratch_total_match", "Scratch-Gesamt")}
          </p>
        ) : null}
      </footer>
    </article>
  );
}

type PlayerRowProps = {
  side: NonNullable<KoBracketPayload["matches"]>[number]["side_a"];
  match: NonNullable<KoBracketPayload["matches"]>[number];
  sideId: "a" | "b";
  colors: ReturnType<typeof bracketLaneColors>;
  focusKey: string;
  pathLane: ReturnType<typeof matchOnFinalistPath>;
  isFinal: boolean;
  onPlayerClick?: (player: string) => void;
};

function PlayerRow({
  side,
  match,
  sideId,
  colors,
  focusKey,
  pathLane,
  isFinal,
  onPlayerClick,
}: PlayerRowProps) {
  const name = side?.name ?? "—";
  const noShow = isNoShowName(name);
  const won = match.winner === sideId;
  const rowColor = resolveRowColor({
    sideId,
    name,
    colors,
    focusKey,
    pathLane,
    isFinal,
    match,
    highlight: Boolean(side.highlight),
  });

  const inner = (
    <>
      <span className="min-w-0 flex-1 truncate font-medium" style={rowColor ? { color: rowColor } : undefined}>
        {name}
      </span>
      {!noShow && !match.walkover && !match.scratch_series ? (
        <span
          className={
            "font-mono text-caption tabular-nums " + (won ? "font-semibold text-foreground" : "text-muted")
          }
        >
          {side?.games_won ?? 0}
        </span>
      ) : null}
      {won ? (
        <span className="text-caption font-semibold text-success-fg" aria-label="Winner">
          ✓
        </span>
      ) : null}
    </>
  );

  const className =
    "flex items-center gap-2 px-3 py-2 text-small " +
    (side.highlight ? "bg-accent-tint/50 " : "") +
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

function resolveMatchBorder(
  match: KoBracketMatch,
  colors: ReturnType<typeof bracketLaneColors>,
  focusKey: string,
  pathLane: ReturnType<typeof matchOnFinalistPath>,
): CSSProperties {
  if (focusKey) {
    if (!matchIncludesFocus(match, focusKey)) {
      return { borderColor: "var(--color-border)" };
    }
    if (focusPlayerWonMatch(match, focusKey)) {
      return {
        borderColor: colors.focus,
        boxShadow: `0 0 0 1px ${colors.focus}`,
      };
    }
    return { borderColor: "var(--color-border-strong)" };
  }

  if (pathLane === "both" && match.key === "F" && match.winner) {
    const c = match.winner === "a" ? colors.a : colors.b;
    return { borderColor: c, boxShadow: `0 0 0 1px ${c}` };
  }
  if (pathLane === "a") return { borderColor: colors.a, boxShadow: `0 0 0 1px ${colors.a}` };
  if (pathLane === "b") return { borderColor: colors.b, boxShadow: `0 0 0 1px ${colors.b}` };
  return { borderColor: "var(--color-border)" };
}

function resolveRowColor(args: {
  sideId: "a" | "b";
  name: string;
  colors: ReturnType<typeof bracketLaneColors>;
  focusKey: string;
  pathLane: ReturnType<typeof matchOnFinalistPath>;
  isFinal: boolean;
  match: NonNullable<KoBracketPayload["matches"]>[number];
  highlight: boolean;
}): string | undefined {
  const { sideId, name, colors, focusKey, pathLane, isFinal, match, highlight } = args;
  if (focusKey) {
    if (sideKey({ name }) === focusKey) return colors.focus;
    return undefined;
  }
  if (isFinal && match.winner) {
    return match.winner === sideId ? (sideId === "a" ? colors.a : colors.b) : undefined;
  }
  if (pathLane === "a" && sideId === "a") return colors.a;
  if (pathLane === "b" && sideId === "b") return colors.b;
  if (pathLane === "both") return sideId === "a" ? colors.a : colors.b;
  if (highlight) return colors.focus;
  return undefined;
}

function BracketWires({ variant }: { variant: "qf-sf" | "sf-f" }) {
  return (
    <div className="ko-bracket-wires hidden w-8 shrink-0 self-stretch md:flex" aria-hidden>
      <svg viewBox="0 0 32 200" className="h-full w-full text-border" preserveAspectRatio="none">
        {variant === "qf-sf" ? (
          <>
            <path
              d="M0 40 H16 V100 H0 M0 160 H16 V100"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <path d="M16 50 V150" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M16 100 H32" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </>
        ) : (
          <>
            <path d="M0 60 V140" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="M0 100 H32" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </>
        )}
      </svg>
    </div>
  );
}
