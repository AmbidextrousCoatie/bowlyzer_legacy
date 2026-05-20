type Props = {
  className?: string;
  /** Pixel size (width and height). Default 28 — matches sidebar brand slot. */
  size?: number;
};

/** Bowl-A-Lyzer mark from `public/favicon.png`. */
export function AppLogo({ className = "", size = 28 }: Props) {
  return (
    <img
      src="/favicon.png"
      alt=""
      width={size}
      height={size}
      className={`shrink-0 rounded-xs object-cover ${className}`.trim()}
      decoding="async"
    />
  );
}
