"use client";

import { useMemo } from "react";
import { createColumnHelper, createSortedRowModel, rowSortingFeature, sortFn_text, tableFeatures, useTable } from "@tanstack/react-table";
import type { RankingResponse, RankingRow } from "@/lib/api/types";
import { fmt } from "./format";

// TanStack Table v9: features (sorting, with its row model) are registered once, at module scope
const features = tableFeatures({ rowSortingFeature, sortedRowModel: createSortedRowModel(), sortFns: { text: sortFn_text } });
const col = createColumnHelper<typeof features, RankingRow>();

/** Groups ranked worst first; rows behind few projects are greyed; a row click opens its records. */
export function RankingTable({ data, onSelect, selected }: { data: RankingResponse; onSelect: (row: RankingRow) => void; selected: string | null }) {
  const max = Math.max(...data.rows.map((r) => r.value), 0) || 1;
  const columns = useMemo(
    () => col.columns([
      col.display({ id: "rank", header: "#", cell: (c) => c.row.index + 1 }),
      col.accessor("label", { header: data.groupLabel }),
      col.accessor("value", {
        header: data.measure.label,
        cell: (c) => (
          <div className="flex items-center gap-2">
            <div className="h-2 rounded bg-risk-high/70" style={{ width: `${Math.max(4, (c.getValue() / max) * 120)}px` }} />
            <span className="whitespace-nowrap tabular-nums">{fmt(data.measure, c.getValue())}</span>
          </div>
        ),
      }),
      col.accessor("projects", { header: "Projects", cell: (c) => <span className="tabular-nums">{c.getValue()}</span> }),
      col.accessor("n", { header: data.measure.level === "package" ? "Awards" : data.measure.level === "country" ? "Projects" : "Counted", cell: (c) => <span className="tabular-nums">{c.getValue()}</span> }),
    ]),
    [data, max],
  );
  const table = useTable({ features, columns, data: data.rows });

  return (
    <div className="max-h-[28rem] overflow-auto">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-surface text-xs text-ink-muted">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="cursor-pointer select-none py-1 pr-3 font-medium" onClick={h.column.getToggleSortingHandler()}>
                  <table.FlexRender header={h} />
                  {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id} onClick={() => onSelect(r.original)}
              className={`cursor-pointer border-t border-line hover:bg-subtle ${r.original.few ? "text-ink-muted" : ""} ${selected === r.original.key ? "bg-brand-soft" : ""}`}
              title={r.original.few ? "Too few projects to compare" : "Show the records behind this row"}>
              {r.getAllCells().map((c) => (
                <td key={c.id} className="py-1 pr-3"><table.FlexRender cell={c} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
