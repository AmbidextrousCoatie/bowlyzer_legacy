import type { OptionItem } from "../types";

type Props = {
  database: string;
  league: string;
  season: string;
  week: string;
  team: string;
  leagues: OptionItem[];
  seasons: OptionItem[];
  weeks: OptionItem[];
  teams: OptionItem[];
  coreLoading: boolean;
  matchdayLoading: boolean;
  teamWeekLoading: boolean;
  onDatabaseChange: (v: string) => void;
  onLeagueChange: (v: string) => void;
  onSeasonChange: (v: string) => void;
  onWeekChange: (v: string) => void;
  onTeamChange: (v: string) => void;
  onRefreshCore: () => void;
  onRefreshMatchday: () => void;
  onRefreshTeamWeek: () => void;
};

export default function FilterBar(props: Props) {
  const {
    database,
    league,
    season,
    week,
    team,
    leagues,
    seasons,
    weeks,
    teams,
    coreLoading,
    matchdayLoading,
    teamWeekLoading,
    onDatabaseChange,
    onLeagueChange,
    onSeasonChange,
    onWeekChange,
    onTeamChange,
    onRefreshCore,
    onRefreshMatchday,
    onRefreshTeamWeek,
  } = props;

  return (
    <section className="panel">
      <h2>Filters</h2>
      <div className="grid">
        <label>
          Database
          <input value={database} onChange={(e) => onDatabaseChange(e.target.value)} placeholder="optional" />
        </label>
        <label>
          League
          <select value={league} onChange={(e) => onLeagueChange(e.target.value)}>
            <option value="">Select...</option>
            {leagues.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Season
          <select value={season} onChange={(e) => onSeasonChange(e.target.value)}>
            <option value="">Select...</option>
            {seasons.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Week
          <select value={week} onChange={(e) => onWeekChange(e.target.value)}>
            <option value="">Optional...</option>
            {weeks.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Team
          <select value={team} onChange={(e) => onTeamChange(e.target.value)}>
            <option value="">Optional...</option>
            {teams.map((i) => (
              <option key={i.value} value={i.value}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="actionsRow">
        <button onClick={onRefreshCore} disabled={!league || !season || coreLoading}>
          {coreLoading ? "Refreshing..." : "Refresh Core"}
        </button>
        <button onClick={onRefreshMatchday} disabled={!league || !season || !week || matchdayLoading}>
          {matchdayLoading ? "Refreshing..." : "Refresh Matchday"}
        </button>
        <button onClick={onRefreshTeamWeek} disabled={!league || !season || !week || !team || teamWeekLoading}>
          {teamWeekLoading ? "Refreshing..." : "Refresh Team Week"}
        </button>
      </div>
    </section>
  );
}
