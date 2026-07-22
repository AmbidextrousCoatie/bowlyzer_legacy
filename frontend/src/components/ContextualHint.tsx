import { X } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { dismissHint, isHintDismissed } from "../lib/contextualHintStorage";

export { dismissHint, isHintDismissed } from "../lib/contextualHintStorage";

type ContextualHintProps = {
  hintId: string;
  children: ReactNode;
  className?: string;
  dismissLabel?: string;
};

/**
 * Dismissible first-visit banner. Persists dismissal in localStorage per hintId.
 */
export function ContextualHint({
  hintId,
  children,
  className,
  dismissLabel = "Verstanden",
}: ContextualHintProps) {
  const [visible, setVisible] = useState(() => !isHintDismissed(hintId));

  const dismiss = useCallback(() => {
    dismissHint(hintId);
    setVisible(false);
  }, [hintId]);

  if (!visible) return null;

  return (
    <div
      role="note"
      className={
        "flex items-start gap-3 rounded-sm border border-info/30 bg-accent-tint px-4 py-3 text-small text-foreground " +
        (className ?? "")
      }
    >
      <div className="min-w-0 flex-1 leading-relaxed">{children}</div>
      <button
        type="button"
        onClick={dismiss}
        className="inline-flex shrink-0 items-center gap-1 rounded-sm px-2 py-1 text-caption font-medium text-accent hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        aria-label={dismissLabel}
      >
        <span className="hidden sm:inline">{dismissLabel}</span>
        <X size={14} strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  );
}
