import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { HOME_ENTITY_MAP } from "../../lib/homeContent";
import { useAppLink } from "../../hooks/useAppLink";
import {
  HOME_TOPIC_PALETTE,
  homePaletteColor,
  homePaletteStyles,
} from "../../lib/homePalette";
import { HOME_BLOCK_STACK, HomeSection } from "./HomeSection";

export function HomeEntityMap() {
  const link = useAppLink();

  return (
    <div className={HOME_BLOCK_STACK}>
      {HOME_ENTITY_MAP.groups.map((group, groupIndex) => (
        <HomeSection
          key={group.id}
          eyebrow={group.eyebrow}
          title={group.title}
          titleId={groupIndex === 0 ? "home-entity-map-stats-title" : `home-entity-map-${group.id}-title`}
        >
          <ul className="grid gap-3 grid-cols-1 sm:grid-cols-3">
            {group.steps.map((step) => {
              const paletteIndex = HOME_TOPIC_PALETTE[step.paletteKey];
              return (
                <li key={step.label} className="min-w-0">
                  <Link
                    to={link(step.to)}
                    style={homePaletteStyles(paletteIndex)}
                    className="group flex h-full flex-col rounded-sm border border-border border-t-[3px] p-4 transition-colors hover:border-border-strong"
                  >
                    <span className="text-h3 mb-1" style={{ color: homePaletteColor(paletteIndex) }}>
                      {step.label}
                    </span>
                    <span className="text-small text-muted leading-relaxed">{step.description}</span>
                    <ArrowRight
                      size={16}
                      strokeWidth={1.75}
                      className="mt-auto pt-3 text-muted group-hover:text-accent"
                      aria-hidden
                    />
                  </Link>
                </li>
              );
            })}
          </ul>
        </HomeSection>
      ))}

      {HOME_ENTITY_MAP.footnote ? (
        <p className="text-small text-muted max-w-[72ch] leading-relaxed">
          {HOME_ENTITY_MAP.footnote}
        </p>
      ) : null}
    </div>
  );
}
