"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import type { ChartBar, Signal, TechnicalAnalysis } from "@/types/api";

interface CandlestickChartProps {
  bars: ChartBar[];
  signals: Signal[];
  showEma9?: boolean;
  showEma21?: boolean;
  showEma50?: boolean;
  showEma200?: boolean;
  showVwap?: boolean;
  showRs?: boolean;
  technicalAnalysis?: TechnicalAnalysis | null;
  showSupportResistance?: boolean;
  showTrendlines?: boolean;
  showPatterns?: boolean;
  showProjections?: boolean;
}

function toTime(ts: string): Time {
  return ts.split("T")[0] as Time;
}

export function CandlestickChart({
  bars,
  signals,
  showEma9 = true,
  showEma21 = true,
  showEma50 = false,
  showEma200 = false,
  showVwap = false,
  showRs = false,
  technicalAnalysis,
  showSupportResistance = false,
  showTrendlines = false,
  showPatterns = false,
  showProjections = false,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

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
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#3f3f46" },
      timeScale: { borderColor: "#3f3f46" },
      width: containerRef.current.clientWidth,
      height: 420,
    });
    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });

    candleSeries.setData(
      bars.map((b) => ({
        time: toTime(b.timestamp),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }))
    );

    // EMA overlays
    const addLine = (
      values: (number | null)[],
      color: string,
      show: boolean
    ) => {
      if (!show) return;
      const series = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const data = bars
        .map((b, i) =>
          values[i] !== null
            ? { time: toTime(b.timestamp), value: values[i]! }
            : null
        )
        .filter((d): d is { time: Time; value: number } => d !== null);
      series.setData(data);
    };

    addLine(bars.map((b) => b.ema9), "#06b6d4", showEma9);
    addLine(bars.map((b) => b.ema21), "#eab308", showEma21);
    addLine(bars.map((b) => b.ema50), "#f97316", showEma50);
    addLine(bars.map((b) => b.ema200), "#ef4444", showEma200);
    addLine(bars.map((b) => b.vwap), "#a855f7", showVwap);

    // RS vs SPY overlay (separate price scale)
    if (showRs) {
      const rsSeries = chart.addSeries(LineSeries, {
        color: "#ec4899",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        priceScaleId: "rs",
        title: "RS",
      });
      chart.priceScale("rs").applyOptions({
        scaleMargins: { top: 0.7, bottom: 0 },
      });
      const rsData = bars
        .map((b) =>
          b.rs_vs_spy !== null
            ? { time: toTime(b.timestamp), value: b.rs_vs_spy }
            : null
        )
        .filter((d): d is { time: Time; value: number } => d !== null);
      rsSeries.setData(rsData);
    }

    // Signal markers as price lines on the candlestick series
    for (const s of signals) {
      candleSeries.createPriceLine({
        price: s.entry,
        color: s.action === "BUY" ? "#22c55e80" : "#ef444480",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: false,
        title: s.action,
      });
    }

    // --- Technical Analysis Overlays ---
    const ta = technicalAnalysis;

    // Support/Resistance zones
    if (showSupportResistance && ta) {
      for (const level of ta.support_levels) {
        candleSeries.createPriceLine({
          price: level.price,
          color: "#22c55e60",
          lineWidth: 1,
          lineStyle: 1,
          axisLabelVisible: true,
          title: `S ${level.touches}t`,
        });
      }
      for (const level of ta.resistance_levels) {
        candleSeries.createPriceLine({
          price: level.price,
          color: "#ef444460",
          lineWidth: 1,
          lineStyle: 1,
          axisLabelVisible: true,
          title: `R ${level.touches}t`,
        });
      }
    }

    // Trendlines
    if (showTrendlines && ta) {
      for (const line of ta.trendlines) {
        try {
          const color = line.trend_type === "uptrend" ? "#22c55e" : "#ef4444";
          const startTime = toTime(line.start_time);
          const endTime = toTime(line.end_time);

          // Ensure start < end
          if ((startTime as string) >= (endTime as string)) continue;

          const trendSeries = chart.addSeries(LineSeries, {
            color,
            lineWidth: 2,
            lineStyle: 0,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          trendSeries.setData([
            { time: startTime, value: line.start_price },
            { time: endTime, value: line.end_price },
          ]);

          // Projection (dashed)
          if (line.projection.length > 0) {
            const projSeries = chart.addSeries(LineSeries, {
              color: color + "80",
              lineWidth: 1,
              lineStyle: 2,
              priceLineVisible: false,
              lastValueVisible: false,
              crosshairMarkerVisible: false,
            });
            const projData = [
              { time: endTime, value: line.end_price },
              ...line.projection.map((p) => ({
                time: toTime(p.time),
                value: p.price,
              })),
            ];
            projSeries.setData(projData);
          }
        } catch {
          // Skip trendlines that can't be rendered
        }
      }
    }

    // Chart patterns — build a time→description lookup for tooltip
    type PatternHit = { description: string; bias: string; name: string; price: number };
    const patternTimeMap = new Map<string, PatternHit[]>();

    if (showPatterns && ta) {
      for (const pattern of ta.patterns) {
        try {
          const patternColor =
            pattern.bias === "bullish" ? "#22c55e" :
            pattern.bias === "bearish" ? "#ef4444" : "#8b5cf6";
          const patternName = pattern.pattern_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

          if (pattern.boundary_points.length >= 2) {
            // Sort by time — lightweight-charts requires ascending order
            const sorted = [...pattern.boundary_points]
              .map((p) => ({ time: toTime(p.time), value: p.price }))
              .sort((a, b) => (a.time as string).localeCompare(b.time as string));

            // Deduplicate same-time entries (keep first)
            const deduped = sorted.filter(
              (pt, i, arr) => i === 0 || pt.time !== arr[i - 1].time
            );

            if (deduped.length >= 2) {
              const patternSeries = chart.addSeries(LineSeries, {
                color: patternColor,
                lineWidth: 2,
                lineStyle: 0,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
              });
              patternSeries.setData(deduped);
            }

            // Register boundary point times for tooltip
            for (const pt of deduped) {
              const key = pt.time as string;
              const hit: PatternHit = {
                description: pattern.description,
                bias: pattern.bias,
                name: patternName,
                price: pt.value,
              };
              const existing = patternTimeMap.get(key);
              if (existing) {
                // Avoid duplicate pattern names at same time
                if (!existing.some((h) => h.name === patternName)) {
                  existing.push(hit);
                }
              } else {
                patternTimeMap.set(key, [hit]);
              }
            }
          }
          // Target price line
          if (pattern.target_price) {
            candleSeries.createPriceLine({
              price: pattern.target_price,
              color: patternColor + "80",
              lineWidth: 1,
              lineStyle: 3,
              axisLabelVisible: true,
              title: `${pattern.bias === "bullish" ? "\u25B2" : pattern.bias === "bearish" ? "\u25BC" : "\u25C6"} ${pattern.pattern_type.replace(/_/g, " ")}`,
            });
          }
        } catch {
          // Skip patterns that can't be rendered
        }
      }
    }

    // Pattern tooltip on crosshair hover
    if (patternTimeMap.size > 0) {
      chart.subscribeCrosshairMove((param) => {
        const tooltip = tooltipRef.current;
        if (!tooltip || !containerRef.current) return;

        if (!param.time || !param.point) {
          tooltip.style.display = "none";
          return;
        }

        const timeStr = param.time as string;
        const hits = patternTimeMap.get(timeStr);

        if (!hits || hits.length === 0) {
          tooltip.style.display = "none";
          return;
        }

        // Build tooltip content
        const lines = hits.map((h) => {
          const badge = h.bias === "bullish" ? "🟢" : h.bias === "bearish" ? "🔴" : "🟣";
          return `<div style="margin-bottom:4px"><strong>${badge} ${h.name}</strong><br/><span style="color:#a1a1aa">${h.description}</span></div>`;
        });

        tooltip.innerHTML = lines.join("");
        tooltip.style.display = "block";

        // Position tooltip near cursor
        const chartRect = containerRef.current.getBoundingClientRect();
        let left = param.point.x + 16;
        let top = param.point.y - 16;

        // Keep tooltip within chart bounds
        if (left + 280 > chartRect.width) left = param.point.x - 296;
        if (top < 0) top = 0;

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
      });
    }

    // Price projections
    if (showProjections && ta) {
      for (const proj of ta.projections) {
        const color = proj.projection_type === "bullish" ? "#22c55e" : "#ef4444";
        candleSeries.createPriceLine({
          price: proj.price,
          color: color + "90",
          lineWidth: 1,
          lineStyle: 3,
          axisLabelVisible: true,
          title: `${proj.reason} (${Math.round(proj.confidence * 100)}%)`,
        });
      }
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
  }, [bars, signals, showEma9, showEma21, showEma50, showEma200, showVwap, showRs, technicalAnalysis, showSupportResistance, showTrendlines, showPatterns, showProjections]);

  return (
    <div className="relative w-full">
      <div ref={containerRef} className="w-full" />
      <div
        ref={tooltipRef}
        style={{ display: "none" }}
        className="pointer-events-none absolute z-50 max-w-[280px] rounded-lg border border-zinc-700 bg-zinc-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
      />
    </div>
  );
}
