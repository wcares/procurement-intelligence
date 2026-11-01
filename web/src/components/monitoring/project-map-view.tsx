"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useMemo } from "react";
import { CircleMarker, LayersControl, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { MapPoint } from "@/lib/api/types";
import { BASE_MAPS } from "@/lib/map-tiles";

interface Spot { key: string; lat: number; lon: number; place: string; level: string; projects: MapPoint[] }

/** Projects grouped by the place they are pinned at (today one spot per country). */
function spots(points: MapPoint[]): Spot[] {
  const by = new Map<string, Spot>();
  for (const p of points) {
    const where = p.places[0];
    if (!where) continue;
    const key = `${where.lat.toFixed(3)},${where.lon.toFixed(3)}`;
    const s = by.get(key) ?? { key, lat: where.lat, lon: where.lon, place: where.place, level: where.level, projects: [] };
    s.projects.push(p);
    by.set(key, s);
  }
  return [...by.values()];
}

function FlyTo({ spot }: { spot: Spot | null }) {
  const map = useMap();
  useEffect(() => {
    if (spot) map.flyTo([spot.lat, spot.lon], Math.max(map.getZoom(), 5), { duration: 0.8 });
  }, [map, spot?.key]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** The leaflet map itself (browser only: loaded through project-map.tsx). */
export default function ProjectMapView({ points, focus, onOpen }: { points: MapPoint[]; focus: string | null; onOpen: (projectId: string) => void }) {
  const all = useMemo(() => spots(points), [points]);
  const focused = all.find((s) => s.projects.some((p) => p.projectId === focus)) ?? null;
  return (
    <MapContainer center={[10, 20]} zoom={2} minZoom={2} worldCopyJump scrollWheelZoom={false}
      className="h-80 w-full rounded-xl border border-line" style={{ zIndex: 0 }}>
      <LayersControl position="topright">
        {BASE_MAPS.map((b, i) => (
          <LayersControl.BaseLayer key={b.name} name={b.name} checked={i === 0}>
            <TileLayer url={b.url} attribution={b.attribution} maxZoom={b.maxZoom} />
          </LayersControl.BaseLayer>
        ))}
      </LayersControl>
      <FlyTo spot={focused} />
      {all.map((s) => {
        const warn = s.projects.some((p) => p.warnings > 0);
        return (
          <CircleMarker key={s.key} center={[s.lat, s.lon]} radius={6 + Math.min(10, s.projects.length * 2)}
            pathOptions={{ color: warn ? "#b27c00" : "#004370", fillOpacity: 0.55, weight: 2 }}>
            <Tooltip>{s.place}: {s.projects.length} project{s.projects.length > 1 ? "s" : ""}</Tooltip>
            <Popup>
              <div className="space-y-1 text-xs">
                <p className="font-medium">{s.place}</p>
                <p className="text-[11px] opacity-70">{s.level === "country" ? "Country level: pinned at the capital, not the project site" : s.level}</p>
                <ul className="space-y-0.5">
                  {s.projects.map((p) => (
                    <li key={p.projectId}>
                      <button className="text-left underline" onClick={() => onOpen(p.projectId)}>{p.name}</button>{" "}
                      <span className="opacity-70">{p.projectId} · {p.active} active{p.warnings ? ` · ⚠ ${p.warnings}` : ""}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
