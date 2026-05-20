import { Link } from "react-router-dom";
import type { ClubHistoryRow } from "../../../lib/playerClubHistory";
import { buildUrl } from "../../../lib/api";

type Props = {
  rows: ClubHistoryRow[];
  t: (key: string, fallback?: string) => string;
};

export function ClubAffiliationHistory({ rows, t }: Props) {
  if (rows.length === 0) return null;

  return (
    <section className="mt-12 border-t border-border pt-10">
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">
          {t("ui.player.club_history_eyebrow", "Historie")}
        </p>
        <h2 className="text-h2">
          {t("ui.player.club_history_title", "Clubzugehörigkeit")}
        </h2>
      </div>

      <div className="overflow-x-auto rounded-sm border border-border">
        <table className="w-full min-w-[280px] border-collapse text-left text-small">
          <thead>
            <tr className="border-b border-border bg-surface-subtle">
              <th scope="col" className="px-4 py-2.5 font-medium text-foreground lg:px-5">
                {t("ui.player.club", "Verein")}
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium text-foreground lg:px-5">
                {t("ui.player.club_history_period", "Zugehörigkeit")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border bg-surface">
            {rows.map((row, idx) => (
              <tr key={`${row.club}-${row.period}-${idx}`}>
                <td className="px-4 py-3 text-foreground lg:px-5">
                  <Link
                    to={buildUrl("/club", { club: row.club })}
                    className="font-medium text-accent hover:text-accent-hover hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    {row.club}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted tabular-nums lg:px-5">{row.period}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
