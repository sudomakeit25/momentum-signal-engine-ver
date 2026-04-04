"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  HistogramSeries,
  LineSeries,
  type Time,
} from "lightweight-charts";
import type { ChartBar } from "@/types/api";

function toTime(ts: string): Time {
  return ts.split("T")[0] as Time;
}

export function VolumePanel({ bars }: { bars: ChartBar[] }) {
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
      timeScale: { borderColor: "#3f3f46" },
      width: containerRef.current.clientWidth,
      height: 80,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: "volume" },
    });

    volumeSeries.setData(
      bars.map((b) => ({
        time: toTime(b.timestamp),
        value: b.volume,
        color: b.close >= b.open ? "#22c55e40" : "#ef444440",
      }))
    );

    // Volume SMA overlay
    const smaData = bars
      .filter((b) => b.volume_sma20 !== null)
      .map((b) => ({ time: toTime(b.timestamp), value: b.volume_sma20! }));

    if (smaData.length > 0) {
      const smaSeries = chart.addSeries(LineSeries, {
        color: "#f97316",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      smaSeries.setData(smaData);
    }

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
        Volume
      </span>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
