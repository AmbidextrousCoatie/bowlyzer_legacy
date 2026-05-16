import { useEffect, useMemo, useRef } from "react";
import { createDataTable, type DataTableHandle } from "./createDataTable";
import { getTableDataKey } from "./tableDataKey";
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
 * on unmount, and rebuilds when table payload or options change (by value, not
 * reference). Callers should still memoize options when possible.
 */
export function DataTable({ data, options, className, onReady }: DataTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<DataTableHandle | null>(null);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const dataRef = useRef(data);
  dataRef.current = data;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const dataKey = useMemo(() => getTableDataKey(data), [data]);
  const optionsKey = useMemo(() => JSON.stringify(options ?? {}), [options]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handle = createDataTable(container, dataRef.current, optionsRef.current);
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
  }, [dataKey, optionsKey]);

  return <div ref={containerRef} className={className} />;
}
