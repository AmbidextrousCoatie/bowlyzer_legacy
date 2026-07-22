import type { CSSProperties, ReactNode } from "react";
import {
  type HomeTopicPaletteKey,
  homePaletteColorForTopic,
  topicTintStyle,
} from "../lib/homePalette";

type TopicPageHeaderProps = {
  topic: HomeTopicPaletteKey;
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  className?: string;
  hideOnLandscape?: boolean;
};

export function TopicPageHeader({
  topic,
  eyebrow,
  title,
  description,
  className = "mb-6 lg:mb-8",
  hideOnLandscape = false,
}: TopicPageHeaderProps) {
  const accentColor = homePaletteColorForTopic(topic);
  const bandStyle: CSSProperties = topicTintStyle(topic);

  return (
    <header
      className={
        hideOnLandscape ? `${className} max-lg:landscape:hidden` : className
      }
    >
      <div
        className="rounded-sm border border-border border-t-[3px] px-4 py-4 lg:px-5 lg:py-5"
        style={bandStyle}
      >
        <p className="text-label uppercase mb-2" style={{ color: accentColor }}>
          {eyebrow}
        </p>
        <h1 className="text-h1">{title}</h1>
        {description ? (
          <div className="text-body text-muted mt-2 max-w-[72ch] leading-relaxed">{description}</div>
        ) : null}
      </div>
    </header>
  );
}
