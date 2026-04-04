"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  type Time,
} from "lightweight-charts";
import type { ChartBar } from "@/types/api";

function toTime(ts: string): Time {
  return ts.split("T")[0] as Time;
}

export function RSIPanel({ bars }: { bars: ChartBar[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#71717a",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      rightPriceScale: { borderColor: "#3f3f46" },
      timeScale: { borderColor: "#3f3f46", visible: false },
      width: containerRef.current.clientWidth,
      height: 120,
      crosshair: { horzLine: { visible: false } },
    });

    const rsiSeries = chart.addSeries(LineSeries, {
      color: "#a1a1aa",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
    });

    const rsiData = bars
      .filter((b) => b.rsi !== null)
      .map((b) => ({ time: toTime(b.timestamp), value: b.rsi! }));

    rsiSeries.setData(rsiData);

    // Overbought / oversold lines
    rsiSeries.createPriceLine({
      price: 70,
      color: "#ef444480",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "",
    });
    rsiSeries.createPriceLine({
      price: 30,
      color: "#22c55e80",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "",
    });

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [bars]);

  return (
    <div>
      <span className="text-[10px] font-medium uppercase text-zinc-500">
        RSI (14)
      </span>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
