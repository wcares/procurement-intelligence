"use client";

import { useMemo, useState } from "react";
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { AskResponse } from "@/lib/api/types";

const COL_X = { question: 0, finding: 260, source: 640 };
const ROW = 120;
const SIDEWAYS = { sourcePosition: Position.Right, targetPosition: Position.Left };

/** The answer as a graph: the question, each finding (answer sentence; wider when more sources support it) and the
 * sources it cites, labelled by project and report section. Filter the sources by country; click a source to jump to
 * its quote and report link below. */
export function AnswerMap({ r, question, onSource }: { r: AskResponse; question: string; onSource: (index: number) => void }) {
  const countries = useMemo(() => [...new Set(r.citations.map((c) => c.countryCode).filter(Boolean))].sort(), [r]);
  const [country, setCountry] = useState("");

  const { nodes, edges } = useMemo(() => {
    const visible = r.citations.map((c) => !country || c.countryCode === country);
    const findings = r.answer.map((s, i) => ({ s, i, sources: s.citations.filter((c) => visible[c]) })).filter((f) => f.sources.length);
    const used = [...new Set(findings.flatMap((f) => f.sources))].sort((a, b) => a - b);
    const height = Math.max(findings.length, used.length) * ROW;
    const nodes: Node[] = [
      { id: "q", ...SIDEWAYS, position: { x: COL_X.question, y: height / 2 - 30 }, data: { label: question }, type: "input",
        style: { width: 200, fontSize: 12, fontWeight: 600 } },
      ...findings.map((f, k) => ({
        id: `f${f.i}`, ...SIDEWAYS, position: { x: COL_X.finding, y: k * ROW + (height - findings.length * ROW) / 2 },
        data: { label: `${f.s.text.slice(0, 140)}${f.s.text.length > 140 ? "…" : ""} (${f.sources.length} source${f.sources.length === 1 ? "" : "s"})` },
        style: { width: 220 + 30 * Math.min(f.sources.length, 4), fontSize: 11 },
      })),
      ...used.map((c, k) => {
        const cit = r.citations[c];
        return { id: `c${c}`, type: "output", ...SIDEWAYS, position: { x: COL_X.source + 60, y: k * ROW + (height - used.length * ROW) / 2 },
          data: { label: `[${c + 1}] ${cit.projectName || cit.projectId} (${cit.countryCode}) · ${cit.section}` },
          style: { width: 240, fontSize: 11, cursor: "pointer" } };
      }),
    ];
    const edges: Edge[] = [
      ...findings.map((f) => ({ id: `q-f${f.i}`, source: "q", target: `f${f.i}` })),
      ...findings.flatMap((f) => f.sources.map((c) => ({ id: `f${f.i}-c${c}`, source: `f${f.i}`, target: `c${c}`, animated: false }))),
    ];
    return { nodes, edges };
  }, [r, question, country]);

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
        <span>Findings and the sources behind them.</span>
        {countries.length > 1 && (
          <select className="rounded-md border border-line bg-surface px-2 py-1" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Filter sources by country">
            <option value="">all countries</option>
            {countries.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
        <span>Click a source for its quote.</span>
      </div>
      <div className="h-[28rem]">
        <ReactFlow nodes={nodes} edges={edges} fitView colorMode="system" nodesConnectable={false} nodesDraggable proOptions={{ hideAttribution: true }}
          onNodeClick={(_, n) => n.id.startsWith("c") && onSource(Number(n.id.slice(1)))}>
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
