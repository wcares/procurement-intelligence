"use client";

import { useEffect, useRef } from "react";
import type { EChartsOption, EChartsType } from "echarts";

/** ECharts in a div: loaded in the browser only (it needs the DOM), resized with its box, option replaced on change.
 * onClick receives the clicked item's data. Used instead of a wrapper package (React 19 support unconfirmed there). */
export function useECharts(option: EChartsOption | null, onClick?: (data: unknown) => void) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const click = useRef(onClick);
  useEffect(() => {
    click.current = onClick; // the latest handler, without re-creating the chart
  }, [onClick]);

  useEffect(() => {
    let disposed = false;
    let observer: ResizeObserver | null = null;
    import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
      chart.current.on("click", (p) => click.current?.(p.data));
      observer = new ResizeObserver(() => chart.current?.resize());
      observer.observe(ref.current);
      if (option) chart.current.setOption(option);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
    // created once; the option is applied by the effect below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (option && chart.current) chart.current.setOption(option, true);
  }, [option]);

  return ref;
}

/** A CSS custom property's value (the app's colour tokens), for chart libraries that need concrete colours. */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
