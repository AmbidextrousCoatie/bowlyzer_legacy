import type { DataTableOptions } from "../../lib/datatable/types";

/** Leaderboard: plain #, row wash from cut metadata (inside / on cut). */
export const tournamentLeaderboardTableOptions: DataTableOptions = {
  disablePositionCircle: true,
  tournamentCutRowStyling: true,
  enableSpecialRowStyling: false,
  tooltips: true,
  disableTeamColorUpdate: true,
  stripedRows: false,
  /** Backend sets stripedColGroups; league-style odd-group tint fights cut-row washes. */
  stripedColumnGroups: false,
  freezeColumnGroupCount: 1,
  boldColumnGroupIndexes: [1],
  resizableColumns: false,
};

/** Round / player tables: plain rank, no league-style team row wash. */
export const tournamentResultsTableOptions: DataTableOptions = {
  disablePositionCircle: true,
  enableSpecialRowStyling: false,
  tooltips: true,
  disableTeamColorUpdate: true,
};
