import { Link } from "react-router-dom";
import { HOME_HERO } from "../../lib/homeContent";
import { useAppLink } from "../../hooks/useAppLink";

type HomeHeroProps = {
  myClubActive: boolean;
  resolvedClub: string;
};

export function HomeHero({ myClubActive, resolvedClub }: HomeHeroProps) {
  const link = useAppLink();

  return (
    <header>
      <p className="text-label uppercase text-muted mb-2">{HOME_HERO.eyebrow}</p>
      <h1 className="text-h2 md:text-h1 text-foreground mb-4 max-w-[72ch] leading-snug">
        {myClubActive && resolvedClub ? HOME_HERO.welcomeClub(resolvedClub) : HOME_HERO.headline}
      </h1>
      <p className="text-body text-muted max-w-[72ch] leading-relaxed">
        {myClubActive && resolvedClub ? HOME_HERO.welcomeClubSub : HOME_HERO.subcopy}
      </p>
      <p className="mt-3 text-small text-muted max-w-[72ch]">
        Quelle:{" "}
        <a
          href={HOME_HERO.bbuUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent hover:text-accent-hover hover:underline"
        >
          {HOME_HERO.bbuLabel}
        </a>
        {" · "}
        <Link
          to={link("/einstieg")}
          className="text-accent hover:text-accent-hover hover:underline"
        >
          {HOME_HERO.einstiegLabel}
        </Link>
        {" · "}
        <Link
          to={link("/warum-bowlyzer")}
          className="text-accent hover:text-accent-hover hover:underline"
        >
          Warum Bowl-A-Lyzer?
        </Link>
      </p>
    </header>
  );
}
