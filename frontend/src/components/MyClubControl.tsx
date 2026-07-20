import { HeartHandshake } from "lucide-react";
import { useMyClub } from "../hooks/useMyClub";
import { useClubMatrix } from "../hooks/useLeague";
import { useTranslations } from "../hooks/useTranslations";
import { ClubSearch } from "./ClubSearch";

type MyClubControlProps = {
  collapsed: boolean;
  onExpand?: () => void;
};

/**
 * Sidebar “Mein Club” picker — fuzzy search over clubs from ``get_club_matrix``.
 * Selection writes ``?myClub=`` (global; not stripped by route sanitizer).
 */
export function MyClubControl({ collapsed, onExpand }: MyClubControlProps) {
  const { t } = useTranslations();
  const { myClub, active, resolvedClub, setMyClub } = useMyClub();
  const clubsQuery = useClubMatrix(null, false);

  const clubs = clubsQuery.data?.clubs ?? [];
  const displayValue = resolvedClub || myClub;

  if (collapsed) {
    return (
      <button
        type="button"
        aria-label={
          active
            ? t("ui.my_club.selected_aria", "Mein Club: {club}").replace("{club}", displayValue)
            : t("ui.my_club.pick", "Mein Club wählen")
        }
        title={active ? displayValue : t("ui.my_club.pick", "Mein Club wählen")}
        className={
          "grid h-9 w-full place-items-center rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
          (active
            ? "bg-accent-tint text-accent"
            : "text-muted hover:bg-surface-subtle hover:text-foreground")
        }
        onClick={() => onExpand?.()}
      >
        <HeartHandshake size={16} strokeWidth={1.75} aria-hidden />
      </button>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 px-0.5">
        <HeartHandshake
          size={12}
          strokeWidth={1.75}
          className={active ? "text-accent" : "text-muted"}
          aria-hidden
        />
        <span className="text-label uppercase text-subtle">
          {t("ui.my_club.label", "Mein Club")}
        </span>
      </div>
      <ClubSearch
        value={displayValue}
        clubs={clubs}
        isLoading={clubsQuery.isPending}
        placeholder={t("ui.my_club.search_placeholder", "Club suchen…")}
        ariaLabel={t("ui.my_club.label", "Mein Club")}
        clearAriaLabel={t("ui.my_club.clear", "Club-Auswahl aufheben")}
        containerClassName="relative w-full min-w-0"
        onSelect={(club) => setMyClub(club)}
      />
      {active ? (
        <p className="px-0.5 text-[11px] leading-snug text-muted">
          {t("ui.my_club.sidebar_hint", "Filter aktiv · bleibt in der URL")}
        </p>
      ) : null}
    </div>
  );
}
