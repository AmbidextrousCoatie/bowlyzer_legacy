import type { DataTableOptions } from "../../lib/datatable/types";

/** Shared styling for league standings and matchday tables (# clip, subtle col-group stripes). */
export const rankedTeamTableOptions: DataTableOptions = {
  disablePositionCircle: false,
  enableSpecialRowStyling: true,
  tooltips: true,
  stripedRows: false,
  stripedColumnGroups: true,
  columnGroupStripeVariant: "league",
};

export const teamVsTeamTableOptions: DataTableOptions = {
  ...rankedTeamTableOptions,
  enableHeatMap: true,
  teamField: "team",
  /** Matrix seeds team-keyed colors in TeamVsTeamMatrix; avoid row-order overwrite. */
  disableTeamColorUpdate: true,
};
