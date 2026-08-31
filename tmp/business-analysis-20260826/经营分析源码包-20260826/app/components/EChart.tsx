"use client";

import { useEffect, useRef } from "react";
import type {
  ECElementEvent,
  EChartsOption,
  EChartsType,
} from "echarts";

export interface EChartProps {
  option: EChartsOption;
  theme?: string | object;
  height?: number | string;
  onClick?: (event: ECElementEvent) => void;
  ariaLabel?: string;
  className?: string;
}

function applyOption(
  chart: EChartsType,
  option: EChartsOption,
  reduceMotion: boolean,
) {
  chart.dispatchAction({ type: "hideTip" });
  chart.setOption(
    reduceMotion ? { ...option, animation: false } : option,
    { notMerge: true },
  );
}

export default function EChart({
  option,
  theme,
  height = 320,
  onClick,
  ariaLabel = "数据图表",
  className,
}: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const optionRef = useRef(option);
  const onClickRef = useRef(onClick);
  const reduceMotionRef = useRef(false);

  useEffect(() => {
    optionRef.current = option;
    onClickRef.current = onClick;
  }, [onClick, option]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => {
      reduceMotionRef.current = media.matches;
      const chart = chartRef.current;
      if (chart && !chart.isDisposed()) {
        applyOption(chart, optionRef.current, media.matches);
      }
    };

    syncMotion();
    media.addEventListener("change", syncMotion);
    return () => media.removeEventListener("change", syncMotion);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let chart: EChartsType | null = null;
    let observer: ResizeObserver | null = null;
    let initializing = false;

    const initialize = () => {
      if (cancelled || initializing || chart || !container.clientWidth || !container.clientHeight) return;
      initializing = true;
      void import("../lib/echarts-client").then((echarts) => {
        if (cancelled || !container.clientWidth || !container.clientHeight) return;
        chart = echarts.init(container, theme ?? null);
        chartRef.current = chart;
        applyOption(chart, optionRef.current, reduceMotionRef.current);
        chart.on("click", (event: ECElementEvent) => onClickRef.current?.(event));
      }).finally(() => {
        initializing = false;
      });
    };

    observer = new ResizeObserver(() => {
      if (chart && !chart.isDisposed()) chart.resize();
      else initialize();
    });
    observer.observe(container);
    initialize();

    return () => {
      cancelled = true;
      observer?.disconnect();
      if (chart && !chart.isDisposed()) chart.dispose();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [theme]);

  useEffect(() => {
    const chart = chartRef.current;
    if (chart && !chart.isDisposed()) {
      applyOption(chart, option, reduceMotionRef.current);
    }
  }, [option]);

  return (
    <div
      ref={containerRef}
      className={className}
      role="img"
      aria-label={ariaLabel}
      style={{ height, width: "100%" }}
    />
  );
}
