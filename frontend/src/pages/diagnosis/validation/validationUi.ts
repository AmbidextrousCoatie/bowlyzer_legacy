export const STATUS_CLASS: Record<string, string> = {
  perfect: "text-emerald-700 dark:text-emerald-400",
  corrected: "text-emerald-700 dark:text-emerald-400",
  green: "text-emerald-700 dark:text-emerald-400",
  yellow: "text-amber-700 dark:text-amber-400",
  red: "text-rose-700 dark:text-rose-400",
  skipped: "text-muted",
};

export const GREEN_STATUSES = new Set(["perfect", "corrected", "green"]);

export const LEAGUE_STATUS_KEYS = [
  "perfect",
  "corrected",
  "yellow",
  "red",
  "skipped",
] as const;

export const TOURNAMENT_STATUS_KEYS = ["green", "yellow", "red"] as const;
