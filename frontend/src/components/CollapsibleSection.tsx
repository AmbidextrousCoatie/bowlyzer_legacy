import { useId, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

type Props = {
  eyebrow?: string;
  title: string;
  children: ReactNode;
  /** When false, body is hidden on first render. */
  defaultOpen?: boolean;
  /** Optional stable id for aria-controls (auto-generated if omitted). */
  id?: string;
  expandLabel?: string;
  collapseLabel?: string;
};

/**
 * Page section with a header control to show or hide body content.
 * Matches Stadium section typography (eyebrow + h2).
 */
export function CollapsibleSection({
  eyebrow,
  title,
  children,
  defaultOpen = false,
  id: idProp,
  expandLabel = "Show section",
  collapseLabel = "Hide section",
}: Props) {
  const autoId = useId();
  const panelId = idProp ?? `collapsible-${autoId}`;
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="rounded-sm border border-border bg-surface">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-4 px-4 py-4 text-left transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="min-w-0">
          {eyebrow ? <p className="text-label uppercase text-muted mb-1.5">{eyebrow}</p> : null}
          <h2 className="text-h2">{title}</h2>
        </span>
        <ChevronDown
          size={20}
          strokeWidth={1.75}
          aria-hidden
          className={
            "mt-1 shrink-0 text-muted transition-transform duration-200 " +
            (open ? "rotate-180" : "")
          }
        />
        <span className="sr-only">{open ? collapseLabel : expandLabel}</span>
      </button>
      <div id={panelId} hidden={!open} className="border-t border-border px-4 pb-4 pt-4">
        {children}
      </div>
    </section>
  );
}
