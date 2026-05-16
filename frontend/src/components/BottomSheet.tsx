import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";

type BottomSheetProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel?: string;
  children: React.ReactNode;
};

export function BottomSheet({ open, onClose, title, closeLabel = "Schließen", children }: BottomSheetProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const panel = "fixed inset-x-0 bottom-0 z-50 flex max-h-[min(85vh,640px)] flex-col rounded-t-md border border-border bg-surface shadow-[0_16px_32px_rgba(9,9,11,0.12)]";

  return (
    <div className="lg:hidden" role="presentation">
      <button
        type="button"
        aria-label={closeLabel}
        onClick={onClose}
        className="fixed inset-0 z-40 bg-zinc-950/40 backdrop-blur-sm"
      />
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className={panel}>
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h2 id={titleId} className="text-h3">
            {title}
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="inline-flex h-11 min-w-[5.5rem] items-center justify-center gap-1.5 rounded-sm border border-border bg-surface-subtle px-3 text-small font-medium text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <X size={18} strokeWidth={1.75} aria-hidden />
            {closeLabel}
          </button>
        </header>
        <div className="overflow-y-auto px-4 py-4">{children}</div>
      </div>
    </div>
  );
}
