import type { ReactNode } from "react";
import { EChart } from "../../../lib/charts/EChart";
import { DataTable } from "../../../lib/datatable/DataTable";
import type { DataTableOptions, TableData } from "../../../lib/datatable/types";

export function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-4">
        <p className="text-label uppercase text-muted mb-1.5">{eyebrow}</p>
        <h2 className="text-h2">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function DataTableSection({
  query,
  options,
}: {
  query: {
    data: TableData | undefined;
    isPending: boolean;
    isError: boolean;
    error: Error | null;
  };
  options: DataTableOptions;
}) {
  if (query.isPending) {
    return <div className="h-48 rounded-sm border border-border bg-surface-subtle" />;
  }
  if (query.isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {query.error?.message ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!query.data?.columns || !query.data?.data) {
    return (
      <div className="rounded-sm border border-dashed border-border p-6 text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return <DataTable data={query.data} options={options} />;
}

export function ChartFrame({
  isPending,
  isError,
  errorMessage,
  option,
}: {
  isPending: boolean;
  isError: boolean;
  errorMessage?: string;
  option: import("echarts").EChartsOption | null;
}) {
  if (isPending) {
    return <div className="h-[300px] rounded-sm border border-border bg-surface-subtle" />;
  }
  if (isError) {
    return (
      <div className="rounded-sm border border-danger-fg/40 bg-surface p-6 text-small text-danger-fg">
        {errorMessage ?? "Fehler beim Laden"}
      </div>
    );
  }
  if (!option) {
    return (
      <div className="grid h-[300px] place-items-center rounded-sm border border-dashed border-border text-small text-muted">
        Keine Daten vorhanden.
      </div>
    );
  }
  return (
    <div className="rounded-sm border border-border bg-surface p-3">
      <EChart option={option} height={280} />
    </div>
  );
}
