import { Link } from "react-router-dom";
import type { ClubMatrixRow } from "../../../hooks/useLeague";
import {
  formatMatrixCellItem,
  normalizeClubMatrixCell,
  type ClubMatrixSeasonCell,
} from "../../../lib/clubMatrixCell";
import { leagueTeamSeasonPath } from "../../../lib/diagnosisLinks";
import {
  clubTeamFullName,
  getClubTeamColor,
  splitClubAndTeamNumber,
  teamDisplayLabel,
} from "../../../lib/teamUtils";
import { buildTeamNavPath } from "../../../lib/teamNavigation";
import { ClubPositionHistoryChart } from "./ClubPositionHistoryChart";

type Props = {
  club: string;
  teams: string[];
  matrixRows: ClubMatrixRow[];
  seasons: string[];
  matrixLoading?: boolean;
  matrixError?: boolean;
  leagueLongNames: Record<string, string>;
  t: (key: string, fallback?: string) => string;
};

function latestSeasonWithLeague(
  row: ClubMatrixRow,
  seasons: string[],
): { season: string; cell: ClubMatrixSeasonCell } | null {
  for (let i = seasons.length - 1; i >= 0; i--) {
    const s = seasons[i];
    const cell = row.seasons[s];
    const { label } = normalizeClubMatrixCell(cell);
    if (label.trim()) return { season: s, cell };
  }
  return null;
}

function countDistinctLeagues(rows: ClubMatrixRow[]): number {
  const leagues = new Set<string>();
  for (const row of rows) {
    for (const cell of Object.values(row.seasons)) {
      const { items } = normalizeClubMatrixCell(cell);
      for (const item of items) {
        if (item.league) leagues.add(item.league);
      }
    }
  }
  return leagues.size;
}

