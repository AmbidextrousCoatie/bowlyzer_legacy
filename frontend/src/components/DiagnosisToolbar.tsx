import type { ReactNode } from "react";

type DiagnosisToolbarProps = {
  children?: ReactNode;
};

/** Shared filter row for diagnosis pages (page-specific controls only). */
export function DiagnosisToolbar({ children }: DiagnosisToolbarProps) {
  return (
    <div className="rounded-sm border border-border bg-surface p-4 lg:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">{children}</div>
    </div>
  );
}
