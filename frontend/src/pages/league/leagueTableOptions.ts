import type { DataTableOptions } from "../../lib/datatable/types";

/** Shared styling for league standings and team-vs-team matrix (# clip, no zebra, no col-group stripe). */
export const rankedTeamTableOptions: DataTableOptions = {
  disablePositionCircle: false,
  enableSpecialRowStyling: true,
  tooltips: true,
  stripedRows: false,
  stripedColumnGroups: false,
};

export const teamVsTeamTableOptions: DataTableOptions = {
  ...rankedTeamTableOptions,
  enableHeatMap: true,
  teamField: "team",
};
