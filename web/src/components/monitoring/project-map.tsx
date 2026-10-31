"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { MapPoint } from "@/lib/api/types";

const View = dynamic(() => import("./project-map-view"), { ssr: false, loading: () => <div className="h-80 rounded-xl border border-line bg-subtle" /> });

/** The ongoing (or watched) projects on a map; a pin opens the project in the list below. */
export function ProjectMap({ scope, focus, onOpen }: { scope: "ongoing" | "watched"; focus: string | null; onOpen: (projectId: string) => void }) {
  const [data, setData] = useState<{ points: MapPoint[]; unplaced: string[] } | null>(null);
  useEffect(() => {
    api.monitoringMap(scope).then(setData).catch(() => setData({ points: [], unplaced: [] }));
  }, [scope]);
  if (!data) return <div className="h-80 rounded-xl border border-line bg-subtle" />;
  return (
    <div className="space-y-1">
      <View points={data.points} focus={focus} onOpen={onOpen} />
      <p className="text-[11px] text-ink-muted">
        Country level: the reports and the projects API give no site locations yet, so each project is pinned at its country&apos;s capital.
        {data.unplaced.length ? ` Not on the map (regional or multi-country): ${data.unplaced.join(", ")}.` : ""}
      </p>
    </div>
  );
}
