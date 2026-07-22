import { Link } from "react-router-dom";
import type { HomeExplainerBlock } from "../../lib/homeContent";
import { HOME_EXPLAINERS } from "../../lib/homeContent";
import { useAppLink } from "../../hooks/useAppLink";
import { HOME_BLOCK_STACK, HomeSection } from "./HomeSection";

export function HomeExplainerSections() {
  return (
    <div className={HOME_BLOCK_STACK}>
      {HOME_EXPLAINERS.map((block) => (
        <HomeExplainerBlock key={block.id} block={block} />
      ))}
    </div>
  );
}

function HomeExplainerBlock({ block }: { block: HomeExplainerBlock }) {
  const link = useAppLink();

  return (
    <HomeSection
      eyebrow={block.eyebrow}
      title={block.title}
      titleId={`home-explainer-${block.id}`}
    >
      <p className="text-body text-muted max-w-[72ch] leading-relaxed">{block.body}</p>
      {block.bullets?.length ? (
        <ul className="mt-4 list-disc space-y-2 pl-5 text-body text-muted">
          {block.bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      ) : null}
      {block.cta ? (
        <Link
          to={link(block.cta.to)}
          className="mt-5 inline-flex min-h-[44px] items-center text-body font-medium text-accent hover:text-accent-hover hover:underline"
        >
          {block.cta.label}
        </Link>
      ) : null}
    </HomeSection>
  );
}
