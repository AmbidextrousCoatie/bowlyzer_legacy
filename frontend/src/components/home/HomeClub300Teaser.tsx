import { Link } from "react-router-dom";
import { Star } from "lucide-react";
import { useClub300Games } from "../../hooks/usePlayer";
import { useAppLink } from "../../hooks/useAppLink";
import { buildUrl } from "../../lib/api";
import { HOME_SECTIONS } from "../../lib/homeContent";

export function HomeClub300Teaser() {
  const link = useAppLink();
  const gamesQuery = useClub300Games(null);
  const recent = (gamesQuery.data ?? []).slice(0, 2);

  return (
    <section className="py-10" aria-labelledby="home-club300-title">
      <div className="flex items-center gap-2 mb-2">
        <Star size={16} strokeWidth={1.75} className="text-warning" aria-hidden />
        <p className="text-label uppercase text-muted">{HOME_SECTIONS.club300}</p>
      </div>
      <h2 id="home-club300-title" className="text-h2 mb-2">
        Perfekte 300er
      </h2>
      <p className="text-body text-muted mb-4 max-w-[72ch]">{HOME_SECTIONS.club300Teaser}</p>

      {gamesQuery.isPending ? (
        <p className="text-small text-muted">Laden…</p>
      ) : recent.length === 0 ? (
        <p className="text-small text-muted">Noch keine 300er in der Datenquelle.</p>
      ) : (
        <ul className="divide-y divide-border rounded-sm border border-border bg-surface">
          {recent.map((game) => {
            const href = game.player_name
              ? buildUrl("/spieler", {
                  player_name: game.player_name,
                  ...(game.player_id ? { player_id: game.player_id } : {}),
                })
              : "/club-300";
            return (
              <li key={`${game.player_name}-${game.date}-${game.competition}`}>
                <Link
                  to={link(href)}
                  className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-small hover:bg-surface-subtle"
                >
                  <span className="font-medium text-foreground">{game.player_name ?? "—"}</span>
                  <span className="font-mono tabular-nums text-accent">300</span>
                  <span className="w-full text-muted">
                    {[game.competition, game.season, game.date].filter(Boolean).join(" · ")}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      <Link
        to={link("/club-300")}
        className="mt-4 inline-flex min-h-[44px] items-center text-body font-medium text-accent hover:text-accent-hover hover:underline"
      >
        Alle 300er ansehen
      </Link>
    </section>
  );
}
