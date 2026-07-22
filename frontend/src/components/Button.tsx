import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "palette";
export type ButtonSize = "sm" | "md" | "lg";

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 min-h-7 px-2.5 text-caption",
  md: "h-8 min-h-8 px-3 text-small",
  lg: "h-11 min-h-[44px] px-4 text-body",
};

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-accent-foreground hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  secondary:
    "border border-border bg-transparent text-foreground hover:border-border-strong hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  ghost:
    "text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  danger:
    "border border-danger/30 text-danger-fg hover:bg-danger/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  palette:
    "hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
};

const buttonClass = (variant: ButtonVariant, size: ButtonSize, className?: string) =>
  `inline-flex items-center justify-center rounded-sm font-medium transition-colors duration-120 ${BUTTON_SIZE[size]} ${BUTTON_VARIANT[variant]} ${className ?? ""}`;

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

type ButtonLinkProps = {
  to: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
  onClick?: () => void;
};

export function ButtonLink({
  to,
  variant = "primary",
  size = "md",
  className,
  style,
  children,
  onClick,
}: ButtonLinkProps) {
  return (
    <Link
      to={to}
      className={buttonClass(variant, size, className)}
      style={style}
      onClick={onClick}
    >
      {children}
    </Link>
  );
}
