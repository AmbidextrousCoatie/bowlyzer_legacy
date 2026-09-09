import { Link } from "react-router-dom";
import { homePaletteColorForTopic } from "../../lib/homePalette";

type Props = {
  href?: string | null;
  title?: string;
  size?: "sm" | "md";
};

const accent = homePaletteColorForTopic("club300");

export function Club300Mark({ href, title, size = "sm" }: Props) {
  const compact = size === "sm";
  const className =
    "inline-flex shrink-0 items-center justify-center rounded-sm border font-mono font-semibold tabular-nums leading-none " +
    (compact ? "h-7 min-w-[2.5rem] px-1 text-[11px]" : "h-9 min-w-[3.25rem] px-1.5 text-small");
  const style = {
    color: accent,
    borderColor: accent,
    backgroundColor: `color-mix(in srgb, ${accent} 12%, transparent)`,
  };

  if (href) {
    return (
      <Link to={href} title={title} className={`${className} hover:brightness-110`} style={style}>
        300
      </Link>
    );
  }

  return (
    <span title={title} className={className} style={style}>
      300
    </span>
  );
}
