import type { ReactNode } from "react";

export const HOME_BLOCK_STACK = "space-y-10";

type HomeSectionProps = {
  eyebrow?: string;
  title: string;
  titleId?: string;
  ariaLabel?: string;
  children: ReactNode;
  className?: string;
};

export function HomeSection({
  eyebrow,
  title,
  titleId,
  ariaLabel,
  children,
  className,
}: HomeSectionProps) {
  return (
    <section
      aria-labelledby={titleId}
      aria-label={ariaLabel}
      className={className}
    >
      {eyebrow ? <p className="text-label uppercase text-muted mb-2">{eyebrow}</p> : null}
      <h2 id={titleId} className="text-h2 mb-6">
        {title}
      </h2>
      {children}
    </section>
  );
}
