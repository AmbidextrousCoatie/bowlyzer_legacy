import { HeartHandshake, X } from "lucide-react";
import { useMyClub } from "../hooks/useMyClub";
import { useTranslations } from "../hooks/useTranslations";
import { homePaletteColorForTopic, topicTintStyle } from "../lib/homePalette";

/**
 * Persistent “home club” ribbon — visible on every page while ``?myClub=`` is set.
 * Ticket-stub vibe: left accent rail, mono club name, clear affordance.
 */
export function MyClubBanner() {
  const { t } = useTranslations();
  const { active, resolvedClub, clearMyClub } = useMyClub();

  if (!active || !resolvedClub) return null;

  const myClubColor = homePaletteColorForTopic("myClub");
  const bannerStyle = {
    ...topicTintStyle("myClub"),
    backgroundColor: `${myClubColor}E6`,
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="border-b border-border backdrop-blur"
      style={bannerStyle}
    >
      <div className="mx-auto flex max-w-[1280px] items-stretch gap-0 px-4 lg:px-8">
        <span
          aria-hidden
          className="w-1 shrink-0 self-stretch"
          style={{ backgroundColor: myClubColor }}
        />
        <div className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pl-3 pr-1">
          <span
            className="grid size-8 shrink-0 place-items-center rounded-sm border border-border bg-surface"
            style={{ color: myClubColor }}
          >
            <HeartHandshake size={16} strokeWidth={1.75} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-label uppercase tracking-wide" style={{ color: myClubColor }}>
              {t("ui.my_club.selected_label", "Mein Club")}
            </p>
            <p className="truncate text-body font-semibold text-foreground">
              <span className="font-mono text-[0.95em]">{resolvedClub}</span>
            </p>
          </div>
          <p className="hidden shrink-0 text-small text-muted sm:block">
            {t("ui.my_club.filter_hint", "Liga & Turnier auf Club-Teilnahmen gefiltert")}
          </p>
          <button
            type="button"
            onClick={clearMyClub}
            aria-label={t("ui.my_club.clear", "Club-Auswahl aufheben")}
            title={t("ui.my_club.clear", "Club-Auswahl aufheben")}
            className="grid size-9 shrink-0 place-items-center rounded-sm text-muted hover:bg-surface hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <X size={16} strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
