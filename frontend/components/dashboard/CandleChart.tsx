"use client";

import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, type IChartApi, type CandlestickData, type Time } from "lightweight-charts";
import { useTradingStore } from "@/stores/tradingStore";
import type { Candle } from "@/lib/types";

function toChartData(c: Candle): CandlestickData<Time> {
  return {
    time: (new Date(c.timestamp).getTime() / 1000) as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

export function CandleChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null);
  const prevLengthRef = useRef(0);

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#18181b" },
        textColor: "#a1a1aa",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      width: containerRef.current.clientWidth,
      height: 300,
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      prevLengthRef.current = 0;
    };
  }, []);

  // Subscribe to candle updates
  useEffect(() => {
    const unsub = useTradingStore.subscribe((state) => {
      const series = seriesRef.current;
      if (!series) return;

      const { candles } = state;
      if (candles.length === 0) return;

      if (candles.length > prevLengthRef.current + 5 || prevLengthRef.current === 0) {
        // Bulk set on initial load or large batch
        series.setData(candles.map(toChartData));
      } else if (candles.length > prevLengthRef.current) {
        // Incremental update
        const latest = candles[candles.length - 1];
        series.update(toChartData(latest));
      }
      prevLengthRef.current = candles.length;

      chartRef.current?.timeScale().scrollToRealTime();
    });

    return unsub;
  }, []);

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        MES Price
      </h3>
      <div ref={containerRef} />
    </div>
  );
}
