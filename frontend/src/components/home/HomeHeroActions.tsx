import { useNavigate } from "react-router-dom";
import type { CSSProperties, ReactNode } from "react";
import { ClubSearch } from "../ClubSearch";
import { ButtonLink } from "../Button";
import { PlayerSearch } from "../PlayerSearch";
import { useAppLink } from "../../hooks/useAppLink";
import { useClubMatrix } from "../../hooks/useLeague";
import { useMyClub } from "../../hooks/useMyClub";
import { type PlayerSearchEntry, usePlayerSearch } from "../../hooks/usePlayer";
import { HOME_QUICK_START } from "../../lib/homeContent";
import {
  HOME_TOPIC_PALETTE,
  type HomeTopicPaletteKey,
  homePaletteButtonStyleForTopic,
  homePaletteColor,
  homePaletteStyles,
} from "../../lib/homePalette";
import { HomeSection } from "./HomeSection";

type HomeHeroActionsProps = {
  myClubActive: boolean;
  resolvedClub: string;
};

export function HomeHeroActions({ myClubActive, resolvedClub }: HomeHeroActionsProps) {
  const navigate = useNavigate();
  const link = useAppLink();
  const { setMyClub, clearMyClub } = useMyClub();
  const clubsQuery = useClubMatrix(null, false);
  const playersQuery = usePlayerSearch(null);
  const clubs = clubsQuery.data?.clubs ?? [];

  function browseClub(club: string | null) {
    if (club) {
      navigate(link("/club", { club }));
    }
  }

  function selectMyClub(club: string | null) {
    setMyClub(club);
  }

  function selectPlayer(entry: PlayerSearchEntry | null) {
    if (!entry) return;
    navigate(
      link("/spieler", {
        player_name: entry.name,
        ...(entry.id ? { player_id: entry.id } : {}),
      }),
    );
  }

  return (
    <HomeSection
      eyebrow={HOME_QUICK_START.eyebrow}
      title={HOME_QUICK_START.title}
      titleId="home-quick-start-title"
    >
      {/* Order matches HOME_TOPIC_PALETTE slots 1–2, 6, 7 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <HeroActionCard
          title={HOME_QUICK_START.playerSearchCta}
          description={HOME_QUICK_START.playerSearchDescription}
          paletteKey="player"
        >
          <PlayerSearch
            value=""
            players={playersQuery.data ?? []}
            isLoading={playersQuery.isPending}
            placeholder="Name / EDV eingeben…"
            ariaLabel={HOME_QUICK_START.playerSearchCta}
            onSelect={selectPlayer}
          />
        </HeroActionCard>

        <HeroActionCard
          title={HOME_QUICK_START.clubSearchCta}
          description={HOME_QUICK_START.clubSearchDescription}
          paletteKey="club"
        >
          <ClubSearch
            value=""
            clubs={clubs}
            isLoading={clubsQuery.isPending}
            placeholder="Club suchen…"
            ariaLabel={HOME_QUICK_START.clubSearchCta}
            clearAriaLabel="Eingabe löschen"
            containerClassName="relative w-full"
            onSelect={browseClub}
          />
        </HeroActionCard>

        <HeroActionCard
          title={HOME_QUICK_START.myClubCta}
          description={HOME_QUICK_START.myClubDescription}
          paletteKey="myClub"
        >
          <ClubSearch
            value={resolvedClub}
            clubs={clubs}
            isLoading={clubsQuery.isPending}
            placeholder="Meinen Club wählen…"
            ariaLabel={HOME_QUICK_START.myClubCta}
            clearAriaLabel="Mein Club aufheben"
            containerClassName="relative w-full"
            onSelect={selectMyClub}
          />
          {myClubActive && resolvedClub ? (
            <button
              type="button"
              onClick={() => clearMyClub()}
              className="mt-3 inline-flex min-h-[44px] w-full items-center justify-center rounded-sm border border-border bg-surface/80 text-small font-medium text-muted hover:border-border-strong hover:bg-surface hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              Filter aufheben
            </button>
          ) : null}
        </HeroActionCard>

        <HeroActionCard
          title={HOME_QUICK_START.glossaryCta}
          description={HOME_QUICK_START.glossaryDescription}
          paletteKey="glossary"
        >
          <ButtonLink
            to={link("/glossar")}
            variant="palette"
            size="lg"
            className="w-full"
            style={homePaletteButtonStyleForTopic("glossary")}
          >
            {HOME_QUICK_START.glossaryButton}
          </ButtonLink>
        </HeroActionCard>
      </div>
    </HomeSection>
  );
}

function HeroActionCard({
  title,
  description,
  paletteKey,
  children,
}: {
  title: string;
  description: string;
  paletteKey: HomeTopicPaletteKey;
  children: ReactNode;
}) {
  const paletteIndex = HOME_TOPIC_PALETTE[paletteKey];
  const cardStyle: CSSProperties = homePaletteStyles(paletteIndex);
  const titleStyle: CSSProperties = { color: homePaletteColor(paletteIndex) };

  return (
    <div
      style={cardStyle}
      className="flex h-full flex-col rounded-sm border border-border border-t-[3px] p-4 lg:p-5"
    >
      <h3 className="text-h3 mb-1" style={titleStyle}>
        {title}
      </h3>
      <p className="text-small text-muted mb-4 leading-relaxed">{description}</p>
      <div className="mt-auto">{children}</div>
    </div>
  );
}
