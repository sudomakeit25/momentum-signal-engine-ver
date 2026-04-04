"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useChartData } from "@/hooks/use-chart-data";
import { useScanSymbol } from "@/hooks/use-scan";
import { CandlestickChart } from "@/components/chart/candlestick-chart";
import { RSIPanel } from "@/components/chart/rsi-panel";
import { VolumePanel } from "@/components/chart/volume-panel";
import { ChartToolbar } from "@/components/chart/chart-toolbar";
import { StockInfoHeader } from "@/components/chart/stock-info-header";
import { TechnicalAnalysisPanel } from "@/components/chart/technical-analysis-panel";
import { Skeleton } from "@/components/ui/skeleton";

export default function ChartPage() {
  const params = useParams();
  const symbol = (params.symbol as string).toUpperCase();

  const [days, setDays] = useState(200);
  const [indicators, setIndicators] = useState({
    ema9: true,
    ema21: true,
    ema50: false,
    ema200: false,
    vwap: false,
    rs: false,
  });
  const [analysis, setAnalysis] = useState({
    sr: false,
    trendlines: false,
    patterns: false,
    projections: false,
  });

  const { data: chartData, isLoading } = useChartData(symbol, days);
  const { data: scanResult } = useScanSymbol(symbol);

  const handleIndicatorToggle = (key: string, val: boolean) => {
    setIndicators((prev) => ({ ...prev, [key]: val }));
  };

  const handleAnalysisToggle = (key: string, val: boolean) => {
    setAnalysis((prev) => ({ ...prev, [key]: val }));
  };

  return (
    <div className="space-y-4">
      <ChartToolbar
        days={days}
        onDaysChange={setDays}
        indicators={indicators}
        onIndicatorToggle={handleIndicatorToggle}
        analysis={analysis}
        onAnalysisToggle={handleAnalysisToggle}
      />

      {isLoading || !chartData ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-96 bg-zinc-800" />
          <Skeleton className="h-[420px] w-full bg-zinc-800" />
          <Skeleton className="h-[120px] w-full bg-zinc-800" />
          <Skeleton className="h-[80px] w-full bg-zinc-800" />
        </div>
      ) : (
        <>
          <StockInfoHeader
            symbol={symbol}
            bars={chartData.bars}
            signals={chartData.signals}
            scanResult={scanResult}
          />

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-2">
            <CandlestickChart
              bars={chartData.bars}
              signals={chartData.signals}
              showEma9={indicators.ema9}
              showEma21={indicators.ema21}
              showEma50={indicators.ema50}
              showEma200={indicators.ema200}
              showVwap={indicators.vwap}
              showRs={indicators.rs}
              technicalAnalysis={chartData.technical_analysis}
              showSupportResistance={analysis.sr}
              showTrendlines={analysis.trendlines}
              showPatterns={analysis.patterns}
              showProjections={analysis.projections}
            />
          </div>

          <div className="grid grid-cols-1 gap-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-2">
              <RSIPanel bars={chartData.bars} />
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-2">
              <VolumePanel bars={chartData.bars} />
            </div>
          </div>

          {chartData.technical_analysis && (
            <TechnicalAnalysisPanel analysis={chartData.technical_analysis} />
          )}
        </>
      )}
    </div>
  );
}