export function ClubOverview({
  club,
  teams,
  matrixRows,
  seasons,
  matrixLoading = false,
  matrixError = false,
  leagueLongNames,
  t,
}: Props) {
  const teamEntries = teams.map((fullName) => {
    const { teamNumber } = splitClubAndTeamNumber(fullName);
    const matrixRow = matrixRows.find(
      (r) =>
        r.team_number === teamNumber ||
        (!teamNumber && r.team_number === "base"),
    );
    const latest = matrixRow ? latestSeasonWithLeague(matrixRow, seasons) : null;
    const latestLeague = latest ? normalizeClubMatrixCell(latest.cell).label : null;
    const seasonCount = matrixRow
      ? Object.values(matrixRow.seasons).filter((c) => normalizeClubMatrixCell(c).label.trim())
          .length
      : 0;
    const color = getClubTeamColor(fullName);
    return { fullName, latest, latestLeague, seasonCount, color };
  });

  const distinctLeagues = countDistinctLeagues(matrixRows);

  return (
    <div className="space-y-8">
      <section className="rounded-sm border border-border bg-surface">
        <header className="border-b border-border px-4 py-3 lg:px-5">
          <h2 className="text-h3">
            {t("ui.team.club_position_history", "Platzierungsverlauf aller Teams des Clubs")}
          </h2>
          <p className="text-small text-muted mt-1">
            {t(
              "ui.team.club_position_history_hint",
              "Wie sie im Laufe der Zeit abgeschintten haben",
            )}
          </p>
        </header>
        {matrixLoading ? (
          <p className="text-small text-muted p-4">
            {t("ui.team.club_matrix_loading", "Platzierungsverlauf wird geladen…")}
          </p>
        ) : matrixError ? (
          <p className="text-small text-muted p-4">
            {t(
              "ui.team.club_matrix_error",
              "Platzierungsverlauf konnte nicht geladen werden.",
            )}
          </p>
        ) : (
          <ClubPositionHistoryChart
            teams={teams}
            matrixRows={matrixRows}
            matrixSeasons={seasons}
            t={t}
          />
        )}
      </section>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label={t("ui.team.club_teams_count", "Mannschaften")}
          value={String(teams.length)}
        />
        <StatTile
          label={t("ui.team.club_seasons_span", "Saisons in Daten")}
          value={String(seasons.length)}
        />
        <StatTile
          label={t("ui.team.club_leagues_count", "Ligen (gesamt)")}
          value={String(distinctLeagues)}
        />
      </div>

      <section className="rounded-sm border border-border bg-surface">
        <header className="border-b border-border px-4 py-3 lg:px-5">
          <h2 className="text-h3">{t("ui.team.club_teams_heading", "Mannschaften des Clubs")}</h2>
          <p className="text-small text-muted mt-1">
            {t(
              "ui.team.club_teams_hint",
              "Übersicht — wähle eine Mannschaft für die Detailanalyse.",
            )}
          </p>
        </header>
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 lg:p-5">
          {teamEntries.map(({ fullName, latest, latestLeague, seasonCount, color }) => (
            <Link
              key={fullName}
              to={buildTeamNavPath({ club, team: fullName })}
              className="group rounded-sm border border-border border-l-4 bg-surface-subtle p-4 transition-colors hover:border-accent hover:bg-surface"
              style={{ borderLeftColor: color }}
            >
              <p className="text-label" style={{ color }}>
                {t("team", "Mannschaft")} {teamDisplayLabel(fullName)}
              </p>
              <p className="text-h3 mt-1 truncate text-foreground" title={fullName}>
                {fullName}
              </p>
              <dl className="mt-3 space-y-1 text-small">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">{t("ui.team.latest_season", "Letzte Saison")}</dt>
                  <dd className="font-mono tabular-nums">{latest?.season ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">{t("league", "Liga")}</dt>
                  <dd className="truncate text-right" title={latestLeague ?? undefined}>
                    {latestLeague ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted">{t("ui.team.seasons_with_data", "Saisons mit Daten")}</dt>
                  <dd className="font-mono tabular-nums">{seasonCount}</dd>
                </div>
              </dl>
              <p className="text-label text-accent mt-3 group-hover:underline">
                {t("ui.team.open_team_analysis", "Analyse öffnen →")}
              </p>
            </Link>
          ))}
        </div>
      </section>

      {matrixRows.length > 0 && seasons.length > 0 && (
        <section className="rounded-sm border border-border bg-surface">
          <header className="border-b border-border px-4 py-3 lg:px-5">
            <h2 className="text-h3">
              {t("ui.team.club_matrix_compact", "Liga-Zuordnung (Übersicht)")}
            </h2>
          </header>
          <div className="overflow-x-auto p-4 lg:p-5">
            <table className="w-full min-w-[480px] border-collapse text-small">
              <thead>
                <tr>
                  <th className="border border-border bg-surface-subtle px-3 py-2 text-left font-semibold">
                    {t("team", "Mannschaft")}
                  </th>
                  {seasons.map((s) => (
                    <th
                      key={s}
                      className="border border-border bg-surface-subtle px-3 py-2 text-center font-semibold"
                    >
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrixRows.map((row) => {
                  const fullName = clubTeamFullName(club, row.team_number);
                  const rowColor = getClubTeamColor(fullName);
                  return (
                    <tr key={row.team_number}>
                      <td
                        className="border border-border border-l-[3px] px-3 py-2 font-medium"
                        style={{ borderLeftColor: rowColor }}
                      >
                        {row.team_number === "base"
                          ? t("ui.diagnosis.team_base", "Basis")
                          : row.team_number}
                      </td>
                      {seasons.map((s) => {
                        const { items } = normalizeClubMatrixCell(row.seasons[s]);
                        return (
                          <td
                            key={s}
                            className="border border-border px-3 py-2 text-center align-top"
                          >
                            {items.length > 0 ? (
                              <div className="flex flex-col gap-1">
                                {items.map((item) => (
                                  <Link
                                    key={`${s}-${item.league}`}
                                    to={leagueTeamSeasonPath(
                                      s,
                                      item.league,
                                      fullName,
                                      leagueLongNames,
                                    )}
                                    className="text-accent hover:underline"
                                    title={t("ui.team.open_liga", "Liga · Saison · Team öffnen")}
                                  >
                                    {formatMatrixCellItem(item)}
                                  </Link>
                                ))}
                              </div>
                            ) : (
                              "—"
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-border bg-surface px-4 py-3">
      <p className="text-label text-muted">{label}</p>
      <p className="text-h2 font-mono tabular-nums mt-1">{value}</p>
    </div>
  );
}
