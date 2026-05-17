import type { DataTableOptions } from "../../lib/datatable/types";

/** Leaderboard: plain #, row wash from cut metadata (inside / on cut). */
export const tournamentLeaderboardTableOptions: DataTableOptions = {
  disablePositionCircle: true,
  tournamentCutRowStyling: true,
  enableSpecialRowStyling: false,
  tooltips: true,
  disableTeamColorUpdate: true,
  stripedRows: false,
};

/** Round / player tables: plain rank, no league-style team row wash. */
export const tournamentResultsTableOptions: DataTableOptions = {
  disablePositionCircle: true,
  enableSpecialRowStyling: false,
  tooltips: true,
  disableTeamColorUpdate: true,
};
