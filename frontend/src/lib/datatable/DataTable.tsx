import { useEffect, useRef } from "react";
import { createDataTable, type DataTableHandle } from "./createDataTable";
import type { DataTableOptions, TableData } from "./types";

import "tabulator-tables/dist/css/tabulator.min.css";
import "./datatable.css";

type DataTableProps = {
  data: TableData;
  options?: DataTableOptions;
  className?: string;
  /** Fired when Tabulator has built the table (safe to call column APIs). */
  onReady?: (handle: DataTableHandle) => void;
};

/**
 * React wrapper around the Tabulator factory. Mounts on first render, destroys
 * on unmount, and rebuilds whenever the data identity changes. Caller is
 * responsible for memoizing the data + options if rerenders are unwanted.
 */
export function DataTable({ data, options, className, onReady }: DataTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<DataTableHandle | null>(null);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    if (!containerRef.current) return;
    const handle = createDataTable(containerRef.current, data, options);
    if (!handle) return;
    handleRef.current = handle;

    const notifyReady = () => onReadyRef.current?.(handle);
    handle.tabulator.on("tableBuilt", notifyReady);
    handle.tabulator.on("dataProcessed", notifyReady);

    return () => {
      handle.tabulator.off("tableBuilt", notifyReady);
      handle.tabulator.off("dataProcessed", notifyReady);
      handle.destroy();
      handleRef.current = null;
    };
  }, [data, options]);

  return <div ref={containerRef} className={className} />;
}
