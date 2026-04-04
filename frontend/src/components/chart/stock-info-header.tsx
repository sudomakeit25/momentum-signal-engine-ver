import { ScoreBadge } from "@/components/scanner/score-badge";
import { SignalChip } from "@/components/scanner/signal-chip";
import type { ChartBar, Signal, ScanResult } from "@/types/api";

interface StockInfoHeaderProps {
  symbol: string;
  bars: ChartBar[];
  signals: Signal[];
  scanResult?: ScanResult | null;
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(0)}K`;
  return vol.toString();
}

export function StockInfoHeader({
  symbol,
  bars,
  signals,
  scanResult,
}: StockInfoHeaderProps) {
  const lastBar = bars[bars.length - 1];
  const prevBar = bars.length > 1 ? bars[bars.length - 2] : null;

  if (!lastBar) return null;

  const change = prevBar ? lastBar.close - prevBar.close : 0;
  const changePct = prevBar ? (change / prevBar.close) * 100 : 0;
  const isUp = change >= 0;

  return (
    <div className="flex items-center gap-6">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">{symbol}</h1>
      </div>
      <div>
        <span className="text-2xl font-bold font-mono">
          ${lastBar.close.toFixed(2)}
        </span>
        <span
          className={`ml-2 text-sm font-mono ${
            isUp ? "text-emerald-400" : "text-red-400"
          }`}
        >
          {isUp ? "+" : ""}
          {change.toFixed(2)} ({changePct.toFixed(2)}%)
        </span>
      </div>
      <div className="text-xs text-zinc-500">
        Vol: {formatVolume(lastBar.volume)}
      </div>
      {scanResult && <ScoreBadge score={scanResult.score} />}
      <div className="flex gap-1">
        {signals.map((s, i) => (
          <SignalChip key={i} action={s.action} />
        ))}
      </div>
    </div>
  );
}
