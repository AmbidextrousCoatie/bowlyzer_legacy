import { useEffect, useRef } from "react";
import { createDataTable, type DataTableHandle } from "./createDataTable";
import type { DataTableOptions, TableData } from "./types";

import "tabulator-tables/dist/css/tabulator.min.css";
import "./datatable.css";

type DataTableProps = {
  data: TableData;
  options?: DataTableOptions;
  className?: string;
};

/**
 * React wrapper around the Tabulator factory. Mounts on first render, destroys
 * on unmount, and rebuilds whenever the data identity changes. Caller is
 * responsible for memoizing the data + options if rerenders are unwanted.
 */
export function DataTable({ data, options, className }: DataTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<DataTableHandle | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    handleRef.current = createDataTable(containerRef.current, data, options);
    return () => {
      handleRef.current?.destroy();
      handleRef.current = null;
    };
  }, [data, options]);

  return <div ref={containerRef} className={className} />;
}
